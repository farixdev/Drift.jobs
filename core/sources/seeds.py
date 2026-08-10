"""Verified company-board seeds per ATS.

Each token returned real jobs from its ATS's public API on a live probe (honest
UA, robots-checked). The 2026-08-11 expansion added 43 boards across
Greenhouse/Lever/Ashby/Recruitee, all confirmed with >=1 live posting that day.
These are the default boards a source queries; a user can extend them (Phase 5
`only_companies`) or Drift can discover more later. The concurrent engine
(Phase 7) is what keeps a wide scan fast.
"""

SEEDS: dict[str, list[str]] = {
    # boards-api.greenhouse.io/v1/boards/{token}/jobs
    "greenhouse": [
        "stripe", "airbnb", "gitlab", "coinbase", "robinhood", "dropbox",
        "figma", "databricks",
        # verified 2026-08-11
        "mongodb", "datadog", "brex", "cloudflare", "samsara", "elastic",
        "pinterest", "affirm", "lyft", "twilio", "reddit", "flexport", "asana",
        "instacart", "gusto", "faire", "carta", "sofi", "chime", "discord",
        "gemini", "airtable", "betterment", "cockroachlabs", "webflow",
    ],
    # api.lever.co/v0/postings/{token}
    "lever": [
        "spotify", "matchgroup", "gopuff", "ro",
        # verified 2026-08-11
        "angellist", "veeva",
    ],
    # api.ashbyhq.com/posting-api/job-board/{token}
    "ashby": [
        "ashby", "linear", "posthog", "hex", "ramp", "runway",
        # verified 2026-08-11
        "openai", "harvey", "elevenlabs", "sierra", "notion", "decagon",
        "cursor", "perplexity", "vanta", "suno", "writer", "abridge",
        "watershed", "modal", "browserbase", "cointracker",
    ],
    # apply.workable.com/api/v1/widget/accounts/{token}
    "workable": ["huggingface"],
    # {token}.recruitee.com/api/offers/
    "recruitee": ["channable"],
}


def boards_for(slug: str, override: list[str] | None = None) -> list[str]:
    return list(override) if override else list(SEEDS.get(slug, []))
