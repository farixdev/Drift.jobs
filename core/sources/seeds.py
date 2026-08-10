"""Verified company-board seeds per ATS (probed live 2026-08-10).

Each token returned real jobs from its ATS's public API on that date. These are
the default boards a source queries; a user can extend them (Phase 5
`only_companies`) or Drift can discover more later. Kept modest so a scan stays
fast — the concurrent engine (Phase 7) is what scales this to hundreds.
"""

SEEDS: dict[str, list[str]] = {
    # boards-api.greenhouse.io/v1/boards/{token}/jobs
    "greenhouse": ["stripe", "airbnb", "gitlab", "coinbase", "robinhood",
                   "dropbox", "figma", "databricks"],
    # api.lever.co/v0/postings/{token}
    "lever": ["spotify", "matchgroup", "gopuff", "ro"],
    # api.ashbyhq.com/posting-api/job-board/{token}
    "ashby": ["ashby", "linear", "posthog", "hex", "ramp", "runway"],
    # apply.workable.com/api/v1/widget/accounts/{token}
    "workable": ["huggingface"],
}


def boards_for(slug: str, override: list[str] | None = None) -> list[str]:
    return list(override) if override else list(SEEDS.get(slug, []))
