<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { api } from "./api"
import FormulaProfiles from "./components/FormulaProfiles.vue"
import HelpCenter from "./components/HelpCenter.vue"
import { DESIGN_DRAFT_KEY, parseDesignDraft, serializeDesignDraft } from "./designDraft"

const page = ref("design")
const loading = ref(false)
const error = ref("")
const result = ref(null)
const components = ref([])
const category = ref("ALL")
const bands = ref({})
const selectedCandidateIndex = ref(0)
const selectedComponent = ref(null)
const crawlState = ref("idle")
const crawlLogs = ref([])
const crawlOffset = ref(0)
const crawlStartedAt = ref(null)
const crawlFinishedAt = ref(null)
const terminal = ref(null)
const resultsPanel = ref(null)
const designForm = ref(null)
const preferences = ref({ favorite_manufacturers: [], favorite_components: [] })
const pinnedComponents = ref([])
const pinSearch = ref("")
const componentSearch = ref("")
const selectedStageIndex = ref(0)
const comparedCandidateIndexes = ref([])
const comparisonOpen = ref(false)
const compareMessage = ref("")
const wizardStep = ref(1)
const unlockedWizardStep = ref(1)
const activePinStageIndex = ref(0)
const stageDecisions = ref({})
const formulaProfiles = ref([])
const selectedFormulaProfile = ref({ id: "default-v1", revision: 1 })
const formulaTraceIndex = ref(0)
const compatibilityResults = ref([])
const compatibilityLoading = ref(false)
const previousPage = ref("design")
let crawlTimer = null
let compatibilityRequest = 0

const requirement = ref({
  application: "Terminal",
  direction: "Uplink",
  center_freq_ghz: 29.25,
  channel_bw_mhz: 20,
  target_throughput_mbps: 40,
  control_overhead: 0.18,
  fill_factor: 0.88704,
  altitude_km: 888,
  elevation_deg: 30,
  num_beams: 1,
  antenna_gain_db: 34,
  receiver_nf_db: 2,
  coherent_gain_db: 28.5,
  sky_temperature_k: 30,
  atmospheric_loss_db: 1,
  scintillation_loss_db: 0,
  rain_loss_db: 0,
  bf_error_db: 0.5,
  nonlinear_snr_db: 28,
  max_slant_nonlinear_snr_db: 28,
  if_freq_ghz: 4,
  output_backoff_db: 3,
  tx_input_power_dbm: -20,
})

const categories = computed(() => ["ALL", ...new Set(components.value.map((item) => item.category))].sort())
const filteredComponents = computed(() => components.value.filter((item) => {
  const matchesCategory = category.value === "ALL" || item.category === category.value
  const query = componentSearch.value.trim().toLowerCase()
  return matchesCategory && (!query || `${item.category} ${item.manufacturer} ${item.part_no}`.toLowerCase().includes(query))
}))
const selectedCandidate = computed(() => result.value?.candidates?.[selectedCandidateIndex.value] ?? null)
const comparedCandidates = computed(() => comparedCandidateIndexes.value
  .map((index) => ({ index, candidate: result.value?.candidates?.[index] }))
  .filter((item) => item.candidate))
const comparisonStages = computed(() => {
  const stages = []
  for (const { candidate } of comparedCandidates.value) {
    for (const component of candidate.components) {
      if (!stages.includes(component.category)) stages.push(component.category)
    }
  }
  return stages
})
const requirementFunction = computed(() => {
  const application = requirement.value.application.toLowerCase()
  const direction   = requirement.value.direction.toLowerCase()
  if (["tx", "transmit"].includes(direction)) return "Tx"
  if (["rx", "receive"].includes(direction)) return "Rx"
  if (["ul", "uplink"].includes(direction)) return application === "terminal" ? "Tx" : "Rx"
  if (["dl", "downlink"].includes(direction)) return application === "terminal" ? "Rx" : "Tx"
  return requirement.value.direction
})
const pinStages = computed(() => requirementFunction.value === "Rx" ? [
  { key: "SWITCH", label: "스위치", categories: ["SWITCH"], optional: true },
  { key: "LNA", label: "LNA", categories: ["LNA", "FEM"] },
  { key: "BFIC", label: "BFIC", categories: ["BFIC"] },
  { key: "MIXER", label: "믹서", categories: ["MIXER"] },
  { key: "CONVERTER", label: "ADC / 변환기", categories: ["ADC", "CONVERTER"], optional: true },
  { key: "PLL", label: "PLL", categories: ["PLL"] },
] : [
  { key: "CONVERTER", label: "DAC / 변환기", categories: ["DAC", "CONVERTER"], optional: true },
  { key: "MIXER", label: "믹서", categories: ["MIXER"] },
  { key: "PLL", label: "PLL", categories: ["PLL"] },
  { key: "BFIC", label: "BFIC", categories: ["BFIC"] },
  { key: "PA", label: "PA", categories: ["PA", "FEM"] },
  { key: "SWITCH", label: "스위치", categories: ["SWITCH"], optional: true },
])
const wizardSteps = ["설계 유형", "요구사항", "수식 프로필", "선호 조건", "부품 선택", "검토 및 계산", "결과"]
const activePinStage = computed(() => pinStages.value[activePinStageIndex.value])
const selectedFormulaSummary = computed(() => formulaProfiles.value.find((item) => item.id === selectedFormulaProfile.value.id))
const selectedFormulaTrace = computed(() => selectedCandidate.value?.calculation_trace?.[formulaTraceIndex.value] ?? null)
const activeStageCompatibilityCounts = computed(() => {
  const counts = { PASS: 0, WARN: 0, UNKNOWN: 0, FAIL: 0 }
  if (!activePinStage.value) return counts
  for (const component of availableForStage(activePinStage.value)) {
    const status = compatibilityFor(component)?.status ?? "UNKNOWN"
    counts[status] += 1
  }
  return counts
})
const componentFields = computed(() => {
  const item = selectedComponent.value
  if (!item) return []
  return [
    ["적용 대상", displayApplication(item.application)],
    ["기능", item.function],
    ["등급", item.grade],
    ["주파수", frequencyRange(item)],
    ["공정", item.process],
    ["공급 전압", unitValue(item.supply_voltage_v, "V")],
    ["소비 전력", unitValue(item.power_consumption_w, "W")],
    ["패키지", item.package],
    ["동작 온도", temperatureRange(item)],
    ["데이터시트 개정", item.datasheet_revision],
    ["데이터시트 페이지", item.datasheet_page],
    ["추출 방식", item.extraction_method],
    ["비고", item.note],
  ].filter((entry) => entry[1] != null && entry[1] !== "")
})
const selectedComponentEvidence = computed(() => parseExtractionEvidence(selectedComponent.value?.extraction_evidence))
const componentSpecs = computed(() => Object.entries(selectedComponent.value?.specs ?? {})
  .filter((entry) => entry[1] != null && entry[1] !== "")
  .map(([key, value]) => [fieldLabel(key), unitValue(value, specificationUnit(key))]))
const calculationInputs = computed(() => {
  const input = result.value?.requirement
  if (!input) return []
  return [
    ["적용 대상", displayApplication(input.application)],
    ["방향", displayDirection(input.direction)],
    ["중심 주파수", input.center_freq_ghz, "GHz"],
    ["채널 대역폭", input.channel_bw_mhz, "MHz"],
    ["목표 처리량", input.target_throughput_mbps, "Mbps"],
    ["제어 오버헤드", input.control_overhead],
    ["자원 계수", input.fill_factor],
    ["빔 수", input.num_beams],
    ["정면 거리 / 고도", input.altitude_km, "km"],
    ["앙각", input.elevation_deg, "deg"],
    ["송신 안테나 이득", input.antenna_gain_db, "dBi"],
    ["급전 손실", input.feed_loss_db, "dB"],
    ["수신 잡음 지수", input.receiver_nf_db, "dB"],
    ["수신 코히어런트 이득", input.coherent_gain_db, "dB"],
    ["하늘 잡음 온도", input.sky_temperature_k, "K"],
    ["빔포밍 오차", input.bf_error_db, "dB"],
    ["대기 손실", input.atmospheric_loss_db, "dB"],
    ["신틸레이션 손실", input.scintillation_loss_db, "dB"],
    ["강우 감쇠", input.rain_loss_db, "dB"],
    ["비선형 SNR", input.nonlinear_snr_db, "dB"],
    ["최대 경사거리 비선형 SNR", input.max_slant_nonlinear_snr_db, "dB"],
    ["IF 주파수", input.if_freq_ghz, "GHz"],
    ["LO 경로 손실", input.lo_routing_loss_db, "dB"],
    ["출력 백오프", input.output_backoff_db, "dB"],
    ["송신 입력", input.tx_input_power_dbm, "dBm"],
    ["최대 EIRP 재정의", input.peak_eirp_dbw, "dBW"],
  ]
})
const crawlProgress = computed(() => {
  for (let index = crawlLogs.value.length - 1; index >= 0; index -= 1) {
    const match = crawlLogs.value[index].match(/^\[(\d+)\/(\d+)\]/)
    if (match) return { current: Number(match[1]), total: Number(match[2]) }
  }
  return null
})

async function loadInitialData() {
  try {
    const [config, inventory, savedPreferences, formulas] = await Promise.all([
      api("/api/config"),
      api("/api/components"),
      api("/api/preferences"),
      api("/api/formula-profiles"),
    ])
    requirement.value = config.default_requirement
    bands.value = config.bands
    components.value = inventory.components
    preferences.value = savedPreferences
    formulaProfiles.value = formulas.profiles
    restoreDraft()
    syncSelectedFormulaProfile()
  } catch (reason) {
    error.value = reason.message
  }
}

async function loadComponents() {
  const inventory = await api("/api/components")
  components.value = inventory.components
}

async function updateCrawlStatus(reset = false) {
  if (reset) {
    crawlLogs.value = []
    crawlOffset.value = 0
  }
  const previousState = crawlState.value
  const status = await api(`/api/crawl?after=${crawlOffset.value}`)
  crawlLogs.value.push(...status.logs)
  crawlOffset.value = status.next_offset
  crawlState.value = status.state
  crawlStartedAt.value = status.started_at
  crawlFinishedAt.value = status.finished_at
  await nextTick()
  if (terminal.value) terminal.value.scrollTop = terminal.value.scrollHeight
  if (status.state === "running") {
    startCrawlPolling()
  } else {
    stopCrawlPolling()
    if (status.state === "succeeded" && previousState === "running") {
      await loadComponents()
      if (wizardStep.value === 5) await loadCompatibility()
    }
  }
}

function startCrawlPolling() {
  if (crawlTimer) return
  crawlTimer = window.setInterval(() => {
    updateCrawlStatus().catch((reason) => {
      error.value = reason.message
      stopCrawlPolling()
    })
  }, 500)
}

function stopCrawlPolling() {
  if (!crawlTimer) return
  window.clearInterval(crawlTimer)
  crawlTimer = null
}

async function startCrawl() {
  error.value = ""
  try {
    const status = await api("/api/crawl", { method: "POST" })
    crawlLogs.value = status.logs
    crawlOffset.value = status.next_offset
    crawlState.value = status.state
    crawlStartedAt.value = status.started_at
    crawlFinishedAt.value = null
    startCrawlPolling()
    await nextTick()
    if (terminal.value) terminal.value.scrollTop = terminal.value.scrollHeight
  } catch (reason) {
    error.value = reason.message
  }
}

async function startCrawlFromComponents() {
  page.value = "crawl"
  if (crawlState.value !== "running") await startCrawl()
}

function openComponentWorkspace() {
  page.value = "components"
  category.value = "ALL"
  componentSearch.value = ""
  selectedComponent.value = null
}

function restartComponentSelection() {
  clearPins()
  stageDecisions.value = {}
  activePinStageIndex.value = 0
  pinSearch.value = ""
}

function openComponentSelection() {
  const alreadyOnComponentStep = wizardStep.value === 5
  page.value = "design"
  wizardStep.value = 5
  unlockedWizardStep.value = Math.max(unlockedWizardStep.value, 5)
  restartComponentSelection()
  if (alreadyOnComponentStep) loadCompatibility()
}

function crawlTime(value) {
  return value ? new Date(value).toLocaleString() : "-"
}

function applyBand() {
  const band = bands.value[`${requirement.value.application}-${requirement.value.direction}`]
  if (band) requirement.value.center_freq_ghz = (band[0] + band[1]) / 2
}

async function calculate() {
  loading.value = true
  error.value = ""
  result.value = null
  selectedCandidateIndex.value = 0
  selectedComponent.value = null
  comparedCandidateIndexes.value = []
  comparisonOpen.value = false
  compareMessage.value = ""
  try {
    result.value = await api("/api/designs", {
      method: "POST",
      body: JSON.stringify({
        requirement: requirement.value,
        pinned_components: pinnedComponents.value,
        formula_profile: selectedFormulaProfile.value,
      }),
    })
    if (result.value.candidates.length) selectCandidate(0)
    wizardStep.value = 7
    unlockedWizardStep.value = 7
    await nextTick()
    resultsPanel.value?.focus({ preventScroll: true })
    resultsPanel.value?.scrollIntoView({ behavior: "smooth", block: "start" })
  } catch (reason) {
    error.value = reason.message
  } finally {
    loading.value = false
  }
}

function chain(candidate) {
  return candidate.components.map((item) => `${item.category}: ${item.part_no}`).join(" → ")
}

function selectCandidate(index) {
  selectedCandidateIndex.value = index
  selectedStageIndex.value = 0
  selectedComponent.value = result.value?.candidates?.[index]?.components?.[0] ?? null
  formulaTraceIndex.value = 0
}

function selectStage(index) {
  selectedStageIndex.value = index
  selectedComponent.value = selectedCandidate.value?.components?.[index] ?? null
}

function moveCandidate(offset) {
  const next = selectedCandidateIndex.value + offset
  if (next >= 0 && next < (result.value?.candidates?.length ?? 0)) selectCandidate(next)
}

function moveStage(offset) {
  const next = selectedStageIndex.value + offset
  if (next >= 0 && next < (selectedCandidate.value?.components?.length ?? 0)) selectStage(next)
}

function componentKey(item) {
  return { category: item.category, manufacturer: item.manufacturer, part_no: item.part_no }
}

function componentToken(item) {
  return JSON.stringify(componentKey(item))
}

function sameComponent(left, right) {
  return left?.category.toLowerCase() === right?.category.toLowerCase()
    && left?.manufacturer.toLowerCase() === right?.manufacturer.toLowerCase()
    && left?.part_no.toLowerCase() === right?.part_no.toLowerCase()
}

function isFavoriteManufacturer(manufacturer) {
  return preferences.value.favorite_manufacturers.some((item) => item.toLowerCase() === manufacturer.toLowerCase())
}

function isFavoriteComponent(component) {
  return preferences.value.favorite_components.some((item) => sameComponent(item, component))
}

async function savePreferences() {
  preferences.value = await api("/api/preferences", {
    method: "PUT",
    body: JSON.stringify(preferences.value),
  })
}

async function toggleFavoriteManufacturer(manufacturer) {
  const index = preferences.value.favorite_manufacturers.findIndex((item) => item.toLowerCase() === manufacturer.toLowerCase())
  if (index >= 0) preferences.value.favorite_manufacturers.splice(index, 1)
  else preferences.value.favorite_manufacturers.push(manufacturer)
  try {
    await savePreferences()
  } catch (reason) {
    error.value = reason.message
  }
}

async function toggleFavoriteComponent(component) {
  const index = preferences.value.favorite_components.findIndex((item) => sameComponent(item, component))
  if (index >= 0) preferences.value.favorite_components.splice(index, 1)
  else preferences.value.favorite_components.push(componentKey(component))
  try {
    await savePreferences()
  } catch (reason) {
    error.value = reason.message
  }
}

function pinnedForStage(stage) {
  return pinnedComponents.value.find((item) => stage.categories.includes(item.category.toUpperCase())) ?? null
}

function availableForStage(stage) {
  const query = pinSearch.value.trim().toLowerCase()
  const current = pinnedForStage(stage)
  return components.value.filter((item) => {
    if (!stage.categories.includes(item.category.toUpperCase())) return false
    if (current && sameComponent(current, item)) return true
    return !query || `${item.manufacturer} ${item.part_no}`.toLowerCase().includes(query)
  }).sort((left, right) => {
    const statusOrder = { PASS: 0, WARN: 1, UNKNOWN: 2, FAIL: 3 }
    const leftStatus  = compatibilityFor(left)?.status ?? "UNKNOWN"
    const rightStatus = compatibilityFor(right)?.status ?? "UNKNOWN"
    const statusDifference = statusOrder[leftStatus] - statusOrder[rightStatus]
    if (statusDifference) return statusDifference
    const favoriteDifference = Number(isFavoriteComponent(right)) - Number(isFavoriteComponent(left))
    if (favoriteDifference) return favoriteDifference
    return `${left.manufacturer} ${left.part_no}`.localeCompare(`${right.manufacturer} ${right.part_no}`)
  })
}

function compatibilityFor(component) {
  return compatibilityResults.value.find((item) => sameComponent(item.component, component)) ?? null
}

function compatibilityReason(component) {
  const compatibility = compatibilityFor(component)
  if (!compatibility) return "호환성 정보를 확인하는 중입니다."
  const notable = compatibility.checks.find((check) => check.status !== "PASS")
  return notable?.message ?? "현재 요구사항의 필수 조건을 모두 만족합니다."
}

function selectPinnedComponent(stage, component) {
  stageDecisions.value[stage.key] = "pinned"
  setPinnedStage(stage, componentToken(component))
}

async function loadCompatibility() {
  const requestId = ++compatibilityRequest
  compatibilityLoading.value = true
  try {
    const response = await api("/api/compatibility", {
      method: "POST",
      body: JSON.stringify(requirement.value),
    })
    if (requestId === compatibilityRequest) compatibilityResults.value = response.results
  } catch (reason) {
    if (requestId === compatibilityRequest) error.value = reason.message
  } finally {
    if (requestId === compatibilityRequest) compatibilityLoading.value = false
  }
}

function setPinnedStage(stage, token) {
  pinnedComponents.value = pinnedComponents.value.filter((item) => !stage.categories.includes(item.category.toUpperCase()))
  if (token) pinnedComponents.value.push(JSON.parse(token))
}

function clearPins() {
  pinnedComponents.value = []
  pinSearch.value = ""
}

function openWizardStep(step) {
  if (step <= unlockedWizardStep.value) wizardStep.value = step
}

function advanceWizard() {
  if (wizardStep.value === 2 && designForm.value && !designForm.value.reportValidity()) return
  const next = Math.min(wizardStep.value + 1, 6)
  wizardStep.value = next
  unlockedWizardStep.value = Math.max(unlockedWizardStep.value, next)
}

function previousWizardStep() {
  wizardStep.value = Math.max(1, wizardStep.value - 1)
}

function chooseStageDecision(mode) {
  const stage = activePinStage.value
  if (!stage) return
  stageDecisions.value[stage.key] = mode
  if (mode === "auto") setPinnedStage(stage, "")
}

function advancePinStage() {
  const stage = activePinStage.value
  if (!stageDecisions.value[stage.key]) stageDecisions.value[stage.key] = pinnedForStage(stage) ? "pinned" : "auto"
  if (activePinStageIndex.value < pinStages.value.length - 1) {
    activePinStageIndex.value += 1
  } else {
    wizardStep.value = 6
    unlockedWizardStep.value = Math.max(unlockedWizardStep.value, 6)
  }
}

function resetDesign() {
  localStorage.removeItem(DESIGN_DRAFT_KEY)
  result.value = null
  pinnedComponents.value = []
  stageDecisions.value = {}
  activePinStageIndex.value = 0
  wizardStep.value = 1
  unlockedWizardStep.value = 1
}

function selectFormulaProfile(profileId) {
  const profile = formulaProfiles.value.find((item) => item.id === profileId)
  if (!profile) return
  selectedFormulaProfile.value = { id: profile.id, revision: profile.revision }
  result.value = null
}

function syncSelectedFormulaProfile(updatedProfiles = formulaProfiles.value) {
  formulaProfiles.value = updatedProfiles
  const profile = updatedProfiles.find((item) => item.id === selectedFormulaProfile.value.id)
    ?? updatedProfiles.find((item) => item.id === "default-v1")
  if (profile) selectedFormulaProfile.value = { id: profile.id, revision: profile.revision }
}

function restoreDraft() {
  try {
    const saved = parseDesignDraft(localStorage.getItem(DESIGN_DRAFT_KEY))
    if (!saved) return
    requirement.value = { ...requirement.value, ...saved.requirement }
    pinnedComponents.value = saved.pinnedComponents ?? []
    stageDecisions.value = saved.stageDecisions ?? {}
    selectedFormulaProfile.value = saved.formulaProfile ?? selectedFormulaProfile.value
    wizardStep.value = Math.min(saved.wizardStep ?? 1, 6)
    unlockedWizardStep.value = Math.min(saved.unlockedWizardStep ?? 1, 6)
  } catch {
    localStorage.removeItem(DESIGN_DRAFT_KEY)
  }
}

let draftTimer = null
function scheduleDraftSave() {
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(() => {
    localStorage.setItem(DESIGN_DRAFT_KEY, serializeDesignDraft({
      requirement: requirement.value,
      pinnedComponents: pinnedComponents.value,
      stageDecisions: stageDecisions.value,
      formulaProfile: selectedFormulaProfile.value,
      wizardStep: Math.min(wizardStep.value, 6),
      unlockedWizardStep: Math.min(unlockedWizardStep.value, 6),
      savedAt: new Date().toISOString(),
    }))
  }, 300)
}

function isCompared(index) {
  return comparedCandidateIndexes.value.includes(index)
}

function toggleComparison(index) {
  compareMessage.value = ""
  if (isCompared(index)) {
    comparedCandidateIndexes.value = comparedCandidateIndexes.value.filter((item) => item !== index)
    return
  }
  if (comparedCandidateIndexes.value.length >= 5) {
    compareMessage.value = "후보는 최대 5개까지 비교할 수 있습니다."
    return
  }
  comparedCandidateIndexes.value.push(index)
}

function candidateComponent(candidate, stage) {
  return candidate.components.find((item) => item.category === stage)
}

function csvCell(value) {
  let content = value == null ? "" : String(value)
  if (/^[=+\-@]/.test(content)) content = `'${content}`
  return `"${content.replaceAll('"', '""')}"`
}

function comparisonCsv() {
  const inputHeaders = ["적용 대상", "방향", "중심 주파수 GHz", "채널 대역폭 MHz", "목표 처리량 Mbps"]
  const metricHeaders = result.value.function === "Tx"
    ? ["상태", "선호 점수", "링크 마진 dB", "선형 EIRP dBW", "최대 처리량 Mbps", "최소 처리량 Mbps", "소비 전력 W"]
    : ["선호 점수", "잡음 지수 dB", "이득 dB", "소비 전력 W"]
  const stageHeaders = comparisonStages.value.flatMap((stage) => [`${stage} 제조사`, `${stage} 부품 번호`])
  const headers = ["순위", ...inputHeaders, ...metricHeaders, ...stageHeaders]
  const rows = comparedCandidates.value.map(({ index, candidate }) => {
    const inputs = [
      displayApplication(result.value.requirement.application),
      displayDirection(result.value.requirement.direction),
      result.value.requirement.center_freq_ghz,
      result.value.requirement.channel_bw_mhz,
      result.value.requirement.target_throughput_mbps,
    ]
    const metrics = result.value.function === "Tx" ? [
      statusLabel(candidate.status),
      candidate.preference_score,
      candidate.link_budget?.link_margin_db,
      candidate.eirp_dbw,
      candidate.link_budget?.max_throughput_mbps,
      candidate.link_budget?.min_throughput_mbps,
      candidate.total_power_w,
    ] : [candidate.preference_score, candidate.total_nf_db, candidate.total_gain_db, candidate.total_power_w]
    const stages = comparisonStages.value.flatMap((stage) => {
      const component = candidateComponent(candidate, stage)
      return [component?.manufacturer, component?.part_no]
    })
    return [index + 1, ...inputs, ...metrics, ...stages]
  })
  return `\uFEFF${[headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n")}\r\n`
}

async function exportComparison() {
  if (!comparedCandidates.value.length) return
  try {
    if (!window.desktop?.exportCsv) throw new Error("CSV 내보내기는 Electron 앱에서만 사용할 수 있습니다.")
    const outcome = await window.desktop.exportCsv({
      defaultName: `rf-candidate-comparison-${new Date().toISOString().slice(0, 10)}.csv`,
      content: comparisonCsv(),
    })
    if (outcome?.error) throw new Error(outcome.error)
  } catch (reason) {
    error.value = reason.message
  }
}

function fieldLabel(key) {
  const acronyms = { adc: "ADC", bfic: "BFIC", db: "dB", dbm: "dBm", dbc: "dBc", enob: "ENOB", evm: "EVM", ghz: "GHz", if: "IF", iip3: "IIP3", lna: "LNA", lo: "LO", mhz: "MHz", nf: "NF", oip3: "OIP3", p1db: "P1dB", pa: "PA", pae: "PAE", pll: "PLL", psat: "Psat", rf: "RF", rms: "RMS", sfdr: "SFDR", sinad: "SINAD", snr: "SNR" }
  const words = { analog: "아날로그", bandwidth: "대역폭", beams: "빔", channel: "채널", channels: "채널", consumption: "소비", error: "오차", figure: "지수", frequency: "주파수", gain: "이득", input: "입력", insertion: "삽입", loss: "손실", max: "최대", min: "최소", noise: "잡음", number: "수", output: "출력", phase: "위상", power: "전력", sampling: "샘플링", supply: "공급", voltage: "전압" }
  return key.split("_").map((word) => acronyms[word] ?? words[word] ?? word).join(" ")
}

function parseExtractionEvidence(value) {
  if (!value) return []
  try {
    const parsed = typeof value === "string" ? JSON.parse(value) : value
    const items  = Array.isArray(parsed) ? parsed : [parsed]
    return items.filter((item) => item && typeof item === "object").map((item) => ({
      field: item.field ?? "-",
      value: item.value,
      unit: item.unit ?? "",
      page: item.page,
      evidence: item.evidence ?? "",
      confidence: item.confidence ?? "REVIEW_REQUIRED",
    }))
  } catch {
    return [{ field: "원문", value: null, unit: "", page: null, evidence: String(value), confidence: "UNKNOWN" }]
  }
}

function confidenceLabel(value) {
  return { VERIFIED: "검증됨", HIGH: "신뢰 높음", REVIEW_REQUIRED: "검토 필요", UNKNOWN: "확인 필요" }[value] ?? value
}

function displayApplication(value) {
  return { Terminal: "단말", Payload: "탑재체", Common: "공통" }[value] ?? value
}

function displayDirection(value) {
  return { Uplink: "상향 링크", Downlink: "하향 링크", Tx: "송신", Rx: "수신" }[value] ?? value
}

function statusLabel(value) {
  return { PASS: "통과", WARN: "주의", FAIL: "실패", UNKNOWN: "확인 필요" }[value] ?? value
}

function crawlStateLabel(value) {
  return { idle: "대기", running: "수집 중", succeeded: "완료", failed: "실패" }[value] ?? value
}

function specificationUnit(key) {
  if (key.endsWith("_ghz")) return "GHz"
  if (key.endsWith("_gsps")) return "GSPS"
  if (key.endsWith("_dbm")) return "dBm"
  if (key.endsWith("_dbc")) return "dBc"
  if (key.endsWith("_db")) return "dB"
  if (key.endsWith("_deg")) return "deg"
  if (key.endsWith("_percent")) return "%"
  if (key.endsWith("_bit")) return "bit"
  return ""
}

function unitValue(value, unit) {
  return value == null ? null : `${value}${unit ? ` ${unit}` : ""}`
}

function frequencyRange(item) {
  if (item.freq_min_ghz == null && item.freq_max_ghz == null) return null
  return `${item.freq_min_ghz ?? "?"}–${item.freq_max_ghz ?? "?"} GHz`
}

function temperatureRange(item) {
  if (item.operating_temp_min_c == null && item.operating_temp_max_c == null) return null
  return `${item.operating_temp_min_c ?? "?"}–${item.operating_temp_max_c ?? "?"} °C`
}

function number(value, digits = 2) {
  return value == null ? "-" : Number(value).toFixed(digits)
}

function inputValue(value, unit) {
  if (value == null) return "-"
  return unit ? `${value} ${unit}` : value
}

function openHelp() {
  if (page.value !== "help") previousPage.value = page.value
  page.value = "help"
}

function closeHelp() {
  page.value = previousPage.value
}

function navigateFromHelp(destination) {
  previousPage.value = destination
  page.value = destination
  if (destination === "components") openComponentWorkspace()
}

function handleGlobalKeydown(event) {
  if (event.key === "F1") {
    event.preventDefault()
    openHelp()
  } else if (event.key === "Escape" && page.value === "help") {
    closeHelp()
  } else if (event.key === "/" && page.value === "help") {
    event.preventDefault()
    document.querySelector(".help-search input")?.focus()
  }
}

onMounted(async () => {
  window.addEventListener("keydown", handleGlobalKeydown)
  await Promise.all([loadInitialData(), updateCrawlStatus(true)])
})
watch(requirementFunction, () => {
  clearPins()
  stageDecisions.value = {}
  activePinStageIndex.value = 0
  result.value = null
}, { flush: "sync" })
watch([requirement, pinnedComponents, stageDecisions, selectedFormulaProfile, wizardStep, unlockedWizardStep], scheduleDraftSave, { deep: true })
watch(wizardStep, (step) => {
  if (step === 5) loadCompatibility()
})
onBeforeUnmount(() => {
  window.removeEventListener("keydown", handleGlobalKeydown)
  stopCrawlPolling()
  window.clearTimeout(draftTimer)
})
</script>

<template>
  <header class="app-titlebar">
    <div class="titlebar-product">
      <span class="app-mark">RF</span>
      <h1>Ka-대역 RF 설계 도구</h1>
    </div>
  </header>

  <nav class="activity-bar" aria-label="주요 화면">
    <button :class="{ active: page === 'design' }" title="체인 설계" aria-label="체인 설계" @click="page = 'design'">
      <span class="activity-icon">◇</span><span class="activity-label">체인 설계</span>
    </button>
    <button :class="{ active: page === 'formulas' }" title="수식 프로필" aria-label="수식 프로필" @click="page = 'formulas'">
      <span class="activity-icon formula-icon">ƒx</span><span class="activity-label">수식 프로필</span>
    </button>
    <button :class="{ active: page === 'components' }" title="부품 탐색" aria-label="부품 탐색" @click="openComponentWorkspace">
      <span class="activity-icon">▦</span><span class="activity-label">부품 탐색</span>
    </button>
    <button :class="{ active: page === 'crawl' }" title="데이터 수집" aria-label="데이터 수집" @click="page = 'crawl'">
      <span class="activity-icon">↻</span><span class="activity-label">데이터 수집</span>
    </button>
    <button class="help-activity" :class="{ active: page === 'help' }" title="Help (F1)" aria-label="Help" @click="openHelp">
      <span class="activity-icon help-icon">?</span><span class="activity-label">Help</span>
    </button>
  </nav>

  <main>
    <p v-if="error" class="alert error">{{ error }}</p>

    <template v-if="page === 'design'">
      <div class="wizard-shell">
        <aside class="wizard-steps" aria-label="설계 단계">
          <div class="wizard-brand"><strong>설계 절차</strong><button type="button" @click="resetDesign">새 설계</button></div>
          <button
            v-for="(step, index) in wizardSteps"
            :key="step"
            type="button"
            :class="{ active: wizardStep === index + 1, complete: unlockedWizardStep > index + 1 }"
            :disabled="index + 1 > unlockedWizardStep"
            @click="openWizardStep(index + 1)"
          >
            <span>{{ unlockedWizardStep > index + 1 ? "✓" : index + 1 }}</span>
            {{ step }}
          </button>
          <section class="design-summary">
            <h3>설계 요약</h3>
            <dl>
              <div><dt>기능</dt><dd>{{ requirementFunction }}</dd></div>
              <div><dt>적용 대상</dt><dd>{{ displayApplication(requirement.application) }}</dd></div>
              <div><dt>주파수</dt><dd>{{ requirement.center_freq_ghz }} GHz</dd></div>
              <div><dt>대역폭</dt><dd>{{ requirement.channel_bw_mhz }} MHz</dd></div>
              <div><dt>수식</dt><dd>{{ selectedFormulaSummary?.name ?? "기본 프로필 v1" }}</dd></div>
              <div><dt>고정 부품</dt><dd>{{ pinnedComponents.length }}</dd></div>
            </dl>
          </section>
        </aside>

        <div class="wizard-content">
      <section v-if="wizardStep <= 6" class="panel wizard-panel">
        <div class="section-title">
          <div class="section-heading">
            <h2>{{ wizardSteps[wizardStep - 1] }}</h2>
            <p v-if="wizardStep === 2"><span class="input-key"></span>필수 입력 항목은 옅은 노란색으로 표시됩니다.</p>
          </div>
          <button v-if="wizardStep === 2" class="secondary" @click="applyBand">ESA 대역 중심값 적용</button>
        </div>

        <form ref="designForm" class="form-grid" @submit.prevent="calculate">
          <template v-if="wizardStep === 1">
          <label class="key-input required-input">적용 대상
            <select v-model="requirement.application" required>
              <option value="Terminal">단말</option>
              <option value="Payload">탑재체</option>
            </select>
          </label>
          <label class="key-input required-input">링크 방향
            <select v-model="requirement.direction" required>
              <option value="Uplink">상향 링크</option>
              <option value="Downlink">하향 링크</option>
              <option value="Tx">송신</option>
              <option value="Rx">수신</option>
            </select>
          </label>
          </template>
          <template v-if="wizardStep === 2">
          <label class="key-input required-input">중심 주파수 (GHz)<input v-model.number="requirement.center_freq_ghz" required type="number" step="0.001" min="0.001" /></label>
          <label class="key-input required-input">채널 대역폭 (MHz)<input v-model.number="requirement.channel_bw_mhz" required type="number" step="0.001" min="0.001" /></label>
          <label class="key-input required-input">목표 처리량 (Mbps)<input v-model.number="requirement.target_throughput_mbps" required type="number" step="1" min="0" /></label>
          <label class="key-input required-input">빔 수<input v-model.number="requirement.num_beams" required type="number" step="1" min="1" /></label>
          <label class="key-input required-input">정면 거리 / 고도 (km)<input v-model.number="requirement.altitude_km" required type="number" step="0.001" min="0.001" /></label>
          <label class="key-input required-input">앙각 (deg)<input v-model.number="requirement.elevation_deg" required type="number" step="1" min="0" max="90" /></label>
          <details class="advanced-settings">
            <summary>고급 설정</summary>
            <div class="advanced-grid">
          <label>제어 오버헤드 (비율)<input v-model.number="requirement.control_overhead" type="number" step="0.01" min="0" max="0.99" /></label>
          <label>자원 계수 η<input v-model.number="requirement.fill_factor" type="number" step="0.00001" min="0.00001" /></label>
          <label>송신 안테나 이득 (dBi)<input v-model.number="requirement.antenna_gain_db" type="number" step="0.1" /></label>
          <label>수신 잡음 지수 (dB)<input v-model.number="requirement.receiver_nf_db" type="number" step="0.1" min="0" /></label>
          <label>수신 코히어런트 이득 (dB)<input v-model.number="requirement.coherent_gain_db" type="number" step="0.1" /></label>
          <label>하늘 잡음 온도 (K)<input v-model.number="requirement.sky_temperature_k" type="number" step="1" min="0" /></label>
          <label>빔포밍 오차 (dB)<input v-model.number="requirement.bf_error_db" type="number" step="0.1" min="0" /></label>
          <label>대기 손실 (dB)<input v-model.number="requirement.atmospheric_loss_db" type="number" step="0.1" min="0" /></label>
          <label>신틸레이션 손실 (dB)<input v-model.number="requirement.scintillation_loss_db" type="number" step="0.1" min="0" /></label>
          <label>강우 감쇠 (dB)<input v-model.number="requirement.rain_loss_db" type="number" step="0.1" min="0" /></label>
          <label>비선형 SNR (dB)<input v-model.number="requirement.nonlinear_snr_db" type="number" step="0.1" /></label>
          <label>최대 경사거리 비선형 SNR (dB)<input v-model.number="requirement.max_slant_nonlinear_snr_db" type="number" step="0.1" /></label>
          <label>IF 주파수 (GHz)<input v-model.number="requirement.if_freq_ghz" type="number" step="0.1" min="0" /></label>
          <label>출력 백오프 (dB)<input v-model.number="requirement.output_backoff_db" type="number" step="0.1" min="0" /></label>
          <label>송신 입력 (dBm)<input v-model.number="requirement.tx_input_power_dbm" type="number" step="0.1" /></label>
            </div>
          </details>
          </template>
        </form>

        <section v-if="wizardStep === 3" class="wizard-choice-panel">
          <label>수식 프로필
            <select :value="selectedFormulaProfile.id" @change="selectFormulaProfile($event.target.value)">
              <option v-for="profile in formulaProfiles" :key="profile.id" :value="profile.id">
                {{ profile.name }} — 개정 {{ profile.revision }}
              </option>
            </select>
          </label>
          <article v-if="selectedFormulaSummary" class="selection-summary">
            <strong>{{ selectedFormulaSummary.name }}</strong>
            <span>{{ selectedFormulaSummary.description }}</span>
            <small>개정 {{ selectedFormulaSummary.revision }}{{ selectedFormulaSummary.built_in ? " · 기본 제공" : "" }}</small>
          </article>
          <button type="button" @click="page = 'formulas'">수식 프로필 관리 열기</button>
        </section>

        <section v-if="wizardStep === 4" class="wizard-choice-panel">
          <p>선호 조건은 선택 사항이며, 호환 부품을 제외하지 않고 후보 순위에만 반영됩니다.</p>
          <div class="preference-counts">
            <article><strong>{{ preferences.favorite_manufacturers.length }}</strong><span>선호 제조사</span></article>
            <article><strong>{{ preferences.favorite_components.length }}</strong><span>선호 부품</span></article>
          </div>
          <button type="button" @click="page = 'components'">선호 조건 관리</button>
        </section>

        <section v-if="wizardStep === 5 && activePinStage" class="pin-panel" aria-labelledby="pinned-components-title">
          <div class="pin-heading">
            <div>
              <span class="count">RF 단계 {{ activePinStageIndex + 1 }} / {{ pinStages.length }}</span>
              <h3 id="pinned-components-title">{{ activePinStage.label }}</h3>
              <p>자동 선택을 사용하거나 호환되는 특정 부품 하나를 고정할 수 있습니다.</p>
              <p v-if="compatibilityLoading" class="compatibility-note">현재 요구사항에 대한 부품 호환성을 확인하는 중…</p>
            </div>
            <div class="pin-actions">
              <span v-if="activePinStage.optional" class="optional">선택 단계</span>
              <button type="button" @click="restartComponentSelection">선택 처음부터</button>
              <button type="button" @click="startCrawlFromComponents">최신 데이터 수집</button>
            </div>
          </div>
          <label class="pin-search">부품 찾기
            <input v-model="pinSearch" type="search" placeholder="제조사 또는 부품 번호" />
          </label>
          <div class="compatibility-counts" aria-label="호환성 요약">
            <span class="pass">통과 {{ activeStageCompatibilityCounts.PASS }}</span>
            <span class="warn">주의 {{ activeStageCompatibilityCounts.WARN }}</span>
            <span class="unknown">확인 필요 {{ activeStageCompatibilityCounts.UNKNOWN }}</span>
            <span class="fail">호환 불가 {{ activeStageCompatibilityCounts.FAIL }}</span>
          </div>
          <div class="part-choice-list">
            <button
              type="button"
              class="part-choice auto-choice"
              :class="{ selected: stageDecisions[activePinStage.key] === 'auto' }"
              @click="chooseStageDecision('auto')"
            >
              <span class="choice-radio" aria-hidden="true"></span>
              <span class="part-choice-main">
                <strong>자동 선택 <small>권장</small></strong>
                <span>호환성, 선호 조건, 성능 마진과 소비 전력을 기준으로 가장 적합한 조합을 계산합니다.</span>
              </span>
            </button>
            <button
              v-for="item in availableForStage(activePinStage)"
              :key="componentToken(item)"
              type="button"
              class="part-choice"
              :class="[
                compatibilityFor(item)?.status?.toLowerCase() ?? 'unknown',
                { selected: pinnedForStage(activePinStage) && sameComponent(pinnedForStage(activePinStage), item) },
              ]"
              :disabled="compatibilityFor(item)?.status === 'FAIL'"
              @click="selectPinnedComponent(activePinStage, item)"
            >
              <span class="choice-radio" aria-hidden="true"></span>
              <span class="part-choice-main">
                <span class="part-choice-title">
                  <strong>{{ item.manufacturer }} <b>{{ item.part_no }}</b></strong>
                  <span v-if="isFavoriteManufacturer(item.manufacturer) || isFavoriteComponent(item)" class="favorite-tag">★ 선호</span>
                </span>
                <span class="part-choice-specs">
                  <span>{{ frequencyRange(item) ?? "주파수 정보 없음" }}</span>
                  <span>{{ item.grade || "등급 정보 없음" }}</span>
                  <span>{{ item.power_consumption_w == null ? "전력 정보 없음" : `${item.power_consumption_w} W` }}</span>
                </span>
                <span class="part-choice-reason">{{ compatibilityReason(item) }}</span>
              </span>
              <span class="status-badge" :class="compatibilityFor(item)?.status?.toLowerCase() ?? 'unknown'">
                {{ statusLabel(compatibilityFor(item)?.status ?? "UNKNOWN") }}
              </span>
            </button>
            <p v-if="!compatibilityLoading && !availableForStage(activePinStage).length" class="empty-parts">검색 조건에 맞는 부품이 없습니다.</p>
          </div>
          <div class="stage-progress">
            <button v-for="(stage, index) in pinStages" :key="stage.key" type="button" :title="stage.label" :class="{ active: index === activePinStageIndex, complete: stageDecisions[stage.key] }" @click="activePinStageIndex = index">{{ index + 1 }}</button>
          </div>
          <button class="primary" type="button" :disabled="stageDecisions[activePinStage.key] === 'pinned' && !pinnedForStage(activePinStage)" @click="advancePinStage">
            {{ activePinStageIndex === pinStages.length - 1 ? "부품 선택 완료" : "다음 RF 단계" }}
          </button>
        </section>

        <section v-if="wizardStep === 6" class="review-grid">
          <article><span>설계</span><strong>{{ displayApplication(requirement.application) }} · {{ displayDirection(requirement.direction) }} · {{ requirementFunction }}</strong><button type="button" @click="wizardStep = 1">수정</button></article>
          <article><span>요구사항</span><strong>{{ requirement.center_freq_ghz }} GHz · {{ requirement.channel_bw_mhz }} MHz · {{ requirement.target_throughput_mbps }} Mbps</strong><button type="button" @click="wizardStep = 2">수정</button></article>
          <article><span>수식 프로필</span><strong>{{ selectedFormulaSummary?.name }} · 개정 {{ selectedFormulaProfile.revision }}</strong><button type="button" @click="wizardStep = 3">수정</button></article>
          <article><span>선호 조건</span><strong>제조사 {{ preferences.favorite_manufacturers.length }}개 · 부품 {{ preferences.favorite_components.length }}개</strong><button type="button" @click="wizardStep = 4">수정</button></article>
          <article><span>고정 부품</span><strong>{{ pinnedComponents.length ? pinnedComponents.map((item) => item.part_no).join(", ") : "자동 선택" }}</strong><button type="button" @click="wizardStep = 5">수정</button></article>
          <button class="primary calculate-button" type="button" :disabled="loading" @click="calculate">{{ loading ? "계산 중…" : "RF 체인 계산" }}</button>
        </section>

        <footer v-if="wizardStep < 5" class="wizard-footer">
          <button type="button" :disabled="wizardStep === 1" @click="previousWizardStep">이전</button>
          <button class="primary" type="button" @click="advanceWizard">다음</button>
        </footer>
        <footer v-else-if="wizardStep === 5" class="wizard-footer">
          <button type="button" @click="previousWizardStep">이전</button>
        </footer>
        <footer v-else-if="wizardStep === 6" class="wizard-footer">
          <button type="button" @click="previousWizardStep">이전</button>
        </footer>
      </section>

      <section v-if="wizardStep === 7 && result" ref="resultsPanel" class="panel results" tabindex="-1">
        <div class="section-title">
          <div>
            <h2>{{ selectedCandidate ? `후보 ${selectedCandidateIndex + 1}` : "후보 없음" }}</h2>
          </div>
          <div class="candidate-navigation">
            <button type="button" :disabled="selectedCandidateIndex === 0" @click="moveCandidate(-1)">이전 후보</button>
            <span class="count">{{ selectedCandidate ? `${selectedCandidateIndex + 1} / ${result.returned_candidates}` : `${result.evaluated_candidates}개 평가됨` }}</span>
            <button type="button" :disabled="selectedCandidateIndex >= result.returned_candidates - 1" @click="moveCandidate(1)">다음 후보</button>
          </div>
        </div>

        <p v-for="warning in result.warnings" :key="warning" class="alert warning">{{ warning }}</p>

        <template v-if="selectedCandidate">
          <section class="result-overview">
            <div>
              <span class="eyebrow">추천 후보 {{ selectedCandidateIndex + 1 }}</span>
              <h3>{{ result.function === "Tx" ? "송신 RF 체인" : "수신 RF 체인" }}</h3>
              <p>{{ selectedCandidate.components.length }}개 부품 · {{ result.formula_profile.name }} 개정 {{ result.formula_profile.revision }}</p>
            </div>
            <span v-if="result.function === 'Tx'" class="result-status" :class="selectedCandidate.status.toLowerCase()">
              {{ statusLabel(selectedCandidate.status) }}
            </span>
          </section>
          <div v-if="result.function === 'Tx'" class="metrics primary-metrics">
            <article><span>링크 마진</span><strong>{{ number(selectedCandidate.link_budget?.link_margin_db) }} dB</strong></article>
            <article><span>최소 처리량</span><strong>{{ number(selectedCandidate.link_budget?.min_throughput_mbps) }} Mbps</strong></article>
            <article><span>빔당 선형 EIRP</span><strong>{{ number(selectedCandidate.eirp_dbw) }} dBW</strong></article>
            <article><span>소비 전력</span><strong>{{ number(selectedCandidate.total_power_w) }} W</strong></article>
          </div>
          <div v-else class="metrics primary-metrics">
            <article><span>전체 잡음 지수</span><strong>{{ number(selectedCandidate.total_nf_db) }} dB</strong></article>
            <article><span>전체 이득</span><strong>{{ number(selectedCandidate.total_gain_db) }} dB</strong></article>
            <article><span>소비 전력</span><strong>{{ number(selectedCandidate.total_power_w) }} W</strong></article>
          </div>
          <div class="chain" aria-label="선택한 RF 체인 부품">
            <button
              v-for="(item, index) in selectedCandidate.components"
              :key="item.component_id ?? `${item.category}-${item.part_no}`"
              class="chain-component"
              :class="{ active: selectedStageIndex === index }"
              type="button"
              @click="selectStage(index)"
            >
              <span>단계 {{ index + 1 }} · {{ item.category }}</span>
              <strong>{{ item.part_no }}</strong>
              <small>{{ item.manufacturer }}</small>
            </button>
          </div>

          <section v-if="selectedComponent" class="component-detail" aria-live="polite">
            <div class="component-detail-title">
              <div>
                <span>{{ selectedComponent.category }}</span>
                <h3>{{ selectedComponent.manufacturer }} {{ selectedComponent.part_no }}</h3>
              </div>
              <div class="stage-navigation">
                <button type="button" :disabled="selectedStageIndex === 0" @click="moveStage(-1)">이전 단계</button>
                <span>{{ selectedStageIndex + 1 }} / {{ selectedCandidate.components.length }}</span>
                <button type="button" :disabled="selectedStageIndex >= selectedCandidate.components.length - 1" @click="moveStage(1)">다음 단계</button>
              </div>
            </div>
            <div class="component-detail-grid">
              <table v-if="componentFields.length">
                <tbody><tr v-for="field in componentFields" :key="field[0]"><th>{{ field[0] }}</th><td>{{ field[1] }}</td></tr></tbody>
              </table>
              <table v-if="componentSpecs.length">
                <tbody><tr v-for="spec in componentSpecs" :key="spec[0]"><th>{{ spec[0] }}</th><td>{{ spec[1] }}</td></tr></tbody>
              </table>
            </div>
            <section v-if="selectedComponentEvidence.length" class="evidence-panel">
              <h4>데이터 추출 근거</h4>
              <div class="table-wrap">
                <table>
                  <thead><tr><th>항목</th><th>추출값</th><th>페이지</th><th>근거 문장</th><th>상태</th></tr></thead>
                  <tbody>
                    <tr v-for="(evidence, index) in selectedComponentEvidence" :key="`${evidence.field}-${index}`">
                      <td>{{ fieldLabel(evidence.field) }}</td>
                      <td><strong>{{ evidence.value ?? "-" }}</strong>{{ evidence.unit ? ` ${evidence.unit}` : "" }}</td>
                      <td>{{ evidence.page ?? "-" }}</td>
                      <td class="evidence-quote">{{ evidence.evidence || "근거 문장이 없습니다." }}</td>
                      <td><span class="review-badge" :class="evidence.confidence.toLowerCase()">{{ confidenceLabel(evidence.confidence) }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>
            <div class="component-links">
              <a v-if="selectedComponent.product_url" :href="selectedComponent.product_url" target="_blank" rel="noreferrer">제품 페이지</a>
              <a v-if="selectedComponent.datasheet_url" :href="selectedComponent.datasheet_url" target="_blank" rel="noreferrer">데이터시트</a>
            </div>
          </section>
          <div class="preference-summary">
            <strong>선호 점수 {{ selectedCandidate.preference_score }}</strong>
            <span v-if="selectedCandidate.preference_matches.length">{{ selectedCandidate.preference_matches.join(" · ") }}</span>
            <span v-else>이 후보에는 선호 제조사 또는 선호 부품이 없습니다.</span>
          </div>
          <details class="calculation-inputs">
            <summary>계산에 사용한 입력값</summary>
            <table>
              <tbody>
                <tr v-for="input in calculationInputs" :key="input[0]">
                  <th>{{ input[0] }}</th>
                  <td>{{ inputValue(input[1], input[2]) }}</td>
                </tr>
              </tbody>
            </table>
          </details>

          <details v-if="selectedFormulaTrace" class="calculation-trace">
            <summary>계산 근거 보기 · 수식 {{ selectedCandidate.calculation_trace.length }}개</summary>
            <div class="trace-title">
              <div><span>계산 {{ formulaTraceIndex + 1 }} / {{ selectedCandidate.calculation_trace.length }}</span><h3>{{ selectedFormulaTrace.label }}</h3></div>
              <div class="stage-navigation">
                <button type="button" :disabled="formulaTraceIndex === 0" @click="formulaTraceIndex -= 1">이전 수식</button>
                <button type="button" :disabled="formulaTraceIndex >= selectedCandidate.calculation_trace.length - 1" @click="formulaTraceIndex += 1">다음 수식</button>
              </div>
            </div>
            <code>{{ selectedFormulaTrace.expression }}</code>
            <div class="trace-values">
              <span v-for="input in selectedFormulaTrace.inputs" :key="input.symbol"><strong>{{ input.symbol }}</strong> = {{ number(input.value, 4) }} {{ input.unit }}</span>
            </div>
            <p><strong>결과:</strong> {{ number(selectedFormulaTrace.result, 4) }} {{ selectedFormulaTrace.unit }}</p>
          </details>

          <div class="comparison-actions">
            <div>
              <strong>비교 후보 {{ comparedCandidateIndexes.length }}개 선택됨</strong>
              <span v-if="compareMessage" class="inline-warning">{{ compareMessage }}</span>
            </div>
            <div>
              <button type="button" :disabled="!comparedCandidateIndexes.length" @click="comparisonOpen = !comparisonOpen">
                {{ comparisonOpen ? "비교 닫기" : "선택 후보 비교" }}
              </button>
              <button class="primary" type="button" :disabled="!comparedCandidateIndexes.length" @click="exportComparison">CSV 내보내기</button>
            </div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr><th>비교</th><th>순위</th><th>체인</th><th>선호 점수</th><th v-if="result.function === 'Tx'">상태</th><th>{{ result.function === "Tx" ? "링크 마진" : "잡음 지수" }}</th><th>소비 전력</th></tr></thead>
              <tbody>
                <tr v-for="(candidate, index) in result.candidates" :key="index" :class="{ selected: selectedCandidateIndex === index }">
                  <td><input class="compare-checkbox" type="checkbox" :checked="isCompared(index)" :aria-label="`후보 ${index + 1} 비교`" @change="toggleComparison(index)" /></td>
                  <td>{{ index + 1 }}</td>
                  <td><button class="candidate-link" type="button" @click="selectCandidate(index)">{{ chain(candidate) }}</button></td>
                  <td>{{ candidate.preference_score }}</td>
                  <td v-if="result.function === 'Tx'">{{ statusLabel(candidate.status) }}</td>
                  <td>{{ number(result.function === "Tx" ? candidate.link_budget?.link_margin_db : candidate.total_nf_db) }} dB</td>
                  <td>{{ number(candidate.total_power_w) }} W</td>
                </tr>
              </tbody>
            </table>
          </div>

          <section v-if="comparisonOpen && comparedCandidates.length" class="comparison-panel">
            <h3>후보 비교</h3>
            <div class="table-wrap">
              <table>
                <thead>
                  <tr><th>항목</th><th v-for="item in comparedCandidates" :key="item.index">후보 {{ item.index + 1 }}</th></tr>
                </thead>
                <tbody>
                  <tr><th>선호 점수</th><td v-for="item in comparedCandidates" :key="item.index">{{ item.candidate.preference_score }}</td></tr>
                  <tr v-if="result.function === 'Tx'"><th>상태</th><td v-for="item in comparedCandidates" :key="item.index">{{ statusLabel(item.candidate.status) }}</td></tr>
                  <tr><th>{{ result.function === "Tx" ? "링크 마진" : "잡음 지수" }}</th><td v-for="item in comparedCandidates" :key="item.index">{{ number(result.function === "Tx" ? item.candidate.link_budget?.link_margin_db : item.candidate.total_nf_db) }} dB</td></tr>
                  <tr v-if="result.function === 'Rx'"><th>이득</th><td v-for="item in comparedCandidates" :key="item.index">{{ number(item.candidate.total_gain_db) }} dB</td></tr>
                  <tr><th>소비 전력</th><td v-for="item in comparedCandidates" :key="item.index">{{ number(item.candidate.total_power_w) }} W</td></tr>
                  <tr v-for="stage in comparisonStages" :key="stage">
                    <th>{{ stage }}</th>
                    <td v-for="item in comparedCandidates" :key="item.index">
                      <template v-if="candidateComponent(item.candidate, stage)">
                        {{ candidateComponent(item.candidate, stage).manufacturer }}<br />
                        <strong>{{ candidateComponent(item.candidate, stage).part_no }}</strong>
                      </template>
                      <span v-else>—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </section>
        </div>

      </div>
    </template>

    <FormulaProfiles v-else-if="page === 'formulas'" @error="error = $event" @updated="syncSelectedFormulaProfile" />

    <HelpCenter v-else-if="page === 'help'" @close="closeHelp" @navigate="navigateFromHelp" />

    <section v-else-if="page === 'components'" class="panel">
      <div class="section-title">
        <div>
          <h2>부품</h2>
          <p class="section-description">선호 제조사와 특정 부품을 표시하면 후보 순위에 반영됩니다.</p>
        </div>
        <div class="component-filters">
          <input v-model="componentSearch" type="search" placeholder="제조사 또는 부품 검색" aria-label="부품 검색" />
          <select v-model="category" class="category"><option v-for="item in categories" :key="item">{{ item }}</option></select>
        </div>
      </div>
      <section class="component-workflow" aria-label="부품 데이터 사용 순서">
        <article class="workflow-step active">
          <span>1</span>
          <div><strong>데이터 최신화</strong><small>제조사 제품과 데이터시트를 수집합니다.</small></div>
          <button type="button" :disabled="crawlState === 'running'" @click="startCrawlFromComponents">
            {{ crawlState === "running" ? "수집 중" : "수집 시작" }}
          </button>
        </article>
        <article class="workflow-step">
          <span>2</span>
          <div><strong>부품 검토</strong><small>{{ components.length }}개 부품에서 선호 항목을 지정합니다.</small></div>
        </article>
        <article class="workflow-step">
          <span>3</span>
          <div><strong>조합 계산</strong><small>체인 설계의 부품 선택 단계에서 조합합니다.</small></div>
          <button type="button" @click="openComponentSelection">처음부터 선택</button>
        </article>
      </section>
      <div class="table-wrap">
        <table>
          <thead><tr><th>선호 제조사</th><th>선호 부품</th><th>분류</th><th>제조사</th><th>부품 번호</th><th>적용 대상</th><th>주파수</th><th>등급</th><th>출처</th></tr></thead>
          <tbody>
            <tr v-for="item in filteredComponents" :key="item.component_id">
              <td><button class="favorite-button" type="button" :class="{ active: isFavoriteManufacturer(item.manufacturer) }" :aria-label="`${item.manufacturer} 선호 여부 전환`" @click="toggleFavoriteManufacturer(item.manufacturer)">{{ isFavoriteManufacturer(item.manufacturer) ? "★" : "☆" }}</button></td>
              <td><button class="favorite-button" type="button" :class="{ active: isFavoriteComponent(item) }" :aria-label="`${item.part_no} 선호 여부 전환`" @click="toggleFavoriteComponent(item)">{{ isFavoriteComponent(item) ? "★" : "☆" }}</button></td>
              <td>{{ item.category }}</td><td>{{ item.manufacturer }}</td><td><button class="candidate-link" type="button" @click="selectedComponent = item">{{ item.part_no }}</button></td><td>{{ displayApplication(item.application) }}</td>
              <td>{{ number(item.freq_min_ghz, 1) }}–{{ number(item.freq_max_ghz, 1) }} GHz</td><td>{{ item.grade }}</td>
              <td><a v-if="item.datasheet_url" :href="item.datasheet_url" target="_blank" rel="noreferrer">데이터시트</a><span v-else>-</span></td>
            </tr>
          </tbody>
        </table>
      </div>
      <section v-if="selectedComponent" class="inventory-detail">
        <div class="component-detail-title">
          <div><span>{{ selectedComponent.category }}</span><h3>{{ selectedComponent.manufacturer }} {{ selectedComponent.part_no }}</h3></div>
          <button type="button" aria-label="상세 닫기" @click="selectedComponent = null">×</button>
        </div>
        <div class="component-detail-grid">
          <table v-if="componentFields.length"><tbody><tr v-for="field in componentFields" :key="field[0]"><th>{{ field[0] }}</th><td>{{ field[1] }}</td></tr></tbody></table>
          <table v-if="componentSpecs.length"><tbody><tr v-for="spec in componentSpecs" :key="spec[0]"><th>{{ spec[0] }}</th><td>{{ spec[1] }}</td></tr></tbody></table>
        </div>
        <section v-if="selectedComponentEvidence.length" class="evidence-panel">
          <h4>데이터 추출 근거</h4>
          <div class="table-wrap">
            <table>
              <thead><tr><th>항목</th><th>추출값</th><th>페이지</th><th>근거 문장</th><th>상태</th></tr></thead>
              <tbody><tr v-for="(evidence, index) in selectedComponentEvidence" :key="`${evidence.field}-${index}`"><td>{{ fieldLabel(evidence.field) }}</td><td><strong>{{ evidence.value ?? "-" }}</strong>{{ evidence.unit ? ` ${evidence.unit}` : "" }}</td><td>{{ evidence.page ?? "-" }}</td><td class="evidence-quote">{{ evidence.evidence || "근거 문장이 없습니다." }}</td><td><span class="review-badge" :class="evidence.confidence.toLowerCase()">{{ confidenceLabel(evidence.confidence) }}</span></td></tr></tbody>
            </table>
          </div>
        </section>
      </section>
    </section>

    <section v-else class="panel crawl-panel">
      <div class="section-title">
        <div>
          <h2>제조사 데이터 수집</h2>
        </div>
        <div class="crawl-actions">
          <span class="crawl-state" :class="crawlState">{{ crawlStateLabel(crawlState) }}</span>
          <button class="primary" type="button" :disabled="crawlState === 'running'" @click="startCrawl">
            {{ crawlState === "running" ? "수집 중…" : "수집 시작" }}
          </button>
        </div>
      </div>

      <p class="crawl-description">
        제조사의 공식 제품을 검색하고 데이터시트를 내려받아 사양을 추출한 뒤 부품 데이터베이스를 갱신합니다.
      </p>
      <div class="crawl-meta">
        <span>시작: {{ crawlTime(crawlStartedAt) }}</span>
        <span>종료: {{ crawlTime(crawlFinishedAt) }}</span>
        <span>부품 수: {{ components.length }}</span>
        <span v-if="crawlProgress">진행: {{ crawlProgress.current }} / {{ crawlProgress.total }}</span>
      </div>
      <div v-if="crawlState === 'running' && crawlProgress" class="crawl-progress" :aria-label="`데이터 수집 ${crawlProgress.current}/${crawlProgress.total}`">
        <span :style="{ width: `${crawlProgress.current / crawlProgress.total * 100}%` }"></span>
      </div>

      <div ref="terminal" class="terminal" role="log" aria-live="polite" aria-label="수집기 출력">
        <div class="terminal-bar"><span></span><span></span><span></span><strong>수집기 — 파이프라인 출력</strong></div>
        <pre v-if="crawlLogs.length">{{ crawlLogs.join("\n") }}</pre>
        <pre v-else class="terminal-empty">준비되었습니다. 수집 시작을 눌러 부품 파이프라인을 실행하세요.</pre>
      </div>
    </section>
  </main>

  <footer class="app-statusbar">
    <span>로컬 작업 공간</span>
    <span>{{ requirementFunction }} · {{ requirement.center_freq_ghz }} GHz</span>
    <span>{{ crawlState === "running" ? "데이터 수집 중" : "준비됨" }}</span>
  </footer>
</template>
