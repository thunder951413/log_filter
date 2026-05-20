(function () {
  'use strict';

  var dragDepth = 0;
  var overlayId = 'log-filter-drop-overlay';
  var allowed = /\.(txt|log|text)$/i;

  function isFilterTabActive() {
    var tab = document.querySelector('#main-tabs .nav-link.active');
    return !!(tab && tab.textContent && tab.textContent.indexOf('日志过滤') !== -1);
  }

  function isElectronRuntime() {
    return !!(window.electronAPI && window.electronAPI.openLogsDir);
  }

  function hasElectronFilePaths(event) {
    var files = event && event.dataTransfer && event.dataTransfer.files;
    if (!files || !files.length) return false;
    for (var i = 0; i < files.length; i++) {
      if (files[i] && files[i].path) return true;
    }
    return false;
  }

  function ensureOverlay() {
    var el = document.getElementById(overlayId);
    if (el) return el;
    el = document.createElement('div');
    el.id = overlayId;
    el.className = 'log-filter-drop-overlay';
    el.innerHTML = '<div class="log-filter-drop-card"><div class="log-filter-drop-icon">+</div><div class="log-filter-drop-title">释放以上传日志</div><div class="log-filter-drop-subtitle">支持文件或目录，目录结构会保留</div></div>';
    document.body.appendChild(el);
    return el;
  }

  function showOverlay() {
    ensureOverlay().classList.add('show');
  }

  function hideOverlay() {
    var el = document.getElementById(overlayId);
    if (el) el.classList.remove('show');
  }

  function showToast(message, type) {
    if (window.showToast) {
      window.showToast(message, type || 'info');
      return;
    }
    console.log('[log drop]', message);
  }

  function readEntries(entry, prefix) {
    prefix = prefix || '';
    return new Promise(function (resolve) {
      if (!entry) {
        resolve([]);
        return;
      }
      if (entry.isFile) {
        entry.file(function (file) {
          if (!allowed.test(file.name || '')) {
            resolve([]);
            return;
          }
          var relativePath = (prefix ? prefix + '/' : '') + (file.name || 'log.log');
          resolve([{ file: file, path: relativePath }]);
        }, function () { resolve([]); });
        return;
      }
      if (entry.isDirectory) {
        var reader = entry.createReader();
        var all = [];
        function readBatch() {
          reader.readEntries(function (entries) {
            if (!entries.length) {
              Promise.all(all).then(function (groups) {
                resolve([].concat.apply([], groups));
              });
              return;
            }
            for (var i = 0; i < entries.length; i++) {
              all.push(readEntries(entries[i], (prefix ? prefix + '/' : '') + entry.name));
            }
            readBatch();
          }, function () { resolve([]); });
        }
        readBatch();
        return;
      }
      resolve([]);
    });
  }

  function collectDroppedFiles(dataTransfer) {
    var items = dataTransfer && dataTransfer.items;
    if (items && items.length) {
      var jobs = [];
      for (var i = 0; i < items.length; i++) {
        var item = items[i];
        if (!item) continue;
        var entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        if (entry) {
          jobs.push(readEntries(entry, ''));
        } else if (item.kind === 'file') {
          var file = item.getAsFile();
          if (file && allowed.test(file.name || '')) jobs.push(Promise.resolve([{ file: file, path: file.name }]));
        }
      }
      return Promise.all(jobs).then(function (groups) {
        return [].concat.apply([], groups);
      });
    }

    var files = dataTransfer && dataTransfer.files;
    var result = [];
    for (var j = 0; files && j < files.length; j++) {
      var f = files[j];
      if (f && allowed.test(f.name || '')) {
        result.push({ file: f, path: f.webkitRelativePath || f.name });
      }
    }
    return Promise.resolve(result);
  }

  function uploadFiles(files) {
    if (!files.length) {
      showToast('未找到支持的日志文件', 'warning');
      return;
    }
    var form = new FormData();
    files.forEach(function (item) {
      form.append('files', item.file, item.file.name || 'log.log');
      form.append('relative_paths', item.path || item.file.name || 'log.log');
    });
    showToast('正在上传日志...', 'info');
    fetch('/api/upload-log-files', { method: 'POST', body: form })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok || !result.data || !result.data.imported || !result.data.imported.length) {
          throw new Error((result.data && result.data.error) || '上传失败');
        }
        var imported = result.data.imported;
        showToast('已导入 ' + imported.length + ' 个日志文件', 'success');
        var url = new URL(window.location.href);
        url.searchParams.set('open', imported[0]);
        window.history.replaceState(null, '', url.toString());
        window.dispatchEvent(new PopStateEvent('popstate'));
        window.location.search = url.search;
      })
      .catch(function (err) {
        showToast('上传日志失败: ' + (err && err.message ? err.message : err), 'error');
      });
  }

  document.addEventListener('dragenter', function (event) {
    if (isElectronRuntime() || !isFilterTabActive() || hasElectronFilePaths(event)) return;
    dragDepth += 1;
    showOverlay();
  });

  document.addEventListener('dragover', function (event) {
    if (isElectronRuntime() || !isFilterTabActive() || hasElectronFilePaths(event)) return;
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
    showOverlay();
  });

  document.addEventListener('dragleave', function () {
    dragDepth -= 1;
    if (dragDepth <= 0) {
      dragDepth = 0;
      hideOverlay();
    }
  });

  document.addEventListener('drop', function (event) {
    if (isElectronRuntime() || !isFilterTabActive() || hasElectronFilePaths(event)) return;
    event.preventDefault();
    dragDepth = 0;
    hideOverlay();
    collectDroppedFiles(event.dataTransfer).then(uploadFiles);
  });
})();
