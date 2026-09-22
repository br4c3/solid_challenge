<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import katex from "katex"
import "katex/dist/katex.min.css"

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
let crawlTimer = null

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
const filteredComponents = computed(() =>
  category.value === "ALL" ? components.value : components.value.filter((item) => item.category === category.value),
)
const selectedCandidate = computed(() => result.value?.candidates?.[selectedCandidateIndex.value] ?? null)
const requirementFunction = computed(() => {
  const application = requirement.value.application.toLowerCase()
  const direction   = requirement.value.direction.toLowerCase()
  if (["tx", "transmit"].includes(direction)) return "Tx"
  if (["rx", "receive"].includes(direction)) return "Rx"
  if (["ul", "uplink"].includes(direction)) return application === "terminal" ? "Tx" : "Rx"
  if (["dl", "downlink"].includes(direction)) return application === "terminal" ? "Rx" : "Tx"
  return requirement.value.direction
})
const calculationEquations = computed(() => {
  if (requirementFunction.value === "Rx") {
    return [
      {
        title: "Cascaded Gain",
        latex: String.raw`G_{\mathrm{total,dB}}=\sum_{k=1}^{n}G_{k,\mathrm{dB}}`,
        description: "Adds the gain or loss of every selected receiver stage.",
      },
      {
        title: "Friis Noise Factor",
        latex: String.raw`F_{\mathrm{total}}=F_1+\sum_{k=2}^{n}\frac{F_k-1}{\prod_{i=1}^{k-1}G_i}`,
        description: "Combines each stage noise factor using preceding linear gain.",
      },
      {
        title: "Total Noise Figure",
        latex: String.raw`NF_{\mathrm{total,dB}}=10\log_{10}\!\left(F_{\mathrm{total}}\right),\quad F_k=10^{NF_{k,\mathrm{dB}}/10}`,
        description: "Converts component noise figures to linear factors, then returns the cascade result to dB.",
      },
    ]
  }
  return [
    {
      title: "Stage Output Power",
      latex: String.raw`P_{\mathrm{out},k}[\mathrm{dBm}]=P_{\mathrm{in},k}[\mathrm{dBm}]+G_k[\mathrm{dB}]`,
      description: "Propagates power through the selected Tx chain and checks each linear output limit.",
    },
    {
      title: "Slant Range",
      latex: String.raw`d=\sqrt{(R_E+h)^2-(R_E\cos e)^2}-R_E\sin e`,
      description: "Computes maximum slant range from altitude h and elevation e using spherical-Earth geometry.",
    },
    {
      title: "Free-space Path Loss",
      latex: String.raw`L_{\mathrm{FSPL}}[\mathrm{dB}]=92.45+20\log_{10}(f_{\mathrm{GHz}})+20\log_{10}(d_{\mathrm{km}})`,
      description: "Calculates propagation loss at boresight and maximum slant range.",
    },
    {
      title: "Linear EIRP per Beam",
      latex: String.raw`EIRP_{\mathrm{beam}}=P_{\mathrm{ant}}-30+G_{\mathrm{ant}}-L_{\mathrm{feed}}-10\log_{10}(N_{\mathrm{beams}})-OBO`,
      description: "Applies antenna gain, feed loss, beam splitting, and output back-off to final-stage power.",
    },
    {
      title: "Equivalent Input Noise",
      latex: String.raw`EIS[\mathrm{dBm}]=-174+10\log_{10}(B_{\mathrm{Hz}})+NF-G_{\mathrm{rx}}`,
      description: "Derives receiver input noise over the configured channel bandwidth.",
    },
    {
      title: "Noise-limited SNR",
      latex: String.raw`SNR_{\mathrm{noise}}=EIRP_{\mathrm{beam}}+30-L_{\mathrm{FSPL}}-L_{\mathrm{atm}}-L_{\mathrm{scint}}-L_{\mathrm{rain}}-EIS`,
      description: "Subtracts path and environmental losses from available signal power.",
    },
    {
      title: "Combined SNR",
      latex: String.raw`SNR_{\mathrm{total}}=-10\log_{10}\!\left(10^{-SNR_{\mathrm{noise}}/10}+10^{-SNR_{\mathrm{nonlinear}}/10}\right)`,
      description: "Combines thermal-noise and nonlinear impairment limits in the linear domain.",
    },
    {
      title: "Throughput",
      latex: String.raw`R[\mathrm{Mbps}]=\eta_{\mathrm{MCS}}\,B_{\mathrm{MHz}}\,(1-O_{\mathrm{control}})\,\eta_{\mathrm{resource}}`,
      description: "Selects the highest valid MCS at the calculated SNR and applies overhead and resource factors.",
    },
  ]
})
const componentFields = computed(() => {
  const item = selectedComponent.value
  if (!item) return []
  return [
    ["Application", item.application],
    ["Function", item.function],
    ["Grade", item.grade],
    ["Frequency", frequencyRange(item)],
    ["Process", item.process],
    ["Supply Voltage", unitValue(item.supply_voltage_v, "V")],
    ["Power Consumption", unitValue(item.power_consumption_w, "W")],
    ["Package", item.package],
    ["Operating Temperature", temperatureRange(item)],
    ["Datasheet Revision", item.datasheet_revision],
    ["Datasheet Page", item.datasheet_page],
    ["Extraction Method", item.extraction_method],
    ["Evidence", item.extraction_evidence],
    ["Note", item.note],
  ].filter((entry) => entry[1] != null && entry[1] !== "")
})
const componentSpecs = computed(() => Object.entries(selectedComponent.value?.specs ?? {})
  .filter((entry) => entry[1] != null && entry[1] !== "")
  .map(([key, value]) => [fieldLabel(key), unitValue(value, specificationUnit(key))]))
const calculationInputs = computed(() => {
  const input = result.value?.requirement
  if (!input) return []
  return [
    ["Application", input.application],
    ["Direction", input.direction],
    ["Center Frequency", input.center_freq_ghz, "GHz"],
    ["Channel Bandwidth", input.channel_bw_mhz, "MHz"],
    ["Target Throughput", input.target_throughput_mbps, "Mbps"],
    ["Control Overhead", input.control_overhead],
    ["Resource Factor", input.fill_factor],
    ["Number of Beams", input.num_beams],
    ["Boresight Range / Altitude", input.altitude_km, "km"],
    ["Elevation", input.elevation_deg, "deg"],
    ["Tx Antenna Gain", input.antenna_gain_db, "dBi"],
    ["Feed Loss", input.feed_loss_db, "dB"],
    ["Rx NF", input.receiver_nf_db, "dB"],
    ["Rx Coherent Gain", input.coherent_gain_db, "dB"],
    ["Sky Temperature", input.sky_temperature_k, "K"],
    ["BF Error", input.bf_error_db, "dB"],
    ["Atmospheric Loss", input.atmospheric_loss_db, "dB"],
    ["Scintillation Loss", input.scintillation_loss_db, "dB"],
    ["Rain Attenuation", input.rain_loss_db, "dB"],
    ["Nonlinear SNR", input.nonlinear_snr_db, "dB"],
    ["Max-slant Nonlinear SNR", input.max_slant_nonlinear_snr_db, "dB"],
    ["IF Frequency", input.if_freq_ghz, "GHz"],
    ["LO Routing Loss", input.lo_routing_loss_db, "dB"],
    ["Output Back-off", input.output_backoff_db, "dB"],
    ["Tx Input", input.tx_input_power_dbm, "dBm"],
    ["Peak EIRP Override", input.peak_eirp_dbw, "dBW"],
  ]
})

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  })
  const content = await response.text()
  let body = null
  if (content) {
    try {
      body = JSON.parse(content)
    } catch {
      throw new Error(`The API returned an invalid response (HTTP ${response.status}).`)
    }
  }
  if (!response.ok) {
    const unavailable = response.status >= 500 ? " Make sure the backend server is running." : ""
    throw new Error(body?.error ?? `The API request failed (HTTP ${response.status}).${unavailable}`)
  }
  if (body == null) throw new Error(`The API returned an empty response for ${path}.`)
  return body
}

async function loadInitialData() {
  try {
    const [config, inventory] = await Promise.all([api("/api/config"), api("/api/components")])
    requirement.value = config.default_requirement
    bands.value = config.bands
    components.value = inventory.components
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
    if (status.state === "succeeded" && previousState === "running") await loadComponents()
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
  try {
    result.value = await api("/api/designs", {
      method: "POST",
      body: JSON.stringify({ requirement: requirement.value }),
    })
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
  selectedComponent.value = null
}

function fieldLabel(key) {
  const acronyms = { adc: "ADC", bfic: "BFIC", db: "dB", dbm: "dBm", dbc: "dBc", enob: "ENOB", evm: "EVM", ghz: "GHz", if: "IF", iip3: "IIP3", lna: "LNA", lo: "LO", mhz: "MHz", nf: "NF", oip3: "OIP3", p1db: "P1dB", pa: "PA", pae: "PAE", pll: "PLL", psat: "Psat", rf: "RF", rms: "RMS", sfdr: "SFDR", sinad: "SINAD", snr: "SNR" }
  return key.split("_").map((word) => acronyms[word] ?? `${word[0].toUpperCase()}${word.slice(1)}`).join(" ")
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

function renderLatex(expression) {
  return katex.renderToString(expression, { displayMode: true, throwOnError: false })
}

onMounted(async () => {
  await Promise.all([loadInitialData(), updateCrawlStatus(true)])
})
onBeforeUnmount(stopCrawlPolling)
</script>

<template>
  <header>
    <div>
      <h1>Ka-band RF Designer</h1>
    </div>
    <nav>
      <button :class="{ active: page === 'design' }" @click="page = 'design'">Chain Design</button>
      <button :class="{ active: page === 'components' }" @click="page = 'components'">Components</button>
      <button :class="{ active: page === 'crawl' }" @click="page = 'crawl'">Data Crawl</button>
    </nav>
  </header>

  <main>
    <p v-if="error" class="alert error">{{ error }}</p>

    <template v-if="page === 'design'">
      <section class="panel">
        <div class="section-title">
          <div>
            <h2>Design Requirements</h2>
          </div>
          <button class="secondary" @click="applyBand">Apply ESA Band Center</button>
        </div>

        <form class="form-grid" @submit.prevent="calculate">
          <label>Application
            <select v-model="requirement.application">
              <option>Terminal</option>
              <option>Payload</option>
            </select>
          </label>
          <label>Direction
            <select v-model="requirement.direction">
              <option>Uplink</option>
              <option>Downlink</option>
              <option>Tx</option>
              <option>Rx</option>
            </select>
          </label>
          <label>Center Frequency (GHz)<input v-model.number="requirement.center_freq_ghz" type="number" step="0.001" min="0.001" /></label>
          <label>Channel Bandwidth (MHz)<input v-model.number="requirement.channel_bw_mhz" type="number" step="0.001" min="0.001" /></label>
          <label>Target Throughput (Mbps)<input v-model.number="requirement.target_throughput_mbps" type="number" step="1" min="0" /></label>
          <label>Control Overhead (ratio)<input v-model.number="requirement.control_overhead" type="number" step="0.01" min="0" max="0.99" /></label>
          <label>Resource Factor η<input v-model.number="requirement.fill_factor" type="number" step="0.00001" min="0.00001" /></label>
          <label>Number of Beams<input v-model.number="requirement.num_beams" type="number" step="1" min="1" /></label>
          <label>Boresight Range / Altitude (km)<input v-model.number="requirement.altitude_km" type="number" step="0.001" min="0.001" /></label>
          <label>Elevation (deg)<input v-model.number="requirement.elevation_deg" type="number" step="1" min="0" max="90" /></label>
          <label>Tx Antenna Gain (dBi)<input v-model.number="requirement.antenna_gain_db" type="number" step="0.1" /></label>
          <label>Rx NF (dB)<input v-model.number="requirement.receiver_nf_db" type="number" step="0.1" min="0" /></label>
          <label>Rx coherent gain (dB)<input v-model.number="requirement.coherent_gain_db" type="number" step="0.1" /></label>
          <label>Sky Temperature (K)<input v-model.number="requirement.sky_temperature_k" type="number" step="1" min="0" /></label>
          <label>BF Error (dB)<input v-model.number="requirement.bf_error_db" type="number" step="0.1" min="0" /></label>
          <label>Atmospheric Loss (dB)<input v-model.number="requirement.atmospheric_loss_db" type="number" step="0.1" min="0" /></label>
          <label>Scintillation Loss (dB)<input v-model.number="requirement.scintillation_loss_db" type="number" step="0.1" min="0" /></label>
          <label>Rain Attenuation (dB)<input v-model.number="requirement.rain_loss_db" type="number" step="0.1" min="0" /></label>
          <label>Nonlinear SNR (dB)<input v-model.number="requirement.nonlinear_snr_db" type="number" step="0.1" /></label>
          <label>Max-slant Nonlinear SNR (dB)<input v-model.number="requirement.max_slant_nonlinear_snr_db" type="number" step="0.1" /></label>
          <label>IF Frequency (GHz)<input v-model.number="requirement.if_freq_ghz" type="number" step="0.1" min="0" /></label>
          <label>Output Back-off (dB)<input v-model.number="requirement.output_backoff_db" type="number" step="0.1" min="0" /></label>
          <label>Tx Input (dBm)<input v-model.number="requirement.tx_input_power_dbm" type="number" step="0.1" /></label>
          <button class="primary submit" type="submit" :disabled="loading">
            {{ loading ? "Calculating…" : "Calculate RF Chain" }}
          </button>
        </form>

        <details class="calculation-equations" open>
          <summary>Calculation Equations ({{ requirementFunction }})</summary>
          <div class="equation-grid">
            <article v-for="equation in calculationEquations" :key="equation.title">
              <h3>{{ equation.title }}</h3>
              <div class="equation" v-html="renderLatex(equation.latex)"></div>
              <p>{{ equation.description }}</p>
            </article>
          </div>
        </details>
      </section>

      <section v-if="result" class="panel results">
        <div class="section-title">
          <div>
            <h2>{{ selectedCandidate ? `Candidate ${selectedCandidateIndex + 1}` : "No Candidate" }}</h2>
          </div>
          <span class="count">{{ result.evaluated_candidates }} evaluated</span>
        </div>

        <p v-for="warning in result.warnings" :key="warning" class="alert warning">{{ warning }}</p>

        <template v-if="selectedCandidate">
          <div class="chain" aria-label="Selected RF chain components">
            <button
              v-for="item in selectedCandidate.components"
              :key="item.component_id ?? `${item.category}-${item.part_no}`"
              class="chain-component"
              :class="{ active: selectedComponent?.component_id === item.component_id && selectedComponent?.part_no === item.part_no }"
              type="button"
              @click="selectedComponent = item"
            >
              <span>{{ item.category }}</span>
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
              <button type="button" aria-label="Close component details" @click="selectedComponent = null">×</button>
            </div>
            <div class="component-detail-grid">
              <table v-if="componentFields.length">
                <tbody><tr v-for="field in componentFields" :key="field[0]"><th>{{ field[0] }}</th><td>{{ field[1] }}</td></tr></tbody>
              </table>
              <table v-if="componentSpecs.length">
                <tbody><tr v-for="spec in componentSpecs" :key="spec[0]"><th>{{ spec[0] }}</th><td>{{ spec[1] }}</td></tr></tbody>
              </table>
            </div>
            <div class="component-links">
              <a v-if="selectedComponent.product_url" :href="selectedComponent.product_url" target="_blank" rel="noreferrer">Product page</a>
              <a v-if="selectedComponent.datasheet_url" :href="selectedComponent.datasheet_url" target="_blank" rel="noreferrer">Datasheet</a>
            </div>
          </section>
          <div v-if="result.function === 'Tx'" class="metrics">
            <article><span>Status</span><strong :class="selectedCandidate.status">{{ selectedCandidate.status }}</strong></article>
            <article><span>Linear EIRP / Beam</span><strong>{{ number(selectedCandidate.eirp_dbw) }} dBW</strong></article>
            <article><span>Boresight SNR</span><strong>{{ number(selectedCandidate.link_budget?.boresight_total_snr_db) }} dB</strong></article>
            <article><span>Max-slant SNR</span><strong>{{ number(selectedCandidate.link_budget?.max_slant_total_snr_db) }} dB</strong></article>
            <article><span>Max Throughput</span><strong>{{ number(selectedCandidate.link_budget?.max_throughput_mbps) }} Mbps</strong></article>
            <article><span>Min Throughput</span><strong>{{ number(selectedCandidate.link_budget?.min_throughput_mbps) }} Mbps</strong></article>
          </div>
          <div v-else class="metrics">
            <article><span>Total NF</span><strong>{{ number(selectedCandidate.total_nf_db) }} dB</strong></article>
            <article><span>Total Gain</span><strong>{{ number(selectedCandidate.total_gain_db) }} dB</strong></article>
            <article><span>Power</span><strong>{{ number(selectedCandidate.total_power_w) }} W</strong></article>
          </div>

          <details class="calculation-inputs" open>
            <summary>Calculation Inputs Used</summary>
            <table>
              <tbody>
                <tr v-for="input in calculationInputs" :key="input[0]">
                  <th>{{ input[0] }}</th>
                  <td>{{ inputValue(input[1], input[2]) }}</td>
                </tr>
              </tbody>
            </table>
          </details>

          <div class="table-wrap">
            <table>
              <thead><tr><th>Rank</th><th>Chain</th><th v-if="result.function === 'Tx'">Status</th><th>{{ result.function === "Tx" ? "Link Margin" : "NF" }}</th><th>Power</th></tr></thead>
              <tbody>
                <tr v-for="(candidate, index) in result.candidates" :key="index" :class="{ selected: selectedCandidateIndex === index }">
                  <td>{{ index + 1 }}</td>
                  <td><button class="candidate-link" type="button" @click="selectCandidate(index)">{{ chain(candidate) }}</button></td>
                  <td v-if="result.function === 'Tx'">{{ candidate.status }}</td>
                  <td>{{ number(result.function === "Tx" ? candidate.link_budget?.link_margin_db : candidate.total_nf_db) }} dB</td>
                  <td>{{ number(candidate.total_power_w) }} W</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>
    </template>

    <section v-else-if="page === 'components'" class="panel">
      <div class="section-title">
        <div><h2>Components</h2></div>
        <select v-model="category" class="category"><option v-for="item in categories" :key="item">{{ item }}</option></select>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Category</th><th>Manufacturer</th><th>Part Number</th><th>Application</th><th>Frequency</th><th>Grade</th><th>Source</th></tr></thead>
          <tbody>
            <tr v-for="item in filteredComponents" :key="item.component_id">
              <td>{{ item.category }}</td><td>{{ item.manufacturer }}</td><td>{{ item.part_no }}</td><td>{{ item.application }}</td>
              <td>{{ number(item.freq_min_ghz, 1) }}–{{ number(item.freq_max_ghz, 1) }} GHz</td><td>{{ item.grade }}</td>
              <td><a v-if="item.datasheet_url" :href="item.datasheet_url" target="_blank" rel="noreferrer">Datasheet</a><span v-else>-</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-else class="panel crawl-panel">
      <div class="section-title">
        <div>
          <h2>Manufacturer Data Crawl</h2>
        </div>
        <div class="crawl-actions">
          <span class="crawl-state" :class="crawlState">{{ crawlState }}</span>
          <button class="primary" type="button" :disabled="crawlState === 'running'" @click="startCrawl">
            {{ crawlState === "running" ? "Crawling…" : "Start Crawl" }}
          </button>
        </div>
      </div>

      <p class="crawl-description">
        Discover official manufacturer products, download datasheets, extract specifications, and refresh the component database.
      </p>
      <div class="crawl-meta">
        <span>Started: {{ crawlTime(crawlStartedAt) }}</span>
        <span>Finished: {{ crawlTime(crawlFinishedAt) }}</span>
        <span>Components: {{ components.length }}</span>
      </div>

      <div ref="terminal" class="terminal" role="log" aria-live="polite" aria-label="Crawler output">
        <div class="terminal-bar"><span></span><span></span><span></span><strong>crawler — pipeline output</strong></div>
        <pre v-if="crawlLogs.length">{{ crawlLogs.join("\n") }}</pre>
        <pre v-else class="terminal-empty">Ready. Press Start Crawl to run the component pipeline.</pre>
      </div>
    </section>
  </main>
</template>
