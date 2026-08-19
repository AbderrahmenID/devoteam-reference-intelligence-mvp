export const NARRATIVE_SESSION_KEY = "devoteam-narrative-studio-v1";

export function generationRequest(options, referenceIds) {
  return {
    selected_reference_ids: referenceIds,
    opportunity_title: options.opportunity_title.trim(),
    opportunity_description: options.opportunity_description.trim(),
    requirements: options.requirements.split("\n").map((value) => value.trim()).filter(Boolean),
    target_language: options.target_language,
    tone: options.tone,
    audience: options.audience,
    detail_level: options.detail_level,
  };
}

export function editableNarrative(narrative) {
  return {
    section_intro: narrative.section_intro.text,
    overall_storyline: narrative.overall_storyline.text,
    why_these_references: narrative.why_these_references.text,
    references: narrative.references.map((reference) => ({
      headline: reference.headline.text,
      short_description: reference.short_description.text,
      challenge: reference.challenge.text,
      devoteam_contribution: reference.devoteam_contribution.text,
      realisations: reference.realisations.map((item) => item.text),
      benefits: reference.benefits.map((item) => item.text),
      why_relevant_to_opportunity: reference.why_relevant_to_opportunity.text,
    })),
  };
}

export function warningCounts(warnings = []) {
  return warnings.reduce((counts, warning) => {
    const severity = warning.severity || "BLOCKING";
    counts[severity] = (counts[severity] || 0) + 1;
    return counts;
  }, { INFO: 0, WARNING: 0, BLOCKING: 0 });
}

export function warningsForField(warnings, path) {
  return warnings.filter((warning) => warning.field_path === path || warning.field_path?.startsWith(`${path}[`));
}

export function studioStatus({ hasNarrative, approved, dirty, warnings }) {
  if (!hasNarrative) return "DRAFT";
  const blocking = warningCounts(warnings).BLOCKING > 0;
  if (approved && !blocking && !dirty) return "READY FOR PRESENTATION";
  if (blocking || dirty) return "NEEDS REVIEW";
  return "DRAFT";
}

export function canApproveNarrative(warnings, validating) {
  return !validating && warningCounts(warnings).BLOCKING === 0;
}

export function validStudioSession(value, referenceIds) {
  return Boolean(
    value
    && Array.isArray(value.reference_ids)
    && value.reference_ids.join("|") === referenceIds.join("|")
    && value.review?.narrative
    && value.options,
  );
}
