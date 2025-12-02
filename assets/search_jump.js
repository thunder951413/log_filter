// search_jump.js - wire keyword search and line jump controls to rolling window
(function(){
  function isVisible(el) {
    if (!el) return false;
    var style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
    // also ensure it's in the layout tree
    if (!el.offsetParent && style.position !== 'fixed') return false;
    return true;
  }

  function getActiveLogWindow() {
    // Prefer the last VISIBLE log-window if multiple exist
    var nodes = document.querySelectorAll("div[id^='log-window-']");
    if (!nodes || nodes.length === 0) return null;
    for (var i = nodes.length - 1; i >= 0; i--) {
      if (isVisible(nodes[i])) return nodes[i];
    }
    // fallback to the last one
    return nodes[nodes.length - 1];
  }

  function getSessionId(div){
    if (!div) return null;
    var id = div.getAttribute('data-session-id') || div.id || '';
    var prefix = 'log-window-';
    if (id.indexOf(prefix) === 0) return id.slice(prefix.length);
    return div.getAttribute('data-session-id') || null;
  }

  function getCenterLine(sessionId){
    try {
      var reg = (window.__rollingRegistry || {})[sessionId];
      if (!reg) return null;
      var st = reg.getState();
      if (!st) return null;
      var start = parseInt(st.startLine || 1, 10);
      var end = parseInt(st.endLine || start, 10);
      var center = Math.floor((start + end) / 2);
      if (center < 1) center = 1;
      return center;
    } catch(e){ return null; }
  }

  function handleSearchNext() {
    var div = getActiveLogWindow();
    if (!div) { window.showToast && window.showToast('请先生成日志视图', 'warning'); return; }
    var sessionId = getSessionId(div);
    var reg = (window.__rollingRegistry || {})[sessionId];
    if (!sessionId || !reg) { window.showToast && window.showToast('滚动窗口未初始化', 'error'); return; }

    var input = document.getElementById('global-search-input');
    var kw = input ? String(input.value || '').trim() : '';
    if (!kw) { window.showToast && window.showToast('请输入关键字', 'warning'); return; }

    var center = getCenterLine(sessionId) || 1;
    var fromLine = center + 1;

    fetch('/api/search-next', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, keyword: kw, from_line: fromLine })
    })
    .then(function(r){ return r.json(); })
    .then(function(res){
      if (!res || res.success !== true) {
        window.showToast && window.showToast('搜索失败: ' + (res && res.error ? res.error : '未知错误'), 'error');
        return;
      }
      if (!res.match_line || res.match_line < 1) {
        window.showToast && window.showToast('未找到匹配项', 'info');
        return;
      }
      if (reg.setHighlightKeyword) {
        reg.setHighlightKeyword(kw);
      }
      reg.jumpToLine(res.match_line);
      window.showToast && window.showToast('定位到第 ' + res.match_line + ' 行', 'success', 2500);
    })
    .catch(function(err){ window.showToast && window.showToast('搜索异常: ' + err, 'error'); });
  }

  function handleSearchPrev() {
    var div = getActiveLogWindow();
    if (!div) { window.showToast && window.showToast('请先生成日志视图', 'warning'); return; }
    var sessionId = getSessionId(div);
    var reg = (window.__rollingRegistry || {})[sessionId];
    if (!sessionId || !reg) { window.showToast && window.showToast('滚动窗口未初始化', 'error'); return; }

    var input = document.getElementById('global-search-input');
    var kw = input ? String(input.value || '').trim() : '';
    if (!kw) { window.showToast && window.showToast('请输入关键字', 'warning'); return; }

    var center = getCenterLine(sessionId) || 1;
    var fromLine = Math.max(1, center); // 向上查找，从center之上开始（后端会用 fromLine-1 作为上界）

    fetch('/api/search-prev', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, keyword: kw, from_line: fromLine })
    })
    .then(function(r){ return r.json(); })
    .then(function(res){
      if (!res || res.success !== true) {
        window.showToast && window.showToast('搜索失败: ' + (res && res.error ? res.error : '未知错误'), 'error');
        return;
      }
      if (!res.match_line || res.match_line < 1) {
        window.showToast && window.showToast('未找到匹配项', 'info');
        return;
      }
      if (reg.setHighlightKeyword) {
        reg.setHighlightKeyword(kw);
      }
      reg.jumpToLine(res.match_line);
      window.showToast && window.showToast('定位到第 ' + res.match_line + ' 行', 'success', 2500);
    })
    .catch(function(err){ window.showToast && window.showToast('搜索异常: ' + err, 'error'); });
  }

  function handleJumpLine() {
    var div = getActiveLogWindow();
    if (!div) { window.showToast && window.showToast('请先生成日志视图', 'warning'); return; }
    var sessionId = getSessionId(div);
    var reg = (window.__rollingRegistry || {})[sessionId];
    if (!sessionId || !reg) { window.showToast && window.showToast('滚动窗口未初始化', 'error'); return; }

    var input = document.getElementById('jump-line-input');
    var val = input ? parseInt(input.value, 10) : NaN;
    if (!isFinite(val) || val < 1) { window.showToast && window.showToast('请输入有效的行号', 'warning'); return; }
    reg.jumpToLine(val);
  }

  function onKeyDown(e){
    if (e && e.key === 'Enter') {
      if (e.target && e.target.id === 'global-search-input') {
        handleSearchNext();
      } else if (e.target && e.target.id === 'jump-line-input') {
        handleJumpLine();
      }
    }
  }

  function bind() {
    document.addEventListener('click', function(e){
      var t = e.target;
      if (!t) return;
      if (t.id === 'global-search-btn') {
        handleSearchNext();
      } else if (t.id === 'global-search-prev-btn') {
        handleSearchPrev();
      } else if (t.id === 'jump-line-btn') {
        handleJumpLine();
      }
    });
    var si = document.getElementById('global-search-input');
    var ji = document.getElementById('jump-line-input');
    si && si.addEventListener('keydown', onKeyDown);
    ji && ji.addEventListener('keydown', onKeyDown);

    // also observe DOM changes to rebind keydown if inputs re-render
    var obs = new MutationObserver(function(){
      var si2 = document.getElementById('global-search-input');
      var ji2 = document.getElementById('jump-line-input');
      si2 && si2.removeEventListener && si2.addEventListener('keydown', onKeyDown);
      ji2 && ji2.removeEventListener && ji2.addEventListener('keydown', onKeyDown);
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();


