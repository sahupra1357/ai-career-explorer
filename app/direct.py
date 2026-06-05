"""Generate a structured deep-dive for a single STEM field via Claude."""
from __future__ import annotations

import os

import structlog
from anthropic import AsyncAnthropic

from app.kb import store
from app.models import DeepDiveSection, DirectResponse

log = structlog.get_logger()

_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

_SECTIONS = [
    ("What it really is", "Explain what this field actually involves day-to-day, beyond the textbook definition. 3-4 sentences, plain English."),
    ("Who thrives here", "Describe the personality type, working style, and intrinsic motivations that predict success. 3-4 sentences."),
    ("Your high school starting line", "Specific steps a high school student can take right now: courses, clubs, projects, competitions. Be concrete."),
    ("Where it leads", "Career paths, graduate school options, and unexpected directions this field can take. 3-4 sentences."),
    ("Honest trade-offs", "What's hard, underrated, or surprising about this field that most guides don't mention. 2-3 sentences."),
]

_MOCK_CONTENT = "This is a mock deep-dive section. Set MOCK_CLAUDE=0 in .env for real Claude output."


async def generate_deep_dive(field_id: str) -> DirectResponse | None:
    field = store.get(field_id)
    if field is None:
        return None

    from app.llm import complete, mock_llm

    if mock_llm():
        sections = [DeepDiveSection(title=title, content=_MOCK_CONTENT) for title, _ in _SECTIONS]
        return DirectResponse(field_id=field.field_id, name=field.name, sections=sections)

    field_context = (
        f"Field: {field.name}\n"
        f"Plain English: {field.plain_english}\n"
        f"Common roles: {', '.join(field.career_outcomes.common_roles[:4])}\n"
        f"Personality fit: {field.personality_fit.fit_description}\n"
        f"Key courses: {', '.join(field.undergrad_path.key_courses[:5])}\n"
    )
    system = "You are a knowledgeable, honest career counselor for high school students. Be specific and direct."

    sections: list[DeepDiveSection] = []
    try:
        for title, instruction in _SECTIONS:
            content = await complete(
                f"{field_context}\n\nSection: {title}\nInstructions: {instruction}\n\n"
                "Write only the section content. No headers, no markdown.",
                system=system, max_tokens=300,
            )
            if content:
                sections.append(DeepDiveSection(title=title, content=content))

        log.info("deep_dive_ok", field_id=field_id, sections=len(sections))
        return DirectResponse(field_id=field.field_id, name=field.name, sections=sections)

    except Exception as exc:
        log.error("deep_dive_error", field_id=field_id, error=str(exc))
        return None
    finally:
        await client.close()
