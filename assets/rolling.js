// rolling.js - client-side rolling window for large log view
// This file runs automatically by Dash (assets folder). No inline scripts needed.

(function () {
  var OBSERVER = null;
  // Persist last known center line per session across DOM re-renders (e.g., tab/mode switches)
  window.__savedCentersBySession = window.__savedCentersBySession || {};

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

  function preTopInContainer(preEl, container) {
    if (!container || container === window) {
      return preTopInDocument(preEl);
    }
    var preRect = preEl.getBoundingClientRect();
    var conRect = container.getBoundingClientRect();
    return preRect.top - conRect.top + container.scrollTop;
  }

  function elTopInContainer(el, container) {
    if (!container || container === window) {
      var rect = el.getBoundingClientRect();
      return rect.top + docScrollTop();
    }
    var elRect = el.getBoundingClientRect();
    var conRect = container.getBoundingClientRect();
    return elRect.top - conRect.top + container.scrollTop;
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
      endLine: Math.min(windowSize, parseInt(div.getAttribute('data-total-lines') || '0', 10) || windowSize),
      centerLine: null,
      highlightKeyword: null
    };

    console.log('[前端滚动窗口][assets] 初始化:', { sessionId: sessionId, windowSize: windowSize, state: state });

    function ensureStructure() {
      var topPad = div.querySelector('.pad-top');
      var pre = div.querySelector('pre');
      var bottomPad = div.querySelector('.pad-bottom');
      var changed = false;
      if (!topPad) { topPad = document.createElement('div'); topPad.className = 'pad-top'; topPad.style.height = '0px'; changed = true; }
      if (!pre) { pre = document.createElement('pre'); pre.className = 'small'; changed = true; }
      if (!bottomPad) { bottomPad = document.createElement('div'); bottomPad.className = 'pad-bottom'; bottomPad.style.height = '0px'; changed = true; }
      if (changed) {
        div.innerHTML = '';
        div.appendChild(topPad);
        div.appendChild(pre);
        div.appendChild(bottomPad);
      }
      return { topPad: topPad, pre: pre, bottomPad: bottomPad };
    }

    // Determine the primary scroll target once per setup
    var scrollTarget = (function(){
      try {
        var s = findScrollableAncestor(div);
        return s || window;
      } catch(e) { return window; }
    })();

    function getDocScrollHeight() {
      var de = document.documentElement, db = document.body;
      return Math.max(
        de ? de.scrollHeight : 0,
        db ? db.scrollHeight : 0
      );
    }

    function isVisible(el) {
      if (!el) return false;
      var style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
      if (!el.offsetParent && style.position !== 'fixed') return false;
      return true;
    }

    function updateStatusDisplay() {
      try {
        var el = document.getElementById('log-window-line-status');
        if (!el) return;
        // Only the visible rolling instance should update the shared status
        if (!isVisible(div)) return;
        var c = parseInt(state.centerLine || 0, 10) || 0;
        var t = parseInt(state.totalLines || 0, 10) || 0;
        if (c <= 0 || t <= 0) {
          el.textContent = '( - / - / -% )';
        } else {
          var pct = Math.max(0, Math.min(100, (c / t) * 100));
          var pctText = pct.toFixed(1) + '%';
          el.textContent = '(' + c + ' / ' + t + ' / ' + pctText + ')';
        }
      } catch (e) {}
    }

    function loadRange(startLine, endLine, anchorArg) {
      if (state.isLoading) return;
      state.isLoading = true;
      var payload = { session_id: sessionId, start_line: startLine, end_line: endLine };
      if (state.highlightKeyword) {
        payload.highlight_keyword = state.highlightKeyword;
      }
      console.log('[前端滚动窗口][assets] 请求窗口:', payload);
      fetch('/api/get-log-window', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload)
      })
      .then(function(r){ return r.json(); })
      .then(function(data){
        if (data && data.success) {
          var prevStart = state.startLine;
          var prevEnd = state.endLine;
          state.startLine = data.start_line; state.endLine = data.end_line; state.totalLines = data.total_lines || state.totalLines;

          var nodes = ensureStructure();
          var pre = nodes.pre;
          var topPad = nodes.topPad;
          var bottomPad = nodes.bottomPad;
          if (data && data.is_html) {
            pre.innerHTML = data.content || '';
          } else {
            pre.textContent = data.content || '';
          }

          var lh = getLineHeight(pre);
          var viewportHeight = (scrollTarget === window) ? window.innerHeight : scrollTarget.clientHeight;

          // Make scrollbar reflect only current window (virtualized within window)
          topPad.style.height = '0px';
          bottomPad.style.height = '0px';

          // Anchor handling: prefer absolute center line; fallback to ratio within window
          var opts = anchorArg;
          var isOpts = opts && typeof opts === 'object' && (opts.mode || typeof opts.centerLine === 'number' || typeof opts.ratio === 'number');
          var anchorCenterLine;
          if (isOpts && typeof opts.centerLine === 'number' && isFinite(opts.centerLine)) {
            var cl = Math.floor(opts.centerLine);
            // clamp within new window just in case
            var minL = (data.start_line || 1);
            var maxL = (data.end_line || minL);
            if (cl < minL) cl = minL;
            if (cl > maxL) cl = maxL;
            anchorCenterLine = cl;
          } else if (isOpts && typeof opts.ratio === 'number') {
            var spanNew = Math.max(1, (data.end_line || 0) - (data.start_line || 0));
            var r = Math.max(0, Math.min(1, opts.ratio));
            anchorCenterLine = Math.round((data.start_line || 1) + r * spanNew);
          } else {
            anchorCenterLine = (typeof anchorArg === 'number') ? anchorArg : (data.start_line + Math.floor((data.end_line - data.start_line + 1) / 2));
          }
          // Compute offset: support 'top' mode (place anchor line at top), otherwise center by default
          var offsetWithinPre;
          if (isOpts && opts.mode === 'top') {
            // place the anchor line at the very top of the viewport within the pre element
            offsetWithinPre = (anchorCenterLine - data.start_line) * lh;
          } else {
            // center mode (default): place the anchor line at the center of the viewport
            offsetWithinPre = (anchorCenterLine - data.start_line) * lh - ((viewportHeight / 2) - lh / 2);
          }
          var isTopMode = isOpts && opts && opts.mode === 'top';
          if (scrollTarget === window) {
            var docH = getDocScrollHeight();
            if (docH > window.innerHeight + 1) {
              var targetScrollY = preTopInDocument(pre) + offsetWithinPre;
              window.scrollTo(0, Math.max(0, targetScrollY));
            }
          } else {
            if (isTopMode) {
              scrollTarget.scrollTop = 0;
            } else {
              var preTop = preTopInContainer(pre, scrollTarget);
              var targetScrollTop = preTop + offsetWithinPre;
              if (scrollTarget.scrollHeight > scrollTarget.clientHeight + 1) {
                scrollTarget.scrollTop = Math.max(0, targetScrollTop);
              }
            }
          }
          var centerLogged = (typeof anchorCenterLine !== 'undefined' ? anchorCenterLine : undefined);
          state.centerLine = centerLogged || null;
          // Persist current center line for this session
          try { window.__savedCentersBySession[sessionId] = state.centerLine; } catch(e) {}
          console.log('[前端滚动窗口][assets] 窗口更新:', { start: data.start_line, end: data.end_line, center: centerLogged, total: state.totalLines });
          updateStatusDisplay();
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

      var currentScrollTop = (scrollTarget === window) ? docScrollTop() : scrollTarget.scrollTop;
      var viewportHeight = (scrollTarget === window) ? window.innerHeight : scrollTarget.clientHeight;

      // Compute center strictly within the currently loaded window (pre)
      var preTop = (scrollTarget === window) ? preTopInDocument(pre) : preTopInContainer(pre, scrollTarget);
      var topPxInPre = Math.max(0, currentScrollTop - preTop);
      var visibleLines = Math.max(1, Math.floor(viewportHeight / lh));
      var loadedLineCount = Math.max(1, (state.endLine || 0) - (state.startLine || 0) + 1);
      var topLineInLoaded = Math.min(loadedLineCount, Math.max(1, Math.floor(topPxInPre / lh) + 1));
      var centerInLoaded = Math.min(loadedLineCount, Math.max(1, topLineInLoaded + Math.floor(visibleLines / 2)));
      var centerGlobal = state.startLine + centerInLoaded - 1;

      console.log('[前端滚动窗口][assets] 滚动检测', { centerGlobal: centerGlobal, start: state.startLine, end: state.endLine, visibleLines: visibleLines, lh: lh });
      state.centerLine = centerGlobal;
      // Persist current center line for this session
      try { window.__savedCentersBySession[sessionId] = centerGlobal; } catch(e) {}
      updateStatusDisplay();

      // 后端调试打印
      try {
        fetch('/api/scroll-debug', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            center_line: centerGlobal,
            window_start: state.startLine,
            window_end: state.endLine,
            doc_scroll_top: currentScrollTop,
            pre_top_in_doc: preTop,
            top_px_in_pre: topPxInPre,
            visible_lines: visibleLines,
            line_height: lh
          })
        });
      } catch(e) {}

      // 计算当前滚动容器高度信息
      var margin = Math.min(prefetchThreshold, Math.floor(((state.endLine || 0) - (state.startLine || 0) + 1) / 3));
      var scrollHeightNow = (scrollTarget === window) ? (function(){ var de=document.documentElement, db=document.body; return Math.max(de?de.scrollHeight:0, db?db.scrollHeight:0); })() : scrollTarget.scrollHeight;
      var metrics = {
        scrollTop: currentScrollTop,
        clientHeight: viewportHeight,
        scrollHeight: scrollHeightNow,
        distanceToBottom: Math.max(0, scrollHeightNow - (currentScrollTop + viewportHeight))
      };

      // 若已完整加载（已加载行数 >= 总行数），则不触发窗口切换，避免“小文件”视图里滑块被自动回拉
      var loadedCountNow = Math.max(1, (state.endLine || 0) - (state.startLine || 0) + 1);
      var isFullyLoadedNow = (state.totalLines > 0) && (loadedCountNow >= state.totalLines);

      if (!isFullyLoadedNow && margin > 0) {
        if (centerGlobal > state.endLine - margin) {
          var span1 = Math.max(1, (state.endLine || 0) - (state.startLine || 0));
          var ratio1 = Math.max(0, Math.min(1, (centerGlobal - (state.startLine || 1)) / span1));
          var ns = Math.max(1, centerGlobal - linesBefore);
          var ne = Math.min((state.totalLines || (ns + linesBefore + linesAfter)), centerGlobal + linesAfter);
          if (ne < ns) ne = ns + linesBefore + linesAfter; // fallback safety
          // 保持底部滚动体验，默认以居中锚定
          loadRange(ns, ne, { centerLine: centerGlobal, ratio: ratio1 });
        } else if (centerGlobal < state.startLine + margin && state.startLine > 1) {
          var span2 = Math.max(1, (state.endLine || 0) - (state.startLine || 0));
          var ratio2 = Math.max(0, Math.min(1, (centerGlobal - (state.startLine || 1)) / span2));
          var ns2 = Math.max(1, centerGlobal - linesBefore);
          var ne2 = Math.min((state.totalLines || (ns2 + linesBefore + linesAfter)), centerGlobal + linesAfter);
          if (ne2 < ns2) ne2 = ns2 + linesBefore + linesAfter; // fallback safety
          // 当用户处于容器顶部附近时，使用 'top' 模式对齐，避免自动回到底部
          var nearTopByContainer = currentScrollTop <= 2;
          var nearTopByPre = topPxInPre <= Math.max(1, Math.floor(lh / 2));
          var anchorOpts = nearTopByContainer || nearTopByPre
            ? { centerLine: centerGlobal, ratio: ratio2, mode: 'top' }
            : { centerLine: centerGlobal, ratio: ratio2 };
          loadRange(ns2, ne2, anchorOpts);
        }
      }
    }, 120);

    function findScrollableAncestor(el) {
      var node = el; var limit = 10;
      while (node && limit-- > 0) {
        var style = window.getComputedStyle(node);
        var overflowY = style.overflowY;
        if (overflowY === 'auto' || overflowY === 'scroll') {
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
    if (scrollTarget && scrollTarget !== window) {
      scrollTarget.addEventListener('scroll', onScroll, { passive: true });
      console.log('[前端滚动窗口][assets] 已检测滚动容器:', scrollTarget);
    }

    // Fire once to seed values
    try { onScroll(); } catch (e) {}
    // initialize status once
    try { updateStatusDisplay(); } catch (e) {}
    // Force-load initial window:
    // - On first view (no saved center), place scrollbar at the very top (line 1)
    // - When revisiting the same session, restore to the previously saved center line
    try {
      var savedCenters = window.__savedCentersBySession || {};
      var saved = savedCenters[sessionId];
      var initialCenter = (typeof saved === 'number' && isFinite(saved)) ? Math.max(1, Math.floor(saved)) : 1;
      var initialMode = (typeof saved === 'number' && isFinite(saved)) ? 'center' : 'top';
      loadRange(state.startLine, state.endLine, { centerLine: initialCenter, mode: initialMode });
    } catch (e) {}

    // Expose simple registry for external controls (search/jump)
    try {
      window.__rollingRegistry = window.__rollingRegistry || {};
      window.__rollingRegistry[sessionId] = {
        // Set temporary highlight keyword for search
        setHighlightKeyword: function(kw) { state.highlightKeyword = kw; },
        // Jump to make targetLine the visual center (within available bounds)
        jumpToLine: function(targetLine) {
          var tl = parseInt(targetLine, 10);
          if (!isFinite(tl)) return;
          if (tl < 1) tl = 1;
          var total = state.totalLines || (state.endLine || 0);
          if (total && tl > total) tl = total;
          var ns = Math.max(1, tl - linesBefore);
          var ne = Math.min(total || (ns + linesBefore + linesAfter), tl + linesAfter);
          if (ne < ns) ne = ns + linesBefore + linesAfter;
          loadRange(ns, ne, { centerLine: tl });
        },
        // Current loaded window state (copy)
        getState: function() { return { startLine: state.startLine, endLine: state.endLine, totalLines: state.totalLines, isLoading: state.isLoading }; },
        // Rolling parameters
        getConfig: function() { return { linesBefore: linesBefore, linesAfter: linesAfter, prefetchThreshold: prefetchThreshold }; }
      };
    } catch(e) { console.warn('[前端滚动窗口][assets] 注册外部控制失败:', e); }
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

