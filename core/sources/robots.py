"""robots.txt compliance check, cached per host for the process lifetime.

Policy (Compliance §robots): before fetching a URL for a source with
`robots_check=True`, confirm our honest User-Agent is allowed. A missing or
unreadable robots.txt (404/401/network) is treated as *allowed* — the absence of
rules is not a prohibition. An explicit Disallow is respected: the fetch is
skipped and surfaced as `blocked`.
"""
from __future__ import annotations

import urllib.robotparser as rp
from urllib.parse import urlparse

import requests

from core.sources.http import USER_AGENT

_cache: dict[str, rp.RobotFileParser | None] = {}


def _parser_for(host_root: str) -> rp.RobotFileParser | None:
    if host_root in _cache:
        return _cache[host_root]
    parser: rp.RobotFileParser | None
    try:
        resp = requests.get(host_root + "/robots.txt",
                            headers={"User-Agent": USER_AGENT}, timeout=15)
        if resp.status_code != 200:
            parser = None  # no rules => allowed
        else:
            parser = rp.RobotFileParser()
            parser.parse(resp.text.splitlines())
    except requests.RequestException:
        parser = None
    _cache[host_root] = parser
    return parser


def allowed(url: str) -> bool:
    p = urlparse(url)
    root = f"{p.scheme}://{p.netloc}"
    parser = _parser_for(root)
    if parser is None:
        return True
    return parser.can_fetch(USER_AGENT, url)


def clear_cache() -> None:
    _cache.clear()
