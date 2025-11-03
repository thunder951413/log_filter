// rolling.js - client-side rolling window for large log view
// This file runs automatically by Dash (assets folder). No inline scripts needed.

(function () {
  var OBSERVER = null;

  function debounce(fn, wait) {
    var t; return function () { clearTimeout(t); var args = arguments, self = this; t = setTimeout(function(){ fn.apply(self, args); }, wait); };
  }

  function parseSessionIdFromId(id) {
    // id pattern: log-window-<sessionId>
    var idx = (id || '').indexOf('log-window-');
    if (idx === 0) return id.slice('log-window-'.length);
    return null;
  }

  function getLineHeight(preEl) {
    var lh = parseFloat(window.getComputedStyle(preEl).lineHeight);
    if (!isFinite(lh) || lh <= 0) return 16;
    return lh;
  }

  function docScrollTop() {
    return window.scrollY || document.documentElement.scrollTop || 0;
  }

  function preTopInDocument(preEl) {
    var rect = preEl.getBoundingClientRect();
    return rect.top + docScrollTop();
  }

  function setup(div) {
    var sessionId = div.getAttribute('data-session-id') || parseSessionIdFromId(div.id);
    var windowSize = parseInt(div.getAttribute('data-window-size') || '500', 10);
    var linesBefore = parseInt(div.getAttribute('data-lines-before') || '', 10);
    var linesAfter = parseInt(div.getAttribute('data-lines-after') || '', 10);
    var prefetchThreshold = parseInt(div.getAttribute('data-prefetch-threshold') || '', 10);

    if (!isFinite(linesBefore)) {
      linesBefore = Math.floor(windowSize / 2);
    }
    if (!isFinite(linesAfter)) {
      var rest = windowSize - linesBefore - 1;
      linesAfter = rest >= 0 ? rest : Math.max(0, Math.floor(windowSize / 2) - 1);
    }
    if (!isFinite(prefetchThreshold)) {
      prefetchThreshold = Math.floor(windowSize / 4);
    }

    var state = {
      isLoading: false,
      totalLines: parseInt(div.getAttribute('data-total-lines') || '0', 10) || 0,
      startLine: 1,
      endLine: Math.min(windowSize, parseInt(div.getAttribute('data-total-lines') || '0', 10) || windowSize)
    };

    console.log('[前端滚动窗口][assets] 初始化:', { sessionId: sessionId, windowSize: windowSize, state: state });

    function loadRange(startLine, endLine, anchorCenterLine) {
      if (state.isLoading) return;
      state.isLoading = true;
      var payload = { session_id: sessionId, start_line: startLine, end_line: endLine };
      console.log('[前端滚动窗口][assets] 请求窗口:', payload);
      fetch('/api/get-log-window', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      })
      .then(function(r){ return r.json(); })
      .then(function(data){
        if (data && data.success) {
          state.startLine = data.start_line; state.endLine = data.end_line; state.totalLines = data.total_lines || state.totalLines;

          var pre = div.querySelector('pre');
          if (!pre) { pre = document.createElement('pre'); pre.className = 'small'; div.innerHTML = ''; div.appendChild(pre); }
          pre.textContent = data.content || '';

          var lh = getLineHeight(pre);
          var targetScrollY = preTopInDocument(pre) + (anchorCenterLine - data.start_line) * lh - (window.innerHeight / 2 - lh / 2);
          window.scrollTo(0, Math.max(0, targetScrollY));

          console.log('[前端滚动窗口][assets] 窗口更新:', { start: data.start_line, end: data.end_line, center: anchorCenterLine, total: state.totalLines });
        } else {
          console.error('[前端滚动窗口][assets] 响应失败:', data && data.error);
        }
      })
      .catch(function(err){ console.error('[前端滚动窗口][assets] 请求异常:', err); })
      .finally(function(){ state.isLoading = false; });
    }

    var onScroll = debounce(function(){
      var pre = div.querySelector('pre'); if (!pre) return;
      var lh = getLineHeight(pre);
      var preTop = preTopInDocument(pre);
      var topPxInPre = Math.max(0, docScrollTop() - preTop);
      var visibleLines = Math.max(1, Math.floor(window.innerHeight / lh));
      var topLineInLoaded = Math.floor(topPxInPre / lh) + 1;
      var centerInLoaded = topLineInLoaded + Math.floor(visibleLines / 2);
      var centerGlobal = state.startLine + centerInLoaded - 1;

      console.log('[前端滚动窗口][assets] 滚动检测', { centerGlobal: centerGlobal, start: state.startLine, end: state.endLine, visibleLines: visibleLines, lh: lh });

      // 后端调试打印
      try {
        fetch('/api/scroll-debug', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            center_line: centerGlobal,
            window_start: state.startLine,
            window_end: state.endLine,
            doc_scroll_top: docScrollTop(),
            pre_top_in_doc: preTop,
            top_px_in_pre: topPxInPre,
            visible_lines: visibleLines,
            line_height: lh
          })
        });
      } catch(e) {}

      var margin = prefetchThreshold;
      if (centerGlobal > state.endLine - margin) {
        var ns = Math.max(1, centerGlobal - linesBefore);
        var ne = Math.min((state.totalLines || (ns + linesBefore + linesAfter)), centerGlobal + linesAfter);
        if (ne < ns) ne = ns + linesBefore + linesAfter; // fallback safety
        loadRange(ns, ne, centerGlobal);
      } else if (centerGlobal < state.startLine + margin && state.startLine > 1) {
        var ns2 = Math.max(1, centerGlobal - linesBefore);
        var ne2 = Math.min((state.totalLines || (ns2 + linesBefore + linesAfter)), centerGlobal + linesAfter);
        if (ne2 < ns2) ne2 = ns2 + linesBefore + linesAfter; // fallback safety
        loadRange(ns2, ne2, centerGlobal);
      }
    }, 120);

    function findScrollableAncestor(el) {
      var node = el; var limit = 10;
      while (node && limit-- > 0) {
        var style = window.getComputedStyle(node);
        var overflowY = style.overflowY;
        if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
          return node;
        }
        node = node.parentElement;
      }
      return null;
    }

    // Attach listeners to multiple potential scrollers
    window.addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('scroll', onScroll, { passive: true });
    document.documentElement && document.documentElement.addEventListener('scroll', onScroll, { passive: true });
    document.body && document.body.addEventListener('scroll', onScroll, { passive: true });
    div.addEventListener('scroll', onScroll, { passive: true });
    var scrollable = findScrollableAncestor(div);
    if (scrollable) {
      scrollable.addEventListener('scroll', onScroll, { passive: true });
      console.log('[前端滚动窗口][assets] 已检测滚动容器:', scrollable); 
    }

    // Fire once to seed values
    try { onScroll(); } catch (e) {}
  }

  function bootstrap() {
    var nodes = document.querySelectorAll("div[id^='log-window-']");
    nodes.forEach(function(div){
      if (!div.__rollingSetup) { div.__rollingSetup = true; setup(div); }
    });

    if (OBSERVER) OBSERVER.disconnect();
    OBSERVER = new MutationObserver(function(muts){
      muts.forEach(function(m){
        m.addedNodes && Array.prototype.forEach.call(m.addedNodes, function(n){
          if (n.nodeType === 1 && /^log-window-/.test(n.id || '')) {
            if (!n.__rollingSetup) { n.__rollingSetup = true; setup(n); }
          } else if (n.querySelectorAll) {
            var matches = n.querySelectorAll("div[id^='log-window-']");
            matches.forEach(function(div){ if (!div.__rollingSetup) { div.__rollingSetup = true; setup(div); } });
          }
        });
      });
    });
    OBSERVER.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})();


