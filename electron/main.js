const { app, BrowserWindow, Menu, shell, ipcMain, Notification } = require('electron')
const path = require('path')
const { spawn } = require('child_process')
const http = require('http')
const fs = require('fs')
const { autoUpdater } = require('electron-updater')
const log = require('electron-log')

log.transports.file.resolvePathFn = function () {
  return path.join(getAppSubdir('runtime_logs'), 'electron-main.log')
}

// 配置 autoUpdater 日志
autoUpdater.logger = log
autoUpdater.logger.transports.file.level = 'info'
log.info('App starting...')

// 设置自动下载为 false，让用户决定是否更新
autoUpdater.autoDownload = false

const PORT = parseInt(process.env.LOG_FILTER_PORT || '8052', 10)
const HOST = '127.0.0.1'
const SERVER_URL = 'http://' + HOST + ':' + PORT + '/'
const SERVER_WAIT_RETRIES = 180
const SERVER_WAIT_INTERVAL = 500
const LINUX_DISABLE_SANDBOX = process.platform === 'linux'

let pyProc = null
let mainWindow = null
let autoUpdaterEnabled = false
let lastPythonState = 'not started'

if (LINUX_DISABLE_SANDBOX) {
  app.commandLine.appendSwitch('no-sandbox')
  app.commandLine.appendSwitch('disable-setuid-sandbox')
  log.info('Linux sandbox compatibility mode enabled')
}

process.on('unhandledRejection', function (reason) {
  log.error('Unhandled promise rejection', reason)
})

process.on('uncaughtException', function (error) {
  log.error('Uncaught exception', error)
})

function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function createInlinePage(title, message, detail) {
  const html = '<!doctype html><html><head><meta charset="utf-8"><title>' + escapeHtml(title) + '</title><style>body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;margin:0;background:#f8fafc;color:#0f172a}main{max-width:760px;margin:0 auto;padding:48px 32px}h1{font-size:26px;margin:0 0 16px}p{font-size:15px;line-height:1.7;margin:0 0 12px;white-space:pre-wrap}pre{font-size:13px;line-height:1.6;background:#0f172a;color:#e2e8f0;padding:16px;border-radius:12px;overflow:auto;white-space:pre-wrap}</style></head><body><main><h1>' + escapeHtml(title) + '</h1><p>' + escapeHtml(message) + '</p>' + (detail ? '<pre>' + escapeHtml(detail) + '</pre>' : '') + '</main></body></html>'
  return 'data:text/html;charset=UTF-8,' + encodeURIComponent(html)
}

function getRuntimeDataDir() {
  if (app.isPackaged) return app.getPath('userData')
  return process.cwd()
}

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
}

function getAppSubdir(name) {
  const dir = path.join(getRuntimeDataDir(), name)
  ensureDir(dir)
  return dir
}

function getLogFilePath() {
  try {
    return log.transports.file.getFile().path
  } catch (error) {
    return ''
  }
}

function showLoadingScreen(win) {
  return win.loadURL(createInlinePage('LogFilter 正在启动', '正在启动后端服务。首次打开或冷启动通常需要 20~40 秒，请稍候。'))
}

function showStartupError(win, error) {
  const detail = [
    '后端地址: ' + SERVER_URL,
    '运行目录: ' + getRuntimeDataDir(),
    '后端状态: ' + lastPythonState,
    getLogFilePath() ? '主进程日志: ' + getLogFilePath() : '',
    error ? '错误信息: ' + (error.stack || error.message || String(error)) : ''
  ].filter(Boolean).join('\n')
  return win.loadURL(createInlinePage('LogFilter 启动失败', '后端服务未能在预期时间内启动，因此没有加载主界面。请关闭应用后重试；如果问题持续，请把这里的信息和日志一并反馈。', detail))
}

function readUpdaterFeedUrl() {
  if (!app.isPackaged) return ''
  const filePath = path.join(process.resourcesPath || '', 'app-update.yml')
  try {
    if (!fs.existsSync(filePath)) return ''
    const content = fs.readFileSync(filePath, 'utf8')
    const match = content.match(/^\s*url:\s*(.+)\s*$/m)
    return match ? match[1].trim() : ''
  } catch (error) {
    log.warn('Unable to read updater config', error)
    return ''
  }
}

function shouldEnableAutoUpdater() {
  if (!app.isPackaged) return false
  const feedUrl = readUpdaterFeedUrl()
  if (!feedUrl) return false
  return !/^https?:\/\/(localhost|127\.0\.0\.1)(?::\d+)?(?:\/|$)/i.test(feedUrl)
}

async function checkForUpdatesSafely() {
  if (!autoUpdaterEnabled) {
    const feedUrl = readUpdaterFeedUrl()
    log.info('Skip auto update check because update feed is unavailable or local only', feedUrl || '(missing)')
    return { skipped: true, reason: 'updater_disabled', feedUrl }
  }
  try {
    return await autoUpdater.checkForUpdatesAndNotify()
  } catch (error) {
    log.error('Auto update check failed', error)
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('update-error', error.toString())
    }
    return { skipped: false, error: error.message || String(error) }
  }
}

function setupAutoUpdater() {
  autoUpdaterEnabled = shouldEnableAutoUpdater()
  log.info('Auto updater enabled:', autoUpdaterEnabled, 'feed:', readUpdaterFeedUrl() || '(missing)')

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
  ipcMain.handle('checkForUpdates', async () => {
    return checkForUpdatesSafely()
  })

  // 监听渲染进程触发的下载更新
  ipcMain.handle('downloadUpdate', async () => {
    if (!autoUpdaterEnabled) return { skipped: true, reason: 'updater_disabled' }
    try {
      return await autoUpdater.downloadUpdate()
    } catch (error) {
      log.error('Auto update download failed', error)
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('update-error', error.toString())
      }
      return { skipped: false, error: error.message || String(error) }
    }
  })

  // 监听渲染进程触发的退出并安装
  ipcMain.handle('quitAndInstall', async () => {
    if (!autoUpdaterEnabled) return { skipped: true, reason: 'updater_disabled' }
    autoUpdater.quitAndInstall()
    return { ok: true }
  })
}

function resolveServerBinary() {
  const devCandidates = [
    path.join(process.cwd(), 'dist', 'log_filter_server'),
    path.join(process.cwd(), 'dist', 'log_filter_server.exe')
  ]
  for (const p of devCandidates) {
    try { if (fs.existsSync(p)) return p } catch (e) {}
  }
  const res = process.resourcesPath || process.cwd()
  const prodCandidates = [
    path.join(res, 'python', 'log_filter_server'),
    path.join(res, 'python', 'log_filter_server.exe')
  ]
  for (const p of prodCandidates) {
    try { if (fs.existsSync(p)) return p } catch (e) {}
  }
  return null
}

function wirePythonLogging(stream, level, prefix) {
  if (!stream) return
  let buffer = ''
  stream.on('data', function (chunk) {
    buffer += chunk.toString()
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() || ''
    for (const line of lines) {
      const message = line.trim()
      if (message) log[level](prefix + message)
    }
  })
  stream.on('end', function () {
    const message = buffer.trim()
    if (message) log[level](prefix + message)
  })
}

function startPython() {
  if (pyProc) return pyProc

  ensureDir(getRuntimeDataDir())
  const bin = resolveServerBinary()
  const runtimeDir = getRuntimeDataDir()
  const env = Object.assign({}, process.env, {
    LOG_FILTER_RUNTIME_DIR: runtimeDir,
    LOG_FILTER_RESOURCES_DIR: process.resourcesPath || process.cwd()
  })
  lastPythonState = 'starting'

  log.info('Starting backend server', { bin, runtimeDir, serverUrl: SERVER_URL })
  if (bin) {
    pyProc = spawn(bin, ['--port', String(PORT), '--host', HOST], { cwd: runtimeDir, env })
  } else {
    const script = path.join(process.cwd(), 'app.py')
    pyProc = spawn('python', [script, '--port', String(PORT), '--host', HOST], { cwd: runtimeDir, env })
  }

  pyProc.on('spawn', function () {
    lastPythonState = 'running pid=' + pyProc.pid
    log.info('Backend process started with pid', pyProc.pid)
  })
  pyProc.on('error', function (error) {
    lastPythonState = 'spawn error: ' + error.message
    log.error('Backend process failed to start', error)
  })
  pyProc.on('exit', function (code, signal) {
    lastPythonState = 'exited code=' + code + ' signal=' + signal
    log.info('Backend process exited', { code, signal })
    pyProc = null
  })
  wirePythonLogging(pyProc.stdout, 'info', '[backend] ')
  wirePythonLogging(pyProc.stderr, 'error', '[backend] ')

  return pyProc
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
        if (attempts >= retries) reject(new Error('server not ready after ' + attempts + ' attempts; ' + lastPythonState))
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
      sandbox: !LINUX_DISABLE_SANDBOX,
      webSecurity: true
    }
  })
  win.loadURL(createInlinePage('LogFilter 正在启动', '正在准备界面...'))
  mainWindow = win
  return win
}

async function loadMainApp(win, queryString) {
  if (!win || win.isDestroyed()) return
  const url = queryString ? SERVER_URL + queryString : SERVER_URL
  await win.loadURL(url)
}

async function bootstrapRenderer(win) {
  await showLoadingScreen(win)
  startPython()
  await waitForServer(SERVER_WAIT_RETRIES, SERVER_WAIT_INTERVAL)
  await loadMainApp(win)
}

function createMenu() {
  function exportRuntimeLogs() {
    const targetWindow = BrowserWindow.getFocusedWindow() || mainWindow
    if (!targetWindow || targetWindow.isDestroyed()) return
    targetWindow.webContents.executeJavaScript(`
      (function () {
        var btn = document.getElementById('export-runtime-logs-btn')
        if (!btn) return false
        btn.click()
        return true
      })();
    `).catch(function (error) {
      log.error('Failed to trigger runtime log export', error)
    })
  }
  const template = [
    { label: '文件', submenu: [
      { label: '打开日志目录', click: function () { shell.openPath(getAppSubdir('logs')) } },
      { label: '打开配置目录', click: function () { shell.openPath(getAppSubdir('configs')) } },
      { label: '打开配置组目录', click: function () { shell.openPath(getAppSubdir('config_groups')) } },
      { type: 'separator' },
      { label: '导出运行日志', click: exportRuntimeLogs },
      { type: 'separator' },
      { role: 'quit' }
    ] },
    { label: '视图', submenu: [
      { role: 'reload' },
      { role: 'toggleDevTools' },
      { role: 'resetZoom' },
      { role: 'zoomIn' },
      { role: 'zoomOut' },
      { role: 'togglefullscreen' }
    ] },
    { label: '帮助', submenu: [
      { label: '关于', click: function () {} }
    ] }
  ]
  const menu = Menu.buildFromTemplate(template)
  Menu.setApplicationMenu(menu)
}

app.on('ready', async function () {
  setupAutoUpdater()
  const win = createWindow()
  createMenu()
  try {
    await bootstrapRenderer(win)
  } catch (error) {
    log.error('Application bootstrap failed', error)
    await showStartupError(win, error)
  }
  if (app.isPackaged) {
    checkForUpdatesSafely()
  }
})

app.on('window-all-closed', function () { if (process.platform !== 'darwin') app.quit() })
app.on('activate', async function () {
  if (BrowserWindow.getAllWindows().length !== 0) return
  const win = createWindow()
  createMenu()
  try {
    await showLoadingScreen(win)
    await waitForServer(SERVER_WAIT_RETRIES, SERVER_WAIT_INTERVAL)
    await loadMainApp(win)
  } catch (error) {
    log.error('Failed to restore main window', error)
    await showStartupError(win, error)
  }
})
app.on('quit', function () { if (pyProc) { pyProc.kill(); pyProc = null } })

ipcMain.handle('openLogsDir', async function () { return shell.openPath(getAppSubdir('logs')) })

ipcMain.handle('handleDropFiles', async function (_evt, files) {
  try {
    if (!files || !files.length) return { ok: false }
    const destDir = getAppSubdir('logs')
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
      loadMainApp(mainWindow, '?open=' + encodeURIComponent(opened)).catch(function (error) {
        log.error('Failed to open dropped file', error)
      })
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
    const destDir = getAppSubdir('logs')
    const now = new Date()
    function pad(n) { return String(n).padStart(2, '0') }
    const name = (payload.name || 'log.txt')
    const ext = path.extname(name)
    const base = path.basename(name, ext)
    const stamped = `${base}_${now.getFullYear()}${pad(now.getMonth()+1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}${ext || '.log'}`
    const dest = path.join(destDir, stamped)
    try { fs.writeFileSync(dest, Buffer.from(payload.data)) } catch (e) { return { ok: false } }
    if (mainWindow) {
      loadMainApp(mainWindow, '?open=' + encodeURIComponent(stamped)).catch(function (error) {
        log.error('Failed to open dropped binary', error)
      })
      try { new Notification({ title: '日志复制成功', body: '已复制并重命名为: ' + stamped }).show() } catch (_) {}
    }
    return { ok: true, file: stamped }
  } catch (err) { return { ok: false } }
})
