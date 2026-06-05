"""Course-name → CIP resolution.

Students type "CS", "Data Science", "Comp Sci", "Nursing" — not "11.07". This maps common
course names/abbreviations to canonical CIP 4-digit codes so the knowledge graph can match
on the standard taxonomy instead of free-text titles alone.

CIP codes are best-effort for common majors. Matching uses the resolved CIP as a *boost*;
title matching still runs as a fallback, so an imperfect or missing code degrades gracefully
(it just stops adding precision — it never drops a legitimate title match).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz


@dataclass(frozen=True)
class CourseResolution:
    name: str             # canonical display name, e.g. "Computer Science"
    cips: tuple[str, ...]  # dotted 4-digit (or 2-digit series) CIP codes


# name → CIP codes → aliases. The canonical `name` is added as an alias automatically.
CIP_PROGRAMS: list[dict] = [
    {"name": "Computer Science", "cips": ["11.07"],
     "aliases": ["cs", "comp sci", "compsci", "computer sci"]},
    {"name": "Computer and Information Sciences", "cips": ["11"],
     "aliases": ["computing", "computer information science", "cis"]},
    {"name": "Information Technology", "cips": ["11.10", "11.01"],
     "aliases": ["it", "information tech", "computer information technology"]},
    {"name": "Cybersecurity", "cips": ["11.10", "43.03"],
     "aliases": ["cyber security", "information security", "infosec"]},
    {"name": "Data Science", "cips": ["30.70", "30.71"],
     "aliases": ["data analytics", "data analysis", "datascience"]},
    {"name": "Software Engineering", "cips": ["14.09", "11.08"],
     "aliases": ["software eng", "software"]},
    {"name": "Electrical Engineering", "cips": ["14.10"],
     "aliases": ["ee", "electrical eng"]},
    {"name": "Mechanical Engineering", "cips": ["14.19"],
     "aliases": ["meche", "mech e", "mechanical eng"]},
    {"name": "Civil Engineering", "cips": ["14.08"], "aliases": ["civil eng"]},
    {"name": "Chemical Engineering", "cips": ["14.07"], "aliases": ["chem e", "chemical eng"]},
    {"name": "Biomedical Engineering", "cips": ["14.05"], "aliases": ["bme", "biomedical eng", "bioengineering"]},
    {"name": "Nursing", "cips": ["51.38", "51.39"],
     "aliases": ["registered nursing", "rn", "bsn", "nurse"]},
    {"name": "Business Administration", "cips": ["52.02"],
     "aliases": ["business", "management", "mba", "business admin"]},
    {"name": "Finance", "cips": ["52.08"], "aliases": []},
    {"name": "Accounting", "cips": ["52.03"], "aliases": ["accountancy"]},
    {"name": "Economics", "cips": ["45.06"], "aliases": ["econ"]},
    {"name": "Psychology", "cips": ["42.01"], "aliases": ["psych"]},
    {"name": "Biology", "cips": ["26.01"], "aliases": ["bio", "biological sciences"]},
    {"name": "Chemistry", "cips": ["40.05"], "aliases": ["chem"]},
    {"name": "Physics", "cips": ["40.08"], "aliases": []},
    {"name": "Mathematics", "cips": ["27.01"], "aliases": ["math", "maths"]},
    {"name": "Political Science", "cips": ["45.10"], "aliases": ["poli sci", "polisci", "government"]},
    {"name": "Mechanical Engineering Technology", "cips": ["15.08"], "aliases": ["engineering technology"]},
]

_FUZZY_CUTOFF = 88


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _build_lookup() -> dict[str, CourseResolution]:
    lookup: dict[str, CourseResolution] = {}
    for prog in CIP_PROGRAMS:
        res = CourseResolution(name=prog["name"], cips=tuple(prog["cips"]))
        for alias in [prog["name"], *prog["aliases"]]:
            lookup.setdefault(_norm(alias), res)
    return lookup


_ALIAS_LOOKUP = _build_lookup()


def resolve_course(query: str) -> CourseResolution | None:
    """Resolve a free-text course query to a canonical CIP entry, or None if unknown."""
    q = _norm(query)
    if not q:
        return None
    if q in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[q]

    best: CourseResolution | None = None
    best_score = 0.0
    for alias, res in _ALIAS_LOOKUP.items():
        if len(alias) < 4:
            continue  # short aliases (cs, ee, it, rn) match exactly only — avoid false hits
        if alias in q or q in alias:
            score = 95.0
        else:
            score = fuzz.ratio(q, alias)
        if score >= _FUZZY_CUTOFF and score > best_score:
            best, best_score = res, score
    return best
