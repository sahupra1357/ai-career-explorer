#!/usr/bin/env python3
"""
Interactive CLI to add a new STEM field entry to data/fields.yaml.

Usage:
    python scripts/add_field.py             # interactive wizard
    python scripts/add_field.py --template  # print blank YAML template to stdout
    python scripts/add_field.py --validate  # validate all existing entries, no changes
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
from pydantic import ValidationError

from app.models import FieldEntry, normalize_slug

FIELDS_FILE = Path("data/fields.yaml")

BLANK_TEMPLATE = """\
- schema_version: "1.0"
  field_id: your-field-slug
  name: Your Field Name
  plain_english: >
    2-3 sentence plain-English description for a high schooler.
  sub_areas:
    - name: Sub-area 1
      description: One sentence.
    - name: Sub-area 2
      description: One sentence.
    - name: Sub-area 3
      description: One sentence.
  undergrad_path:
    high_school_prereqs:
      - Prerequisite 1
    common_majors:
      - Major Name
    key_courses:
      - Course Name
  career_outcomes:
    common_roles:
      - Job Title 1
      - Job Title 2
      - Job Title 3
    salary_range:
      min: 60000
      max: 120000
      currency: USD
      source_year: 2024
      region: US national median
    outlook: "X% growth 2022-2032 (BLS)"
    outlook_pct: null
  personality_fit:
    math_intensity: 3
    lab_intensity: 3
    coding_intensity: 3
    people_facing: 3
    fit_description: >
      2-3 sentences on who thrives here.
  adjacent_fields: []
  follow_on_questions:
    - Question 1?
    - Question 2?
    - Question 3?
"""


def prompt(label: str, hint: str = "", required: bool = True) -> str:
    suffix = f"  [{hint}]" if hint else ""
    while True:
        val = input(f"\n{label}{suffix}\n> ").strip()
        if val or not required:
            return val
        print("  (required — please enter a value)")


def prompt_int(label: str, lo: int = 1, hi: int = 5) -> int:
    while True:
        raw = input(f"\n{label} ({lo}-{hi})\n> ").strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  Enter a number between {lo} and {hi}.")


def prompt_list(label: str, hint: str = "one per line, blank to finish") -> list[str]:
    print(f"\n{label}  [{hint}]")
    items: list[str] = []
    while True:
        val = input(f"  item {len(items) + 1}: ").strip()
        if not val:
            if items:
                return items
            print("  (at least one item required)")
        else:
            items.append(val)


def prompt_sub_areas() -> list[dict]:
    print("\nSub-areas (3-5, blank name to finish after 3)")
    areas: list[dict] = []
    while len(areas) < 5:
        required = len(areas) < 3
        name = input(f"\n  sub-area {len(areas)+1} name{'*' if required else ' (or blank to finish)'}: ").strip()
        if not name:
            if len(areas) >= 3:
                break
            print("  (required — need at least 3 sub-areas)")
            continue
        desc = input(f"  sub-area {len(areas)+1} description: ").strip()
        areas.append({"name": name, "description": desc})
    return areas


def build_entry() -> dict:
    print("\n" + "=" * 60)
    print("  Add a new STEM field entry")
    print("  Tip: run with --template to get a blank YAML you can fill in")
    print("=" * 60)

    name = prompt("Field name (display)", "e.g. Biomedical Engineering")
    field_id = normalize_slug(name)
    confirm = input(f"\n  slug will be: {field_id!r}  (press Enter to accept or type override): ").strip()
    if confirm:
        field_id = normalize_slug(confirm)

    plain_english = prompt(
        "Plain-English description (2-3 sentences for a high schooler)",
        "What do people in this field actually do day to day?",
    )

    sub_areas = prompt_sub_areas()

    print("\n── Undergrad path ──────────────────────────────────────────")
    hs_prereqs = prompt_list("High school prerequisites")
    majors = prompt_list("Common undergraduate majors")
    courses = prompt_list("Key undergraduate courses")

    print("\n── Career outcomes ─────────────────────────────────────────")
    roles = prompt_list("Common job titles (3-5)")
    salary_min = int(prompt("Salary range MIN (USD, BLS national median)", "e.g. 65000"))
    salary_max = int(prompt("Salary range MAX (USD, BLS national median)", "e.g. 120000"))
    source_year = int(prompt("BLS data year", "e.g. 2024"))
    outlook = prompt("Job outlook string", 'e.g. "12% growth 2022-2032, faster than average (BLS)"')
    outlook_pct_raw = prompt("Outlook growth percent (numeric, or blank if unavailable)", required=False)
    outlook_pct = float(outlook_pct_raw) if outlook_pct_raw else None

    print("\n── Personality fit ─────────────────────────────────────────")
    print("  Rate 1 (very low) to 5 (very high):")
    math_i = prompt_int("  Math intensity")
    lab_i = prompt_int("  Lab / hands-on intensity")
    code_i = prompt_int("  Coding intensity")
    people_i = prompt_int("  People-facing / teamwork")
    fit_desc = prompt("Fit description (2-3 sentences on who thrives here)")

    print("\n── Follow-on questions ─────────────────────────────────────")
    follow_qs = prompt_list("Questions a student might ask to go deeper (3-5)")

    return {
        "schema_version": "1.0",
        "field_id": field_id,
        "name": name,
        "plain_english": plain_english,
        "sub_areas": sub_areas,
        "undergrad_path": {
            "high_school_prereqs": hs_prereqs,
            "common_majors": majors,
            "key_courses": courses,
        },
        "career_outcomes": {
            "common_roles": roles,
            "salary_range": {
                "min": salary_min,
                "max": salary_max,
                "currency": "USD",
                "source_year": source_year,
                "region": "US national median",
            },
            "outlook": outlook,
            "outlook_pct": outlook_pct,
        },
        "personality_fit": {
            "math_intensity": math_i,
            "lab_intensity": lab_i,
            "coding_intensity": code_i,
            "people_facing": people_i,
            "fit_description": fit_desc,
        },
        "adjacent_fields": [],
        "follow_on_questions": follow_qs,
    }


def validate_all(data: dict) -> bool:
    fields = data.get("fields") or []
    if not fields:
        print("No field entries found in fields.yaml.")
        return True
    errors: list[str] = []
    for entry in fields:
        fid = entry.get("field_id", "?")
        try:
            FieldEntry(**entry)
        except ValidationError as e:
            errors.append(f"  field '{fid}': {e.error_count()} error(s)\n" +
                          "\n".join(f"    {err['loc']} — {err['msg']}" for err in e.errors()))
    if errors:
        print(f"\n✗ Validation failed ({len(errors)} field(s) with errors):\n")
        print("\n".join(errors))
        return False
    print(f"✓ All {len(fields)} field entries are valid.")
    return True


def load_yaml() -> dict:
    raw = yaml.safe_load(FIELDS_FILE.read_text()) or {}
    if "fields" not in raw:
        raw["fields"] = []
    return raw


def save_yaml(data: dict) -> None:
    FIELDS_FILE.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Add a STEM field entry to data/fields.yaml")
    parser.add_argument("--template", action="store_true", help="Print blank YAML template to stdout")
    parser.add_argument("--validate", action="store_true", help="Validate all existing entries")
    args = parser.parse_args()

    if args.template:
        print(BLANK_TEMPLATE)
        return

    if not FIELDS_FILE.exists():
        print(f"Error: {FIELDS_FILE} not found. Run from the project root.")
        sys.exit(1)

    data = load_yaml()

    if args.validate:
        ok = validate_all(data)
        sys.exit(0 if ok else 1)

    entry_dict = build_entry()

    # Validate before writing
    try:
        validated = FieldEntry(**entry_dict)
    except ValidationError as e:
        print(f"\n✗ Validation failed — entry not saved:\n{e}")
        sys.exit(1)

    # Check for duplicate field_id
    existing_ids = {f.get("field_id") for f in (data.get("fields") or [])}
    if validated.field_id in existing_ids:
        print(f"\n✗ A field with id '{validated.field_id}' already exists. Not saved.")
        sys.exit(1)

    data["fields"].append(entry_dict)
    save_yaml(data)

    print(f"\n✓ Added '{validated.name}' ({validated.field_id}) to {FIELDS_FILE}")
    print(f"  Total fields: {len(data['fields'])}")


if __name__ == "__main__":
    main()
