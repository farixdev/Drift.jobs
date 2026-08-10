"""Phase 6 Tier 6 — browser adapter compliance logic (no Playwright required)."""
from __future__ import annotations

import random

from core.sources.browser import (
    BrowserSource,
    Pacer,
    available,
    is_challenge,
    run_browser_source,
)
from core.sources.spec import SearchCriteria


class TestChallengeDetection:
    def test_403_and_429_are_challenges(self):
        assert is_challenge(403, "ok") is True
        assert is_challenge(429, "ok") is True

    def test_captcha_text_is_a_challenge(self):
        assert is_challenge(200, "Please verify you are human via CAPTCHA") is True
        assert is_challenge(200, "hCaptcha widget") is True

    def test_normal_page_is_not(self):
        assert is_challenge(200, "<div class='job'>Senior Engineer</div>") is False


class TestPacer:
    def test_hourly_cap_enforced(self):
        p = Pacer(hourly_cap=3)
        url = "https://example.com/jobs"
        assert all(p.allow(url, now=100 + i) for i in range(3))
        assert p.allow(url, now=104) is False              # 4th within the hour blocked

    def test_cap_resets_after_an_hour(self):
        p = Pacer(hourly_cap=1)
        url = "https://example.com/jobs"
        assert p.allow(url, now=0) is True
        assert p.allow(url, now=10) is False
        assert p.allow(url, now=3700) is True              # >1h later, allowed again

    def test_wait_is_within_bounds_and_random(self):
        delays = []
        p = Pacer(min_delay=2, max_delay=6, rng=random.Random(1),
                  sleep=lambda d: delays.append(d))
        for _ in range(5):
            d = p.wait()
            assert 2.0 <= d <= 6.0
        assert len(set(delays)) > 1                        # not a fixed delay


class TestRunner:
    def test_skips_gracefully_without_playwright(self):
        # Playwright isn't a Drift dependency, so a browser source degrades to
        # 'skipped' rather than crashing.
        assert available() is False
        cfg = BrowserSource(slug="demo", display_name="Demo",
                            start_url="https://example.com/jobs",
                            card_selector=".job", title_selector=".title")
        r = run_browser_source(cfg, SearchCriteria())
        assert r.status == "skipped" and r.error_class == "playwright_unavailable"
