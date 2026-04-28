// Log text selection context menu (Chat / Copy)
(function() {
  var menuEl = null;
  var VISIBLE_CLASS = 'log-ctx-menu-visible';

  function createMenu() {
    if (menuEl) return menuEl;
    menuEl = document.createElement('div');
    menuEl.id = 'log-ctx-menu';
    menuEl.className = 'log-ctx-menu';
    menuEl.innerHTML =
      '<button class="log-ctx-item" data-action="chat">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>' +
        'Chat' +
      '</button>' +
      '<button class="log-ctx-item" data-action="copy">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px;vertical-align:-2px"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
        'Copy' +
      '</button>';
    document.body.appendChild(menuEl);

    menuEl.addEventListener('mousedown', function(e) {
      e.stopPropagation();
    });

    menuEl.addEventListener('click', function(e) {
      var btn = e.target.closest('[data-action]');
      if (!btn) return;
      var action = btn.getAttribute('data-action');
      var sel = window.getSelection();
      var text = sel ? sel.toString().trim() : '';
      if (!text) { hideMenu(); return; }

      if (action === 'copy') {
        navigator.clipboard.writeText(text).then(function() {
          showToast('已复制到剪贴板');
        }).catch(function() {
          // fallback
          var ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          showToast('已复制到剪贴板');
        });
      } else if (action === 'chat') {
        // Store selected text globally for Dash to pick up
        window.__selectedLogTextForChat = text;
        // Trigger Dash callback via hidden div
        var chatInput = document.getElementById('chat-selected-text-input');
        if (chatInput) {
          chatInput.textContent = text;
          chatInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        // Open floating Chat window and add log attachment
        if (window.__chatWin) {
          window.__chatWin.show();
          window.__chatWin.addAttachment(text, '日志片段 (' + text.length + '字)');
        }
      }
      hideMenu();
    });

    return menuEl;
  }

  function showToast(msg) {
    var t = document.createElement('div');
    t.className = 'log-ctx-toast';
    t.textContent = msg;
    document.body.appendChild(t);
    requestAnimationFrame(function() { t.classList.add('show'); });
    setTimeout(function() {
      t.classList.remove('show');
      setTimeout(function() { document.body.removeChild(t); }, 200);
    }, 1500);
  }

  function showMenu(x, y) {
    var menu = createMenu();
    menu.style.left = x + 'px';
    menu.style.top = y + 'px';
    menu.classList.add(VISIBLE_CLASS);
  }

  function hideMenu() {
    if (menuEl) menuEl.classList.remove(VISIBLE_CLASS);
  }

  function isInsideLogView(el) {
    if (!el) return false;
    // Check if inside filtered results, source view, or log-window
    var node = el;
    var limit = 15;
    while (node && limit-- > 0) {
      var id = node.id || '';
      if (id.indexOf('log-window-') === 0) return true;
      if (id === 'log-filter-results') return true;
      if (id === 'log-source-results') return true;
      node = node.parentElement;
    }
    return false;
  }

  // Listen for mouseup to detect text selection
  document.addEventListener('mouseup', function(e) {
    // Small delay to let browser finalize selection
    setTimeout(function() {
      var sel = window.getSelection();
      var text = sel ? sel.toString().trim() : '';
      if (!text || text.length === 0) { hideMenu(); return; }

      // Check if selection is inside a log view
      var anchor = sel.anchorNode;
      if (!anchor || !isInsideLogView(anchor.parentElement || anchor)) {
        hideMenu();
        return;
      }

      // Get selection bounding rect
      var range = sel.getRangeAt(0);
      var rect = range.getBoundingClientRect();

      // Position menu below the selection
      var x = rect.left + rect.width / 2 - 50;
      var y = rect.bottom + 6;

      // Keep menu within viewport
      x = Math.max(8, Math.min(x, window.innerWidth - 120));
      y = Math.min(y, window.innerHeight - 50);

      showMenu(x, y);
    }, 10);
  });

  // Hide menu on scroll, click outside, or selection change
  document.addEventListener('mousedown', function(e) {
    if (menuEl && !menuEl.contains(e.target)) {
      hideMenu();
    }
  });

  document.addEventListener('scroll', function() {
    hideMenu();
  }, true);

  // Hide when selection is cleared
  document.addEventListener('selectionchange', function() {
    var sel = window.getSelection();
    if (!sel || sel.toString().trim().length === 0) {
      hideMenu();
    }
  });
})();
