from fastapi import APIRouter
from fastapi.responses import HTMLResponse


PLAYGROUND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Research AI Agent Playground</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3efe5;
      --panel: rgba(255, 252, 246, 0.92);
      --panel-strong: #fffaf0;
      --text: #231f1a;
      --muted: #6c655d;
      --accent: #c35b2c;
      --accent-soft: #efc3a7;
      --border: rgba(35, 31, 26, 0.12);
      --success: #1f7a4d;
      --danger: #a12622;
      --shadow: 0 24px 60px rgba(73, 50, 31, 0.12);
      --radius: 20px;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", serif;
      background:
        radial-gradient(circle at top left, rgba(195, 91, 44, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(97, 135, 110, 0.18), transparent 30%),
        linear-gradient(180deg, #f7f2e8 0%, var(--bg) 100%);
      color: var(--text);
    }

    main {
      width: min(1120px, calc(100% - 32px));
      margin: 32px auto 48px;
      display: grid;
      gap: 20px;
    }

    .hero, .panel {
      background: var(--panel);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
    }

    .hero {
      padding: 28px;
      overflow: hidden;
      position: relative;
    }

    .hero::after {
      content: "";
      position: absolute;
      inset: auto -20px -36px auto;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(195, 91, 44, 0.18), rgba(195, 91, 44, 0));
      pointer-events: none;
    }

    h1, h2 {
      margin: 0 0 8px;
      font-weight: 700;
    }

    h1 {
      font-size: clamp(2rem, 4vw, 3.5rem);
      line-height: 0.96;
      max-width: 10ch;
      letter-spacing: -0.04em;
    }

    h2 {
      font-size: 1.15rem;
      letter-spacing: 0.01em;
    }

    p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 20px;
    }

    .panel {
      padding: 20px;
    }

    .field {
      display: grid;
      gap: 8px;
      margin-top: 14px;
    }

    .field:first-child {
      margin-top: 0;
    }

    label {
      font-size: 0.92rem;
      font-weight: 700;
    }

    input, textarea, button {
      font: inherit;
    }

    input, textarea {
      width: 100%;
      border: 1px solid rgba(35, 31, 26, 0.16);
      border-radius: 14px;
      background: var(--panel-strong);
      color: var(--text);
      padding: 12px 14px;
      transition: border-color 150ms ease, transform 150ms ease;
    }

    input:focus, textarea:focus {
      outline: none;
      border-color: var(--accent);
      transform: translateY(-1px);
    }

    textarea {
      min-height: 132px;
      resize: vertical;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 12px 18px;
      font-weight: 700;
      cursor: pointer;
      transition: transform 150ms ease, opacity 150ms ease, background 150ms ease;
    }

    button:hover:not(:disabled) {
      transform: translateY(-1px);
    }

    button:disabled {
      opacity: 0.65;
      cursor: progress;
    }

    .primary {
      background: var(--text);
      color: #fff7ed;
    }

    .secondary {
      background: rgba(35, 31, 26, 0.08);
      color: var(--text);
    }

    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
    }

    .conversation-id {
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(35, 31, 26, 0.05);
      border: 1px dashed rgba(35, 31, 26, 0.16);
      word-break: break-all;
      font-family: ui-monospace, "SFMono-Regular", "SF Mono", Consolas, monospace;
      font-size: 0.92rem;
    }

    .files-list, .messages, .status {
      margin-top: 16px;
      display: grid;
      gap: 10px;
    }

    .chip, .message, .status-item {
      border-radius: 16px;
      background: rgba(255, 250, 240, 0.92);
      border: 1px solid rgba(35, 31, 26, 0.12);
      padding: 12px 14px;
    }

    .chip strong, .message strong {
      display: block;
      margin-bottom: 6px;
      font-size: 0.92rem;
    }

    .chip small, .status-item small {
      color: var(--muted);
      display: block;
      margin-top: 4px;
    }

    .message.assistant {
      background: rgba(239, 195, 167, 0.24);
    }

    .message pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: inherit;
      color: var(--text);
    }

    .message-body {
      display: grid;
      gap: 14px;
      color: var(--text);
    }

    .message-body p {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text);
    }

    .message-table-wrap {
      overflow-x: auto;
      border-radius: 14px;
      border: 1px solid rgba(35, 31, 26, 0.12);
      background: rgba(255, 255, 255, 0.6);
    }

    .message-table {
      width: 100%;
      border-collapse: collapse;
      min-width: 520px;
    }

    .message-table th,
    .message-table td {
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
      border-bottom: 1px solid rgba(35, 31, 26, 0.1);
      line-height: 1.45;
    }

    .message-table th {
      background: rgba(35, 31, 26, 0.06);
      font-size: 0.92rem;
    }

    .message-table tr:last-child td {
      border-bottom: 0;
    }

    .status-item.success { border-left: 4px solid var(--success); }
    .status-item.error { border-left: 4px solid var(--danger); }
    .status-item.info { border-left: 4px solid var(--accent); }

    .current-progress {
      min-height: 22px;
      margin-top: 12px;
      color: var(--accent);
      font-weight: 700;
    }

    .muted { color: var(--muted); font-size: 0.92rem; }

    @media (max-width: 640px) {
      main { width: min(100% - 20px, 1120px); margin-top: 20px; }
      .hero, .panel { border-radius: 18px; }
      .hero, .panel { padding: 18px; }
    }
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p style="font-size:0.88rem; text-transform:uppercase; letter-spacing:0.14em; margin-bottom:12px;">Local Playground</p>
      <h1>Test file and image input against the API.</h1>
      <p style="max-width:60ch; margin-top:12px;">
        This page creates a conversation, uploads selected files through <code>/v1/uploads/presign</code>,
        then sends their returned attachment parts into <code>/v1/conversations/{id}/messages</code>.
      </p>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Connection</h2>
        <p>Point the UI at this backend and use the same internal API key required by the protected routes.</p>

        <div class="field">
          <label for="baseUrl">Base URL</label>
          <input id="baseUrl" value="" />
        </div>

        <div class="field">
          <label for="apiKey">Internal API Key</label>
          <input id="apiKey" placeholder="your-internal-key" />
        </div>

        <div class="field">
          <label for="title">Conversation Title</label>
          <input id="title" placeholder="Image upload test" />
        </div>

        <div class="field">
          <label for="systemPrompt">System Prompt</label>
          <textarea id="systemPrompt" placeholder="Optional system prompt"></textarea>
        </div>

        <div class="row" style="margin-top:16px;">
          <button class="primary" id="createConversation">Create Conversation</button>
          <button class="secondary" id="refreshConversation">Reload Messages</button>
        </div>

        <div class="files-list">
          <div class="conversation-id" id="conversationState">No conversation yet.</div>
        </div>
      </div>

      <div class="panel">
        <h2>Compose Message</h2>
        <p>Choose image or file inputs, then send them with optional text and image captions.</p>

        <div class="field">
          <label for="messageText">Message Text</label>
          <textarea id="messageText" placeholder="Ask the assistant to inspect or summarize the attachments"></textarea>
        </div>

        <div class="field">
          <label for="attachments">Attachments</label>
          <input id="attachments" type="file" multiple />
          <div class="muted">Images are sent as <code>image</code> parts. Everything else is sent as <code>file</code> parts.</div>
        </div>

        <div class="files-list" id="selectedFiles">
          <div class="muted">No files selected.</div>
        </div>

        <div class="row" style="margin-top:16px;">
          <button class="primary" id="sendMessage">Upload And Send</button>
          <button class="secondary" id="cancelRequest" disabled>Stop</button>
          <button class="secondary" id="clearComposer">Clear</button>
        </div>
        <div class="current-progress" id="currentProgress" aria-live="polite"></div>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>Request Status</h2>
        <div class="status" id="statusLog">
          <div class="muted">Activity will appear here.</div>
        </div>
      </div>

      <div class="panel">
        <h2>Conversation Messages</h2>
        <div class="messages" id="messages">
          <div class="muted">Create or load a conversation to see messages.</div>
        </div>
      </div>
    </section>
  </main>

  <script>
    const state = {
      conversationId: null,
      selectedFiles: [],
      isProcessing: false,
      abortController: null,
      activeJobId: null,
      activeJobProgressCount: 0,
    };

    const baseUrlInput = document.getElementById("baseUrl");
    const apiKeyInput = document.getElementById("apiKey");
    const titleInput = document.getElementById("title");
    const systemPromptInput = document.getElementById("systemPrompt");
    const messageTextInput = document.getElementById("messageText");
    const attachmentsInput = document.getElementById("attachments");
    const conversationState = document.getElementById("conversationState");
    const selectedFiles = document.getElementById("selectedFiles");
    const statusLog = document.getElementById("statusLog");
    const messages = document.getElementById("messages");
    const createConversationButton = document.getElementById("createConversation");
    const refreshConversationButton = document.getElementById("refreshConversation");
    const sendMessageButton = document.getElementById("sendMessage");
    const cancelRequestButton = document.getElementById("cancelRequest");
    const clearComposerButton = document.getElementById("clearComposer");
    const currentProgress = document.getElementById("currentProgress");

    baseUrlInput.value = window.location.origin;

    function apiBaseUrl() {
      return (baseUrlInput.value || window.location.origin).trim().replace(/\\/$/, "");
    }

    function apiHeaders(json = true) {
      const headers = {
        "x-api-key": apiKeyInput.value.trim(),
      };
      if (json) {
        headers["Content-Type"] = "application/json";
      }
      return headers;
    }

    function logStatus(kind, message) {
      const empty = statusLog.querySelector(".muted");
      if (empty) {
        empty.remove();
      }
      const item = document.createElement("div");
      item.className = `status-item ${kind}`;
      item.innerHTML = `<strong>${message}</strong><small>${new Date().toLocaleTimeString()}</small>`;
      statusLog.prepend(item);
    }

    function showCurrentProgress(message) {
      // Display app-generated lifecycle progress only; this never contains LLM reasoning.
      currentProgress.textContent = message || "";
      if (message && state.isProcessing) {
        sendMessageButton.textContent = message.replace(/\\.+$/, "...");
      }
    }

    function updateComposerControls() {
      const canEditComposer = !state.isProcessing;
      messageTextInput.disabled = !canEditComposer;
      attachmentsInput.disabled = !canEditComposer;
      clearComposerButton.disabled = !canEditComposer;
      sendMessageButton.disabled = state.isProcessing;
      if (!state.isProcessing) {
        sendMessageButton.textContent = "Upload And Send";
      }
      cancelRequestButton.disabled = !state.isProcessing;
      createConversationButton.disabled = state.isProcessing;
      refreshConversationButton.disabled = state.isProcessing;
    }

    function beginProcessing() {
      state.isProcessing = true;
      state.abortController = new AbortController();
      showCurrentProgress("Sending request...");
      updateComposerControls();
      return state.abortController.signal;
    }

    function endProcessing() {
      state.isProcessing = false;
      state.abortController = null;
      state.activeJobId = null;
      state.activeJobProgressCount = 0;
      showCurrentProgress("");
      updateComposerControls();
    }

    function updateConversationState() {
      if (!state.conversationId) {
        conversationState.textContent = "No conversation yet.";
        return;
      }
      conversationState.textContent = `Conversation ID: ${state.conversationId}`;
    }

    function renderSelectedFiles() {
      selectedFiles.innerHTML = "";
      if (!state.selectedFiles.length) {
        selectedFiles.innerHTML = '<div class="muted">No files selected.</div>';
        return;
      }

      state.selectedFiles.forEach((entry, index) => {
        const wrapper = document.createElement("div");
        wrapper.className = "chip";
        const isImage = entry.file.type.startsWith("image/");
        wrapper.innerHTML = `
          <strong>${entry.file.name}</strong>
          <div class="muted">${isImage ? "image" : "file"} · ${entry.file.type || "application/octet-stream"} · ${entry.file.size} bytes</div>
          ${isImage ? `<input data-caption-index="${index}" placeholder="Optional image caption" value="${entry.caption}" style="margin-top:10px;" />` : ""}
        `;
        selectedFiles.appendChild(wrapper);
      });

      selectedFiles.querySelectorAll("input[data-caption-index]").forEach((input) => {
        input.addEventListener("input", (event) => {
          const index = Number(event.target.getAttribute("data-caption-index"));
          state.selectedFiles[index].caption = event.target.value;
        });
      });
    }

    function renderMessages(conversation) {
      messages.innerHTML = "";
      if (!conversation || !conversation.messages || !conversation.messages.length) {
        messages.innerHTML = '<div class="muted">No messages yet.</div>';
        return;
      }

      conversation.messages.forEach((message) => {
        const item = document.createElement("div");
        item.className = `message ${message.role}`;
        const partSummary = (message.parts || []).map((part) => {
          if (part.type === "text") return part.text;
          if (part.type === "image") return `[image] ${part.image.caption || part.image.key}`;
          if (part.type === "file") return `[file] ${part.file.name}`;
          if (part.type === "table") return `[table] ${part.table.columns.join(", ")}`;
          return JSON.stringify(part);
        }).join("\\n\\n");
        const renderedContent = renderMessageContent(message.content || partSummary || "(empty)");
        item.innerHTML = `<strong>${message.role}</strong>${renderedContent}`;
        messages.appendChild(item);
      });
    }

    function escapeHtml(value) {
      return value
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }

    function splitMarkdownRow(row) {
      return row
        .trim()
        .replace(/^\\|/, "")
        .replace(/\\|$/, "")
        .split("|")
        .map((cell) => cell.trim());
    }

    function isMarkdownSeparatorRow(row) {
      const cells = splitMarkdownRow(row);
      return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
    }

    function isMarkdownTableBlock(block) {
      const rows = block.split(/\\n/).map((row) => row.trim()).filter(Boolean);
      return rows.length >= 2 && rows[0].includes("|") && isMarkdownSeparatorRow(rows[1]);
    }

    function renderMarkdownTable(block) {
      const rows = block.split(/\\n/).map((row) => row.trim()).filter(Boolean);
      const headers = splitMarkdownRow(rows[0]);
      const bodyRows = rows.slice(2).map(splitMarkdownRow).filter((cells) => cells.length);
      const headerHtml = headers.map((cell) => `<th>${escapeHtml(cell)}</th>`).join("");
      const bodyHtml = bodyRows.map((cells) => {
        const normalized = headers.map((_, index) => `<td>${escapeHtml(cells[index] || "")}</td>`).join("");
        return `<tr>${normalized}</tr>`;
      }).join("");
      return `
        <div class="message-table-wrap">
          <table class="message-table">
            <thead><tr>${headerHtml}</tr></thead>
            <tbody>${bodyHtml}</tbody>
          </table>
        </div>
      `;
    }

    function renderMessageContent(content) {
      const blocks = content.split(/\\n\\s*\\n/).filter((block) => block.trim());
      const rendered = blocks.map((block) => {
        if (isMarkdownTableBlock(block)) {
          return renderMarkdownTable(block);
        }
        return `<p>${escapeHtml(block)}</p>`;
      }).join("");
      return `<div class="message-body">${rendered || "<p>(empty)</p>"}</div>`;
    }

    async function request(path, options = {}) {
      const response = await fetch(`${apiBaseUrl()}${path}`, options);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.error || data.detail || `Request failed with ${response.status}`);
      }
      return data;
    }

    async function createConversation() {
      const payload = {
        title: titleInput.value.trim() || null,
        systemPrompt: systemPromptInput.value.trim() || null,
      };
      const result = await request("/v1/conversations", {
        method: "POST",
        headers: apiHeaders(true),
        body: JSON.stringify(payload),
      });
      state.conversationId = result.data.id;
      updateConversationState();
      renderMessages(result.data);
      logStatus("success", "Conversation created.");
    }

    async function refreshConversation() {
      if (!state.conversationId) {
        throw new Error("Create a conversation first.");
      }
      const result = await request(`/v1/conversations/${state.conversationId}`, {
        headers: apiHeaders(false),
      });
      renderMessages(result.data);
      logStatus("info", "Conversation reloaded.");
    }

    async function presignAndUpload(entry, signal) {
      const file = entry.file;
      const kind = file.type.startsWith("image/") ? "image" : "file";
      const presign = await request("/v1/uploads/presign", {
        method: "POST",
        headers: apiHeaders(true),
        signal,
        body: JSON.stringify({
          conversationId: state.conversationId,
          fileName: file.name,
          contentType: file.type || "application/octet-stream",
          sizeBytes: file.size || 1,
          kind,
        }),
      });

      const uploadResponse = await fetch(presign.data.uploadUrl, {
        method: presign.data.method,
        headers: presign.data.headers,
        signal,
        body: file,
      });
      if (!uploadResponse.ok) {
        throw new Error(`Upload failed for ${file.name} with ${uploadResponse.status}`);
      }

      const part = presign.data.part;
      if (part.type === "image" && entry.caption.trim()) {
        part.image.caption = entry.caption.trim();
      }
      return part;
    }

    async function sendMessage() {
      if (state.isProcessing) {
        throw new Error("A request is already in progress. Stop it or wait for it to finish before sending another query.");
      }
      if (!state.conversationId) {
        throw new Error("Create a conversation first.");
      }

      const text = messageTextInput.value.trim();
      if (!text && !state.selectedFiles.length) {
        throw new Error("Add message text or at least one attachment.");
      }

      const signal = beginProcessing();
      try {
        logStatus("info", "Preparing attachments...");
        const parts = [];
        for (const entry of state.selectedFiles) {
          parts.push(await presignAndUpload(entry, signal));
          logStatus("info", `Uploaded ${entry.file.name}.`);
        }

        if (text) {
          parts.unshift({ type: "text", text });
        }

        const payloadContent = state.selectedFiles.length ? null : (text || null);
        const jobResponse = await request(`/v1/conversations/${state.conversationId}/messages/jobs`, {
          method: "POST",
          headers: apiHeaders(true),
          signal,
          body: JSON.stringify({
            content: payloadContent,
            parts: parts.length ? parts : null,
          }),
        });
        state.activeJobId = jobResponse.data.jobId;
        state.activeJobProgressCount = 0;
        logStatus("info", `Assistant job started: ${state.activeJobId}`);
        logStatus("info", "Waiting for the assistant response...");

        let result = null;
        while (true) {
          await new Promise((resolve, reject) => {
            const timeoutId = window.setTimeout(resolve, 1200);
            signal.addEventListener("abort", () => {
              window.clearTimeout(timeoutId);
              reject(new DOMException("The operation was aborted.", "AbortError"));
            }, { once: true });
          });

          const jobStatus = await request(
            `/v1/conversations/${state.conversationId}/messages/jobs/${state.activeJobId}`,
            {
              headers: apiHeaders(false),
              signal,
            },
          );
          // These progress messages come from backend job lifecycle events, not from LLM reasoning.
          const progress = jobStatus.data.progress || [];
          progress.slice(state.activeJobProgressCount).forEach((message) => {
            logStatus("info", message);
            showCurrentProgress(message);
          });
          state.activeJobProgressCount = progress.length;
          const status = jobStatus.data.status;
          if (status === "queued" || status === "running") {
            continue;
          }
          if (status === "succeeded") {
            result = jobStatus.data.result;
            break;
          }
          if (status === "canceled") {
            throw new DOMException("The operation was aborted.", "AbortError");
          }
          throw new Error(jobStatus.data.error || `Message job ended with status: ${status}`);
        }

        renderMessages(result.conversation);
        messageTextInput.value = "";
        attachmentsInput.value = "";
        state.selectedFiles = [];
        renderSelectedFiles();
        logStatus("success", "Message sent.");
      } catch (error) {
        if (error.name === "AbortError") {
          logStatus("info", "Request canceled.");
          return;
        }
        throw error;
      } finally {
        endProcessing();
      }
    }

    attachmentsInput.addEventListener("change", (event) => {
      state.selectedFiles = Array.from(event.target.files || []).map((file) => ({ file, caption: "" }));
      renderSelectedFiles();
    });

    createConversationButton.addEventListener("click", async () => {
      try {
        await createConversation();
      } catch (error) {
        logStatus("error", error.message);
      }
    });

    refreshConversationButton.addEventListener("click", async () => {
      try {
        await refreshConversation();
      } catch (error) {
        logStatus("error", error.message);
      }
    });

    sendMessageButton.addEventListener("click", async () => {
      try {
        await sendMessage();
      } catch (error) {
        logStatus("error", error.message);
      }
    });

    cancelRequestButton.addEventListener("click", () => {
      if (state.activeJobId && state.conversationId) {
        fetch(`${apiBaseUrl()}/v1/conversations/${state.conversationId}/messages/jobs/${state.activeJobId}/cancel`, {
          method: "POST",
          headers: apiHeaders(false),
        }).catch(() => {});
      }
      if (!state.abortController) {
        return;
      }
      state.abortController.abort();
    });

    clearComposerButton.addEventListener("click", () => {
      messageTextInput.value = "";
      attachmentsInput.value = "";
      state.selectedFiles = [];
      renderSelectedFiles();
      logStatus("info", "Composer cleared.");
    });

    updateConversationState();
    renderSelectedFiles();
    updateComposerControls();
  </script>
</body>
</html>
"""


router = APIRouter(tags=["playground"])


@router.get("/playground", response_class=HTMLResponse, include_in_schema=False)
async def get_playground() -> HTMLResponse:
    return HTMLResponse(PLAYGROUND_HTML)
