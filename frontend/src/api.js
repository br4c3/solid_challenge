export async function api(path, options = {}) {
  const apiBaseUrl = window.desktop?.apiBaseUrl ?? ""
  const apiToken = window.desktop?.apiToken
  const response = await fetch(`${apiBaseUrl}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(apiToken ? { "X-RF-Design-Token": apiToken } : {}),
      ...(options.headers ?? {}),
    },
    ...options,
  })
  const content = await response.text()
  let body = null
  if (content) {
    try {
      body = JSON.parse(content)
    } catch {
      throw new Error(`API가 올바르지 않은 응답을 반환했습니다(HTTP ${response.status}).`)
    }
  }
  if (!response.ok) {
    const unavailable = response.status >= 500 ? " 백엔드 서버가 실행 중인지 확인하세요." : ""
    throw new Error(body?.error ?? `API 요청에 실패했습니다(HTTP ${response.status}).${unavailable}`)
  }
  if (response.status === 204) return null
  if (body == null) throw new Error(`${path} 요청에 대해 API가 빈 응답을 반환했습니다.`)
  return body
}
