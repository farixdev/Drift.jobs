"""
Characterization ("golden") tests — Phase 0.5, inserted before the Phase 2+
rewrite (see docs/AUDIT.md §9.2).

These tests pin the CURRENT behaviour of the load-bearing pure functions so that
the fingerprint change (Phase 8) and the scoring rewrite (Phase 4/8) can be made
with a concrete before/after diff instead of guesswork. Every expected value in
this file was captured by RUNNING the code on 2026-08-10, not by reading it.

If a rewrite intentionally changes one of these outputs, update the expectation
in the SAME commit and note it in the message — a diff here is the signal that
externally-visible behaviour moved.

Scope: pure, deterministic, offline functions only. No network, no DB, no Qt.
"""
import datetime as _dt

import pytest

from core import local_engine as le
from core import matcher as m
from core.scraper import util
from core.url_utils import InvalidJobsUrlError, normalize_jobs_url
from models import job_fingerprint

# A fixed resume used across scoring tests. Do not edit casually — the golden
# scores below are computed from exactly this text.
RESUME = """John Doe
Senior Backend Engineer — Lahore, Pakistan
Experience: 6 years building REST APIs in Python and Go.
Skills: Python, Django, FastAPI, PostgreSQL, Docker, Kubernetes, AWS, Redis.
Also: React, TypeScript. Led a team of 5. Wrote technical documentation.
Certifications: AWS Certified. Projects: built a data pipeline with Kafka."""

SKILLS = ["REST", "Python", "Django", "Fastapi", "Postgresql",
          "Docker", "Kubernetes", "AWS", "React"]
KEYWORDS = ["REST developer", "Python", "Django", "Fastapi"]


# --------------------------------------------------------------------------- #
# job_fingerprint — the identity function the whole app dedupes on.
# Phase 8 will REPLACE this; these tests document what it does today so the
# migration can prove it preserved (or intentionally changed) every id.
# --------------------------------------------------------------------------- #
class TestFingerprint:
    def test_is_16_hex_chars(self):
        fp = job_fingerprint("https://x.com/j/1", "T", "C")
        assert fp == "d6995d7e2e86bcba"
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)

    def test_url_is_normalized_trailing_slash_and_case(self):
        base = job_fingerprint("https://x.com/j/1", "T", "C")
        assert job_fingerprint("https://x.com/j/1/", "T", "C") == base
        assert job_fingerprint("HTTPS://X.COM/J/1", "T", "C") == base

    def test_url_dominates_title_and_company(self):
        # Same URL, different title/company -> SAME id. This is the core
        # limitation Phase 8 fixes: one job on many boards = many ids only if
        # the URLs differ, but the same URL never splits on title/company.
        assert job_fingerprint("https://x.com/j/1", "A", "B") == \
               job_fingerprint("https://x.com/j/1", "C", "D")

    def test_falls_back_to_title_company_when_url_empty(self):
        assert job_fingerprint("", "Backend Engineer", "Acme") == "3fa42903b15eb160"
        assert job_fingerprint("", "", "") == "f62e0ea6edbc4288"

    def test_empty_url_splits_on_title_company(self):
        assert job_fingerprint("", "T1", "C") != job_fingerprint("", "T2", "C")


# --------------------------------------------------------------------------- #
# local_engine skill/keyword/location extraction
# --------------------------------------------------------------------------- #
class TestExtraction:
    def test_skills_in_appearance_order_and_normalized(self):
        # REST appears first in the resume, so it leads. Note current
        # normalization quirks preserved deliberately: "Fastapi", "Postgresql"
        # (title-case, not FastAPI/PostgreSQL). Phase 4 may fix these — when it
        # does, this expectation changes in the same commit.
        assert le.extract_skills(RESUME) == SKILLS

    def test_location_city_country(self):
        assert le.extract_location(RESUME) == "Lahore, Pakistan"

    def test_keywords_role_phrase_plus_skills(self):
        assert le.generate_keywords(SKILLS) == KEYWORDS

    def test_empty_resume_is_safe(self):
        assert le.extract_skills("") == []
        assert le.extract_location("") == "Remote"
        assert le.generate_keywords([]) == ["software developer", "engineer"]


# --------------------------------------------------------------------------- #
# local_engine.analyze — the scorer. The most important behaviour to pin.
# --------------------------------------------------------------------------- #
class TestAnalyze:
    def _score(self, title, desc):
        terms = le.role_terms(KEYWORDS, SKILLS)
        return le.analyze(SKILLS, title, desc, terms)

    def test_strong_match(self):
        r = self._score("Senior Python Backend Engineer",
                        "We need Python, Django, PostgreSQL, Docker, AWS. REST APIs.")
        assert r["score"] == 91
        assert r["verdict"] == "Strong match"
        assert r["matched_skills"] == ["REST", "Python", "Django", "Postgresql", "Docker"]
        assert r["missing_skills"] == []

    def test_partial_match(self):
        r = self._score("Full Stack Developer",
                        "React, TypeScript, Node.js. Some Python a plus.")
        assert r["score"] == 50
        assert r["verdict"] == "Partial match"
        assert r["matched_skills"] == ["Python", "React"]
        assert r["missing_skills"] == ["Typescript"]

    def test_title_only_weak(self):
        r = self._score("Backend Engineer", "")
        assert r["score"] == 18
        assert r["verdict"] == "Weak match"

    def test_unrelated_is_zero(self):
        r = self._score("Registered Nurse", "Provide patient care in the ICU ward.")
        assert r["score"] == 0
        assert r["verdict"] == "No match"

    def test_go_the_word_does_not_match_go_the_language(self):
        # Regression guard for the headline fix in 2.0. "go ... go" as prose
        # must not count the Go language.
        r = self._score("Warehouse role", "Please go to the loading dock and go fast.")
        assert r["score"] == 0
        assert "Go" not in r["matched_skills"]

    def test_c_does_not_match_inside_cpp(self):
        # Token-aware boundaries: 'c' must not match inside 'c++'.
        r = self._score("C++ Engineer", "Strong C++ and C skills required.")
        assert "C" not in r["matched_skills"]
        assert "c++" in r["missing_skills"]

    def test_verdict_bands(self):
        assert le._verdict(80) == "Strong match"
        assert le._verdict(79) == "Good match"
        assert le._verdict(60) == "Good match"
        assert le._verdict(59) == "Partial match"
        assert le._verdict(40) == "Partial match"
        assert le._verdict(39) == "Weak match"
        assert le._verdict(1) == "Weak match"
        assert le._verdict(0) == "No match"


class TestRelevanceGate:
    def test_relevant_and_noise(self):
        terms = le.role_terms(KEYWORDS, SKILLS)
        assert le.is_relevant(SKILLS, terms, "Python Backend Engineer", "Django, AWS") is True
        assert le.is_relevant(SKILLS, terms, "Sales Representative", "Cold calling, CRM") is False


# --------------------------------------------------------------------------- #
# matcher._align — protects against an LLM renumbering/ dropping batch items.
# --------------------------------------------------------------------------- #
class TestAlign:
    def test_valid_permutation_trusts_ids(self):
        got = m._align([{"id": 1, "v": "b"}, {"id": 0, "v": "a"}], 2)
        assert got == {1: {"id": 1, "v": "b"}, 0: {"id": 0, "v": "a"}}

    def test_duplicate_ids_fall_back_to_positional(self):
        got = m._align([{"id": 0, "v": "a"}, {"id": 0, "v": "b"}], 2)
        assert got == {0: {"id": 0, "v": "a"}, 1: {"id": 0, "v": "b"}}

    def test_out_of_range_ids_fall_back_to_positional(self):
        got = m._align([{"id": 5, "v": "a"}, {"id": 0, "v": "b"}], 2)
        assert got == {0: {"id": 5, "v": "a"}, 1: {"id": 0, "v": "b"}}

    def test_wrong_count_falls_back_to_positional(self):
        got = m._align([{"id": 0, "v": "a"}], 2)
        assert got == {0: {"id": 0, "v": "a"}}


# --------------------------------------------------------------------------- #
# matcher._merge — local score is the backbone; AI lifts freely, drops bounded.
# --------------------------------------------------------------------------- #
class TestMerge:
    def _merge(self, local_score, ai_score):
        local = {"score": local_score, "matched_skills": ["Python"],
                 "missing_skills": ["Go"], "summary": "local", "verdict": "x"}
        ai = None if ai_score is None else {
            "score": ai_score, "matched_skills": ["AWS"],
            "missing_skills": ["K8s"], "summary": "ai says"}
        return m._merge(local, ai)

    def test_ai_higher_is_weighted_0_7(self):
        assert self._merge(60, 90)["score"] == 81   # round(0.7*90 + 0.3*60)

    def test_ai_lower_is_bounded(self):
        assert self._merge(80, 40)["score"] == 60    # max(avg=60, local-20=60)

    def test_ai_much_lower_hits_the_floor(self):
        assert self._merge(80, 10)["score"] == 60    # max(45, 60) -> floor local-20

    def test_ai_none_keeps_backbone_verbatim(self):
        r = self._merge(70, None)
        assert r["score"] == 70
        assert r["verdict"] == "x"
        assert r["summary"] == "local"

    def test_verdict_always_rederived_from_final_score(self):
        r = self._merge(60, 90)
        assert r["verdict"] == "Strong match"        # 81 -> Strong, not local "x"

    def test_ai_summary_and_merged_skills(self):
        r = self._merge(50, 50)
        assert r["summary"] == "ai says"
        assert r["matched_skills"] == ["AWS", "Python"]   # AI first, then local
        assert r["missing_skills"] == ["K8s"]             # AI missing overrides


# --------------------------------------------------------------------------- #
# scraper/util formatting helpers
# --------------------------------------------------------------------------- #
class TestUtil:
    def test_money(self):
        assert util.money(50000, 90000) == "$50,000–$90,000"   # en-dash
        assert util.money(50000, 0) == "$50,000+"
        assert util.money(0, 90000) == "up to $90,000"
        assert util.money(None, None) == ""

    def test_strip_html(self):
        assert util.strip_html("<p>Hello <b>world</b></p><script>x</script>&amp; more") \
            == "Hello world \n & more"
        assert util.strip_html("") == ""

    def test_keyword_match(self):
        assert util.keyword_match(["python developer"], "Senior Python Engineer", "") is True
        assert util.keyword_match(["rust engineer"], "Java Developer", "PHP shop") is False
        assert util.keyword_match([], "anything") is True   # no keywords -> match all

    def test_human_date_relative(self):
        now = _dt.datetime.now(_dt.timezone.utc)
        assert util.human_date((now - _dt.timedelta(days=3)).isoformat()) == "3d ago"
        assert util.human_date((now - _dt.timedelta(days=1)).isoformat()) == "1d ago"
        assert util.human_date("") == ""
        assert util.human_date(None) == ""
        # future dates are clamped to empty
        assert util.human_date((now + _dt.timedelta(days=5)).isoformat()) == ""


# --------------------------------------------------------------------------- #
# url_utils — strict custom /jobs URL validation
# --------------------------------------------------------------------------- #
class TestUrlUtils:
    def test_accepts_bare_domain_jobs(self):
        assert normalize_jobs_url("company.com/jobs") == "https://company.com/jobs"
        assert normalize_jobs_url("https://Example.com/jobs/") == "https://example.com/jobs"

    @pytest.mark.parametrize("bad", [
        "company.com",              # no /jobs
        "company.com/careers",      # wrong path
        "company.com/jobs/engineer",# too deep
        "company.com/jobs?x=1",     # query
        "has space.com/jobs",       # space
    ])
    def test_rejects(self, bad):
        with pytest.raises(InvalidJobsUrlError):
            normalize_jobs_url(bad)

    def test_empty_is_empty_not_error(self):
        assert normalize_jobs_url("   ") == ""
