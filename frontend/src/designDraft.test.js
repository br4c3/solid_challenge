import { describe, expect, it } from "vitest"
import { parseDesignDraft, serializeDesignDraft } from "./designDraft"

describe("design draft", () => {
  it("restores a valid draft and clamps result steps to review", () => {
    const restored = parseDesignDraft(serializeDesignDraft({
      requirement: { application: "Terminal" },
      pinnedComponents: [],
      stageDecisions: { PLL: "auto" },
      formulaProfile: { id: "default-v1", revision: 1 },
      wizardStep: 7,
      unlockedWizardStep: 7,
      savedAt: "2026-10-02T00:00:00Z",
    }))

    expect(restored.wizardStep).toBe(6)
    expect(restored.unlockedWizardStep).toBe(6)
    expect(restored.stageDecisions.PLL).toBe("auto")
  })

  it("rejects corrupted and unsupported drafts", () => {
    expect(parseDesignDraft("not-json")).toBeNull()
    expect(parseDesignDraft('{"version":2,"requirement":{}}')).toBeNull()
  })
})
