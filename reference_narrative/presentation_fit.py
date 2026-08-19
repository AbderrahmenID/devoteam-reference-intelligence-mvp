from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pptx import Presentation

from .template_mapper import EMU_PER_INCH, find_shape, load_template_mapping, measure_text_fit


@dataclass(frozen=True)
class TemplateFieldBudget:
    field: str
    width_inches: float
    height_inches: float
    intended_pt: int
    minimum_pt: int
    maximum_items: int
    optional: bool
    calibrated_lines: int | None = None

    def available_lines(self, font_size_pt: int) -> int:
        return max(
            1,
            math.floor(self.height_inches * 72 / (font_size_pt * 1.12)),
            int(self.calibrated_lines or 0),
        )

    @property
    def normal_lines(self) -> int:
        return self.available_lines(self.intended_pt)

    @property
    def absolute_lines(self) -> int:
        return self.available_lines(self.minimum_pt)

    def measure(self, heading: str, values: list[str]):
        return measure_text_fit(
            heading=heading,
            values=values,
            width_inches=self.width_inches,
            height_inches=self.height_inches,
            intended_pt=self.intended_pt,
            minimum_pt=self.minimum_pt,
            calibrated_lines=self.calibrated_lines,
        )


class TemplateFitProfile:
    """Real template geometry expressed as deterministic generation budgets."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        registry, mapping = load_template_mapping(self.project_root)
        deck = Presentation(self.project_root / registry["source_file"])
        slide = deck.slides[int(mapping["source_slide"]) - 1]
        typography = mapping["typography"]
        body_intended = int(typography["intended_body_pt"])
        body_minimum = int(typography["minimum_body_pt"])

        calibrated = {
            field: int(mapping["calibrated_lines"][field])
            for field in ("mission_title", "challenge", "realisations", "benefits")
        }

        def detailed(field: str, maximum_items: int, optional: bool) -> TemplateFieldBudget:
            shape = find_shape(slide, int(mapping["shape_ids"][field]))
            intended = int(typography["headline_pt"]) if field == "mission_title" else body_intended
            minimum = int(typography["minimum_headline_pt"]) if field == "mission_title" else body_minimum
            return TemplateFieldBudget(
                field="headline" if field == "mission_title" else field,
                width_inches=shape.width / EMU_PER_INCH,
                height_inches=shape.height / EMU_PER_INCH,
                intended_pt=intended,
                minimum_pt=minimum,
                maximum_items=maximum_items,
                optional=optional,
                calibrated_lines=calibrated[field],
            )

        self.budgets: dict[str, dict[str, TemplateFieldBudget]] = {
            "detailed_reference": {
                "headline": detailed("mission_title", 1, False),
                "challenge": detailed("challenge", 3, True),
                "realisations": detailed("realisations", 6, False),
                "benefits": detailed("benefits", 4, True),
            },
            "orange_bank_compact": {
                # These are the exact insertion frames used by compact_pptx_generator.py.
                "headline": TemplateFieldBudget("headline", 1.93, 1.55, 10, 8, 1, False),
                "compact_services": TemplateFieldBudget("compact_services", 8.05, 1.52, 8, 8, 6, False),
            },
        }
        self.labels: dict[str, dict[str, str]] = mapping["labels"]

    def heading(self, template_id: str, field: str, language: str) -> str:
        if template_id == "detailed_reference" and field in {"challenge", "realisations", "benefits"}:
            return str(self.labels[language][field])
        return ""

    def initial_prompt_budget(self, template_id: str) -> dict[str, str]:
        budgets = self.budgets[template_id]
        if template_id == "orange_bank_compact":
            title = budgets["headline"]
            activities = budgets["compact_services"]
            return {
                "display_title": (
                    f"short slide title; fit within {title.absolute_lines} rendered lines at "
                    f"the template minimum of {title.minimum_pt} pt; maximum 96 characters"
                ),
                "activities": (
                    f"complete activity list must fit within {activities.absolute_lines} rendered lines at "
                    f"{activities.minimum_pt} pt; 3-{activities.maximum_items} concise bullets when supported; "
                    "maximum 90 characters per bullet"
                ),
            }
        title = budgets["headline"]
        challenge = budgets["challenge"]
        realisations = budgets["realisations"]
        benefits = budgets["benefits"]
        return {
            "mission_title": (
                f"prefer 2-3 short lines; never exceed the real template capacity of "
                f"{title.absolute_lines} rendered lines at {title.minimum_pt} pt"
            ),
            "challenges": (
                f"complete section including its heading must fit within {challenge.absolute_lines} rendered lines "
                f"at {challenge.minimum_pt} pt; prefer 1-2 short bullets; direct factual phrasing only"
            ),
            "realisations": (
                f"complete section including its heading must fit within {realisations.absolute_lines} rendered lines "
                f"at {realisations.minimum_pt} pt; use no more than {realisations.maximum_items} concise bullets"
            ),
            "benefits": (
                f"complete section including its heading must fit within {benefits.absolute_lines} rendered lines "
                f"at {benefits.minimum_pt} pt; use no more than {benefits.maximum_items} concise bullets; "
                "use explicit results or directly entailed non-quantified value"
            ),
        }

    def manifest(self, template_id: str) -> dict[str, Any]:
        return {
            field: {
                "width_inches": round(budget.width_inches, 4),
                "height_inches": round(budget.height_inches, 4),
                "intended_font_pt": budget.intended_pt,
                "minimum_font_pt": budget.minimum_pt,
                "normal_line_capacity": budget.normal_lines,
                "absolute_line_capacity": budget.absolute_lines,
                "maximum_items": budget.maximum_items,
            }
            for field, budget in self.budgets[template_id].items()
        }
