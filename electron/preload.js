const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
  openLogsDir: function () { return ipcRenderer.invoke('openLogsDir') }
})

function prevent(e){ try{ e && e.preventDefault && e.preventDefault() }catch(_){} }
window.addEventListener('dragenter', prevent)
window.addEventListener('dragover', prevent)
document.addEventListener('dragover', prevent)
document.addEventListener('drop', prevent)
window.addEventListener('drop', function (e) {
  prevent(e)
  try {
    var list = (e && e.dataTransfer && e.dataTransfer.files) || []
    if (!list || !list.length) return
    var paths = []
    for (var i = 0; i < list.length; i++) { var f = list[i]; if (f && f.path) paths.push(f.path) }
    if (paths.length) { ipcRenderer.invoke('handleDropFiles', paths); return }
    var f0 = list[0]
    if (!f0) return
    var reader = new FileReader()
    reader.onload = function(){ try{ var buf = Buffer.from(reader.result); ipcRenderer.invoke('handleDropBinary', { name: f0.name || 'log.txt', data: buf }) }catch(_){}}
    reader.onerror = function(){ /* noop */ }
    try{ reader.readAsArrayBuffer(f0) }catch(_){}
  } catch (err) {}
})
