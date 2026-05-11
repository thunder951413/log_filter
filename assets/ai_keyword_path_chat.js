// AI Keyword Logic Path Modal Chat — uses the same free-code streaming API as the main floating AI chat
(function() {
  var CHAT_API_PREFIX = '/api/free-code';
  var SESSION_KEY = 'log-filter-ai-keyword-path-chat-session-id';
  var messages = [];
  var sending = false;
  var initialized = false;

  function byId(id) {
    return document.getElementById(id);
  }

  function ensureSessionId() {
    var existing = window.localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    var created = 'ai-keyword-path-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    window.localStorage.setItem(SESSION_KEY, created);
    return created;
  }

  function resetSession() {
    var created = 'ai-keyword-path-' + Date.now() + '-' + Math.random().toString(16).slice(2);
    window.localStorage.setItem(SESSION_KEY, created);
    return created;
  }

  function getCwd() {
    var el = byId('ai-keyword-data-path-input');
    return el ? (el.value || '').trim() : '';
  }

  function getDefaultPrompt() {
    var el = byId('ai-keyword-path-default-prompt-input');
    return el ? (el.value || '').trim() : '';
  }

  function getTargetDefaultPrompt() {
    var el = byId('ai-keyword-target-default-prompt-input');
    return el ? (el.value || '').trim() : '';
  }

  function getUserInput() {
    var el = byId('ai-keyword-path-chat-input');
    return el ? (el.value || '').trim() : '';
  }

  function getTargetAnalysisInput() {
    var el = byId('ai-keyword-target-analysis-input');
    return el ? (el.value || '').trim() : '';
  }

  function clearUserInput() {
    var el = byId('ai-keyword-path-chat-input');
    if (el) el.value = '';
  }

  function setStatus(text, isError) {
    var el = byId('ai-keyword-status');
    if (!el) return;
    el.textContent = text || '';
    el.className = isError ? 'text-danger small mt-2' : 'text-muted small mt-2';
  }

  function renderEmpty() {
    var container = byId('ai-keyword-path-chat-container');
    if (!container) return;
    if (messages.length === 0) {
      container.innerHTML = '<div class="text-muted">请描述你希望分析的功能、模块或日志场景。</div>';
    }
  }

  function scrollToBottom() {
    var container = byId('ai-keyword-path-chat-container');
    if (container) container.scrollTop = container.scrollHeight;
  }

  function clearChatDom() {
    var container = byId('ai-keyword-path-chat-container');
    if (container) container.innerHTML = '';
  }

  function addMessage(text, role) {
    var container = byId('ai-keyword-path-chat-container');
    if (!container) return null;
    if (messages.length === 0 && container.querySelector('.text-muted')) {
      container.innerHTML = '';
    }

    var isUser = role === 'user';
    var wrapper = document.createElement('div');
    wrapper.className = isUser ? 'p-2 rounded mb-2 bg-primary text-white ms-auto' : 'p-2 rounded mb-2 bg-light border';
    wrapper.style.maxWidth = '85%';

    var title = document.createElement('div');
    title.className = 'fw-bold small mb-1';
    title.textContent = isUser ? '用户' : 'AI';

    var content = document.createElement('div');
    content.style.whiteSpace = 'pre-wrap';
    content.textContent = text || '';

    wrapper.appendChild(title);
    wrapper.appendChild(content);
    container.appendChild(wrapper);
    scrollToBottom();
    return content;
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
      .filter(function(block) { return block && block.type === 'text' && typeof block.text === 'string'; })
      .map(function(block) { return block.text; })
      .join('');
  }

  async function streamFreeCode(message, cwd, onText) {
    var sessionId = ensureSessionId();
    var response = await fetch(CHAT_API_PREFIX + '/chat/' + encodeURIComponent(sessionId) + '/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, cwd: cwd, timeout: 600, attachments: [] })
    });

    if (!response.ok || !response.body) {
      var errorText = await response.text();
      throw new Error(errorText || '请求失败');
    }

    var reader = response.body.getReader();
    var decoder = new TextDecoder('utf-8');
    var buffer = '';
    var fullText = '';

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
            fullText += text;
            if (onText) onText(text);
          }
          continue;
        }
        if (event.type === 'result') return fullText;
        if (event.type === 'error') throw new Error(event.error || '未知错误');
      }
    }

    return fullText;
  }

  async function sendMessage(message, visible) {
    if (sending) {
      setStatus('上一轮分析尚未完成', true);
      return;
    }
    var cwd = getCwd();
    if (!cwd) {
      setStatus('请先输入 free-code 工作目录/源码根目录', true);
      return;
    }
    if (!message) {
      setStatus('请输入要讨论的内容', true);
      return;
    }

    sending = true;
    setStatus('正在连接 free-code...');
    messages.push({ role: 'user', content: message });
    addMessage(visible || message, 'user');
    var assistantBubble = addMessage('正在分析，请稍候...', 'assistant');
    var assistantText = '';

    try {
      await streamFreeCode(message, cwd, function(delta) {
        assistantText += delta;
        if (assistantBubble) assistantBubble.textContent = assistantText;
        scrollToBottom();
      });
      if (!assistantText && assistantBubble) assistantBubble.textContent = '本轮没有返回内容';
      messages.push({ role: 'assistant', content: assistantText });
      setStatus('本轮完成');
    } catch (error) {
      var errorText = error instanceof Error ? error.message : String(error);
      if (assistantBubble) assistantBubble.textContent = errorText;
      messages.push({ role: 'assistant', content: '请求失败: ' + errorText });
      setStatus('请求失败', true);
    } finally {
      sending = false;
    }
  }

  function buildTargetAnalysisPrompt(targetText) {
    var historyText = messages.map(function(item) {
      return (item.role || 'user') + ': ' + (item.content || '');
    }).join('\n');
    var template = getTargetDefaultPrompt() || '你是 log_filter 的代码流程日志关键字分析助手。请围绕用户提供的代码线索分析前后流程，并提取 keep/filter 关键字线索。';
    return template + '\n\n' +
      'free-code 工作目录/源码根目录：\n' + getCwd() + '\n\n' +
      '用户提供的重点分析线索：\n' + targetText + '\n\n' +
      '已有讨论上下文如下，可结合但不要被其限制：\n' + historyText + '\n\n' +
      '请严格围绕上面的重点分析线索输出自然语言分析。';
  }

  function buildGenerateConfigPrompt() {
    var historyText = messages.map(function(item) {
      return (item.role || 'user') + ': ' + (item.content || '');
    }).join('\n');
    return '你是 log_filter 的日志关键字配置生成助手。\n\n' +
      'free-code 工作目录/源码根目录：\n' + getCwd() + '\n\n' +
      '以下是用户和模型围绕某一个功能流程的讨论内容：\n' + historyText + '\n\n' +
      '请基于上面的讨论内容和你对源码的理解，直接生成 log_filter 可保存的关键字配置文件 JSON。\n\n' +
      'log_filter 配置会保存到 configs/<config_name>.json，配置组会写入 config_groups/config_groups.json。\n' +
      '配置文件本体格式是分类名到 keep/filter 数组的映射。keep 用于保留目标流程相关日志；filter 用于排除无关噪声日志。\n\n' +
      '要求：\n' +
      '1. 优先基于上面的讨论内容生成配置；如信息不足，只做少量必要源码确认，不要进行大范围重复扫描。\n' +
      '2. 只输出 JSON，不要输出 Markdown。\n' +
      '3. keep/filter 都必须是固定字符串关键字，不要输出正则表达式。\n' +
      '4. 避免 error、failed、start、stop、init 这类过泛关键字，除非和具体 tag/模块组合后足够特异。\n' +
      '5. group_name 是配置组名，config_name 是保存到 configs/ 下的文件名，不要带 .json 后缀。\n' +
      '6. JSON 格式必须为：\n' +
      '{\n' +
      '  "group_name": "建议的关键字组名",\n' +
      '  "config_name": "建议的配置文件名",\n' +
      '  "config_data": {\n' +
      '    "分类名": {\n' +
      '      "keep": ["应该保留目标流程日志的关键字"],\n' +
      '      "filter": ["应该排除无关噪声日志的关键字"]\n' +
      '    }\n' +
      '  }\n' +
      '}';
  }

  function extractJsonPayload(text) {
    var raw = (text || '').trim();
    if (raw.indexOf('```') === 0) {
      raw = raw.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '');
    }
    try {
      return JSON.parse(raw);
    } catch (error) {
      var start = raw.indexOf('{');
      var end = raw.lastIndexOf('}');
      if (start >= 0 && end > start) {
        return JSON.parse(raw.slice(start, end + 1));
      }
      throw error;
    }
  }

  function syncGeneratedConfigToDash(payload) {
    var input = byId('ai-keyword-generated-config-sync-input');
    if (!input) {
      throw new Error('找不到生成配置同步组件');
    }
    input.value = JSON.stringify(payload || {});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function generateConfigFile() {
    if (sending) {
      setStatus('上一轮分析尚未完成', true);
      return;
    }
    if (!messages.length) {
      setStatus('请先和 AI 讨论目标流程后再生成配置文件', true);
      return;
    }
    var cwd = getCwd();
    if (!cwd) {
      setStatus('请先输入 free-code 工作目录/源码根目录', true);
      return;
    }

    sending = true;
    setStatus('正在根据讨论生成关键字配置...');
    var prompt = buildGenerateConfigPrompt();
    var rawText = '';
    messages.push({ role: 'user', content: prompt });
    addMessage('生成配置文件：根据当前讨论生成 keep/filter 配置 JSON', 'user');
    var assistantBubble = addMessage('正在生成配置文件，请稍候...', 'assistant');

    try {
      await streamFreeCode(prompt, cwd, function(delta) {
        rawText += delta;
        if (assistantBubble) assistantBubble.textContent = rawText;
        scrollToBottom();
      });
      var payload = extractJsonPayload(rawText);
      syncGeneratedConfigToDash(payload);
      setStatus('已生成关键字配置，请在下方审核后保存');
      messages.push({ role: 'assistant', content: '已生成关键字配置，请在页面下方审核 keep/filter 后保存。' });
      if (assistantBubble) assistantBubble.textContent = '已生成关键字配置，请在页面下方审核 keep/filter 后保存。';
    } catch (error) {
      var errorText = error instanceof Error ? error.message : String(error);
      if (errorText.indexOf('Timed out waiting for CLI event') >= 0) {
        errorText = 'free-code 长时间没有返回事件，已超时。建议先用“针对性分析”缩小范围，或让 AI 基于当前讨论直接生成更少量关键字。';
      }
      setStatus('生成配置文件失败: ' + errorText, true);
      if (assistantBubble) assistantBubble.textContent = '生成配置文件失败: ' + errorText;
    } finally {
      sending = false;
    }
  }

  function bindButton(id, handler) {
    var el = byId(id);
    if (!el || el.getAttribute('data-ai-keyword-path-bound') === '1') return;
    el.setAttribute('data-ai-keyword-path-bound', '1');
    el.addEventListener('click', function(e) {
      e.preventDefault();
      handler(e);
    });
  }

  function init() {
    if (!byId('ai-keyword-path-chat-modal')) return false;
    renderEmpty();
    bindButton('ai-keyword-path-chat-auto-btn', function() {
      var prompt = getDefaultPrompt();
      sendMessage(prompt, prompt);
    });
    bindButton('ai-keyword-target-analysis-btn', function() {
      var targetText = getTargetAnalysisInput();
      if (!targetText) {
        setStatus('请输入要针对性分析的日志打印、函数名、tag、状态名或错误码', true);
        return;
      }
      sendMessage(buildTargetAnalysisPrompt(targetText), '针对性分析：' + targetText);
    });
    bindButton('ai-keyword-path-chat-send-btn', function() {
      var text = getUserInput();
      clearUserInput();
      sendMessage(text, text);
    });
    bindButton('ai-keyword-path-chat-generate-btn', function() {
      generateConfigFile();
    });
    initialized = true;
    return true;
  }

  function tryInit() {
    if (!initialized) {
      init();
      return;
    }
    bindButton('ai-keyword-path-chat-auto-btn', function() {
      var prompt = getDefaultPrompt();
      sendMessage(prompt, prompt);
    });
    bindButton('ai-keyword-target-analysis-btn', function() {
      var targetText = getTargetAnalysisInput();
      if (!targetText) {
        setStatus('请输入要针对性分析的日志打印、函数名、tag、状态名或错误码', true);
        return;
      }
      sendMessage(buildTargetAnalysisPrompt(targetText), '针对性分析：' + targetText);
    });
    bindButton('ai-keyword-path-chat-send-btn', function() {
      var text = getUserInput();
      clearUserInput();
      sendMessage(text, text);
    });
    bindButton('ai-keyword-path-chat-generate-btn', function() {
      generateConfigFile();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryInit);
  } else {
    tryInit();
  }
  setInterval(tryInit, 1000);
})();
