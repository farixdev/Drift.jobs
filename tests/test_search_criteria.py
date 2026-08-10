"""Phase 5 — search criteria: model, filter, saved searches, and widening."""
from __future__ import annotations

import pytest

import db
from core.search import (
    apply_criteria,
    delete_search,
    duplicate_search,
    get_search,
    list_searches,
    save_search,
)
from core.sources.spec import SearchCriteria
from core.normalize import normalize_job
from core.scraper.base import RawJob


@pytest.fixture
def dbpath(tmp_path, monkeypatch):
    from db import connection
    p = tmp_path / "test.db"
    monkeypatch.setattr(connection, "DB_PATH", p)
    monkeypatch.setattr(db, "DB_PATH", p, raising=False)
    db.init_db()
    return p


def _nj(title, company="Acme", desc="Python Django backend", loc="Remote",
        source="greenhouse", salary="", jtype="", posted=""):
    return normalize_job(RawJob(title=title, company=company, location=loc,
                                description=desc, url=f"https://{source}.com/{title}",
                                source=source, remote=("remote" in loc.lower()),
                                salary=salary, job_type=jtype, posted=posted))


# --------------------------------------------------------------------------- #
class TestModel:
    def test_effective_keywords_unifies_role_terms(self):
        c = SearchCriteria(titles=["Backend Engineer"], keywords_required=["Python"],
                           keywords_nice=["AWS"])
        assert c.effective_keywords() == ["Backend Engineer", "Python", "AWS"]

    def test_roundtrip_serialization(self):
        c = SearchCriteria(titles=["SRE"], salary_min=120000, posted_within_days=7,
                           employment_types=["full_time"], exclude_staffing=True)
        c2 = SearchCriteria.from_dict(c.to_dict())
        assert c2.titles == ["SRE"] and c2.salary_min == 120000
        assert c2.posted_within_days == 7 and c2.exclude_staffing is True

    def test_from_dict_ignores_unknown_keys(self):
        c = SearchCriteria.from_dict({"titles": ["X"], "bogus": 1})
        assert c.titles == ["X"]


class TestFilter:
    def test_excluded_and_required_keywords(self):
        jobs = [_nj("Python Engineer", desc="python django"),
                _nj("PHP Engineer", desc="php laravel wordpress")]
        crit = SearchCriteria(keywords_required=["python"], keywords_excluded=["wordpress"])
        kept, dropped = apply_criteria(jobs, crit)
        assert [j.title for j in kept] == ["Python Engineer"]
        assert dropped  # the PHP one dropped

    def test_salary_floor_respects_unstated_toggle(self):
        stated_low = _nj("A", salary="$80,000")
        unstated = _nj("B", salary="")
        crit = SearchCriteria(salary_min=120000, include_unstated_salary=True)
        kept, _ = apply_criteria([stated_low, unstated], crit)
        assert [j.title for j in kept] == ["B"]        # low stated dropped, unstated kept
        crit2 = SearchCriteria(salary_min=120000, include_unstated_salary=False)
        kept2, _ = apply_criteria([stated_low, unstated], crit2)
        assert kept2 == []                              # unstated now dropped too

    def test_exclude_company_and_staffing(self):
        jobs = [_nj("Eng", company="Acme"),
                _nj("Eng", company="Globex"),
                _nj("Eng", company="TalentBridge Staffing")]
        crit = SearchCriteria(exclude_companies=["Globex"], exclude_staffing=True)
        kept, _ = apply_criteria(jobs, crit)
        assert [j.company_name for j in kept] == ["Acme"]

    def test_max_per_company(self):
        jobs = [_nj(f"Role {i}", company="Acme") for i in range(5)]
        crit = SearchCriteria(max_per_company=2)
        kept, dropped = apply_criteria(jobs, crit)
        assert len(kept) == 2 and dropped.get("max_per_company") == 3

    def test_max_results_cap(self):
        jobs = [_nj(f"Role {i}", company=f"Co{i}") for i in range(10)]
        kept, dropped = apply_criteria(jobs, SearchCriteria(max_results=4))
        assert len(kept) == 4 and dropped.get("max_results") == 6

    def test_seniority(self):
        jobs = [_nj("Senior Python Engineer"), _nj("Junior Python Engineer")]
        crit = SearchCriteria(seniority=["senior"])
        kept, _ = apply_criteria(jobs, crit)
        assert [j.title for j in kept] == ["Senior Python Engineer"]


class TestSavedSearches:
    def test_crud_and_duplicate(self, dbpath):
        c = SearchCriteria(titles=["Backend Engineer"], salary_min=100000)
        sid = save_search("My search", c)
        assert any(s["id"] == sid for s in list_searches())
        name, loaded = get_search(sid)
        assert name == "My search" and loaded.salary_min == 100000

        dup = duplicate_search(sid)
        assert dup != sid
        dname, _ = get_search(dup)
        assert dname == "My search (copy)"

        delete_search(sid)
        assert all(s["id"] != sid for s in list_searches())

    def test_update_in_place(self, dbpath):
        sid = save_search("s", SearchCriteria(titles=["A"]))
        save_search("s2", SearchCriteria(titles=["B"]), search_id=sid)
        name, loaded = get_search(sid)
        assert name == "s2" and loaded.titles == ["B"]


class TestWidening:
    def test_widen_relaxes_new_fields_in_order(self):
        from core.engine.engine import _widen
        c = SearchCriteria(keywords_nice=["nice"], posted_within_days=3,
                           location_mode="remote", salary_min=100000,
                           keywords=["python", "backend"])
        c, what = _widen(c); assert "nice-to-have" in what and c.keywords_nice == []
        c, what = _widen(c); assert "freshness" in what and c.posted_within_days == 7
