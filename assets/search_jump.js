// search_jump.js - wire keyword search and line jump controls to rolling window
(function(){
  var searchState = {
    requestToken: 0,
    busy: false,
    cache: {},
    cacheOrder: [],
    cacheLimit: 40,
    highlightTimer: null
  };

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
      var actualCenter = parseInt(st.centerLine || 0, 10);
      if (actualCenter > 0) return actualCenter;
      var start = parseInt(st.startLine || 1, 10);
      var end = parseInt(st.endLine || start, 10);
      var center = Math.floor((start + end) / 2);
      if (center < 1) center = 1;
      return center;
    } catch(e){ return null; }
  }

  function getActiveRegistry() {
    var div = getActiveLogWindow();
    if (!div) return null;
    var sessionId = getSessionId(div);
    var reg = (window.__rollingRegistry || {})[sessionId];
    if (!sessionId || !reg) return null;
    return { div: div, sessionId: sessionId, reg: reg };
  }

  function makeCacheKey(sessionId, direction, keyword, fromLine) {
    return [sessionId || '', direction || '', keyword || '', parseInt(fromLine || 0, 10) || 0].join('|');
  }

  function readCachedResult(sessionId, direction, keyword, fromLine) {
    var key = makeCacheKey(sessionId, direction, keyword, fromLine);
    return searchState.cache[key];
  }

  function writeCachedResult(sessionId, direction, keyword, fromLine, result) {
    var key = makeCacheKey(sessionId, direction, keyword, fromLine);
    if (!searchState.cache[key]) {
      searchState.cacheOrder.push(key);
      if (searchState.cacheOrder.length > searchState.cacheLimit) {
        delete searchState.cache[searchState.cacheOrder.shift()];
      }
    }
    searchState.cache[key] = result;
  }

  function applySearchHighlight(keyword, refresh) {
    var active = getActiveRegistry();
    if (!active) return;
    if (!active.reg.setHighlightKeyword) return;
    active.reg.setHighlightKeyword(keyword || null, { refresh: refresh === true });
  }

  function setSearchStatus(text, titleText) {
    var el = document.getElementById('search-hit-status');
    if (!el) return;
    el.textContent = text || '( - / - )';
    el.title = titleText || '';
  }

  function resetSearchStatus() {
    setSearchStatus('( - / - )', '');
  }

  function updateSearchStatus(result, direction, keyword) {
    var totalMatches = parseInt((result && result.total_matches) || 0, 10) || 0;
    var matchIndex = parseInt((result && result.match_index) || 0, 10) || 0;
    var cursorIndex = parseInt((result && result.cursor_match_index) || 0, 10) || 0;
    var keywordText = keyword ? ('关键字: ' + keyword) : '';
    if (totalMatches <= 0) {
      setSearchStatus('( 0 / 0 )', keywordText);
      return;
    }
    if (matchIndex > 0) {
      setSearchStatus('( ' + matchIndex + ' / ' + totalMatches + ' )', keywordText + ' · 第 ' + matchIndex + ' 个命中');
      return;
    }
    if (direction === 'prev') {
      setSearchStatus('( 0 / ' + totalMatches + ' )', keywordText + ' · 已到第一个命中之前');
      return;
    }
    setSearchStatus('( ' + cursorIndex + ' / ' + totalMatches + ' )', keywordText + ' · 已到最后一个命中之后');
  }

  function scheduleHighlightRefresh() {
    if (searchState.highlightTimer) {
      clearTimeout(searchState.highlightTimer);
    }
    searchState.highlightTimer = setTimeout(function(){
      var input = document.getElementById('global-search-input');
      var keyword = input ? String(input.value || '').trim() : '';
      applySearchHighlight(keyword, true);
      if (!keyword) {
        resetSearchStatus();
      } else {
        setSearchStatus('( - / - )', '关键字: ' + keyword);
      }
    }, 180);
  }

  function performSearch(direction) {
    var active = getActiveRegistry();
    if (!active) { window.showToast && window.showToast('滚动窗口未初始化', 'error'); return; }
    var sessionId = active.sessionId;
    var reg = active.reg;

    var input = document.getElementById('global-search-input');
    var kw = input ? String(input.value || '').trim() : '';
    if (!kw) { window.showToast && window.showToast('请输入关键字', 'warning'); return; }
    if (searchState.busy) { return; }

    var center = getCenterLine(sessionId) || 1;
    var fromLine = direction === 'prev' ? Math.max(1, center) : (center + 1);
    var endpoint = direction === 'prev' ? '/api/search-prev' : '/api/search-next';
    var token = ++searchState.requestToken;
    var cached = readCachedResult(sessionId, direction, kw, fromLine);
    applySearchHighlight(kw, false);
    if (cached) {
      updateSearchStatus(cached, direction, kw);
      if (cached.match_line && cached.match_line > 0) {
        reg.jumpToLine(cached.match_line, { behavior: 'smooth' });
        window.showToast && window.showToast('定位到第 ' + cached.match_line + ' 行', 'success', 2500);
      } else {
        window.showToast && window.showToast('未找到匹配项', 'info');
      }
      return;
    }
    searchState.busy = true;

    fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, keyword: kw, from_line: fromLine })
    })
    .then(function(r){ return r.json(); })
    .then(function(res){
      if (token !== searchState.requestToken) return;
      if (!res || res.success !== true) {
        resetSearchStatus();
        window.showToast && window.showToast('搜索失败: ' + (res && res.error ? res.error : '未知错误'), 'error');
        return;
      }
      writeCachedResult(sessionId, direction, kw, fromLine, res);
      updateSearchStatus(res, direction, kw);
      if (!res.match_line || res.match_line < 1) {
        window.showToast && window.showToast('未找到匹配项', 'info');
        return;
      }
      reg.jumpToLine(res.match_line, { behavior: 'smooth' });
      window.showToast && window.showToast('定位到第 ' + res.match_line + ' 行', 'success', 2500);
    })
    .catch(function(err){
      if (token !== searchState.requestToken) return;
      resetSearchStatus();
      window.showToast && window.showToast('搜索异常: ' + err, 'error');
    })
    .finally(function(){
      if (token === searchState.requestToken) {
        searchState.busy = false;
      }
    });
  }

  function handleSearchNext() {
    performSearch('next');
  }

  function handleSearchPrev() {
    performSearch('prev');
  }

  function handleJumpLine() {
    var active = getActiveRegistry();
    if (!active) { window.showToast && window.showToast('滚动窗口未初始化', 'error'); return; }
    var reg = active.reg;

    var input = document.getElementById('jump-line-input');
    var val = input ? parseInt(input.value, 10) : NaN;
    if (!isFinite(val) || val < 1) { window.showToast && window.showToast('请输入有效的行号', 'warning'); return; }
    reg.jumpToLine(val, { behavior: 'smooth' });
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
      } else if (t.id === 'quick-top-btn') {
        try {
          var div = getActiveLogWindow();
          if (!div) { window.scrollTo && window.scrollTo(0,0); return; }
          var sessionId = getSessionId(div);
          var reg = (window.__rollingRegistry || {})[sessionId];
          if (!sessionId || !reg) { window.scrollTo && window.scrollTo(0,0); return; }
          reg.jumpToLine(1);
        } catch(e){ window.showToast && window.showToast('跳转顶部失败: ' + e, 'error'); }
      } else if (t.id === 'quick-bottom-btn') {
        try {
          var div2 = getActiveLogWindow();
          if (!div2) { var h=(document.documentElement&&document.documentElement.scrollHeight)||document.body.scrollHeight||0; window.scrollTo && window.scrollTo(0,h); return; }
          var sessionId2 = getSessionId(div2);
          var reg2 = (window.__rollingRegistry || {})[sessionId2];
          if (!sessionId2 || !reg2) { var h2=(document.documentElement&&document.documentElement.scrollHeight)||document.body.scrollHeight||0; window.scrollTo && window.scrollTo(0,h2); return; }
          var st = reg2.getState ? reg2.getState() : null;
          var total = (st && parseInt(st.totalLines || 0, 10)) || 0;
          if (!total || total < 1) {
            // fallback to current window end
            total = (st && parseInt(st.endLine || 1, 10)) || 1;
          }
          var bottomTarget = Math.max(1, total - 30);
          reg2.jumpToLine(bottomTarget);
        } catch(e){ window.showToast && window.showToast('跳转底部失败: ' + e, 'error'); }
      }
    });
    var si = document.getElementById('global-search-input');
    var ji = document.getElementById('jump-line-input');
    si && si.addEventListener('keydown', onKeyDown);
    ji && ji.addEventListener('keydown', onKeyDown);
    si && si.addEventListener('input', scheduleHighlightRefresh);
    resetSearchStatus();

    // also observe DOM changes to rebind keydown if inputs re-render
    var obs = new MutationObserver(function(){
      var si2 = document.getElementById('global-search-input');
      var ji2 = document.getElementById('jump-line-input');
      si2 && si2.removeEventListener && si2.addEventListener('keydown', onKeyDown);
      ji2 && ji2.removeEventListener && ji2.addEventListener('keydown', onKeyDown);
      si2 && si2.addEventListener('input', scheduleHighlightRefresh);
    });
    obs.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bind);
  } else {
    bind();
  }
})();
