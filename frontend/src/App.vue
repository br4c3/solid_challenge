<script setup>
import { computed, onMounted, ref } from "vue"

const page = ref("design")
const loading = ref(false)
const error = ref("")
const result = ref(null)
const components = ref([])
const category = ref("ALL")
const bands = ref({})
const selectedCandidateIndex = ref(0)

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
  const body = await response.json()
  if (!response.ok) throw new Error(body.error ?? "The request could not be processed.")
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

function applyBand() {
  const band = bands.value[`${requirement.value.application}-${requirement.value.direction}`]
  if (band) requirement.value.center_freq_ghz = (band[0] + band[1]) / 2
}

async function calculate() {
  loading.value = true
  error.value = ""
  result.value = null
  selectedCandidateIndex.value = 0
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

function number(value, digits = 2) {
  return value == null ? "-" : Number(value).toFixed(digits)
}

function inputValue(value, unit) {
  if (value == null) return "-"
  return unit ? `${value} ${unit}` : value
}

onMounted(loadInitialData)
</script>

<template>
  <header>
    <div>
      <p class="eyebrow">SATELLITE RF SYSTEMS</p>
      <h1>Ka-band RF Designer</h1>
    </div>
    <nav>
      <button :class="{ active: page === 'design' }" @click="page = 'design'">Chain Design</button>
      <button :class="{ active: page === 'components' }" @click="page = 'components'">Components</button>
    </nav>
  </header>

  <main>
    <p v-if="error" class="alert error">{{ error }}</p>

    <template v-if="page === 'design'">
      <section class="panel">
        <div class="section-title">
          <div>
            <p class="eyebrow">REQUIREMENTS</p>
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
      </section>

      <section v-if="result" class="panel results">
        <div class="section-title">
          <div>
            <p class="eyebrow">{{ result.function }} RESULT</p>
            <h2>{{ selectedCandidate ? `Candidate ${selectedCandidateIndex + 1}` : "No Candidate" }}</h2>
          </div>
          <span class="count">{{ result.evaluated_candidates }} evaluated</span>
        </div>

        <p v-for="warning in result.warnings" :key="warning" class="alert warning">{{ warning }}</p>

        <template v-if="selectedCandidate">
          <p class="chain">{{ chain(selectedCandidate) }}</p>
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
                  <td><button class="candidate-link" type="button" @click="selectedCandidateIndex = index">{{ chain(candidate) }}</button></td>
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

    <section v-else class="panel">
      <div class="section-title">
        <div><p class="eyebrow">COMPONENT DATABASE</p><h2>Components</h2></div>
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
  </main>
</template>
