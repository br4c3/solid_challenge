// @vitest-environment jsdom

import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import HelpCenter from "./HelpCenter.vue"

describe("HelpCenter", () => {
  it("filters topics and glossary entries", async () => {
    const wrapper = mount(HelpCenter)

    await wrapper.get('input[type="search"]').setValue("EIRP")

    expect(wrapper.text()).toContain("Equivalent isotropically radiated power")
    expect(wrapper.text()).not.toContain("Quick start")
  })

  it("emits navigation and close actions", async () => {
    const wrapper = mount(HelpCenter)

    await wrapper.get(".help-card button").trigger("click")
    await wrapper.get(".help-header button").trigger("click")

    expect(wrapper.emitted("navigate")).toEqual([["design"]])
    expect(wrapper.emitted("close")).toHaveLength(1)
  })

  it("offers a reset when no help topic matches", async () => {
    const wrapper = mount(HelpCenter)

    await wrapper.get('input[type="search"]').setValue("no-such-help-topic")
    expect(wrapper.text()).toContain("No help topics found")

    await wrapper.get(".help-empty button").trigger("click")
    expect(wrapper.get('input[type="search"]').element.value).toBe("")
  })
})
