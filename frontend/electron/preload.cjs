const { contextBridge, ipcRenderer } = require("electron")

function argumentValue(name) {
  const prefix = `--${name}=`
  const argument = process.argv.find((value) => value.startsWith(prefix))
  return argument ? argument.slice(prefix.length) : ""
}

contextBridge.exposeInMainWorld("desktop", Object.freeze({
  apiBaseUrl: argumentValue("rf-api-base"),
  apiToken: argumentValue("rf-api-token"),
  exportCsv: (payload) => ipcRenderer.invoke("export-csv", payload),
  exportFormulaProfile: (payload) => ipcRenderer.invoke("export-formula-profile", payload),
  importFormulaProfile: () => ipcRenderer.invoke("import-formula-profile"),
}))
