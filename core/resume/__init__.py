"""Resume module (Phase 4): structured parsing, keyword intelligence, transparent
rubric scoring, honest tailoring, and export.

    from core.resume import extract_structured, score_against_job, tailor_bullets
"""
from core.resume.ats import check_ats
from core.resume.export import export, resume_to_text
from core.resume.extract import extract_structured, extract_text
from core.resume.generate import BulletDiff, gap_report, tailor_bullets
from core.resume.keywords import (
    expand_term,
    expansion_map,
    seniority_band,
    target_titles,
    weighted_skills,
    years_experience,
)
from core.resume.rubric import score_against_job
from core.resume.schema import ParsedResume
from core.resume.store import (
    default_resume,
    get_resume,
    list_resumes,
    save_resume,
    save_version,
    set_default,
    update_parsed,
)

__all__ = [
    "extract_structured", "extract_text", "ParsedResume", "check_ats",
    "score_against_job", "tailor_bullets", "gap_report", "BulletDiff",
    "expand_term", "expansion_map", "weighted_skills", "years_experience",
    "target_titles", "seniority_band", "export", "resume_to_text",
    "save_resume", "get_resume", "list_resumes", "default_resume", "set_default",
    "update_parsed", "save_version",
]
