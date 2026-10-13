export const DESIGN_DRAFT_KEY = "rf-design-draft-v1"

export function parseDesignDraft(value) {
  if (!value) return null
  try {
    const draft = JSON.parse(value)
    if (!draft || draft.version !== 1 || typeof draft.requirement !== "object") return null
    return {
      ...draft,
      wizardStep: Math.min(Math.max(Number(draft.wizardStep) || 1, 1), 6),
      unlockedWizardStep: Math.min(Math.max(Number(draft.unlockedWizardStep) || 1, 1), 6),
      pinnedComponents: Array.isArray(draft.pinnedComponents) ? draft.pinnedComponents : [],
      stageDecisions: draft.stageDecisions && typeof draft.stageDecisions === "object" ? draft.stageDecisions : {},
    }
  } catch {
    return null
  }
}

export function serializeDesignDraft(state) {
  return JSON.stringify({
    version: 1,
    requirement: state.requirement,
    pinnedComponents: state.pinnedComponents,
    stageDecisions: state.stageDecisions,
    formulaProfile: state.formulaProfile,
    wizardStep: Math.min(state.wizardStep, 6),
    unlockedWizardStep: Math.min(state.unlockedWizardStep, 6),
    savedAt: state.savedAt,
  })
}
