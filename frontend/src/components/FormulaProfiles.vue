<script setup>
import { computed, onMounted, ref } from "vue"
import { api } from "../api"

const emit = defineEmits(["error", "updated"])
const profiles = ref([])
const slots = ref({})
const selectedId = ref("default-v1")
const draft = ref(null)
const message = ref("")
const saving = ref(false)

const selectedSummary = computed(() => profiles.value.find((item) => item.id === selectedId.value))
const formulaEntries = computed(() => draft.value ? Object.entries(draft.value.formulas) : [])

async function loadProfiles(selectId = selectedId.value) {
  const response = await api("/api/formula-profiles")
  profiles.value = response.profiles
  slots.value = response.slots
  selectedId.value = profiles.value.some((item) => item.id === selectId) ? selectId : "default-v1"
  await loadSelected()
  emit("updated", profiles.value)
}

async function loadSelected() {
  if (!selectedId.value) return
  draft.value = await api(`/api/formula-profiles/${selectedId.value}`)
  message.value = ""
}

async function cloneProfile() {
  try {
    const created = await api("/api/formula-profiles", {
      method: "POST",
      body: JSON.stringify({ source_id: selectedId.value, name: `${draft.value.name} 복사본` }),
    })
    await loadProfiles(created.id)
    message.value = "편집 가능한 프로필을 만들었습니다."
  } catch (reason) {
    emit("error", reason.message)
  }
}

async function saveProfile() {
  saving.value = true
  message.value = ""
  try {
    await api("/api/formula-profiles/validate", { method: "POST", body: JSON.stringify(draft.value) })
    const saved = await api(`/api/formula-profiles/${draft.value.id}`, {
      method: "PUT",
      body: JSON.stringify({ ...draft.value, base_revision: draft.value.revision }),
    })
    await loadProfiles(saved.id)
    message.value = `개정 ${saved.revision}을(를) 검증하고 저장했습니다.`
  } catch (reason) {
    emit("error", reason.message)
  } finally {
    saving.value = false
  }
}

async function deleteProfile() {
  if (draft.value?.built_in) return
  try {
    await api(`/api/formula-profiles/${draft.value.id}`, { method: "DELETE" })
    await loadProfiles("default-v1")
    message.value = "프로필을 삭제했습니다."
  } catch (reason) {
    emit("error", reason.message)
  }
}

async function exportProfile() {
  if (!window.desktop?.exportFormulaProfile) {
    emit("error", "수식 프로필 내보내기는 Electron 앱에서만 사용할 수 있습니다.")
    return
  }
  const result = await window.desktop.exportFormulaProfile({
    defaultName: `${draft.value.name.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-")}.json`,
    content: JSON.stringify(draft.value, null, 2),
  })
  if (result?.error) emit("error", result.error)
}

async function importProfile() {
  if (!window.desktop?.importFormulaProfile) {
    emit("error", "수식 프로필 가져오기는 Electron 앱에서만 사용할 수 있습니다.")
    return
  }
  try {
    const file = await window.desktop.importFormulaProfile()
    if (file.canceled) return
    if (file.error) throw new Error(file.error)
    const created = await api("/api/formula-profiles/import", { method: "POST", body: file.content })
    await loadProfiles(created.id)
    message.value = "프로필을 가져와 검증했습니다."
  } catch (reason) {
    emit("error", reason.message)
  }
}

function moveRule(functionName, index, offset) {
  const rules = draft.value.ranking[functionName]
  const target = index + offset
  if (target < 0 || target >= rules.length) return
  ;[rules[index], rules[target]] = [rules[target], rules[index]]
}

onMounted(() => loadProfiles().catch((reason) => emit("error", reason.message)))
</script>

<template>
  <section class="formula-workspace">
    <aside class="profile-list">
      <div class="profile-list-title">
        <h2>수식 프로필</h2>
        <button type="button" @click="importProfile">가져오기</button>
      </div>
      <button
        v-for="profile in profiles"
        :key="profile.id"
        class="profile-list-item"
        :class="{ active: selectedId === profile.id }"
        type="button"
        @click="selectedId = profile.id; loadSelected()"
      >
        <strong>{{ profile.name }}</strong>
        <span>개정 {{ profile.revision }}{{ profile.built_in ? " · 기본 제공" : "" }}</span>
      </button>
    </aside>

    <section v-if="draft" class="profile-editor">
      <header class="profile-editor-header">
        <div>
          <h2>{{ draft.name }}</h2>
          <p>{{ draft.description }}</p>
        </div>
        <div class="profile-actions">
          <button type="button" @click="cloneProfile">복제</button>
          <button type="button" @click="exportProfile">JSON 내보내기</button>
          <button v-if="!draft.built_in" type="button" class="danger-button" @click="deleteProfile">삭제</button>
          <button v-if="!draft.built_in" class="primary" type="button" :disabled="saving" @click="saveProfile">
            {{ saving ? "검증 중…" : "검증 후 저장" }}
          </button>
        </div>
      </header>

      <p v-if="message" class="alert success">{{ message }}</p>
      <p v-if="draft.built_in" class="alert info">기본 제공 프로필은 읽기 전용입니다. 수식을 수정하려면 복제하세요.</p>

      <div class="profile-meta">
        <label>이름<input v-model="draft.name" :disabled="draft.built_in" /></label>
        <label>설명<input v-model="draft.description" :disabled="draft.built_in" /></label>
      </div>

      <section class="formula-section">
        <h3>계산 수식</h3>
        <article v-for="[key, expression] in formulaEntries" :key="key" class="formula-row">
          <div>
            <strong>{{ slots[key]?.label ?? key }}</strong>
            <span>{{ key }} · 출력 단위 {{ slots[key]?.unit }}</span>
            <small>변수: {{ Object.entries(slots[key]?.variables ?? {}).map(([name, unit]) => `${name} [${unit}]`).join(", ") }}</small>
          </div>
          <textarea
            :value="expression"
            :disabled="draft.built_in"
            rows="3"
            spellcheck="false"
            @input="draft.formulas[key] = $event.target.value"
          ></textarea>
        </article>
      </section>

      <section v-for="functionName in ['Tx', 'Rx']" :key="functionName" class="formula-section">
        <h3>{{ functionName }} 순위 우선순위</h3>
        <article v-for="(rule, index) in draft.ranking[functionName]" :key="index" class="ranking-row">
          <span class="ranking-number">{{ index + 1 }}</span>
          <input v-model="rule.expression" :disabled="draft.built_in" spellcheck="false" />
          <select v-model="rule.direction" :disabled="draft.built_in"><option value="asc">오름차순</option><option value="desc">내림차순</option></select>
          <label class="check-label"><input v-model="rule.enabled" type="checkbox" :disabled="draft.built_in" /> 사용</label>
          <div class="ranking-move">
            <button type="button" :disabled="draft.built_in || index === 0" @click="moveRule(functionName, index, -1)">↑</button>
            <button type="button" :disabled="draft.built_in || index === draft.ranking[functionName].length - 1" @click="moveRule(functionName, index, 1)">↓</button>
          </div>
        </article>
      </section>
    </section>
  </section>
</template>
