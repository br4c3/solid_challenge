const { spawnSync } = require("node:child_process")
const fs = require("node:fs")
const path = require("node:path")

const frontendDir = path.resolve(__dirname, "..")
const projectRoot = path.resolve(frontendDir, "..")
const python = process.platform === "win32"
  ? path.join(projectRoot, ".venv", "Scripts", "python.exe")
  : path.join(projectRoot, ".venv", "bin", "python")

if (!fs.existsSync(python)) {
  console.error(`Python virtual environment was not found: ${python}`)
  process.exit(1)
}

const arguments = [
  "-m", "PyInstaller",
  "--clean",
  "--noconfirm",
  "--onefile",
  "--name", "rf-design-backend",
  "--paths", projectRoot,
  "--exclude-module", "pandas",
  "--exclude-module", "pyarrow",
  "--exclude-module", "pytest",
  "--distpath", path.join(frontendDir, "python-dist"),
  "--workpath", path.join(frontendDir, "python-build"),
  path.join(projectRoot, "backend", "desktop.py"),
]
const result = spawnSync(python, arguments, {
  cwd: frontendDir,
  env: { ...process.env, PYINSTALLER_CONFIG_DIR: path.join(frontendDir, "python-cache") },
  stdio: "inherit",
})

if (result.error) {
  console.error(result.error.message)
  process.exit(1)
}
process.exit(result.status ?? 1)
