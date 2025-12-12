const { app, BrowserWindow, Menu, shell, ipcMain, Notification } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')
const { autoUpdater } = require('electron-updater')
const log = require('electron-log')

// 配置 autoUpdater 日志
autoUpdater.logger = log
autoUpdater.logger.transports.file.level = 'info'
log.info('App starting...')

// 设置自动下载为 false，让用户决定是否更新
autoUpdater.autoDownload = false

function setupAutoUpdater() {
  autoUpdater.on('checking-for-update', () => {
    log.info('Checking for update...')
  })

  autoUpdater.on('update-available', (info) => {
    log.info('Update available.', info)
    // 通知渲染进程
    if (mainWindow) {
      mainWindow.webContents.send('update-available', info)
    }
    // 可以弹窗提示用户
    new Notification({ title: '发现新版本', body: `发现新版本 v${info.version}, 是否下载更新?` }).show()
  })

  autoUpdater.on('update-not-available', (info) => {
    log.info('Update not available.', info)
  })

  autoUpdater.on('error', (err) => {
    log.error('Error in auto-updater. ' + err)
    if (mainWindow) {
      mainWindow.webContents.send('update-error', err.toString())
    }
  })

  autoUpdater.on('download-progress', (progressObj) => {
    let log_message = "Download speed: " + progressObj.bytesPerSecond
    log_message = log_message + ' - Downloaded ' + progressObj.percent + '%'
    log_message = log_message + ' (' + progressObj.transferred + "/" + progressObj.total + ')'
    log.info(log_message)
    if (mainWindow) {
      mainWindow.webContents.send('download-progress', progressObj)
    }
  })

  autoUpdater.on('update-downloaded', (info) => {
    log.info('Update downloaded')
    if (mainWindow) {
      mainWindow.webContents.send('update-downloaded', info)
    }
    new Notification({ title: '更新已下载', body: '更新已下载完毕，将在退出后安装' }).show()
  })

  // 监听渲染进程触发的检查更新
  ipcMain.handle('checkForUpdates', () => {
    autoUpdater.checkForUpdatesAndNotify()
  })

  // 监听渲染进程触发的下载更新
  ipcMain.handle('downloadUpdate', () => {
    autoUpdater.downloadUpdate()
  })

  // 监听渲染进程触发的退出并安装
  ipcMain.handle('quitAndInstall', () => {
    autoUpdater.quitAndInstall()
  })
}

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

let mainWindow = null

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
  mainWindow = win
  return win
}

function createMenu(win) {
  const template = [
    { label: 'File', submenu: [
      { label: 'Open Logs Folder', click: function () { shell.openPath(path.join(process.cwd(), 'logs')) } },
      { label: 'Open Configs Folder', click: function () { const dir = path.join(process.cwd(), 'configs'); if (!fs.existsSync(dir)) { try { fs.mkdirSync(dir, { recursive: true }) } catch (e) {} } shell.openPath(dir) } },
      { label: 'Open Config Groups Folder', click: function () { const dir = path.join(process.cwd(), 'config_groups'); if (!fs.existsSync(dir)) { try { fs.mkdirSync(dir, { recursive: true }) } catch (e) {} } shell.openPath(dir) } },
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
  setupAutoUpdater()
  startPython()
  try { await waitForServer(50, 200) } catch (e) {}
  const win = createWindow()
  createMenu(win)
  // 启动时自动检查更新
  if (app.isPackaged) {
    autoUpdater.checkForUpdatesAndNotify()
  }
})

app.on('window-all-closed', function () { if (process.platform !== 'darwin') app.quit() })
app.on('activate', function () { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
app.on('quit', function () { if (pyProc) { pyProc.kill(); pyProc = null } })

ipcMain.handle('openLogsDir', async function () { return shell.openPath(path.join(process.cwd(), 'logs')) })

ipcMain.handle('handleDropFiles', async function (_evt, files) {
  try {
    if (!files || !files.length) return { ok: false }
    const destDir = path.join(process.cwd(), 'logs')
    try { if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true }) } catch (e) {}
    const now = new Date()
    function pad(n) { return String(n).padStart(2, '0') }
    let opened = null
    for (const src of files) {
      const name = path.basename(src)
      const ext = path.extname(name)
      const base = path.basename(name, ext)
      const stamped = `${base}_${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}${ext}`
      const dest = path.join(destDir, stamped)
      try { fs.copyFileSync(src, dest) } catch (e) { continue }
      opened = stamped
      break
    }
    if (opened && mainWindow) {
      mainWindow.loadURL('http://' + HOST + ':' + PORT + '/?open=' + encodeURIComponent(opened))
      try { new Notification({ title: '日志复制成功', body: '已复制并重命名为: ' + opened }).show() } catch (_) {}
    }
    return { ok: !!opened, file: opened }
  } catch (err) {
    return { ok: false }
  }
})

ipcMain.handle('handleDropBinary', async function (_evt, payload) {
  try {
    if (!payload || !payload.data) return { ok: false }
    const destDir = path.join(process.cwd(), 'logs')
    try { if (!fs.existsSync(destDir)) fs.mkdirSync(destDir, { recursive: true }) } catch (e) {}
    const now = new Date()
    function pad(n) { return String(n).padStart(2, '0') }
    const name = (payload.name || 'log.txt')
    const ext = path.extname(name)
    const base = path.basename(name, ext)
    const stamped = `${base}_${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}${ext || '.log'}`
    const dest = path.join(destDir, stamped)
    try { fs.writeFileSync(dest, Buffer.from(payload.data)) } catch (e) { return { ok: false } }
    if (mainWindow) {
      mainWindow.loadURL('http://' + HOST + ':' + PORT + '/?open=' + encodeURIComponent(stamped))
      try { new Notification({ title: '日志复制成功', body: '已复制并重命名为: ' + stamped }).show() } catch (_) {}
    }
    return { ok: true, file: stamped }
  } catch (err) { return { ok: false } }
})
