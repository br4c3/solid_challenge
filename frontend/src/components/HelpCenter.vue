<script setup>
import { computed, nextTick, onMounted, ref } from "vue"

const emit = defineEmits(["close", "navigate"])
const searchInput = ref(null)
const query = ref("")

const sections = [
  {
    id: "quick-start",
    title: "Quick start",
    summary: "Complete a first RF chain design from requirements to candidate comparison.",
    items: [
      "Choose the application and link direction in Chain Design.",
      "Enter the highlighted required values and adjust advanced losses when needed.",
      "Select a formula profile, set preferences, and choose automatic or pinned parts for each stage.",
      "Review the inputs, calculate candidates, then inspect stages or export a comparison as CSV.",
    ],
    action: { page: "design", label: "Open Chain Design" },
  },
  {
    id: "design",
    title: "Chain Design",
    summary: "The seven-step wizard builds and evaluates a transmit or receive chain.",
    items: [
      "A draft is saved locally while you work. New Design clears the saved draft and current result.",
      "Automatic selection lets the ranking model choose a stage; pinned selection forces a compatible part.",
      "PASS satisfies the modeled constraints, WARN needs engineering review, and FAIL misses a required constraint.",
      "Calculation evidence shows the exact expression, input values, units, and result used for a candidate.",
    ],
    action: { page: "design", label: "Open Chain Design" },
  },
  {
    id: "formulas",
    title: "Formula Profiles",
    summary: "Inspect the built-in model or create a versioned custom calculation profile.",
    items: [
      "The built-in profile is read-only. Clone it before editing formulas or ranking rules.",
      "Validate and save to create an immutable revision. Existing results retain their original revision.",
      "Import and export use JSON so a reviewed profile can be shared between workstations.",
    ],
    action: { page: "formulas", label: "Open Formula Profiles" },
  },
  {
    id: "components",
    title: "Components and Data",
    summary: "Browse source data, mark preferences, and refresh manufacturer information.",
    items: [
      "Stars mark preferred manufacturers or parts and influence ranking without overriding compatibility.",
      "Open a part number to review specifications, source links, and extraction evidence.",
      "Data Crawl downloads public manufacturer information and reports progress in the pipeline log.",
    ],
    action: { page: "components", label: "Open Components" },
  },
  {
    id: "troubleshooting",
    title: "Troubleshooting",
    summary: "Resolve the most common calculation and catalog issues.",
    items: [
      "No candidates: verify frequency coverage, relax pinned-part choices, and check FAIL compatibility messages.",
      "Unexpected result: confirm units, open calculation evidence, and verify the selected formula revision.",
      "Missing parts: run Data Crawl, wait for completion, then return to Components or the part-selection step.",
      "CSV unavailable: export requires the desktop application and at least one selected candidate.",
    ],
  },
]

const glossary = [
  ["BFIC", "Beamforming integrated circuit used to control gain and phase across antenna elements."],
  ["EIRP", "Equivalent isotropically radiated power, expressed in dBW in calculation results."],
  ["Link margin", "Remaining received-power margin above the modeled requirement; a negative value indicates a shortfall."],
  ["NF", "Noise figure: degradation of signal-to-noise ratio introduced by a receive component or chain."],
  ["Output backoff", "Reduction from saturated output power used to preserve linearity."],
  ["Pinned part", "A component explicitly fixed by the user instead of selected by the ranking model."],
]

const normalizedQuery = computed(() => query.value.trim().toLowerCase())
const filteredSections = computed(() => {
  if (!normalizedQuery.value) return sections
  return sections.filter((section) => [section.title, section.summary, ...section.items]
    .join(" ").toLowerCase().includes(normalizedQuery.value))
})
const filteredGlossary = computed(() => {
  if (!normalizedQuery.value) return glossary
  return glossary.filter((entry) => entry.join(" ").toLowerCase().includes(normalizedQuery.value))
})
const hasResults = computed(() => filteredSections.value.length || filteredGlossary.value.length)

function openPage(page) {
  emit("navigate", page)
}

onMounted(async () => {
  await nextTick()
  searchInput.value?.focus()
})
</script>

<template>
  <section class="help-center" aria-labelledby="help-title">
    <header class="help-header">
      <div>
        <span class="eyebrow">USER GUIDE</span>
        <h2 id="help-title">Help Center</h2>
        <p>Find workflow guidance, definitions, and fixes without leaving the application.</p>
      </div>
      <button type="button" @click="emit('close')">Back to previous screen</button>
    </header>

    <label class="help-search">
      <span>Search help</span>
      <input ref="searchInput" v-model="query" type="search" placeholder="Search workflows, terms, or problems" />
      <kbd>/</kbd>
    </label>

    <div v-if="hasResults" class="help-layout">
      <div class="help-sections">
        <article v-for="section in filteredSections" :id="`help-${section.id}`" :key="section.id" class="help-card">
          <div class="help-card-heading">
            <div><h3>{{ section.title }}</h3><p>{{ section.summary }}</p></div>
            <button v-if="section.action" type="button" @click="openPage(section.action.page)">{{ section.action.label }}</button>
          </div>
          <ol v-if="section.id === 'quick-start'">
            <li v-for="item in section.items" :key="item">{{ item }}</li>
          </ol>
          <ul v-else>
            <li v-for="item in section.items" :key="item">{{ item }}</li>
          </ul>
        </article>
      </div>

      <aside v-if="filteredGlossary.length" class="help-glossary" aria-label="RF glossary">
        <h3>RF glossary</h3>
        <dl>
          <div v-for="entry in filteredGlossary" :key="entry[0]">
            <dt>{{ entry[0] }}</dt>
            <dd>{{ entry[1] }}</dd>
          </div>
        </dl>
        <section class="help-shortcuts">
          <h3>Keyboard</h3>
          <p><kbd>F1</kbd><span>Open Help Center</span></p>
          <p><kbd>Esc</kbd><span>Return to previous screen</span></p>
        </section>
      </aside>
    </div>

    <div v-else class="help-empty" role="status">
      <strong>No help topics found</strong>
      <span>Try a broader term such as “candidate,” “formula,” or “data.”</span>
      <button type="button" @click="query = ''">Clear search</button>
    </div>
  </section>
</template>
