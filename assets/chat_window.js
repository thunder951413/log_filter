// Floating Chat Window — DeepSeek-style, drag, minimize, close, open
(function() {
  var win = null;
  var header = null;
  var fab = null;
  var chatInput = null;
  var sendBtn = null;
  var cwdInput = null;
  var cwdApplyBtn = null;
  var resizeHandle = null;
  var isDragging = false;
  var isResizing = false;
  var dragOffset = { x: 0, y: 0 };
  var resizeStart = { x: 0, y: 0, left: 0, top: 0, width: 0, height: 0 };
  var isMinimized = false;
  var sending = false;
  var activeAssistantBubble = null;
  var statusEl = null;
  var resizeObserver = null;
  var analysisRequestObserver = null;
  var lastAnalysisRequestId = '';
  var initialized = false;
  var STORAGE_KEY = 'log-filter-free-code-chat-session-id';
  var CWD_STORAGE_KEY = 'log-filter-free-code-chat-cwd';
  var SIZE_STORAGE_KEY = 'log-filter-free-code-chat-size';
  var CHAT_API_PREFIX = '/api/free-code';
  var DEFAULT_WIDTH = 440;
  var DEFAULT_HEIGHT = 580;
  var MIN_WIDTH = 360;
  var MIN_HEIGHT = 320;
  var WINDOW_MARGIN = 24;

  function init() {
    win = document.getElementById('chat-win');
    header = document.getElementById('chat-win-header');
    fab = document.getElementById('chat-win-open-btn');
    chatInput = document.getElementById('chat-input');
    sendBtn = document.getElementById('chat-send-btn');
    cwdInput = document.getElementById('chat-cwd-input');
    cwdApplyBtn = document.getElementById('chat-cwd-apply-btn');
    resizeHandle = document.getElementById('chat-win-resize-handle');
    if (!win || !header) return;

    statusEl = document.getElementById('chat-status');
    applyStoredSize();
    initResizeObserver();

    // Drag
    header.addEventListener('mousedown', onDragStart);
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('mouseup', onDragEnd);
    if (resizeHandle) resizeHandle.addEventListener('mousedown', onResizeStart);
    window.addEventListener('resize', onViewportResize);

    // Minimize
    var minBtn = document.getElementById('chat-win-minimize-btn');
    if (minBtn) minBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      toggleMinimize();
    });

    // Close
    var closeBtn = document.getElementById('chat-win-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', function(e) {
      e.stopPropagation();
      hideWin();
    });

    // FAB button to reopen
    if (fab) fab.addEventListener('click', function() { showWin(); });

    // Input auto-resize
    if (chatInput) {
      chatInput.addEventListener('input', autoResize);
      chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          if (sendBtn) sendBtn.click();
        }
      });
    }

    if (sendBtn) {
      sendBtn.addEventListener('click', function(e) {
        e.preventDefault();
        handleSend();
      });
    }

    if (cwdInput) {
      cwdInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleApplyWorkingDirectory();
        }
      });
    }

    if (cwdApplyBtn) {
      cwdApplyBtn.addEventListener('click', function(e) {
        e.preventDefault();
        handleApplyWorkingDirectory();
      });
    }

    ensureSessionId();
    loadChatConfig();

    // Expose API
    window.__chatWin = {
      show: showWin,
      hide: hideWin,
      addMessage: addMessage,
      addUserMessage: function(text) { addMessage(text, 'user'); },
      addAIMessage: function(text) { addMessage(text, 'ai'); },
      addAttachment: addAttachment,
      removeAttachment: removeAttachment,
      getAttachments: getAttachments,
      clearMessages: clearMessages,
      scrollToBottom: scrollToBottom,
      getSessionId: ensureSessionId,
      getWorkingDirectory: getWorkingDirectory,
      applyWorkingDirectory: handleApplyWorkingDirectory
    };
  }

  function autoResize() {
    if (!chatInput) return;
    chatInput.style.height = 'auto';
    chatInput.style.height = Math.min(chatInput.scrollHeight, 100) + 'px';
  }

  function addMessage(text, role) {
    var body = document.getElementById('log-chat-results');
    if (!body) return;
    var isAI = role === 'ai';
    var msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg chat-msg-' + (isAI ? 'ai' : 'user');

    var headerDiv = document.createElement('div');
    headerDiv.className = 'chat-msg-header';
    var avatar = document.createElement('span');
    avatar.className = 'chat-msg-avatar chat-msg-avatar-' + (isAI ? 'ai' : 'user');
    avatar.textContent = isAI ? '✦' : 'U';
    var name = document.createElement('span');
    name.className = 'chat-msg-name';
    name.textContent = isAI ? 'AI' : 'You';
    headerDiv.appendChild(avatar);
    headerDiv.appendChild(name);

    var bubble = document.createElement('div');
    bubble.className = 'chat-msg-bubble chat-msg-bubble-' + (isAI ? 'ai' : 'user');
    bubble.textContent = text;

    msgDiv.appendChild(headerDiv);
    msgDiv.appendChild(bubble);
    body.appendChild(msgDiv);
    scrollToBottom();
  }

  function createAssistantBubble() {
    var body = document.getElementById('log-chat-results');
    if (!body) return null;

    var msgDiv = document.createElement('div');
    msgDiv.className = 'chat-msg chat-msg-ai';

    var headerDiv = document.createElement('div');
    headerDiv.className = 'chat-msg-header';

    var avatar = document.createElement('span');
    avatar.className = 'chat-msg-avatar chat-msg-avatar-ai';
    avatar.textContent = '✦';

    var name = document.createElement('span');
    name.className = 'chat-msg-name';
    name.textContent = 'free-code';

    headerDiv.appendChild(avatar);
    headerDiv.appendChild(name);

    var bubble = document.createElement('div');
    bubble.className = 'chat-msg-bubble chat-msg-bubble-ai';
    bubble.textContent = '';

    msgDiv.appendChild(headerDiv);
    msgDiv.appendChild(bubble);
    body.appendChild(msgDiv);
    scrollToBottom();
    return bubble;
  }

  function clearMessages() {
    var body = document.getElementById('log-chat-results');
    if (body) body.innerHTML = '';
    activeAssistantBubble = null;
  }

  var _attachments = [];
  var _attachId = 0;

  function addAttachment(text, label) {
    var container = document.getElementById('chat-attachments');
    if (!container) return;
    var id = 'chat-attach-' + (++_attachId);
    _attachments.push({ id: id, text: text });

    var docIcon = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#888" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>';

    var el = document.createElement('div');
    el.className = 'chat-attachment';
    el.id = id;
    el.setAttribute('data-text', text);
    var displayLabel = label || ('日志 ' + _attachments.length);
    var preview = text.length > 80 ? text.substring(0, 80) + '...' : text;
    el.innerHTML =
      '<div class="chat-attachment-icon">' + docIcon + '<span class="chat-attachment-label">' + displayLabel + '</span></div>' +
      '<div class="chat-attachment-preview">' + escapeHtml(preview) + '</div>' +
      '<button class="chat-attachment-remove" data-attach-id="' + id + '">✕</button>';

    el.querySelector('.chat-attachment-remove').addEventListener('click', function(e) {
      e.stopPropagation();
      removeAttachment(this.getAttribute('data-attach-id'));
    });

    container.appendChild(el);
    return id;
  }

  function removeAttachment(id) {
    _attachments = _attachments.filter(function(a) { return a.id !== id; });
    var el = document.getElementById(id);
    if (el) el.parentElement.removeChild(el);
  }

  function getAttachments() {
    return _attachments.map(function(a) {
      var el = document.getElementById(a.id);
      var labelEl = el ? el.querySelector('.chat-attachment-label') : null;
      return {
        text: a.text,
        label: labelEl ? labelEl.textContent : ''
      };
    });
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function scrollToBottom() {
    var body = document.getElementById('log-chat-results');
    if (body) body.scrollTop = body.scrollHeight;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || '';
    statusEl.classList.toggle('chat-status-error', !!isError);
  }

  function getMaxWidth() {
    return Math.max(MIN_WIDTH, window.innerWidth - WINDOW_MARGIN);
  }

  function getMaxHeight() {
    return Math.max(MIN_HEIGHT, window.innerHeight - WINDOW_MARGIN);
  }

  function clampWidth(value) {
    return Math.max(MIN_WIDTH, Math.min(value, getMaxWidth()));
  }

  function clampHeight(value) {
    return Math.max(MIN_HEIGHT, Math.min(value, getMaxHeight()));
  }

  function saveWindowSize() {
    if (!win || isMinimized) return;
    var size = {
      width: Math.round(win.offsetWidth),
      height: Math.round(win.offsetHeight)
    };
    window.localStorage.setItem(SIZE_STORAGE_KEY, JSON.stringify(size));
  }

  function applyWindowSize(width, height) {
    if (!win) return;
    win.style.width = clampWidth(width) + 'px';
    win.style.height = clampHeight(height) + 'px';
  }

  function applyStoredSize() {
    if (!win) return;
    try {
      var raw = window.localStorage.getItem(SIZE_STORAGE_KEY);
      if (!raw) return;
      var size = JSON.parse(raw);
      if (!size || typeof size.width !== 'number' || typeof size.height !== 'number') return;
      applyWindowSize(size.width, size.height);
    } catch (error) {
      window.localStorage.removeItem(SIZE_STORAGE_KEY);
    }
  }

  function initResizeObserver() {
    if (!win || typeof window.ResizeObserver !== 'function') return;
    resizeObserver = new window.ResizeObserver(function() {
      if (!win.classList.contains('chat-win-visible') || isMinimized) return;
      saveWindowSize();
      resetPosition();
    });
    resizeObserver.observe(win);
  }

  function setSending(next) {
    sending = !!next;
    if (chatInput) chatInput.disabled = sending;
    if (sendBtn) sendBtn.disabled = sending;
    if (sendBtn) sendBtn.textContent = sending ? '...' : '↑';
    if (cwdInput) cwdInput.disabled = sending;
    if (cwdApplyBtn) cwdApplyBtn.disabled = sending;
  }

  function makeSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return 'log-filter-' + window.crypto.randomUUID();
    }
    return 'log-filter-' + String(Date.now());
  }

  function ensureSessionId() {
    var value = window.localStorage.getItem(STORAGE_KEY);
    if (!value) {
      value = makeSessionId();
      window.localStorage.setItem(STORAGE_KEY, value);
    }
    return value;
  }

  function replaceSessionId() {
    var next = makeSessionId();
    window.localStorage.setItem(STORAGE_KEY, next);
    return next;
  }

  function getStoredWorkingDirectory() {
    return (window.localStorage.getItem(CWD_STORAGE_KEY) || '').trim();
  }

  function setStoredWorkingDirectory(value) {
    var normalized = String(value || '').trim();
    if (normalized) {
      window.localStorage.setItem(CWD_STORAGE_KEY, normalized);
    } else {
      window.localStorage.removeItem(CWD_STORAGE_KEY);
    }
  }

  function setWorkingDirectoryInput(value) {
    if (cwdInput) cwdInput.value = value || '';
  }

  function getWorkingDirectory() {
    if (cwdInput && cwdInput.value.trim()) return cwdInput.value.trim();
    return getStoredWorkingDirectory();
  }

  async function requestChatConfig(cwd) {
    var hasCustomCwd = typeof cwd === 'string' && cwd.trim() !== '';
    var url = CHAT_API_PREFIX + '/config';
    var options = {};

    if (hasCustomCwd) {
      options = {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cwd: cwd.trim() })
      };
    }

    var response = await fetch(url, options);
    var data = await parseJsonResponse(response);
    if (!response.ok || !data.ok) {
      throw new Error((data && data.error) || '工作目录配置失败');
    }
    return data;
  }

  async function parseJsonResponse(response) {
    var text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (error) {
      return { error: text };
    }
  }

  async function loadChatConfig() {
    setStatus('正在加载 free-code 配置...');
    try {
      var preferredCwd = getStoredWorkingDirectory();
      var data = await requestChatConfig(preferredCwd);
      setStoredWorkingDirectory(data.cwd);
      setWorkingDirectoryInput(data.cwd);
      setStatus('当前工作目录：' + data.cwd);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error), true);
    }
  }

  async function closeSession(sessionId) {
    if (!sessionId) return;
    try {
      await fetch(CHAT_API_PREFIX + '/sessions/' + encodeURIComponent(sessionId), {
        method: 'DELETE'
      });
    } catch (error) {
      console.warn('close session failed:', error);
    }
  }

  async function handleApplyWorkingDirectory() {
    if (sending) return;
    var requestedCwd = getWorkingDirectory();
    setStatus('正在切换工作目录...');
    try {
      var currentSessionId = window.localStorage.getItem(STORAGE_KEY);
      var data = await requestChatConfig(requestedCwd);
      await closeSession(currentSessionId);
      replaceSessionId();
      setStoredWorkingDirectory(data.cwd);
      setWorkingDirectoryInput(data.cwd);
      clearMessages();
      addMessage('工作目录已切换为：' + data.cwd + '。已开启新会话，你可以直接让我分析这里的代码。', 'ai');
      setStatus('当前工作目录：' + data.cwd);
      if (chatInput) chatInput.focus();
    } catch (error) {
      setStatus(error instanceof Error ? error.message : String(error), true);
    }
  }

  function extractAssistantText(event) {
    if (!event || typeof event !== 'object') return '';
    if (event.type === 'assistant_partial') {
      return typeof event.delta === 'string' ? event.delta : '';
    }
    var message = event.message;
    if (!message) return '';
    if (typeof message.content === 'string') return message.content;
    if (!Array.isArray(message.content)) return '';

    return message.content
      .filter(function(block) {
        return block && block.type === 'text' && typeof block.text === 'string';
      })
      .map(function(block) { return block.text; })
      .join('');
  }

  function getCurrentConfigGroup() {
    var el = document.getElementById('log-filter-config-group-selector');
    return el && typeof el.value === 'string' ? el.value : '';
  }

  function getCurrentDisplayMode() {
    var el = document.getElementById('display-mode-tabs');
    return el && typeof el.getAttribute === 'function' ? (el.getAttribute('active_tab') || 'filtered') : 'filtered';
  }

  function buildStreamPayload(message, extraPayload) {
    var basePayload = {
      message: message,
      attachments: getAttachments(),
      timeout: 180,
      cwd: getWorkingDirectory(),
      config_group: getCurrentConfigGroup(),
      display_mode: getCurrentDisplayMode()
    };
    if (!extraPayload || typeof extraPayload !== 'object') {
      return basePayload;
    }
    var merged = Object.assign({}, basePayload, extraPayload);
    if (!Array.isArray(merged.attachments)) {
      merged.attachments = [];
    }
    if (!merged.config_group && merged.analysis_context && typeof merged.analysis_context.config_group === 'string') {
      merged.config_group = merged.analysis_context.config_group;
    }
    if (!merged.display_mode && merged.analysis_context && typeof merged.analysis_context.display_mode === 'string') {
      merged.display_mode = merged.analysis_context.display_mode;
    }
    return merged;
  }

  async function runStreamRequest(userVisibleMessage, payload) {
    if (sending) {
      setStatus('上一轮分析尚未完成', true);
      return;
    }
    if (userVisibleMessage) {
      addMessage(userVisibleMessage, 'user');
    }
    showWin();
    activeAssistantBubble = null;
    setSending(true);
    setStatus('正在连接 free-code...');

    try {
      await streamMessage(payload);
      setStatus('本轮完成');
    } catch (error) {
      addMessage(error instanceof Error ? error.message : String(error), 'ai');
      setStatus('请求失败', true);
    } finally {
      activeAssistantBubble = null;
      setSending(false);
      if (chatInput) chatInput.focus();
    }
  }

  function buildAnalysisSummary(payload) {
    var ctx = payload && payload.analysis_context && typeof payload.analysis_context === 'object'
      ? payload.analysis_context
      : {};
    var mode = ctx.display_mode === 'filtered' ? '过滤结果' : '源文件';
    var group = ctx.config_group || '未选择配置组';
    var lineCount = ctx.selected_line_count || 0;
    return '[AI分析所选日志] ' + mode + ' / 配置组: ' + group + ' / ' + lineCount + ' 行';
  }

  async function handleExternalAnalysisPayload(rawText) {
    if (!rawText) return;
    var payload;
    try {
      payload = JSON.parse(rawText);
    } catch (error) {
      setStatus('日志分析请求解析失败', true);
      return;
    }
    if (!payload || typeof payload !== 'object') return;
    if (!payload.request_id || payload.request_id === lastAnalysisRequestId) return;
    lastAnalysisRequestId = payload.request_id;
    await runStreamRequest(buildAnalysisSummary(payload), buildStreamPayload(payload.message || '', payload));
  }

  function initAnalysisRequestListener() {
    var target = document.getElementById('log-analysis-context-json');
    if (!target) return false;
    if (analysisRequestObserver) analysisRequestObserver.disconnect();
    analysisRequestObserver = new MutationObserver(function() {
      handleExternalAnalysisPayload(target.textContent || '');
    });
    analysisRequestObserver.observe(target, {
      childList: true,
      characterData: true,
      subtree: true
    });
    return true;
  }

  async function handleSend() {
    if (sending || !chatInput) return;
    var message = (chatInput.value || '').trim();
    if (!message) return;

    chatInput.value = '';
    autoResize();
    await runStreamRequest(message, buildStreamPayload(message));
  }

  async function streamMessage(requestPayload) {
    var sessionId = ensureSessionId();
    var cwd = requestPayload && requestPayload.cwd ? requestPayload.cwd : getWorkingDirectory();
    var response = await fetch(
      CHAT_API_PREFIX + '/chat/' + encodeURIComponent(sessionId) + '/stream',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestPayload)
      }
    );

    if (!response.ok || !response.body) {
      var errorText = await response.text();
      throw new Error(errorText || '请求失败');
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder('utf-8');
    var buffer = '';

    while (true) {
      var result = await reader.read();
      if (result.done) break;

      buffer += decoder.decode(result.value, { stream: true });
      var chunks = buffer.split('\n\n');
      buffer = chunks.pop() || '';

      for (var i = 0; i < chunks.length; i++) {
        var chunk = chunks[i];
        if (!chunk.startsWith('data: ')) continue;
        var event = JSON.parse(chunk.slice(6));

        if (event.type === 'assistant' || event.type === 'assistant_partial') {
          var text = extractAssistantText(event);
          if (text) {
            if (!activeAssistantBubble) {
              activeAssistantBubble = createAssistantBubble();
            }
            if (activeAssistantBubble) {
              activeAssistantBubble.textContent += text;
              scrollToBottom();
            }
          }
          continue;
        }

        if (event.type === 'system' && event.subtype === 'init') {
          setStatus('已连接，模型：' + (event.model || 'unknown') + '，工作目录：' + (cwd || '默认'));
          continue;
        }

        if (event.type === 'result') {
          return;
        }

        if (event.type === 'error') {
          throw new Error(event.error || '未知错误');
        }
      }
    }
  }

  function updateFab() {
    if (!fab) return;
    var isVisible = win.classList.contains('chat-win-visible') && !isMinimized;
    fab.style.display = isVisible ? 'none' : 'flex';
  }

  function showWin() {
    if (!win) return;
    win.classList.remove('chat-win-hidden');
    win.classList.add('chat-win-visible');
    if (isMinimized) {
      isMinimized = false;
      win.classList.remove('chat-win-minimized');
      resetPosition();
    }
    updateFab();
    scrollToBottom();
  }

  function hideWin() {
    if (!win) return;
    win.classList.remove('chat-win-visible');
    win.classList.add('chat-win-hidden');
    isMinimized = false;
    win.classList.remove('chat-win-minimized');
    updateFab();
  }

  function toggleMinimize() {
    hideWin();
  }

  function resetPosition() {
    var rect = win.getBoundingClientRect();
    if (rect.left < 0 || rect.top < 0 || rect.right > window.innerWidth || rect.bottom > window.innerHeight) {
      win.style.left = '';
      win.style.top = '';
      win.style.right = '24px';
      win.style.bottom = '24px';
    }
  }

  function onViewportResize() {
    if (!win || isMinimized) return;
    applyWindowSize(win.offsetWidth || DEFAULT_WIDTH, win.offsetHeight || DEFAULT_HEIGHT);
    resetPosition();
    saveWindowSize();
  }

  function onDragStart(e) {
    if (isMinimized) return;
    if (e.target.closest('.chat-win-btn')) return;
    if (e.target.closest('.chat-win-resize-handle')) return;
    isDragging = true;
    var rect = win.getBoundingClientRect();
    dragOffset.x = e.clientX - rect.left;
    dragOffset.y = e.clientY - rect.top;
    win.classList.add('chat-win-dragging');
    win.style.right = 'auto';
    win.style.bottom = 'auto';
    win.style.left = rect.left + 'px';
    win.style.top = rect.top + 'px';
    e.preventDefault();
  }

  function onDragMove(e) {
    onResizeMove(e);
    if (!isDragging) return;
    var x = e.clientX - dragOffset.x;
    var y = e.clientY - dragOffset.y;
    x = Math.max(0, Math.min(x, window.innerWidth - win.offsetWidth));
    y = Math.max(0, Math.min(y, window.innerHeight - 40));
    win.style.left = x + 'px';
    win.style.top = y + 'px';
  }

  function onDragEnd() {
    onResizeEnd();
    if (isDragging) {
      isDragging = false;
      win.classList.remove('chat-win-dragging');
    }
  }

  function onResizeStart(e) {
    if (isMinimized || !win) return;
    var rect = win.getBoundingClientRect();
    isResizing = true;
    resizeStart.x = e.clientX;
    resizeStart.y = e.clientY;
    resizeStart.left = rect.left;
    resizeStart.top = rect.top;
    resizeStart.width = rect.width;
    resizeStart.height = rect.height;
    win.classList.add('chat-win-resizing');
    win.style.right = 'auto';
    win.style.bottom = 'auto';
    win.style.left = rect.left + 'px';
    win.style.top = rect.top + 'px';
    e.preventDefault();
    e.stopPropagation();
  }

  function onResizeMove(e) {
    if (!isResizing || !win) return;

    var dx = e.clientX - resizeStart.x;
    var dy = e.clientY - resizeStart.y;
    var rightEdge = resizeStart.left + resizeStart.width;
    var bottomEdge = resizeStart.top + resizeStart.height;
    var minLeftByMaxWidth = rightEdge - getMaxWidth();
    var minTopByMaxHeight = bottomEdge - getMaxHeight();
    var maxLeft = rightEdge - MIN_WIDTH;
    var maxTop = bottomEdge - MIN_HEIGHT;

    var nextLeft = resizeStart.left + dx;
    var nextTop = resizeStart.top + dy;

    nextLeft = Math.max(minLeftByMaxWidth, Math.min(maxLeft, nextLeft));
    nextTop = Math.max(minTopByMaxHeight, Math.min(maxTop, nextTop));
    nextLeft = Math.max(0, nextLeft);
    nextTop = Math.max(0, nextTop);

    var nextWidth = rightEdge - nextLeft;
    var nextHeight = bottomEdge - nextTop;

    win.style.left = nextLeft + 'px';
    win.style.top = nextTop + 'px';
    applyWindowSize(nextWidth, nextHeight);
  }

  function onResizeEnd() {
    if (!isResizing || !win) return;
    isResizing = false;
    win.classList.remove('chat-win-resizing');
    saveWindowSize();
    resetPosition();
  }

  // Init on DOM ready or after Dash renders
  function tryInit() {
    if (document.getElementById('chat-win')) {
      if (!initialized) {
        init();
        initialized = true;
      }
      if (!initAnalysisRequestListener()) {
        setTimeout(tryInit, 300);
      }
    } else {
      setTimeout(tryInit, 300);
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInit);
  } else {
    tryInit();
  }
})();
