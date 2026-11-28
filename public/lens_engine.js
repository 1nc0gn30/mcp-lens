/**
 * MCP Lens Engine v2.6.0 — Zero-XSS Real-Time Stdio/SSE Sniffer & Dual-Theme Controller.
 * Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
 * 100% Vanilla ES6+ — Zero External Dependencies, Zero innerHTML Sinks.
 */

(function () {
  "use strict";

  const SOLANA_TIP_ADDRESS = "GG2eQbVh8ut1BK6j1A2tz7pSySdLpD38BgyEhGcxdXoK";

  const DEFAULT_TOOLS = [
    {
      name: "sqlite_query_records",
      description: "Executes a read-only SQL query against the connected SQLite database.",
      total_tokens: 188,
      minified_tokens: 126,
      savings_percent: 33.0,
      tokens_saved: 62,
      raw_schema: {
        name: "sqlite_query_records",
        description: "Executes a read-only SQL query against the connected SQLite database.",
        inputSchema: {
          type: "object",
          properties: {
            database_path: { type: "string", description: "Absolute filesystem path to SQLite DB.", examples: ["/data/production.db"] },
            query: { type: "string", description: "SQL SELECT statement to run.", examples: ["SELECT id, name FROM accounts LIMIT 10;"] },
            limit: { type: "integer", description: "Maximum number of rows to return.", default: 100 }
          },
          required: ["database_path", "query"]
        }
      },
      minified_schema: {
        name: "sqlite_query_records",
        description: "Executes a read-only SQL query against the connected SQLite database.",
        inputSchema: {
          type: "object",
          properties: {
            database_path: { type: "string", description: "Absolute filesystem path to SQLite DB" },
            query: { type: "string", description: "SQL SELECT statement to run" },
            limit: { type: "integer", description: "Maximum number of rows to return" }
          },
          required: ["database_path", "query"]
        }
      }
    },
    {
      name: "filesystem_read_file",
      description: "Reads UTF-8 text content from a workspace file with optional line slicing.",
      total_tokens: 152,
      minified_tokens: 104,
      savings_percent: 31.6,
      tokens_saved: 48,
      raw_schema: {
        name: "filesystem_read_file",
        description: "Reads UTF-8 text content from a workspace file with optional line slicing.",
        inputSchema: {
          type: "object",
          properties: {
            file_path: { type: "string", description: "Workspace-relative or absolute file path." },
            offset: { type: "integer", description: "Zero-indexed line offset." }
          },
          required: ["file_path"]
        }
      },
      minified_schema: {
        name: "filesystem_read_file",
        description: "Reads UTF-8 text content from a workspace file with optional line slicing.",
        inputSchema: {
          type: "object",
          properties: {
            file_path: { type: "string", description: "Workspace-relative or absolute file path" },
            offset: { type: "integer", description: "Zero-indexed line offset" }
          },
          required: ["file_path"]
        }
      }
    }
  ];

  const DEFAULT_FRAMES = [
    {
      frame_id: "frm-101",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 20,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "initialize", id: 1, params: { protocolVersion: "2024-11-05" } }),
      meta: { method: "initialize", id: 1, byte_size: 98, estimated_tokens: 34, primary_topic: "initialize", has_error: false }
    },
    {
      frame_id: "frm-102",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 12,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "tools/list", id: 2, params: {} }),
      meta: { method: "tools/list", id: 2, byte_size: 62, estimated_tokens: 22, primary_topic: "tools/list", has_error: false }
    },
    {
      frame_id: "frm-103",
      direction: "outbound",
      timestamp: Math.floor(Date.now() / 1000) - 5,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", id: 2, result: { tools: DEFAULT_TOOLS.map((t) => t.raw_schema) } }),
      meta: { method: "response", id: 2, byte_size: 842, estimated_tokens: 340, primary_topic: "response", has_error: false }
    }
  ];

  const state = {
    theme: "dark",
    isEmbed: false,
    isLiveDaemon: false,
    frames: [],
    tools: [],
    activeFilter: "all",
    searchQuery: "",
    selectedFrame: null,
    selectedToolName: null,
    isStreamPaused: false,
    sseSource: null,
    stats: {
      total_frames: DEFAULT_FRAMES.length,
      total_bytes: 1002,
      total_tokens: 396,
      token_overhead: 340,
      potential_savings_tokens: 110,
      savings_percent: 32.4
    }
  };

  let elFramesBody;
  let elStatsFrames;
  let elStatsBytes;
  let elStatsTokens;
  let elStatsSavings;
  let elToolSelect;
  let elToolArgsForm;
  let elToolResultBox;
  let elToolRawTokens;
  let elToolMinTokens;
  let elToolSavingsPct;
  let elRawSchemaView;
  let elMinSchemaView;
  let elAuditorTableBody;
  let elModalFrameDetail;
  let elFrameJsonContent;
  let elFrameMetaContent;
  let elLiveMinifierTrace;

  function applyTheme(nextTheme, persist) {
    const resolved = nextTheme === "light" ? "light" : "dark";
    state.theme = resolved;
    document.documentElement.setAttribute("data-theme", resolved);
    const lbl = document.getElementById("theme-toggle-label");
    if (lbl) {
      lbl.textContent = resolved === "dark" ? "☀ Light" : "☾ Dark";
    }
    if (persist) {
      try {
        localStorage.setItem("mcp-lens-theme", resolved);
      } catch (_err) {}
    }
  }

  function initThemeAndEmbed() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("embed") === "1") {
      state.isEmbed = true;
      document.documentElement.setAttribute("data-embed", "1");
    }

    const qTheme = params.get("theme");
    if (qTheme === "light" || qTheme === "dark") {
      applyTheme(qTheme, false);
    } else {
      let saved = null;
      try {
        saved = localStorage.getItem("mcp-lens-theme");
      } catch (_err) {}
      if (saved === "light" || saved === "dark") {
        applyTheme(saved, false);
      } else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
        applyTheme("light", false);
      } else {
        applyTheme("dark", false);
      }
    }

    // Listen for Studio parent postMessage theme updates
    window.addEventListener("message", (event) => {
      const origin = event.origin || "";
      if (
        origin &&
        !origin.startsWith("http://127.0.0.1:") &&
        !origin.startsWith("http://localhost:")
      ) {
        return;
      }
      const data = event.data;
      if (data && (data.theme === "light" || data.theme === "dark")) {
        applyTheme(data.theme, false);
      }
    });
  }

  function clearNode(node) {
    while (node && node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function estimateTokensLocal(input) {
    const text = typeof input === "string" ? input : JSON.stringify(input || "");
    if (!text) return 0;
    const cleaned = text.replace(/\s+/g, " ").trim();
    if (!cleaned) return 0;
    const punct = (cleaned.match(/[{}\[\]":,._\-/\\<>!@#$%^&*()+=|;]/g) || []).length;
    const words = cleaned.match(/[a-zA-Z0-9]+/g) || [];
    let wordTok = 0;
    for (let i = 0; i < words.length; i++) {
      wordTok += Math.max(1, Math.floor((words[i].length + 2) / 4));
    }
    return Math.max(1, Math.floor(punct * 0.95 + wordTok * 1.05));
  }

  document.addEventListener("DOMContentLoaded", () => {
    initThemeAndEmbed();
    initDOMElements();
    setupEventListeners();
    initHeroCanvas();

    state.tools = DEFAULT_TOOLS;
    state.frames = [...DEFAULT_FRAMES];
    renderStats();
    populateToolSelector();
    renderAuditorTable({ tools: DEFAULT_TOOLS });
    renderWaterfall();
    updateMinifierTrace();

    // Probe same-origin backend (/api/health) dynamically on any local port
    probeAndConnectBackend();
  });

  function initDOMElements() {
    elFramesBody = document.getElementById("waterfall-body");
    elStatsFrames = document.getElementById("stat-total-frames");
    elStatsBytes = document.getElementById("stat-total-bytes");
    elStatsTokens = document.getElementById("stat-total-tokens");
    elStatsSavings = document.getElementById("stat-tokens-saved");
    elToolSelect = document.getElementById("tool-selector");
    elToolArgsForm = document.getElementById("tool-args-form");
    elToolResultBox = document.getElementById("tool-exec-result");
    elToolRawTokens = document.getElementById("tool-raw-tokens");
    elToolMinTokens = document.getElementById("tool-min-tokens");
    elToolSavingsPct = document.getElementById("tool-savings-pct");
    elRawSchemaView = document.getElementById("raw-schema-code");
    elMinSchemaView = document.getElementById("min-schema-code");
    elAuditorTableBody = document.getElementById("auditor-table-body");
    elModalFrameDetail = document.getElementById("frame-detail-modal");
    elFrameJsonContent = document.getElementById("frame-raw-json");
    elFrameMetaContent = document.getElementById("frame-meta-tags");
    elLiveMinifierTrace = document.getElementById("live-minifier-trace");
  }

  async function probeAndConnectBackend() {
    if (window.location.protocol === "file:") {
      setStreamStatus("In-Browser Offline Mode");
      return;
    }
    try {
      const res = await fetch("/api/health");
      if (res && res.ok) {
        state.isLiveDaemon = true;
        setStreamStatus("Live Stdio Stream Active");
        await Promise.all([fetchStats(), fetchTools(), fetchInitialTraffic()]);
        connectSSE();
        return;
      }
    } catch (_err) {}
    state.isLiveDaemon = false;
    setStreamStatus("In-Browser Offline Mode");
  }

  function setStreamStatus(text) {
    const statusText = document.getElementById("sse-status-text");
    if (statusText) statusText.textContent = text;
  }

  async function fetchStats() {
    try {
      const res = await fetch("/api/stats");
      if (res && res.ok) {
        state.stats = await res.json();
        renderStats();
      }
    } catch (_err) {}
  }

  function renderStats() {
    if (elStatsFrames) elStatsFrames.textContent = Number(state.stats.total_frames || 0).toLocaleString();
    if (elStatsBytes) {
      const kb = (Number(state.stats.total_bytes || 0) / 1024).toFixed(1);
      elStatsBytes.textContent = `${kb} KB`;
    }
    if (elStatsTokens) {
      const val = Number(state.stats.token_overhead || state.stats.total_tokens || 0);
      elStatsTokens.textContent = val.toLocaleString();
    }
    if (elStatsSavings) {
      const saved = Number(state.stats.potential_savings_tokens || 0);
      const pct = Number(state.stats.savings_percent || 0);
      elStatsSavings.textContent = `${saved.toLocaleString()} (${pct}%)`;
    }
  }

  function connectSSE() {
    if (!state.isLiveDaemon || typeof EventSource === "undefined") return;
    try {
      state.sseSource = new EventSource("/api/events/stream");
      state.sseSource.onmessage = (event) => {
        if (state.isStreamPaused) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "frame" && data.frame) {
            handleNewFrame(data.frame);
          }
        } catch (_err) {}
      };
      state.sseSource.onopen = () => setStreamStatus("Live Stdio Stream Active");
      state.sseSource.onerror = () => {
        if (state.sseSource) {
          state.sseSource.close();
          state.sseSource = null;
        }
        setStreamStatus("Loopback REST Active");
      };
    } catch (_err) {}
  }

  function handleNewFrame(frame) {
    state.frames.unshift(frame);
    if (state.frames.length > 500) state.frames.pop();
    renderWaterfall();
    fetchStats();
  }

  async function fetchInitialTraffic() {
    try {
      const res = await fetch("/api/traffic?limit=100");
      if (res && res.ok) {
        const data = await res.json();
        if (Array.isArray(data.frames)) {
          state.frames = data.frames.slice().reverse();
          renderWaterfall();
        }
      }
    } catch (_err) {}
  }

  // Zero-XSS DOM Builder for Waterfall Table
  function renderWaterfall() {
    if (!elFramesBody) return;
    clearNode(elFramesBody);

    const filtered = state.frames.filter((f) => {
      if (state.activeFilter !== "all") {
        const topic = String(f.meta?.primary_topic || f.meta?.method || "").toLowerCase();
        if (state.activeFilter === "tools" && !topic.includes("tools")) return false;
        if (state.activeFilter === "initialize" && !topic.includes("initialize")) return false;
        if (state.activeFilter === "errors" && !f.meta?.has_error) return false;
        if (state.activeFilter === "resources" && !topic.includes("resource")) return false;
        if (state.activeFilter === "prompts" && !topic.includes("prompt")) return false;
      }
      if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        const raw = String(f.raw_payload || "").toLowerCase();
        const method = String(f.meta?.method || "").toLowerCase();
        if (!raw.includes(q) && !method.includes(q)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      const tr = el("tr");
      const td = el("td", "mono-cell", `No frames matching filter "${state.activeFilter}".`);
      td.colSpan = 7;
      td.style.textAlign = "center";
      td.style.padding = "24px";
      tr.appendChild(td);
      elFramesBody.appendChild(tr);
      return;
    }

    const frag = document.createDocumentFragment();
    filtered.slice(0, 100).forEach((f) => {
      const tr = el("tr");
      tr.style.cursor = "pointer";
      tr.addEventListener("click", () => window.inspectFrame(f.frame_id));

      const timeStr = new Date((f.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString();
      tr.appendChild(el("td", "mono-cell", timeStr));

      const dirTd = el("td");
      const isIn = f.direction === "inbound";
      dirTd.appendChild(el("span", isIn ? "dir-badge dir-in" : "dir-badge dir-out", isIn ? "IN ↓" : "OUT ↑"));
      tr.appendChild(dirTd);

      const method = String(f.meta?.method || (f.meta?.has_error ? "error" : "response"));
      const methodClass = f.meta?.has_error
        ? "mono-cell tone-rose"
        : method.startsWith("tools/")
        ? "mono-cell tone-gold"
        : method.startsWith("initialize")
        ? "mono-cell tone-purple"
        : "mono-cell";
      tr.appendChild(el("td", methodClass, method));

      const rpcId = f.meta?.id !== null && f.meta?.id !== undefined ? `#${String(f.meta.id)}` : "—";
      tr.appendChild(el("td", "mono-cell", rpcId));

      const bytes = Number(f.meta?.byte_size || (f.raw_payload ? f.raw_payload.length : 0));
      tr.appendChild(el("td", "mono-cell", `${bytes} B`));

      const tokens = Number(f.meta?.estimated_tokens || 0);
      tr.appendChild(el("td", "mono-cell tone-sky", `${tokens} tk`));

      const actTd = el("td");
      actTd.style.textAlign = "right";
      const btn = el("button", "btn btn-sm", "Inspect");
      btn.type = "button";
      btn.setAttribute("aria-label", `Inspect frame ${String(f.frame_id)}`);
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        window.inspectFrame(f.frame_id);
      });
      actTd.appendChild(btn);
      tr.appendChild(actTd);

      frag.appendChild(tr);
    });
    elFramesBody.appendChild(frag);
  }

  window.inspectFrame = function (frameId) {
    const frame = state.frames.find((f) => f.frame_id === frameId);
    if (!frame) return;
    state.selectedFrame = frame;

    if (elFrameJsonContent) {
      try {
        const obj = frame.json_data || JSON.parse(frame.raw_payload);
        elFrameJsonContent.textContent = JSON.stringify(obj, null, 2);
      } catch (_err) {
        elFrameJsonContent.textContent = String(frame.raw_payload || "");
      }
    }

    if (elFrameMetaContent) {
      clearNode(elFrameMetaContent);
      const tags = [
        { cls: "badge badge-sky", text: `Direction: ${String(frame.direction || "inbound")}` },
        { cls: "badge badge-gold", text: `Size: ${Number(frame.meta?.byte_size || 0)} bytes` },
        { cls: "badge badge-emerald-soft", text: `Tokens: ${Number(frame.meta?.estimated_tokens || 0)} tk` },
        { cls: "badge badge-sky", text: `Time: ${new Date((frame.timestamp || Date.now() / 1000) * 1000).toISOString()}` }
      ];
      tags.forEach((t) => elFrameMetaContent.appendChild(el("span", t.cls, t.text)));
    }

    if (elModalFrameDetail) {
      elModalFrameDetail.classList.remove("hidden");
    }
  };

  window.closeFrameModal = function () {
    if (elModalFrameDetail) {
      elModalFrameDetail.classList.add("hidden");
    }
  };

  window.copyFrameJson = function () {
    if (!state.selectedFrame) return;
    const txt = elFrameJsonContent ? elFrameJsonContent.textContent : String(state.selectedFrame.raw_payload || "");
    copyText(txt, "✓ Frame JSON copied to clipboard");
  };

  async function fetchTools() {
    try {
      const res = await fetch("/api/tools");
      if (res && res.ok) {
        const data = await res.json();
        if (Array.isArray(data.tools) && data.tools.length > 0) {
          state.tools = data.tools;
          renderAuditorTable(data);
          populateToolSelector();
          updateMinifierTrace();
        }
      }
    } catch (_err) {}
  }

  function populateToolSelector() {
    if (!elToolSelect) return;
    clearNode(elToolSelect);

    if (state.tools.length === 0) {
      const opt = el("option", "", "No tools discovered yet");
      opt.value = "";
      elToolSelect.appendChild(opt);
      return;
    }

    state.tools.forEach((t) => {
      const opt = el("option", "", `${String(t.name)} (${Number(t.total_tokens || 0)} tk)`);
      opt.value = String(t.name);
      elToolSelect.appendChild(opt);
    });

    selectTool(state.tools[0].name);
  }

  function selectTool(toolName) {
    const tool = state.tools.find((t) => t.name === toolName);
    if (!tool) return;
    state.selectedToolName = toolName;

    if (elToolRawTokens) elToolRawTokens.textContent = `${Number(tool.total_tokens || 0)} tk`;
    if (elToolMinTokens) elToolMinTokens.textContent = `${Number(tool.minified_tokens || 0)} tk`;
    if (elToolSavingsPct) elToolSavingsPct.textContent = `-${Number(tool.savings_percent || 0)}%`;
    if (elRawSchemaView) elRawSchemaView.textContent = JSON.stringify(tool.raw_schema, null, 2);
    if (elMinSchemaView) elMinSchemaView.textContent = JSON.stringify(tool.minified_schema, null, 2);

    renderDynamicToolForm(tool);
  }

  function renderDynamicToolForm(tool) {
    if (!elToolArgsForm) return;
    clearNode(elToolArgsForm);

    const schema = tool.raw_schema?.inputSchema || tool.raw_schema?.parameters || {};
    const props = schema.properties || {};
    const required = Array.isArray(schema.required) ? schema.required : [];
    const entries = Object.entries(props);

    if (entries.length === 0) {
      elToolArgsForm.appendChild(el("p", "panel-sub", "This tool takes no arguments."));
      return;
    }

    entries.forEach(([key, meta]) => {
      const wrap = el("div", "form-field");
      const isReq = required.includes(key);
      const inputId = `arg-input-${key.replace(/[^a-zA-Z0-9_-]/g, "_")}`;

      const label = el("label", "form-label");
      label.setAttribute("for", inputId);
      label.appendChild(document.createTextNode(key + (isReq ? " * " : " ")));
      if (meta && meta.description) {
        label.appendChild(el("span", "form-hint", `(${String(meta.description)})`));
      }
      wrap.appendChild(label);

      const input = el("input", "text-input tool-arg-input");
      input.type = "text";
      input.id = inputId;
      input.name = key;
      input.style.width = "100%";
      input.dataset.type = String((meta && meta.type) || "string");
      const defVal =
        meta && meta.default !== undefined
          ? meta.default
          : meta && Array.isArray(meta.examples) && meta.examples.length > 0
          ? meta.examples[0]
          : "";
      input.value = String(defVal);
      input.placeholder = isReq ? "Required parameter" : "Optional";
      wrap.appendChild(input);

      elToolArgsForm.appendChild(wrap);
    });
  }

  // Real POST /api/replay with deterministic offline fallback
  window.executeToolSimulation = async function () {
    if (!state.selectedToolName) return;

    const args = {};
    document.querySelectorAll(".tool-arg-input").forEach((inp) => {
      const key = inp.name;
      const type = inp.dataset.type;
      const val = inp.value.trim();
      if (val === "") return;
      if (type === "integer" || type === "number") {
        const num = Number(val);
        args[key] = Number.isNaN(num) ? val : num;
      } else if (type === "boolean") {
        args[key] = val.toLowerCase() === "true" || val === "1";
      } else {
        args[key] = val;
      }
    });

    if (elToolResultBox) {
      elToolResultBox.textContent = "Dispatching POST /api/replay JSON-RPC 2.0 frame...";
    }

    if (state.isLiveDaemon) {
      try {
        const res = await fetch("/api/replay", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tool_name: state.selectedToolName, arguments: args })
        });
        if (res && res.ok) {
          const data = await res.json();
          if (elToolResultBox) elToolResultBox.textContent = JSON.stringify(data, null, 2);
          showNotification(`✓ Replayed ${state.selectedToolName} via :8109 /api/replay`);
          await Promise.all([fetchStats(), fetchInitialTraffic()]);
          return;
        }
      } catch (_err) {}
    }

    // Deterministic offline fallback
    const rpcReq = {
      jsonrpc: "2.0",
      id: `local_${state.frames.length + 1}`,
      method: "tools/call",
      params: { name: state.selectedToolName, arguments: args }
    };
    const reqJson = JSON.stringify(rpcReq);
    const reqTokens = estimateTokensLocal(reqJson);
    const localResult = {
      success: true,
      mode: "in-browser-deterministic",
      tool: state.selectedToolName,
      arguments: args,
      response: {
        content: [{ type: "text", text: `[Local Replay] Validated tools/call '${state.selectedToolName}' (${reqTokens} tk).` }],
        isError: false,
        request_tokens: reqTokens
      }
    };
    handleNewFrame({
      frame_id: `local_${Date.now()}`,
      direction: "inbound",
      timestamp: Date.now() / 1000,
      raw_payload: reqJson,
      json_data: rpcReq,
      meta: { method: "tools/call", id: rpcReq.id, byte_size: reqJson.length, estimated_tokens: reqTokens, primary_topic: "tools/call", has_error: false }
    });
    if (elToolResultBox) elToolResultBox.textContent = JSON.stringify(localResult, null, 2);
    showNotification(`✓ Tool ${state.selectedToolName} validated locally`);
  };
  window.executeSimulatedTool = window.executeToolSimulation;

  // Tab 3: All 6 columns matching <thead>
  function renderAuditorTable(data) {
    if (!elAuditorTableBody) return;
    clearNode(elAuditorTableBody);

    const tools = Array.isArray(data?.tools) ? data.tools : [];
    if (tools.length === 0) {
      const tr = el("tr");
      const td = el("td", "mono-cell", "No tools analyzed.");
      td.colSpan = 6;
      td.style.textAlign = "center";
      td.style.padding = "20px";
      tr.appendChild(td);
      elAuditorTableBody.appendChild(tr);
      return;
    }

    const frag = document.createDocumentFragment();
    tools.forEach((t) => {
      const tr = el("tr");
      const rawDesc = String(t.description || t.raw_schema?.description || "");
      const snippet = rawDesc.length > 72 ? rawDesc.slice(0, 69) + "..." : rawDesc || "—";
      const savedTok = Number(t.tokens_saved || 0);
      const saved1MCalls = savedTok * 0.000003 * 1000000;

      tr.appendChild(el("td", "mono-cell", String(t.name || "unnamed")));
      tr.appendChild(el("td", "", snippet));
      tr.appendChild(el("td", "mono-cell", `${Number(t.total_tokens || 0)} tk`));
      tr.appendChild(el("td", "mono-cell tone-emerald", `${Number(t.minified_tokens || 0)} tk`));
      tr.appendChild(el("td", "mono-cell tone-sky", `-${savedTok} tk (${Number(t.savings_percent || 0)}%)`));
      tr.appendChild(el("td", "mono-cell tone-gold", `-$${saved1MCalls.toFixed(2)} / 1M`));
      frag.appendChild(tr);
    });
    elAuditorTableBody.appendChild(frag);
  }

  function updateMinifierTrace(extraLine) {
    if (!elLiveMinifierTrace) return;
    const rawTotal = state.tools.reduce((acc, t) => acc + Number(t.total_tokens || 0), 0);
    const minTotal = state.tools.reduce((acc, t) => acc + Number(t.minified_tokens || 0), 0);
    const saved = Math.max(0, rawTotal - minTotal);
    const pct = rawTotal > 0 ? ((saved / rawTotal) * 100).toFixed(1) : "0.0";
    const lines = [
      `[SESSION] Mode: ${state.isLiveDaemon ? "LIVE LOOPBACK API" : "IN-BROWSER ANALYZER"} · Discovered Tools: ${state.tools.length}`,
      `[AUDIT]   Raw Schema Weight: ${rawTotal} tk → Minified: ${minTotal} tk (Saved: ${saved} tk / ${pct}%)`,
      `[TRAFFIC] Captured Frames: ${state.frames.length} · Buffer Streamed: ${(Number(state.stats.total_bytes || 0) / 1024).toFixed(1)} KB`
    ];
    if (extraLine) lines.push(extraLine);
    elLiveMinifierTrace.textContent = lines.join("\n");
  }

  async function runLiveMinifyCheck() {
    const tool = state.tools.find((t) => t.name === state.selectedToolName) || state.tools[0];
    if (!tool) return;
    if (state.isLiveDaemon) {
      try {
        const res = await fetch("/api/minify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ tool: tool.raw_schema })
        });
        if (res && res.ok) {
          const data = await res.json();
          updateMinifierTrace(
            `[POST /api/minify] '${tool.name}': ${data.original_tokens} tk → ${data.minified_tokens} tk (-${data.tokens_saved} tk / ${data.savings_percent}%)`
          );
          showNotification(`✓ Verified /api/minify for ${tool.name}`);
          return;
        }
      } catch (_err) {}
    }
    updateMinifierTrace(
      `[LOCAL MINIFY] '${tool.name}': ${tool.total_tokens} tk → ${tool.minified_tokens} tk (-${tool.tokens_saved} tk / ${tool.savings_percent}%)`
    );
    showNotification(`✓ Audited ${tool.name} locally`);
  }

  function switchTab(tabId) {
    const tabs = ["waterfall", "playground", "auditor", "recipes"];
    tabs.forEach((t) => {
      const sec = document.getElementById("tab-" + t);
      const btn = document.getElementById("tab-btn-" + t);
      if (sec && btn) {
        const active = t === tabId;
        sec.classList.toggle("hidden", !active);
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      }
    });
  }
  window.switchTab = switchTab;

  function copyText(text, successMsg) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        showNotification(successMsg || "✓ Copied to clipboard");
      }).catch(() => {
        showNotification(successMsg || "✓ Ready to copy");
      });
    } else {
      showNotification(successMsg || "✓ Ready to copy");
    }
  }

  function downloadFile(filename, content, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function setupEventListeners() {
    const btnTheme = document.getElementById("btn-theme-toggle");
    if (btnTheme) {
      btnTheme.addEventListener("click", () => {
        applyTheme(state.theme === "dark" ? "light" : "dark", true);
      });
    }

    const btnHeroCopy = document.getElementById("btn-copy-hero-cmd");
    if (btnHeroCopy) {
      btnHeroCopy.addEventListener("click", () => {
        const txt = document.getElementById("hero-cli-cmd")?.textContent || "mcp-lens proxy -- python3 my_mcp_server.py";
        copyText(txt, "✓ Proxy CLI command copied");
      });
    }

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tabId = btn.dataset.tab;
        if (tabId) switchTab(tabId);
      });
    });

    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("is-active"));
        btn.classList.add("is-active");
        state.activeFilter = btn.dataset.filter || "all";
        renderWaterfall();
      });
    });

    const searchInput = document.getElementById("waterfall-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value.trim();
        renderWaterfall();
      });
    }

    const btnPause = document.getElementById("btn-stream-pause");
    if (btnPause) {
      btnPause.addEventListener("click", () => {
        state.isStreamPaused = !state.isStreamPaused;
        btnPause.textContent = state.isStreamPaused ? "▶ Resume" : "⏸ Pause";
      });
    }

    const btnClear = document.getElementById("btn-stream-clear");
    if (btnClear) {
      btnClear.addEventListener("click", () => {
        state.frames = [];
        renderWaterfall();
        showNotification("Traffic waterfall cleared.");
      });
    }

    // Deduplicated single change listener on tool selector
    if (elToolSelect) {
      elToolSelect.addEventListener("change", (e) => {
        selectTool(e.target.value);
      });
    }

    const btnRun = document.getElementById("btn-run-tool");
    if (btnRun) btnRun.addEventListener("click", () => window.executeToolSimulation());

    const btnCopyMin = document.getElementById("btn-copy-minified");
    if (btnCopyMin) {
      btnCopyMin.addEventListener("click", () => {
        copyText(elMinSchemaView ? elMinSchemaView.textContent : "", "✓ Minified schema copied");
      });
    }

    const btnExportCursor = document.getElementById("btn-export-cursor");
    if (btnExportCursor) {
      btnExportCursor.addEventListener("click", () => {
        let md = "# MCP Tools Configuration (Minified by MCP Lens v2.6.0)\n\n";
        state.tools.forEach((t) => {
          md += `## Tool: ${t.name}\n`;
          md += `Description: ${t.minified_schema?.description || ""}\n`;
          md += `Schema: ${JSON.stringify(t.minified_schema?.inputSchema || t.minified_schema?.parameters || {})}\n\n`;
        });
        downloadFile("mcp_cursor_rules.md", md, "text/markdown");
        showNotification("✓ Cursor Rules downloaded");
      });
    }

    const exportAllHandler = () => {
      const catalog = state.tools.map((t) => t.minified_schema);
      downloadFile("mcp_minified_tools_catalog.json", JSON.stringify(catalog, null, 2), "application/json");
      showNotification("✓ Minified tools catalog downloaded");
    };
    const btnExportAll = document.getElementById("btn-export-all");
    if (btnExportAll) btnExportAll.addEventListener("click", exportAllHandler);
    const btnDownloadAudit = document.getElementById("btn-download-audit");
    if (btnDownloadAudit) btnDownloadAudit.addEventListener("click", exportAllHandler);

    const btnGenPrompt = document.getElementById("btn-gen-prompt");
    if (btnGenPrompt) {
      btnGenPrompt.addEventListener("click", () => {
        let prompt = "Available MCP tools (minified):\n\n";
        state.tools.forEach((t) => {
          prompt += `- ${t.name}: ${t.minified_schema?.description || ""} | params=${JSON.stringify(t.minified_schema?.inputSchema || {})}\n`;
        });
        copyText(prompt, "✓ Optimized system prompt copied");
      });
    }

    const btnLiveMinify = document.getElementById("btn-run-live-minify");
    if (btnLiveMinify) btnLiveMinify.addEventListener("click", runLiveMinifyCheck);

    document.querySelectorAll(".btn-copy-recipe").forEach((btn) => {
      btn.addEventListener("click", () => {
        copyText(btn.dataset.copy || "", "✓ Recipe copied to clipboard");
      });
    });

    const btnCloseX = document.getElementById("btn-close-frame-x");
    if (btnCloseX) btnCloseX.addEventListener("click", window.closeFrameModal);
    const btnCloseDone = document.getElementById("btn-close-frame-done");
    if (btnCloseDone) btnCloseDone.addEventListener("click", window.closeFrameModal);
    const btnCopyFrame = document.getElementById("btn-copy-frame-json");
    if (btnCopyFrame) btnCopyFrame.addEventListener("click", window.copyFrameJson);

    const btnSolana = document.getElementById("btn-copy-solana");
    if (btnSolana) {
      btnSolana.addEventListener("click", () => {
        copyText(SOLANA_TIP_ADDRESS, "✓ Solana tip address copied");
      });
    }

    // Safe Escape handler (no dead paywall call)
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        window.closeFrameModal();
      }
    });
  }

  // Kinetic Hexagonal Aperture Canvas (#hero-aperture-canvas)
  function initHeroCanvas() {
    const canvas = document.getElementById("hero-aperture-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width || 210;
    const height = canvas.height || 200;
    const reducedMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let angle = 0.25;

    function drawFrame() {
      ctx.clearRect(0, 0, width, height);
      const isLight = state.theme === "light";
      const cx = width / 2;
      const cy = height / 2;
      const r = Math.min(width, height) * 0.4;

      // Subtle coordinate ring
      ctx.save();
      ctx.translate(cx, cy);

      ctx.strokeStyle = isLight ? "rgba(3, 105, 161, 0.25)" : "rgba(56, 189, 248, 0.25)";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(0, 0, r * 1.06, 0, Math.PI * 2);
      ctx.stroke();

      // Outer Sky Hexagon
      ctx.save();
      ctx.rotate(angle);
      ctx.strokeStyle = isLight ? "#0369A1" : "#38BDF8";
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        const x = r * Math.cos(a);
        const y = r * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
      ctx.restore();

      // Counter-rotating Gold Hexagon
      ctx.save();
      ctx.rotate(-angle * 1.45);
      ctx.strokeStyle = isLight ? "#7A5600" : "#D4AF37";
      ctx.lineWidth = 2.0;
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        const x = r * 0.66 * Math.cos(a);
        const y = r * 0.66 * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();
      ctx.restore();

      // Emerald Core Aperture
      const pulse = reducedMotion ? 0 : Math.sin(angle * 3) * 2.5;
      ctx.fillStyle = isLight ? "rgba(4, 120, 87, 0.2)" : "rgba(16, 185, 129, 0.25)";
      ctx.strokeStyle = isLight ? "#047857" : "#34D399";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(0, 0, 22 + pulse, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = isLight ? "#7A5600" : "#D4AF37";
      ctx.beginPath();
      ctx.arc(0, 0, 7, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();

      if (!reducedMotion) {
        angle += 0.012;
        requestAnimationFrame(drawFrame);
      }
    }

    drawFrame();
  }

  function showNotification(msg) {
    const toast = el("div", "toast", msg);
    toast.setAttribute("role", "status");
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3000);
  }
})();
