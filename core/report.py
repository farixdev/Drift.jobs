import csv
import json
from datetime import datetime
from pathlib import Path

from models import Job

_TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "report.html"


def _rows(jobs: list[Job]) -> list[dict]:
    return [
        {
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "job_type": j.job_type,
            "score": j.score,
            "verdict": j.verdict,
            "matched_skills": list(j.matched_skills),
            "missing_skills": list(j.missing_skills),
            "summary": j.summary,
            "salary": j.salary,
            "posted": j.posted,
            "remote": j.remote,
            "status": j.status,
            "url": j.url,
            "source": j.source,
            "scraped_at": j.scraped_at.strftime("%Y-%m-%d %H:%M"),
        }
        for j in jobs
    ]


def export_csv(jobs: list[Job], threshold: int, output_path: str) -> str:
    path = Path(output_path).with_suffix(".csv")
    rows = _rows(jobs)
    fieldnames = [
        "title", "company", "location", "job_type", "score", "verdict",
        "matched_skills", "missing_skills", "summary", "salary", "posted",
        "remote", "url", "source", "scraped_at",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["matched_skills"] = "; ".join(row["matched_skills"])
            row["missing_skills"] = "; ".join(row["missing_skills"])
            writer.writerow(row)
    return str(path.resolve())


def export_json(jobs: list[Job], threshold: int, output_path: str) -> str:
    path = Path(output_path).with_suffix(".json")
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "threshold": threshold,
        "count": len(jobs),
        "jobs": _rows(jobs),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path.resolve())


def export_html(jobs: list[Job], threshold: int, output_path: str) -> str:
    path = Path(output_path).with_suffix(".html")
    context = {
        "count": len(jobs),
        "threshold": threshold,
        "generated_at": datetime.now().strftime("%b %d, %Y · %H:%M"),
        "jobs": _rows(jobs),
    }
    html = _render(context)
    path.write_text(html, encoding="utf-8")
    return str(path.resolve())


def _render(context: dict) -> str:
    try:
        from jinja2 import Template

        if _TEMPLATE.is_file():
            return Template(_TEMPLATE.read_text(encoding="utf-8")).render(**context)
    except Exception:
        pass
    return _render_fallback(context)


def _render_fallback(context: dict) -> str:
    from html import escape

    cards = []
    for j in context["jobs"]:
        tags = "".join(
            f'<span class="tag">{escape(s)}</span>' for s in j["matched_skills"]
        )
        salary = f' · {escape(j["salary"])}' if j["salary"] else ""
        posted = f' · {escape(j["posted"])}' if j["posted"] else ""
        cards.append(
            f'<div class="card"><span class="score">{j["score"]}%</span>'
            f'<div class="title">{escape(j["title"])}</div>'
            f'<div class="sub">{escape(j["company"])} · {escape(j["location"])}'
            f'{salary}{posted}</div><div class="tags">{tags}</div>'
            f'<p class="summary">{escape(j["summary"])}</p>'
            f'<a class="apply" href="{escape(j["url"])}" target="_blank">Apply →</a></div>'
        )
    return (
        "<!doctype html><meta charset='utf-8'><title>drift.jobs report</title>"
        "<style>body{font-family:system-ui;background:#FAFAF9;color:#111;padding:40px;max-width:720px;margin:auto}"
        ".card{background:#fff;border:1px solid #eee;border-radius:12px;padding:16px;margin:12px 0}"
        ".score{float:right;font-weight:600}.title{font-weight:600}.sub{color:#666;font-size:13px}"
        ".tag{display:inline-block;background:#ECFDF5;color:#065F46;font-size:11px;padding:2px 8px;border-radius:20px;margin:4px 4px 0 0}"
        ".summary{color:#666;font-size:13px;margin-top:8px}a.apply{font-size:12px}</style>"
        f'<h1>drift.jobs report</h1><p>{context["count"]} jobs · above '
        f'{context["threshold"]}% · {context["generated_at"]}</p>' + "".join(cards)
    )


def export(jobs: list[Job], threshold: int, output_path: str, fmt: str = "csv") -> str:
    fmt = (fmt or "csv").lower()
    if fmt == "json":
        return export_json(jobs, threshold, output_path)
    if fmt == "html":
        return export_html(jobs, threshold, output_path)
    return export_csv(jobs, threshold, output_path)
