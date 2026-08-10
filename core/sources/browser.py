"""Tier-6 browser adapter framework (Phase 6) — the last-resort, compliance-first
source type.

Uses Playwright when installed; the module is import-safe without it (`available()`
is False, and a browser source degrades to `skipped`, never crashing). The rules
below are non-negotiable (Compliance §browser):

- Check robots.txt before every browse; disallowed → skip + log, never fetch.
- Human-paced: randomized 2–6s delays, one session per domain, a hard per-domain
  hourly request cap.
- Persistent profile per site so a user who logs into their OWN account stays
  logged in across runs. The user authenticates manually in a visible window —
  the app never handles their password.
- A real, current, honest user-agent. Never impersonate another browser/device.
- On 403 / 429 / CAPTCHA: STOP, mark the source `blocked`, back off, notify, and
  route to a search fallback. Never attempt to solve or evade.
- Screenshot + DOM snapshot on every failure into logs/failures/.

Only the Playwright navigation itself needs the library; the guardrails
(robots, pacing, challenge detection, artifacts) are plain, tested logic.
"""
from __future__ import annotations

import random
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from core.sources import health, robots
from core.sources.http import USER_AGENT
from core.sources.spec import RawJob, SearchCriteria, SourceDefinition, SourceResult

_MIN_DELAY, _MAX_DELAY = 2.0, 6.0
_HOURLY_CAP = 60
_CHALLENGE = re.compile(r"(?i)(captcha|are you a robot|verify you are human|"
                        r"unusual traffic|access denied|cf-challenge|hcaptcha|recaptcha)")


def available() -> bool:
    """True only if Playwright is importable (it is not a Drift dependency)."""
    try:
        import playwright.sync_api  # noqa: F401
        return True
    except Exception:
        return False


def is_challenge(status: int | None, body: str) -> bool:
    """A 403/429 or a bot-check page → treat as blocked (never solve it)."""
    if status in (403, 429):
        return True
    return bool(_CHALLENGE.search(body or ""))


class Pacer:
    """Human pacing + a per-domain hourly cap, one session per domain."""

    def __init__(self, min_delay=_MIN_DELAY, max_delay=_MAX_DELAY, hourly_cap=_HOURLY_CAP,
                 rng: random.Random | None = None, sleep=time.sleep):
        self.min_delay, self.max_delay, self.cap = min_delay, max_delay, hourly_cap
        self._rng = rng or random.Random()
        self._sleep = sleep
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = {}

    def allow(self, url: str, *, now: float | None = None) -> bool:
        """False when the domain's hourly cap is reached."""
        host = urlparse(url).netloc.lower()
        now = now if now is not None else time.monotonic()
        with self._lock:
            hits = [t for t in self._hits.get(host, []) if now - t < 3600]
            self._hits[host] = hits
            if len(hits) >= self.cap:
                return False
            hits.append(now)
            return True

    def wait(self) -> float:
        d = self._rng.uniform(self.min_delay, self.max_delay)
        self._sleep(d)
        return d


@dataclass
class BrowserSource:
    slug: str
    display_name: str
    start_url: str
    card_selector: str
    title_selector: str
    link_selector: str = "a"
    company_selector: str = ""
    location_selector: str = ""
    requires_login: bool = False
    headless: bool = True          # Settings toggle; default off for authed sites
    max_cards: int = 40


def failure_dir() -> Path:
    d = Path("logs") / "failures"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_browser_source(cfg: BrowserSource, criteria: SearchCriteria, *,
                       pacer: Pacer | None = None, robots_check: bool = True) -> SourceResult:
    """Run a browser source under the compliance rules. Returns a SourceResult;
    `skipped` when Playwright is unavailable, `blocked` on any challenge."""
    started = datetime.now(timezone.utc)

    def result(status, **kw):
        now = datetime.now(timezone.utc)
        return SourceResult(slug=cfg.slug, status=status,
                            duration_ms=int((now - started).total_seconds() * 1000),
                            finished_at=now.replace(microsecond=0).isoformat(), **kw)

    if not available():
        return result("skipped", error_class="playwright_unavailable",
                      error_detail="Playwright is not installed; browser sources are off.")
    if robots_check and not robots.allowed(cfg.start_url):
        return result("blocked", error_class="RobotsDisallowed", error_detail=cfg.start_url)

    pacer = pacer or Pacer()
    if not pacer.allow(cfg.start_url):
        return result("skipped", error_class="rate_capped",
                      error_detail="per-domain hourly cap reached")

    try:
        jobs, blocked = _navigate(cfg, criteria, pacer)
    except Exception as exc:  # pragma: no cover - requires a live browser
        _dump_failure(cfg.slug, "", str(exc))
        health.record_failure(cfg.slug, f"{type(exc).__name__}: {exc}")
        return result("failed", error_class=type(exc).__name__, error_detail=str(exc)[:200])

    if blocked:
        health.record_failure(cfg.slug, "challenge/block detected")
        return result("blocked", error_class="Challenge",
                      error_detail="403/429/CAPTCHA — stopped, will fall back to search")
    health.record_success(cfg.slug)
    return result("done", jobs=jobs)


def _navigate(cfg: BrowserSource, criteria: SearchCriteria, pacer: Pacer):  # pragma: no cover
    """The only Playwright-dependent part. Persistent per-site profile; honest UA;
    human pacing; challenge → bail. Returns (jobs, blocked)."""
    from playwright.sync_api import sync_playwright

    profile = Path("logs") / "profiles" / cfg.slug
    profile.mkdir(parents=True, exist_ok=True)
    jobs: list[RawJob] = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(profile), headless=cfg.headless if not cfg.requires_login else False,
            user_agent=USER_AGENT)
        try:
            page = ctx.new_page()
            pacer.wait()
            resp = page.goto(cfg.start_url, wait_until="domcontentloaded")
            status = resp.status if resp else None
            if is_challenge(status, page.content()):
                _dump_failure(cfg.slug, page.content(), f"challenge status={status}", page)
                return [], True
            for card in page.query_selector_all(cfg.card_selector)[: cfg.max_cards]:
                title_el = card.query_selector(cfg.title_selector)
                link_el = card.query_selector(cfg.link_selector)
                if not title_el:
                    continue
                jobs.append(RawJob(
                    title=title_el.inner_text().strip(),
                    company=(card.query_selector(cfg.company_selector).inner_text().strip()
                             if cfg.company_selector and card.query_selector(cfg.company_selector) else ""),
                    location=(card.query_selector(cfg.location_selector).inner_text().strip()
                              if cfg.location_selector and card.query_selector(cfg.location_selector) else ""),
                    description=title_el.inner_text().strip(),
                    url=(link_el.get_attribute("href") if link_el else "") or cfg.start_url,
                    source=cfg.slug))
            return jobs, False
        finally:
            ctx.close()


def _dump_failure(slug: str, html: str, note: str, page=None) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = failure_dir() / f"{slug}_{stamp}"
    try:
        base.with_suffix(".html").write_text(html or note, encoding="utf-8")
        if page is not None:  # pragma: no cover
            page.screenshot(path=str(base.with_suffix(".png")))
    except Exception:
        pass


def browser_definition(cfg: BrowserSource) -> SourceDefinition:
    """Wrap a BrowserSource as a SourceDefinition (adapter_type='browser')."""
    return SourceDefinition(
        slug=cfg.slug, display_name=cfg.display_name, category="browser",
        adapter_type="browser", base_url=cfg.start_url, auth_type="none",
        auth_env_key="", rate_limit_rpm=6, concurrency_limit=1, robots_check=True,
        query_mapper=lambda c: [], response_parser=lambda r, s: [],
        enabled=False, note="Browser adapter (requires Playwright + user setup).")
