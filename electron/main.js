const { app, BrowserWindow, Menu, shell, ipcMain } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')

let pyProc = null
const PORT = parseInt(process.env.LOG_FILTER_PORT || '8052', 10)
const HOST = '127.0.0.1'

function resolveServerBinary() {
  const devCandidates = [
    path.join(process.cwd(), 'dist', 'log_filter_server'),
    path.join(process.cwd(), 'dist', 'log_filter_server.exe')
  ]
  for (const p of devCandidates) {
    try { if (require('fs').existsSync(p)) return p } catch (e) {}
  }
  const res = process.resourcesPath || process.cwd()
  const prodCandidates = [
    path.join(res, 'python', 'log_filter_server'),
    path.join(res, 'python', 'log_filter_server.exe')
  ]
  for (const p of prodCandidates) {
    try { if (require('fs').existsSync(p)) return p } catch (e) {}
  }
  return null
}

function startPython() {
  const bin = resolveServerBinary()
  if (bin) {
    pyProc = spawn(bin, ['--port', String(PORT), '--host', HOST], { cwd: process.cwd(), env: process.env })
  } else {
    const script = path.join(process.cwd(), 'app.py')
    pyProc = spawn('python', [script, '--port', String(PORT), '--host', HOST], { cwd: process.cwd(), env: process.env })
  }
  pyProc.on('exit', function () { pyProc = null })
}

function waitForServer(retries, interval) {
  let attempts = 0
  return new Promise(function (resolve, reject) {
    function tick() {
      attempts++
      const req = http.request({ hostname: HOST, port: PORT, path: '/', method: 'GET' }, function (res) {
        res.destroy()
        resolve()
      })
      req.on('error', function () {
        if (attempts >= retries) reject(new Error('server not ready'))
        else setTimeout(tick, interval)
      })
      req.end()
    }
    tick()
  })
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      webSecurity: true
    }
  })
  win.loadURL('http://' + HOST + ':' + PORT + '/')
  return win
}

function createMenu(win) {
  const template = [
    { label: 'File', submenu: [
      { label: 'Open Logs Folder', click: function () { shell.openPath(path.join(process.cwd(), 'logs')) } },
      { role: 'quit' }
    ] },
    { label: 'View', submenu: [
      { role: 'reload' },
      { role: 'toggleDevTools' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { role: 'togglefullscreen' }
    ] },
    { label: 'Help', submenu: [
      { label: 'About', click: function () {} }
    ] }
  ]
  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

app.on('ready', async function () {
  startPython()
  try { await waitForServer(50, 200) } catch (e) {}
  const win = createWindow()
  createMenu(win)
})

app.on('window-all-closed', function () { if (process.platform !== 'darwin') app.quit() })
app.on('activate', function () { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
app.on('quit', function () { if (pyProc) { pyProc.kill(); pyProc = null } })

ipcMain.handle('openLogsDir', async function () { return shell.openPath(path.join(process.cwd(), 'logs')) })
