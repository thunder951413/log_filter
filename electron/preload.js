const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  openLogsDir: function () { return ipcRenderer.invoke('openLogsDir') }
})
