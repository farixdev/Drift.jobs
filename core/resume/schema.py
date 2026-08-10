"""Strict resume schema for LLM structured extraction (Phase 4).

The JSON schema drives the AI layer's schema-validated extraction; the dataclasses
give the rest of the app a typed view. Only `skills` is required so a sparse
resume still parses.
"""
from __future__ import annotations

from dataclasses import dataclass, field

RESUME_SCHEMA: dict = {
    "type": "object",
    "required": ["skills"],
    "properties": {
        "contact": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "location": {"type": "string"},
            },
        },
        "summary": {"type": "string"},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "title": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "location": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "education": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "institution": {"type": "string"},
                    "degree": {"type": "string"},
                    "field": {"type": "string"},
                    "year": {"type": "string"},
                },
            },
        },
        "skills": {
            "type": "object",
            "properties": {
                "technical": {"type": "array", "items": {"type": "string"}},
                "soft": {"type": "array", "items": {"type": "string"}},
                "tools": {"type": "array", "items": {"type": "string"}},
                "languages": {"type": "array", "items": {"type": "string"}},
            },
        },
        "certifications": {"type": "array", "items": {"type": "string"}},
        "projects": {"type": "array", "items": {"type": "string"}},
        "links": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass
class Experience:
    company: str = ""
    title: str = ""
    start: str = ""
    end: str = ""
    location: str = ""
    bullets: list = field(default_factory=list)


@dataclass
class Education:
    institution: str = ""
    degree: str = ""
    field_: str = ""
    year: str = ""


@dataclass
class ParsedResume:
    contact: dict = field(default_factory=dict)
    summary: str = ""
    experience: list = field(default_factory=list)     # [Experience]
    education: list = field(default_factory=list)       # [Education]
    skills: dict = field(default_factory=lambda: {"technical": [], "soft": [],
                                                   "tools": [], "languages": []})
    certifications: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    links: list = field(default_factory=list)

    def all_skills(self) -> list[str]:
        s = self.skills or {}
        # `or []` guards against a null category (a model may emit "tools": null).
        out = list(s.get("technical") or []) + list(s.get("tools") or [])
        seen, uniq = set(), []
        for x in out:
            k = str(x).strip().lower()
            if k and k not in seen:
                seen.add(k)
                uniq.append(str(x).strip())
        return uniq

    @classmethod
    def from_dict(cls, d: dict) -> "ParsedResume":
        # `d.get(key) or []` (not `d.get(key, [])`) because a present-but-null
        # value would otherwise return None and crash the iteration — one stray
        # null must never discard the whole parse.
        d = d or {}
        exp = [Experience(company=e.get("company", ""), title=e.get("title", ""),
                          start=e.get("start", ""), end=e.get("end", ""),
                          location=e.get("location", ""),
                          bullets=[b for b in (e.get("bullets") or []) if b])
               for e in (d.get("experience") or []) if isinstance(e, dict)]
        edu = [Education(institution=e.get("institution", ""), degree=e.get("degree", ""),
                         field_=e.get("field", ""), year=e.get("year", ""))
               for e in (d.get("education") or []) if isinstance(e, dict)]
        skills = d.get("skills") or {}
        if isinstance(skills, list):                       # models sometimes flatten
            skills = {"technical": skills}
        elif isinstance(skills, str):                      # …or return a CSV string
            skills = {"technical": [s.strip() for s in skills.split(",") if s.strip()]}
        elif not isinstance(skills, dict):
            skills = {}
        return cls(
            contact=(d.get("contact") if isinstance(d.get("contact"), dict) else {}) or {},
            summary=d.get("summary") or "",
            experience=exp, education=edu,
            skills={"technical": list(skills.get("technical") or []),
                    "soft": list(skills.get("soft") or []),
                    "tools": list(skills.get("tools") or []),
                    "languages": list(skills.get("languages") or [])},
            certifications=[c for c in (d.get("certifications") or []) if c],
            projects=[p for p in (d.get("projects") or []) if p],
            links=[l for l in (d.get("links") or []) if l],
        )

    def to_dict(self) -> dict:
        return {
            "contact": self.contact,
            "summary": self.summary,
            "experience": [vars(e) for e in self.experience],
            "education": [{"institution": e.institution, "degree": e.degree,
                           "field": e.field_, "year": e.year} for e in self.education],
            "skills": self.skills,
            "certifications": self.certifications,
            "projects": self.projects,
            "links": self.links,
        }
