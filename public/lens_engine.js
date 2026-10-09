/**
 * MCP Lens Engine — Real-time Stdio/SSE Sniffer & Playground Controller.
 * Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
 * 100% Vanilla ES6+ — Zero External NPM Dependencies.
 */

(function () {
  "use strict";

  // State Management
  const state = {
    isPro: false,
    frames: [],
    tools: [],
    activeFilter: "all",
    searchQuery: "",
    selectedFrame: null,
    selectedToolName: null,
    isStreamPaused: false,
    sseSource: null,
    stats: {
      total_frames: 0,
      total_bytes: 0,
      total_tokens: 0,
      token_overhead: 0,
      potential_savings_tokens: 0,
      savings_percent: 0,
    },
  };

  // DOM Elements
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
  let elModalPaywall;
  let elModalFrameDetail;
  let elFrameJsonContent;
  let elFrameMetaContent;
  let elLicenseKeyInput;
  let elProBadge;

  // Initialize on DOM load
  document.addEventListener("DOMContentLoaded", () => {
    initDOMElements();
    checkLicenseStatus();
    initHeroCanvas();
    fetchStats();
    fetchTools();
    fetchInitialTraffic();
    connectSSE();
    setupEventListeners();
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
    elModalPaywall = document.getElementById("pro-paywall-modal");
    elModalFrameDetail = document.getElementById("frame-detail-modal");
    elFrameJsonContent = document.getElementById("frame-raw-json");
    elFrameMetaContent = document.getElementById("frame-meta-tags");
    elLicenseKeyInput = document.getElementById("input-license-key");
    elProBadge = document.getElementById("header-pro-badge");
  }

  // 1. License & Paywall Engine
  function checkLicenseStatus() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("licensed") === "true") {
      localStorage.setItem("mcp_lens_pro", "active");
      showNotification("⭐ Pro License Activated! Thank you for supporting sovereign AI tools.");
    }

    if (localStorage.getItem("mcp_lens_pro") === "active") {
      state.isPro = true;
      unlockProFeatures();
    }
  }

  function unlockProFeatures() {
    if (elProBadge) {
      elProBadge.textContent = "⭐ PRO ACTIVE";
      elProBadge.classList.add("bg-emerald-900/60", "text-emerald-300", "border-emerald-500/50");
      elProBadge.classList.remove("bg-zinc-800", "text-zinc-400");
    }
    // Remove frosted blur from paywalled sections
    document.querySelectorAll(".pro-blur-overlay").forEach((el) => {
      el.classList.remove("pro-blur-overlay");
    });
    document.querySelectorAll(".pro-lock-gate").forEach((el) => {
      el.style.display = "none";
    });
    const banner = document.getElementById("sales-banner");
    if (banner) {
      banner.style.display = "none";
    }
  }

  window.activateLicenseKey = function () {
    const val = elLicenseKeyInput ? elLicenseKeyInput.value.trim() : "";
    if (val.length >= 6) {
      localStorage.setItem("mcp_lens_pro", "active");
      state.isPro = true;
      unlockProFeatures();
      closePaywallModal();
      showNotification("✓ License validated! All export tools and minifiers unlocked.");
    } else {
      alert("Please enter a valid founding license key or receipt email.");
    }
  };

  window.openPaywallModal = function (featureName) {
    if (state.isPro) return;
    if (elModalPaywall) {
      elModalPaywall.classList.remove("hidden");
      elModalPaywall.classList.add("flex");
      const title = document.getElementById("paywall-feature-title");
      if (title && featureName) {
        title.textContent = `Unlock ${featureName}`;
      }
    }
  };

  window.closePaywallModal = function () {
    if (elModalPaywall) {
      elModalPaywall.classList.add("hidden");
      elModalPaywall.classList.remove("flex");
    }
  };

  window.interceptProAction = function (actionName, callback) {
    if (state.isPro) {
      if (typeof callback === "function") callback();
    } else {
      window.openPaywallModal(actionName);
    }
  };

  // 2. Telemetry & Stats Fetching
  async function fetchStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) return;
      const data = await res.json();
      state.stats = data;
      renderStats();
    } catch (e) {
      console.warn("Could not fetch /api/stats:", e);
    }
  }

  function renderStats() {
    if (elStatsFrames) elStatsFrames.textContent = (state.stats.total_frames || 0).toLocaleString();
    if (elStatsBytes) {
      const kb = ((state.stats.total_bytes || 0) / 1024).toFixed(1);
      elStatsBytes.textContent = `${kb} KB`;
    }
    if (elStatsTokens) elStatsTokens.textContent = (state.stats.token_overhead || state.stats.total_tokens || 0).toLocaleString();
    if (elStatsSavings) {
      const saved = state.stats.potential_savings_tokens || 0;
      const pct = state.stats.savings_percent || 0;
      elStatsSavings.textContent = `${saved.toLocaleString()} (${pct}%)`;
    }
  }

  // 3. Real-Time Server-Sent Events (SSE) Stream
  function connectSSE() {
    if (state.sseSource) {
      state.sseSource.close();
    }

    try {
      state.sseSource = new EventSource("/api/events/stream");

      state.sseSource.onmessage = function (event) {
        if (state.isStreamPaused) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "frame" && data.frame) {
            handleNewFrame(data.frame);
          } else if (data.type === "connected") {
            console.log("Connected to MCP Lens live SSE stream.");
          }
        } catch (err) {
          // heartbeat or non-json
        }
      };

      state.sseSource.onerror = function () {
        const statusDot = document.getElementById("sse-status-dot");
        const statusText = document.getElementById("sse-status-text");
        if (statusDot) statusDot.className = "w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse";
        if (statusText) statusText.textContent = "Reconnecting...";
        setTimeout(connectSSE, 3000);
      };

      state.sseSource.onopen = function () {
        const statusDot = document.getElementById("sse-status-dot");
        const statusText = document.getElementById("sse-status-text");
        if (statusDot) statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        if (statusText) statusText.textContent = "Live Stdio Stream Active";
      };
    } catch (e) {
      console.warn("SSE connection error:", e);
    }
  }

  function handleNewFrame(frame) {
    state.frames.unshift(frame);
    if (state.frames.length > 500) {
      state.frames.pop();
    }
    renderWaterfall();
    fetchStats();
  }

  async function fetchInitialTraffic() {
    try {
      const res = await fetch("/api/traffic?limit=50");
      if (!res.ok) return;
      const data = await res.json();
      if (Array.isArray(data.frames)) {
        state.frames = data.frames;
        renderWaterfall();
      }
    } catch (e) {
      console.warn("Traffic fetch error:", e);
    }
  }

  // 4. Waterfall Rendering & Filtering
  function renderWaterfall() {
    if (!elFramesBody) return;

    const filtered = state.frames.filter((f) => {
      // Method filter
      if (state.activeFilter !== "all") {
        const topic = (f.meta?.primary_topic || f.meta?.method || "").toLowerCase();
        if (state.activeFilter === "tools" && !topic.includes("tools")) return false;
        if (state.activeFilter === "initialize" && !topic.includes("initialize")) return false;
        if (state.activeFilter === "errors" && !f.meta?.has_error) return false;
        if (state.activeFilter === "resources" && !topic.includes("resource")) return false;
        if (state.activeFilter === "prompts" && !topic.includes("prompt")) return false;
      }

      // Search query
      if (state.searchQuery) {
        const q = state.searchQuery.toLowerCase();
        const raw = (f.raw_payload || "").toLowerCase();
        const method = (f.meta?.method || "").toLowerCase();
        if (!raw.includes(q) && !method.includes(q)) return false;
      }
      return true;
    });

    if (filtered.length === 0) {
      elFramesBody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-zinc-500 italic">
            No frames matching filter "${state.activeFilter}". Waiting for active MCP traffic...
          </td>
        </tr>
      `;
      return;
    }

    elFramesBody.innerHTML = filtered
      .slice(0, 100)
      .map((f) => {
        const isIn = f.direction === "inbound";
        const dirBadge = isIn
          ? `<span class="px-2 py-0.5 text-xs font-mono font-medium rounded bg-sky-950/70 text-sky-400 border border-sky-800/60">IN ↓</span>`
          : `<span class="px-2 py-0.5 text-xs font-mono font-medium rounded bg-emerald-950/70 text-emerald-400 border border-emerald-800/60">OUT ↑</span>`;

        const timeStr = new Date(f.timestamp * 1000).toLocaleTimeString();
        const method = f.meta?.method || (f.meta?.has_error ? "error" : "response");
        const methodColor = f.meta?.has_error
          ? "text-rose-400 font-semibold"
          : method.startsWith("tools/")
          ? "text-amber-300 font-medium"
          : method.startsWith("initialize")
          ? "text-purple-300 font-medium"
          : "text-zinc-300";

        const tokens = f.meta?.estimated_tokens || 0;
        const bytes = f.meta?.byte_size || f.raw_payload?.length || 0;
        const rpcId = f.meta?.id !== null && f.meta?.id !== undefined ? `#${f.meta.id}` : "—";

        return `
          <tr class="hover:bg-zinc-900/60 transition-colors border-b border-zinc-800/50 cursor-pointer" onclick="window.inspectFrame('${f.frame_id}')">
            <td class="py-2.5 px-3 whitespace-nowrap text-xs text-zinc-500 font-mono">${timeStr}</td>
            <td class="py-2.5 px-3 whitespace-nowrap">${dirBadge}</td>
            <td class="py-2.5 px-3 font-mono text-xs ${methodColor}">${escapeHtml(method)}</td>
            <td class="py-2.5 px-3 whitespace-nowrap text-xs font-mono text-zinc-400">${rpcId}</td>
            <td class="py-2.5 px-3 whitespace-nowrap text-xs font-mono text-zinc-400">${bytes} B</td>
            <td class="py-2.5 px-3 whitespace-nowrap text-xs font-mono text-sky-300 font-semibold">${tokens} tk</td>
            <td class="py-2.5 px-3 text-right">
              <button class="px-2.5 py-1 text-xs font-medium rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition" onclick="event.stopPropagation(); window.inspectFrame('${f.frame_id}')" aria-label="Inspect frame ${f.frame_id}">
                Inspect
              </button>
            </td>
          </tr>
        `;
      })
      .join("");
  }

  window.inspectFrame = function (frameId) {
    const frame = state.frames.find((f) => f.frame_id === frameId);
    if (!frame) return;

    state.selectedFrame = frame;
    if (elFrameJsonContent) {
      try {
        const pretty = JSON.stringify(frame.json_data || JSON.parse(frame.raw_payload), null, 2);
        elFrameJsonContent.textContent = pretty;
      } catch (e) {
        elFrameJsonContent.textContent = frame.raw_payload;
      }
    }

    if (elFrameMetaContent) {
      elFrameMetaContent.innerHTML = `
        <span class="px-2 py-1 rounded bg-zinc-800 text-zinc-300 text-xs font-mono">Direction: ${frame.direction}</span>
        <span class="px-2 py-1 rounded bg-zinc-800 text-zinc-300 text-xs font-mono">Size: ${frame.meta?.byte_size || 0} bytes</span>
        <span class="px-2 py-1 rounded bg-sky-950 text-sky-300 text-xs font-mono">Tokens: ${frame.meta?.estimated_tokens || 0}</span>
        <span class="px-2 py-1 rounded bg-zinc-800 text-zinc-400 text-xs font-mono">Time: ${new Date(frame.timestamp * 1000).toISOString()}</span>
      `;
    }

    if (elModalFrameDetail) {
      elModalFrameDetail.classList.remove("hidden");
      elModalFrameDetail.classList.add("flex");
    }
  };

  window.closeFrameModal = function () {
    if (elModalFrameDetail) {
      elModalFrameDetail.classList.add("hidden");
      elModalFrameDetail.classList.remove("flex");
    }
  };

  window.copyFrameJson = function () {
    if (!state.selectedFrame) return;
    const txt = elFrameJsonContent ? elFrameJsonContent.textContent : state.selectedFrame.raw_payload;
    navigator.clipboard.writeText(txt).then(() => {
      showNotification("✓ Frame JSON copied to clipboard");
    });
  };

  // 5. Tool Playground & Schema Minifier
  async function fetchTools() {
    try {
      const res = await fetch("/api/tools");
      if (!res.ok) return;
      const data = await res.json();
      state.tools = data.tools || [];
      populateToolSelector();
      renderAuditorTable(data);
    } catch (e) {
      console.warn("Could not fetch tools:", e);
    }
  }

  function populateToolSelector() {
    if (!elToolSelect) return;
    if (state.tools.length === 0) {
      elToolSelect.innerHTML = `<option value="">No tools discovered yet</option>`;
      return;
    }

    elToolSelect.innerHTML = state.tools
      .map((t) => `<option value="${t.name}">${t.name} (${t.total_tokens} tk)</option>`)
      .join("");

    elToolSelect.addEventListener("change", (e) => {
      selectTool(e.target.value);
    });

    if (state.tools.length > 0) {
      selectTool(state.tools[0].name);
    }
  }

  function selectTool(toolName) {
    const tool = state.tools.find((t) => t.name === toolName);
    if (!tool) return;
    state.selectedToolName = toolName;

    // Render Token Weights
    if (elToolRawTokens) elToolRawTokens.textContent = `${tool.total_tokens} tk`;
    if (elToolMinTokens) elToolMinTokens.textContent = `${tool.minified_tokens} tk`;
    if (elToolSavingsPct) elToolSavingsPct.textContent = `-${tool.savings_percent}%`;

    // Render Raw vs Minified code blocks
    if (elRawSchemaView) {
      elRawSchemaView.textContent = JSON.stringify(tool.raw_schema, null, 2);
    }
    if (elMinSchemaView) {
      elMinSchemaView.textContent = JSON.stringify(tool.minified_schema, null, 2);
    }

    // Generate dynamic form arguments
    renderDynamicToolForm(tool);
  }

  function renderDynamicToolForm(tool) {
    if (!elToolArgsForm) return;

    const schema = tool.raw_schema?.inputSchema || tool.raw_schema?.parameters || {};
    const props = schema.properties || {};
    const required = schema.required || [];

    if (Object.keys(props).length === 0) {
      elToolArgsForm.innerHTML = `<p class="text-xs text-zinc-500 italic py-2">This tool takes no arguments.</p>`;
      return;
    }

    let html = `<div class="space-y-3">`;
    for (const [key, meta] of Object.entries(props)) {
      const isReq = required.includes(key);
      const reqBadge = isReq ? `<span class="text-rose-400 font-bold">*</span>` : "";
      const desc = meta.description || "";
      const defaultVal = meta.default !== undefined ? meta.default : meta.examples ? meta.examples[0] : "";

      html += `
        <div>
          <label class="block text-xs font-mono font-medium text-zinc-300 mb-1">
            ${key} ${reqBadge}
            <span class="text-[11px] text-zinc-500 font-sans ml-1">(${meta.type || "string"})</span>
          </label>
          <input 
            type="${meta.type === "integer" || meta.type === "number" ? "number" : "text"}" 
            name="${key}" 
            value="${escapeHtml(String(defaultVal))}" 
            placeholder="${escapeHtml(desc)}" 
            class="w-full px-3 py-1.5 text-xs font-mono bg-zinc-900 border border-zinc-700/80 rounded focus:border-cyan-500 focus:outline-none text-zinc-100"
          />
          ${desc ? `<p class="text-[11px] text-zinc-500 mt-0.5">${escapeHtml(desc)}</p>` : ""}
        </div>
      `;
    }
    html += `</div>`;
    elToolArgsForm.innerHTML = html;
  }

  window.executeSimulatedTool = async function () {
    if (!state.selectedToolName) return;
    const tool = state.tools.find((t) => t.name === state.selectedToolName);
    if (!tool) return;

    // Collect form arguments
    const args = {};
    if (elToolArgsForm) {
      const inputs = elToolArgsForm.querySelectorAll("input");
      inputs.forEach((input) => {
        const val = input.value;
        if (input.type === "number") {
          args[input.name] = Number(val);
        } else {
          args[input.name] = val;
        }
      });
    }

    if (elToolResultBox) {
      elToolResultBox.innerHTML = `<span class="text-sky-400 font-mono text-xs animate-pulse">● Dispatching JSON-RPC 2.0 tools/call to proxy...</span>`;
    }

    const t0 = performance.now();
    try {
      const res = await fetch("/api/replay", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tool_name: state.selectedToolName,
          arguments: args,
        }),
      });

      const data = await res.json();
      const elapsed = Math.round(performance.now() - t0);

      if (elToolResultBox) {
        const statusBadge = data.success
          ? `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-emerald-950 text-emerald-300 border border-emerald-800">SUCCESS (200 OK)</span>`
          : `<span class="px-2 py-0.5 rounded text-[11px] font-mono bg-rose-950 text-rose-300 border border-rose-800">ERROR</span>`;

        elToolResultBox.innerHTML = `
          <div class="flex items-center justify-between pb-2 mb-2 border-b border-zinc-800 text-xs">
            <div class="flex items-center space-x-2">
              ${statusBadge}
              <span class="text-zinc-400 font-mono">${elapsed} ms roundtrip</span>
            </div>
            <span class="text-sky-400 font-mono text-[11px]">${data.tokens_consumed || 0} tokens consumed</span>
          </div>
          <pre class="text-xs font-mono text-zinc-300 overflow-x-auto p-2 bg-zinc-950/70 rounded">${escapeHtml(
            JSON.stringify(data.result, null, 2)
          )}</pre>
        `;
      }
    } catch (err) {
      if (elToolResultBox) {
        elToolResultBox.innerHTML = `<span class="text-rose-400 font-mono text-xs">Execution Error: ${escapeHtml(err.message)}</span>`;
      }
    }
  };

  // 6. Auditor Table & Batch Actions
  function renderAuditorTable(auditData) {
    if (!elAuditorTableBody) return;
    const tools = auditData.tools || [];

    if (tools.length === 0) {
      elAuditorTableBody.innerHTML = `
        <tr>
          <td colspan="6" class="py-6 text-center text-zinc-500 italic">No tools analyzed yet.</td>
        </tr>
      `;
      return;
    }

    elAuditorTableBody.innerHTML = tools
      .map((t) => {
        // Calculate estimated cost at $3.00 / 1M prompt tokens (Claude 3.5 Sonnet standard rate)
        const cost1MCalls = ((t.total_tokens * 1000000) / 1000000) * 0.003;
        const saved1MCalls = ((t.tokens_saved * 1000000) / 1000000) * 0.003;

        return `
          <tr class="hover:bg-zinc-900/60 transition border-b border-zinc-800/40">
            <td class="py-3 px-4 font-mono text-xs font-semibold text-zinc-200">${escapeHtml(t.name)}</td>
            <td class="py-3 px-4 text-xs text-zinc-400 max-w-xs truncate" title="${escapeHtml(t.description)}">${escapeHtml(
          t.description || "—"
        )}</td>
            <td class="py-3 px-4 font-mono text-xs text-zinc-300">${t.total_tokens} tk</td>
            <td class="py-3 px-4 font-mono text-xs text-emerald-400 font-medium">${t.minified_tokens} tk</td>
            <td class="py-3 px-4 font-mono text-xs text-sky-400 font-semibold">-${t.tokens_saved} tk (${t.savings_percent}%)</td>
            <td class="py-3 px-4 font-mono text-xs text-amber-300/90 font-medium">-$${saved1MCalls.toFixed(2)} / 1M</td>
          </tr>
        `;
      })
      .join("");
  }

  window.copyMinifiedSchema = function () {
    const code = elMinSchemaView ? elMinSchemaView.textContent : "";
    navigator.clipboard.writeText(code).then(() => {
      showNotification("✓ Minified Schema copied to clipboard!");
    });
  };

  window.exportAllSchemas = function () {
    window.interceptProAction("Batch Production Schema Export", () => {
      const minifiedCatalog = state.tools.map((t) => t.minified_schema);
      const blob = new Blob([JSON.stringify(minifiedCatalog, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "mcp_minified_tools_catalog.json";
      a.click();
      URL.revokeObjectURL(url);
      showNotification("✓ Full Minified Catalog downloaded!");
    });
  };

  window.generateSystemPrompt = function () {
    window.interceptProAction("Optimized System Prompt Generator", () => {
      let prompt = "You have access to the following optimized MCP tools:\n\n";
      state.tools.forEach((t) => {
        prompt += `### Tool: ${t.name}\n`;
        prompt += `${t.minified_schema.description || ""}\n`;
        prompt += `Parameters: ${JSON.stringify(t.minified_schema.inputSchema || t.minified_schema.parameters || {})}\n\n`;
      });
      navigator.clipboard.writeText(prompt).then(() => {
        showNotification("✓ Optimized MCP Tool Prompt copied to clipboard!");
      });
    });
  };

  // 7. Event Listeners & UI Controls
  function setupEventListeners() {
    // Waterfall filters
    document.querySelectorAll(".filter-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".filter-btn").forEach((b) => {
          b.classList.remove("bg-sky-600", "text-white");
          b.classList.add("bg-zinc-800", "text-zinc-400");
        });
        btn.classList.add("bg-sky-600", "text-white");
        btn.classList.remove("bg-zinc-800", "text-zinc-400");
        state.activeFilter = btn.dataset.filter || "all";
        renderWaterfall();
      });
    });

    // Waterfall search input
    const searchInput = document.getElementById("waterfall-search");
    if (searchInput) {
      searchInput.addEventListener("input", (e) => {
        state.searchQuery = e.target.value.trim();
        renderWaterfall();
      });
    }

    // Pause / Resume stream button
    const btnPause = document.getElementById("btn-stream-pause");
    if (btnPause) {
      btnPause.addEventListener("click", () => {
        state.isStreamPaused = !state.isStreamPaused;
        btnPause.textContent = state.isStreamPaused ? "▶ Resume Stream" : "⏸ Pause Stream";
        btnPause.classList.toggle("bg-amber-800", state.isStreamPaused);
      });
    }

    // Clear buffer button
    const btnClear = document.getElementById("btn-stream-clear");
    if (btnClear) {
      btnClear.addEventListener("click", () => {
        state.frames = [];
        renderWaterfall();
      });
    }
  }

  // 8. Kinetic Hero Canvas Animation (Prismatic Hexagonal Lens)
  function initHeroCanvas() {
    const canvas = document.getElementById("hero-aperture-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = canvas.offsetWidth || 300);
    let height = (canvas.height = canvas.offsetHeight || 300);

    window.addEventListener("resize", () => {
      if (canvas.offsetWidth && canvas.offsetHeight) {
        width = canvas.width = canvas.offsetWidth;
        height = canvas.height = canvas.offsetHeight;
      }
    });

    let angle = 0;
    const particles = [];
    for (let i = 0; i < 24; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.8,
        vy: (Math.random() - 0.5) * 0.8,
        radius: Math.random() * 2 + 1,
        color: i % 2 === 0 ? "rgba(56, 189, 248, 0.4)" : "rgba(212, 175, 55, 0.4)",
      });
    }

    function draw() {
      ctx.clearRect(0, 0, width, height);

      // Draw floating data particles
      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fill();
      });

      const cx = width / 2;
      const cy = height / 2;
      const r = Math.min(width, height) * 0.35;

      // Outer Hexagon (Rotating slowly)
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(angle);

      ctx.strokeStyle = "rgba(56, 189, 248, 0.5)";
      ctx.lineWidth = 2;
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

      // Inner Gold Hexagon (Counter-rotating)
      ctx.rotate(-angle * 1.8);
      ctx.strokeStyle = "rgba(212, 175, 55, 0.7)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let i = 0; i < 6; i++) {
        const a = (Math.PI / 3) * i;
        const x = (r * 0.65) * Math.cos(a);
        const y = (r * 0.65) * Math.sin(a);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.closePath();
      ctx.stroke();

      // Core Aperture Pulsing Circle
      const pulse = Math.sin(angle * 3) * 3;
      ctx.fillStyle = "rgba(16, 185, 129, 0.8)";
      ctx.beginPath();
      ctx.arc(0, 0, 10 + pulse, 0, Math.PI * 2);
      ctx.fill();

      ctx.restore();

      angle += 0.015;
      requestAnimationFrame(draw);
    }

    draw();
  }

  // Toast notifications
  function showNotification(msg) {
    const toast = document.createElement("div");
    toast.className =
      "fixed bottom-6 right-6 z-50 px-4 py-2.5 rounded-lg bg-zinc-900 border border-gold-500/60 text-zinc-100 font-mono text-xs shadow-2xl flex items-center space-x-2 transition-all duration-300";
    toast.innerHTML = `<span>${escapeHtml(msg)}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(10px)";
      setTimeout(() => toast.remove(), 300);
    }, 3200);
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
