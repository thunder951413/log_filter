const { spawnSync } = require('child_process')
const path = require('path')
const fs = require('fs')

const RG_VERSION = '15.1.0'
const RG_ARCHIVE_NAME = `ripgrep-${RG_VERSION}-x86_64-pc-windows-msvc.zip`
const RG_EXTRACTED_DIR = `ripgrep-${RG_VERSION}-x86_64-pc-windows-msvc`
const RG_DOWNLOAD_URL = `https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/${RG_ARCHIVE_NAME}`
const RG_LICENSE_FILES = ['LICENSE-MIT', 'UNLICENSE']

function sepForPlatform(p) { return p === 'win32' ? ';' : ':' }

function buildPyArgs(platform) {
  const sep = sepForPlatform(platform)
  const addData = [
    `assets${sep}assets`,
    `configs${sep}configs`,
    `config_groups${sep}config_groups`,
    `flows.json${sep}.`,
    `keyword_annotations.json${sep}.`,
    `settings.json${sep}.`,
    `string_data.json${sep}.`
  ]
  const args = ['-F', '-n', 'log_filter_server', 'app.py']
  for (const d of addData) { args.push('--add-data'); args.push(d) }
  return args
}

function exists(cmd) {
  try { const which = process.platform === 'win32' ? 'where' : 'which'; const r = spawnSync(which, [cmd], { stdio: 'ignore' }); return r.status === 0 } catch (e) { return false }
}

function useShell(cmd) { return process.platform === 'win32' && (cmd === 'npm' || cmd === 'npx') }

function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: cwd || process.cwd(), shell: useShell(cmd) })
  if (r.error) {
    console.error(r.error.message)
    process.exit(1)
  }
  if (r.status !== 0) { process.exit(r.status || 1) }
}

function pickPowerShell() {
  if (process.platform !== 'win32') return null
  if (exists('pwsh')) return 'pwsh'
  if (exists('powershell')) return 'powershell'
  return null
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function removePath(target) {
  fs.rmSync(target, { recursive: true, force: true })
}

function copyFile(source, target) {
  ensureDir(path.dirname(target))
  fs.copyFileSync(source, target)
}

function psQuote(value) {
  return `'${String(value).replace(/'/g, "''")}'`
}

function prepareBundledRgWindows(dry) {
  if (process.platform !== 'win32') return
  const shell = pickPowerShell()
  if (!shell) {
    console.error('未找到可用的 PowerShell，无法准备 ripgrep')
    process.exit(1)
  }
  const cacheRoot = path.join(process.cwd(), '.cache', 'ripgrep', 'windows-x64', RG_VERSION)
  const archivePath = path.join(cacheRoot, RG_ARCHIVE_NAME)
  const extractRoot = path.join(cacheRoot, 'extract')
  const extractedDir = path.join(extractRoot, RG_EXTRACTED_DIR)
  const bundleDir = path.join(process.cwd(), 'vendor', 'ripgrep', 'windows-x64')
  if (dry) {
    console.log(`prepare-rg ${RG_DOWNLOAD_URL} -> ${bundleDir}`)
    return
  }
  ensureDir(cacheRoot)
  if (!fs.existsSync(path.join(extractedDir, 'rg.exe'))) {
    if (!fs.existsSync(archivePath)) {
      run(shell, ['-NoProfile', '-Command', `Invoke-WebRequest -Uri ${psQuote(RG_DOWNLOAD_URL)} -OutFile ${psQuote(archivePath)}`])
    }
    removePath(extractRoot)
    ensureDir(extractRoot)
    run(shell, ['-NoProfile', '-Command', `Expand-Archive -Path ${psQuote(archivePath)} -DestinationPath ${psQuote(extractRoot)} -Force`])
  }
  ensureDir(bundleDir)
  copyFile(path.join(extractedDir, 'rg.exe'), path.join(bundleDir, 'rg.exe'))
  for (const name of RG_LICENSE_FILES) {
    const source = path.join(extractedDir, name)
    if (fs.existsSync(source)) {
      copyFile(source, path.join(bundleDir, name))
    }
  }
}

function buildBackend(platform, dry) {
  const args = buildPyArgs(platform)
  if (dry) { console.log(['pyinstaller'].concat(args).join(' ')); return }
  if (exists('pyinstaller')) { run('pyinstaller', args) } else { run('python', ['-m', 'PyInstaller'].concat(args)) }
}

function buildFrontendMac(dry) { const args = ['--mac', 'dmg', 'zip']; if (dry) { console.log(['electron-builder'].concat(args).join(' ')); return } run('npx', ['electron-builder'].concat(args)) }
function buildFrontendWin(dry) { const args = ['--win', 'nsis', '--x64']; if (dry) { prepareBundledRgWindows(true); console.log(['electron-builder'].concat(args).join(' ')); return } prepareBundledRgWindows(false); run('npx', ['electron-builder'].concat(args)) }
function buildFrontendLinux(dry) { const args = ['--linux', 'tar.gz']; if (dry) { console.log(['electron-builder'].concat(args).join(' ')); return } run('npx', ['electron-builder'].concat(args)) }

function main() {
  const argv = process.argv.slice(2)
  const dry = argv.includes('dry-run')
  const targets = argv.filter(x => x !== 'dry-run')
  const plat = process.platform
  function doMac() { buildBackend('darwin', dry); buildFrontendMac(dry) }
  function doWin() { buildBackend('win32', dry); buildFrontendWin(dry) }
  function doLinux() { buildBackend('linux', dry); buildFrontendLinux(dry) }
  if (targets.length === 0) {
    if (plat === 'darwin') doMac(); else if (plat === 'win32') doWin(); else doLinux()
    return
  }
  if (targets.includes('all')) { doMac(); doWin(); doLinux(); return }
  if (targets.includes('mac')) doMac()
  if (targets.includes('win')) doWin()
  if (targets.includes('linux')) doLinux()
}

main()
