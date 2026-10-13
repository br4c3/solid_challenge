const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron")
const { spawn } = require("node:child_process")
const crypto = require("node:crypto")
const fs = require("node:fs")
const http = require("node:http")
const net = require("node:net")
const path = require("node:path")

let backendProcess = null
let backendError = null
let mainWindow = null

ipcMain.handle("export-csv", async (_event, payload) => {
  if (!payload || typeof payload.content !== "string" || typeof payload.defaultName !== "string") {
    return { error: "CSV 내보내기 요청이 올바르지 않습니다." }
  }
  if (Buffer.byteLength(payload.content, "utf8") > 10 * 1024 * 1024) {
    return { error: "CSV 내보내기 용량이 10MB 제한을 초과했습니다." }
  }
  const defaultName = path.basename(payload.defaultName).endsWith(".csv")
    ? path.basename(payload.defaultName)
    : `${path.basename(payload.defaultName)}.csv`
  const selection = await dialog.showSaveDialog(mainWindow, {
    title: "후보 비교 결과 내보내기",
    defaultPath: defaultName,
    filters: [{ name: "CSV 파일", extensions: ["csv"] }],
  })
  if (selection.canceled || !selection.filePath) return { canceled: true }
  try {
    await fs.promises.writeFile(selection.filePath, payload.content, "utf8")
    return { canceled: false }
  } catch (error) {
    return { error: error.message }
  }
})

ipcMain.handle("export-formula-profile", async (_event, payload) => {
  if (!payload || typeof payload.content !== "string" || Buffer.byteLength(payload.content, "utf8") > 1024 * 1024) {
    return { error: "수식 프로필 내보내기 요청이 올바르지 않습니다." }
  }
  const defaultName = `${path.basename(payload.defaultName || "formula-profile", ".json")}.json`
  const selection = await dialog.showSaveDialog(mainWindow, {
    title: "수식 프로필 내보내기",
    defaultPath: defaultName,
    filters: [{ name: "JSON 파일", extensions: ["json"] }],
  })
  if (selection.canceled || !selection.filePath) return { canceled: true }
  try {
    await fs.promises.writeFile(selection.filePath, payload.content, "utf8")
    return { canceled: false }
  } catch (error) {
    return { error: error.message }
  }
})

ipcMain.handle("import-formula-profile", async () => {
  const selection = await dialog.showOpenDialog(mainWindow, {
    title: "수식 프로필 가져오기",
    properties: ["openFile"],
    filters: [{ name: "JSON 파일", extensions: ["json"] }],
  })
  if (selection.canceled || !selection.filePaths[0]) return { canceled: true }
  try {
    const stats = await fs.promises.stat(selection.filePaths[0])
    if (stats.size > 1024 * 1024) return { error: "수식 프로필이 1MB 제한을 초과했습니다." }
    return { canceled: false, content: await fs.promises.readFile(selection.filePaths[0], "utf8") }
  } catch (error) {
    return { error: error.message }
  }
})

function projectRoot() {
  return path.resolve(__dirname, "../..")
}

function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on("error", reject)
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address()
      server.close(() => resolve(port))
    })
  })
}

function backendCommand(port) {
  if (app.isPackaged) {
    const executable = process.platform === "win32" ? "rf-design-backend.exe" : "rf-design-backend"
    return {
      command: path.join(process.resourcesPath, "backend", executable),
      args: ["--port", String(port)],
      cwd: process.resourcesPath,
      resourceDir: path.join(process.resourcesPath, "app-resources"),
    }
  }

  const root = projectRoot()
  const virtualEnvironmentPython = process.platform === "win32"
    ? path.join(root, ".venv", "Scripts", "python.exe")
    : path.join(root, ".venv", "bin", "python")
  return {
    command: process.env.RF_DESIGN_PYTHON || (fs.existsSync(virtualEnvironmentPython) ? virtualEnvironmentPython : "python3"),
    args: ["-m", "backend.desktop", "--port", String(port)],
    cwd: root,
    resourceDir: root,
  }
}

function waitForBackend(port, apiToken, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve, reject) => {
    const check = () => {
      if (backendError || backendProcess?.exitCode != null || backendProcess?.signalCode != null) {
        reject(backendError || new Error(`로컬 백엔드가 종료되었습니다. 종료 코드: ${backendProcess.exitCode}`))
        return
      }
      const request = http.get({
        hostname: "127.0.0.1",
        port,
        path: "/api/health",
        headers: { "X-RF-Design-Token": apiToken },
      }, (response) => {
        response.resume()
        if (response.statusCode === 200) {
          resolve()
          return
        }
        retry()
      })
      request.on("error", retry)
    }
    const retry = () => {
      if (Date.now() >= deadline) {
        reject(new Error("로컬 백엔드가 60초 이내에 준비되지 않았습니다."))
        return
      }
      setTimeout(check, 200)
    }
    check()
  })
}

async function startBackend() {
  const port = await availablePort()
  const apiToken = crypto.randomBytes(32).toString("hex")
  const launch = backendCommand(port)
  backendError = null
  backendProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      RF_DESIGN_API_TOKEN: apiToken,
      RF_DESIGN_DATA_DIR: app.isPackaged ? path.join(app.getPath("userData"), "data") : path.join(projectRoot(), "data"),
      RF_DESIGN_DESKTOP: "1",
      RF_DESIGN_RESOURCE_DIR: launch.resourceDir,
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  })
  backendProcess.on("error", (error) => { backendError = error })
  backendProcess.stdout.on("data", (chunk) => process.stdout.write(`[backend] ${chunk}`))
  backendProcess.stderr.on("data", (chunk) => process.stderr.write(`[backend] ${chunk}`))
  await waitForBackend(port, apiToken)
  return { apiBaseUrl: `http://127.0.0.1:${port}`, apiToken }
}

function stopBackend() {
  if (!backendProcess || backendProcess.exitCode != null || backendProcess.signalCode != null) return
  try {
    if (process.platform === "win32") spawn("taskkill", ["/pid", String(backendProcess.pid), "/t", "/f"])
    else process.kill(-backendProcess.pid, "SIGTERM")
  } catch (error) {
    if (error.code !== "ESRCH") throw error
  }
  backendProcess = null
}

async function createWindow(apiBaseUrl, apiToken) {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 1000,
    minHeight: 700,
    show: false,
    backgroundColor: "#f4f6f8",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, "preload.cjs"),
      additionalArguments: [`--rf-api-base=${apiBaseUrl}`, `--rf-api-token=${apiToken}`],
    },
  })

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url)
    return { action: "deny" }
  })
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (url === mainWindow.webContents.getURL()) return
    event.preventDefault()
    if (url.startsWith("https://")) shell.openExternal(url)
  })
  mainWindow.once("ready-to-show", () => mainWindow.show())

  if (app.isPackaged) await mainWindow.loadFile(path.join(__dirname, "../dist/index.html"))
  else await mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL || "http://127.0.0.1:5173")
}

const hasLock = app.requestSingleInstanceLock()
if (!hasLock) app.quit()

app.on("second-instance", () => {
  if (!mainWindow) return
  if (mainWindow.isMinimized()) mainWindow.restore()
  mainWindow.focus()
})

app.whenReady().then(async () => {
  try {
    const { apiBaseUrl, apiToken } = await startBackend()
    await createWindow(apiBaseUrl, apiToken)
  } catch (error) {
    stopBackend()
    dialog.showErrorBox("Ka-대역 RF 설계 도구", error.message)
    app.quit()
  }
})

app.on("before-quit", stopBackend)
app.on("window-all-closed", () => app.quit())
