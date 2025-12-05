const { spawnSync } = require('child_process')
const path = require('path')
const fs = require('fs')

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

function run(cmd, args, cwd) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', cwd: cwd || process.cwd() })
  if (r.status !== 0) { process.exit(r.status || 1) }
}

function buildBackend(platform, dry) {
  const args = buildPyArgs(platform)
  if (dry) { console.log(['pyinstaller'].concat(args).join(' ')); return }
  if (exists('pyinstaller')) { run('pyinstaller', args) } else { run('python', ['-m', 'PyInstaller'].concat(args)) }
}

function buildFrontendMac(dry) { const args = ['--mac', 'dmg,zip']; if (dry) { console.log(['electron-builder'].concat(args).join(' ')); return } run('npx', ['electron-builder'].concat(args)) }
function buildFrontendWin(dry) { const args = ['--win', 'nsis']; if (dry) { console.log(['electron-builder'].concat(args).join(' ')); return } run('npx', ['electron-builder'].concat(args)) }
function buildFrontendLinux(dry) { const args = ['--linux', 'AppImage']; if (dry) { console.log(['electron-builder'].concat(args).join(' ')); return } run('npx', ['electron-builder'].concat(args)) }

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
