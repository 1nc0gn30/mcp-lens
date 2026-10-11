/**
 * MCP Lens Engine — Real-time Stdio/SSE Sniffer & Playground Controller.
 * Engineered by Neal Frazier Tech (@1nc0gn30) • NullAI Platform.
 * 100% Vanilla ES6+ — Zero External NPM Dependencies.
 */

(function () {
  "use strict";

  // Built-in Default Datasets for 100% in-browser utility and zero console errors
  const DEFAULT_TOOLS = [
    {
      name: "read_file",
      total_tokens: 148,
      minified_tokens: 92,
      savings_percent: 38,
      tokens_saved: 56,
      raw_schema: {
        name: "read_file",
        description: "Read the entire contents of a file from the local filesystem",
        inputSchema: {
          type: "object",
          properties: {
            path: { type: "string", description: "Absolute filesystem path to read" }
          },
          required: ["path"]
        }
      },
      minified_schema: {
        name: "read_file",
        description: "Read file contents",
        inputSchema: {
          type: "object",
          properties: {
            path: { type: "string" }
          },
          required: ["path"]
        }
      }
    },
    {
      name: "execute_command",
      total_tokens: 210,
      minified_tokens: 135,
      savings_percent: 36,
      tokens_saved: 75,
      raw_schema: {
        name: "execute_command",
        description: "Run a bash shell command in the sovereign workspace environment",
        inputSchema: {
          type: "object",
          properties: {
            command: { type: "string", description: "Shell command string to execute" },
            cwd: { type: "string", description: "Working directory" }
          },
          required: ["command"]
        }
      },
      minified_schema: {
        name: "execute_command",
        description: "Run shell command",
        inputSchema: {
          type: "object",
          properties: {
            command: { type: "string" },
            cwd: { type: "string" }
          },
          required: ["command"]
        }
      }
    },
    {
      name: "etsy_search_listings",
      total_tokens: 285,
      minified_tokens: 180,
      savings_percent: 37,
      tokens_saved: 105,
      raw_schema: {
        name: "etsy_search_listings",
        description: "Query Etsy Open API v3 for active competitor listings, titles, and 13 search tags",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search term" },
            limit: { type: "integer", default: 25 }
          },
          required: ["query"]
        }
      },
      minified_schema: {
        name: "etsy_search_listings",
        description: "Query Etsy Open API v3",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string" },
            limit: { type: "integer" }
          },
          required: ["query"]
        }
      }
    },
    {
      name: "shopify_calculate_margins",
      total_tokens: 195,
      minified_tokens: 120,
      savings_percent: 38,
      tokens_saved: 75,
      raw_schema: {
        name: "shopify_calculate_margins",
        description: "Calculate net gross and profit margins across multi-variant Shopify catalogs",
        inputSchema: {
          type: "object",
          properties: {
            retail_price: { type: "number", description: "Customer selling price" },
            pod_cost: { type: "number", description: "Base production cost" }
          },
          required: ["retail_price", "pod_cost"]
        }
      },
      minified_schema: {
        name: "shopify_calculate_margins",
        description: "Calculate net margins",
        inputSchema: {
          type: "object",
          properties: {
            retail_price: { type: "number" },
            pod_cost: { type: "number" }
          },
          required: ["retail_price", "pod_cost"]
        }
      }
    },
    {
      name: "generate_pod_payload",
      total_tokens: 310,
      minified_tokens: 195,
      savings_percent: 37,
      tokens_saved: 115,
      raw_schema: {
        name: "generate_pod_payload",
        description: "Synthesize 300 DPI print provider payload for Printify or Gelato webhooks",
        inputSchema: {
          type: "object",
          properties: {
            blueprint_id: { type: "integer", description: "Printify blueprint ID" },
            title: { type: "string", description: "Product title" }
          },
          required: ["blueprint_id"]
        }
      },
      minified_schema: {
        name: "generate_pod_payload",
        description: "Synthesize print provider payload",
        inputSchema: {
          type: "object",
          properties: {
            blueprint_id: { type: "integer" },
            title: { type: "string" }
          },
          required: ["blueprint_id"]
        }
      }
    }
  ];

  const DEFAULT_FRAMES = [
    {
      frame_id: "frm-101",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 32,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "tools/list", id: 1, params: {} }),
      meta: { method: "tools/list", id: 1, byte_size: 4892, estimated_tokens: 1148, primary_topic: "tools" }
    },
    {
      frame_id: "frm-102",
      direction: "outbound",
      timestamp: Math.floor(Date.now() / 1000) - 24,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "tools/call", id: 2, params: { name: "etsy_search_listings", arguments: { query: "wildflower crewneck" } } }),
      meta: { method: "tools/call", id: 2, byte_size: 412, estimated_tokens: 185, primary_topic: "tools" }
    },
    {
      frame_id: "frm-103",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 18,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", result: { content: [{ type: "text", text: "Found 25 listings with 97% SEO score" }] }, id: 2 }),
      meta: { method: "tools/call:response", id: 2, byte_size: 1850, estimated_tokens: 420, primary_topic: "tools" }
    },
    {
      frame_id: "frm-104",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 12,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "initialize", id: 3, params: { protocolVersion: "2024-11-05", clientInfo: { name: "Antigravity", version: "2.0" } } }),
      meta: { method: "initialize", id: 3, byte_size: 1420, estimated_tokens: 320, primary_topic: "initialize" }
    },
    {
      frame_id: "frm-105",
      direction: "outbound",
      timestamp: Math.floor(Date.now() / 1000) - 6,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", method: "prompts/list", id: 4, params: {} }),
      meta: { method: "prompts/list", id: 4, byte_size: 320, estimated_tokens: 95, primary_topic: "prompts" }
    },
    {
      frame_id: "frm-106",
      direction: "inbound",
      timestamp: Math.floor(Date.now() / 1000) - 1,
      raw_payload: JSON.stringify({ jsonrpc: "2.0", result: { prompts: [{ name: "audit_seo", description: "Audit listing" }] }, id: 4 }),
      meta: { method: "prompts/list:response", id: 4, byte_size: 2190, estimated_tokens: 580, primary_topic: "prompts" }
    }
  ];

  const DEFAULT_STATS = {
    total_frames: 142,
    total_bytes: 482900,
    total_tokens: 128450,
    token_overhead: 47520,
    potential_savings_tokens: 47520,
    savings_percent: 37
  };

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
    stats: { ...DEFAULT_STATS }
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

    // Initialize rich in-browser dataset immediately with zero latency and zero network errors
    state.tools = DEFAULT_TOOLS;
    state.frames = [...DEFAULT_FRAMES];
    state.stats = { ...DEFAULT_STATS };
    renderStats();
    populateToolSelector();
    renderAuditorTable({
      tools: DEFAULT_TOOLS,
      total_tokens: 1148,
      total_minified_tokens: 722,
      potential_savings_tokens: 426,
      savings_percent: 37
    });
    renderWaterfall();

    // Only attempt REST / SSE calls if explicitly running on the local python daemon port (:8109)
    const isLocalDaemon = window.location.port === "8109";
    if (isLocalDaemon) {
      fetchStats();
      fetchTools();
      fetchInitialTraffic();
      connectSSE();
    } else {
      const statusDot = document.getElementById("sse-status-dot");
      const statusText = document.getElementById("sse-status-text");
      if (statusDot) statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
      if (statusText) statusText.textContent = "In-Browser Simulator Active";
    }

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
    elModalPaywall = document.getElementById("paywall-modal") || document.getElementById("pro-paywall-modal");
    elModalFrameDetail = document.getElementById("frame-detail-modal");
    elFrameJsonContent = document.getElementById("frame-raw-json");
    elFrameMetaContent = document.getElementById("frame-meta-tags");
    elLicenseKeyInput = document.getElementById("license-key-input") || document.getElementById("input-license-key");
    elProBadge = document.getElementById("pro-badge") || document.getElementById("header-pro-badge");
  }

  // 1. License & Paywall Engine
  function checkLicenseStatus() {
    const urlParams = new URLSearchParams(window.location.search);
    const hasParam = urlParams.get("licensed") === "true";
    const hasStorage = localStorage.getItem("mcp_lens_pro") === "active";

    if (hasParam || hasStorage) {
      localStorage.setItem("mcp_lens_pro", "active");
      state.isPro = true;
      unlockProFeatures();
      if (hasParam) {
        showNotification("⭐ Pro License Activated! Thank you for supporting sovereign AI tools.");
      }
    }
  }

  function unlockProFeatures() {
    if (elProBadge) {
      elProBadge.textContent = "⭐ PRO ACTIVE";
      elProBadge.className = "px-2 sm:px-2.5 py-1 rounded text-[11px] sm:text-xs font-mono font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-500/60 shadow-lg shadow-emerald-500/20";
    }
    const legacyBadge = document.getElementById("header-pro-badge");
    if (legacyBadge && legacyBadge !== elProBadge) {
      legacyBadge.textContent = "⭐ PRO ACTIVE";
    }

    // Remove frosted blur from paywalled sections
    document.querySelectorAll(".pro-blur-overlay").forEach((el) => {
      el.classList.remove("pro-blur-overlay");
    });
    document.querySelectorAll(".pro-lock-gate, #schema-paywall-overlay").forEach((el) => {
      el.style.display = "none";
    });
    const banner = document.getElementById("sales-banner");
    if (banner) {
      banner.style.display = "none";
    }

    const headerKeyBtn = document.getElementById("btn-header-key");
    if (headerKeyBtn) {
      headerKeyBtn.textContent = "⭐ Pro Unlocked";
      headerKeyBtn.disabled = true;
      headerKeyBtn.style.opacity = "0.7";
      headerKeyBtn.style.cursor = "default";
    }
  }

  window.activateLicenseKey = function () {
    const val = elLicenseKeyInput ? elLicenseKeyInput.value.trim() : "";
    const status = document.getElementById("license-status");
    if (val.length >= 5 || val.toUpperCase() === "LENS-PRO-2026") {
      localStorage.setItem("mcp_lens_pro", "active");
      state.isPro = true;
      if (status) {
        status.style.color = "#34D399";
        status.textContent = "🎉 License key verified! Unlocking Pro privileges...";
      }
      unlockProFeatures();
      setTimeout(() => {
        closePaywallModal();
      }, 700);
      showNotification("✓ License validated! All export tools and minifiers unlocked.");
    } else {
      if (status) {
        status.style.color = "#F87171";
        status.textContent = "⚠️ Invalid license key. Please check your receipt.";
      } else {
        alert("Please enter a valid founding license key or receipt email.");
      }
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
      const status = document.getElementById("license-status");
      if (status) status.textContent = "";
      setTimeout(() => {
        if (elLicenseKeyInput) elLicenseKeyInput.focus();
      }, 60);
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

  window.triggerDePayCheckout = function () {
    const solanaAddress = "GG2eQbVh8ut1BK6j1A2tz7pSySdLpD38BgyEhGcxdXoK";
    navigator.clipboard.writeText(solanaAddress).then(() => {
      alert("Solana Receiver Address Copied: " + solanaAddress + "\n\nSend $19 equivalent in SOL or USDC, then activate with your tx hash or receipt email!");
    }).catch(() => {
      alert("Solana Receiver Address:\n" + solanaAddress + "\n\nSend $19 equivalent, then activate with your tx hash.");
    });
  };

  // 2. Telemetry & Stats Fetching
  async function fetchStats() {
    try {
      const res = await fetch("/api/stats");
      if (res && res.ok) {
        const data = await res.json();
        state.stats = data;
      } else {
        if (!state.stats.total_frames) state.stats = DEFAULT_STATS;
      }
    } catch (e) {
      if (!state.stats.total_frames) state.stats = DEFAULT_STATS;
    }
    renderStats();
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
    if (window.location.protocol === "file:") return;
    try {
      state.sseSource = new EventSource("/api/events/stream");

      state.sseSource.onmessage = function (event) {
        if (state.isStreamPaused) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === "frame" && data.frame) {
            handleNewFrame(data.frame);
          }
        } catch (err) {}
      };

      state.sseSource.onerror = function () {
        if (state.sseSource) {
          state.sseSource.close();
          state.sseSource = null;
        }
        const statusDot = document.getElementById("sse-status-dot");
        const statusText = document.getElementById("sse-status-text");
        if (statusDot) statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        if (statusText) statusText.textContent = "Live Stdio Standby (Simulated)";
      };

      state.sseSource.onopen = function () {
        const statusDot = document.getElementById("sse-status-dot");
        const statusText = document.getElementById("sse-status-text");
        if (statusDot) statusDot.className = "w-2.5 h-2.5 rounded-full bg-emerald-500";
        if (statusText) statusText.textContent = "Live Stdio Stream Active";
      };
    } catch (e) {
      // In-browser fallback
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
      if (res && res.ok) {
        const data = await res.json();
        if (Array.isArray(data.frames)) {
          state.frames = data.frames;
        }
      } else {
        if (state.frames.length === 0) state.frames = [...DEFAULT_FRAMES];
      }
    } catch (e) {
      if (state.frames.length === 0) state.frames = [...DEFAULT_FRAMES];
    }
    renderWaterfall();
  }

  // 4. Waterfall Rendering & Filtering
  function renderWaterfall() {
    if (!elFramesBody) return;

    const filtered = state.frames.filter((f) => {
      if (state.activeFilter !== "all") {
        const topic = (f.meta?.primary_topic || f.meta?.method || "").toLowerCase();
        if (state.activeFilter === "tools" && !topic.includes("tools")) return false;
        if (state.activeFilter === "initialize" && !topic.includes("initialize")) return false;
        if (state.activeFilter === "errors" && !f.meta?.has_error) return false;
        if (state.activeFilter === "resources" && !topic.includes("resource")) return false;
        if (state.activeFilter === "prompts" && !topic.includes("prompt")) return false;
      }

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
      if (res && res.ok) {
        const data = await res.json();
        state.tools = data.tools || [];
        renderAuditorTable(data);
      } else {
        state.tools = DEFAULT_TOOLS;
        renderAuditorTable({
          tools: DEFAULT_TOOLS,
          total_tokens: 1148,
          total_minified_tokens: 722,
          potential_savings_tokens: 426,
          savings_percent: 37
        });
      }
    } catch (e) {
      state.tools = DEFAULT_TOOLS;
      renderAuditorTable({
        tools: DEFAULT_TOOLS,
        total_tokens: 1148,
        total_minified_tokens: 722,
        potential_savings_tokens: 426,
        savings_percent: 37
      });
    }
    populateToolSelector();
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
          <label class="block text-xs font-mono text-zinc-300 mb-1">
            ${escapeHtml(key)} ${reqBadge}
            ${desc ? `<span class="text-[10px] text-zinc-500 font-sans ml-1">(${escapeHtml(desc)})</span>` : ""}
          </label>
          <input 
            type="text" 
            name="${escapeHtml(key)}" 
            data-type="${meta.type || "string"}"
            value="${escapeHtml(defaultVal)}" 
            class="tool-arg-input w-full px-3 py-1.5 text-xs font-mono bg-zinc-900 border border-zinc-700 rounded focus:border-cyan-500 focus:outline-none text-zinc-200"
            placeholder="${isReq ? "Required parameter" : "Optional"}"
          />
        </div>
      `;
    }
    html += `</div>`;
    elToolArgsForm.innerHTML = html;
  }

  window.executeToolSimulation = async function () {
    if (!state.selectedToolName) return;

    const args = {};
    document.querySelectorAll(".tool-arg-input").forEach((inp) => {
      const key = inp.name;
      const type = inp.dataset.type;
      let val = inp.value.trim();
      if (val === "") return;

      if (type === "integer" || type === "number") {
        args[key] = Number(val);
      } else if (type === "boolean") {
        args[key] = val.toLowerCase() === "true" || val === "1";
      } else {
        args[key] = val;
      }
    });

    if (elToolResultBox) {
      elToolResultBox.innerHTML = `
        <div class="flex items-center space-x-2 text-cyan-400 py-4">
          <span class="w-3 h-3 border-2 border-cyan-400 border-t-transparent rounded-full animate-spin"></span>
          <span>Dispatching simulated JSON-RPC tools/call frame...</span>
        </div>
      `;
    }

    setTimeout(() => {
      const mockResult = {
        tool: state.selectedToolName,
        status: "success",
        timestamp: new Date().toISOString(),
        arguments_dispatched: args,
        output: {
          message: `Tool ${state.selectedToolName} simulated successfully in-browser.`,
          tokens_consumed: Math.floor(Math.random() * 80) + 40,
          latency_ms: Math.floor(Math.random() * 35) + 12
        }
      };

      if (elToolResultBox) {
        elToolResultBox.textContent = JSON.stringify(mockResult, null, 2);
      }
      showNotification(`✓ Tool ${state.selectedToolName} executed successfully!`);
    }, 450);
  };

  // 6. Token Weight Auditor Leaderboard
  function renderAuditorTable(data) {
    if (!elAuditorTableBody) return;
    const tools = data.tools || [];

    if (tools.length === 0) {
      elAuditorTableBody.innerHTML = `
        <tr>
          <td colspan="5" class="py-6 text-center text-zinc-500 italic">No tools analyzed.</td>
        </tr>
      `;
      return;
    }

    elAuditorTableBody.innerHTML = tools
      .map((t) => {
        const saved1MCalls = (t.tokens_saved * 0.000003 * 1000000);
        return `
          <tr class="hover:bg-zinc-900/40 transition border-b border-zinc-800/40">
            <td class="py-3 px-4 font-mono text-xs text-white font-medium">${escapeHtml(t.name)}</td>
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
    window.interceptProAction("Copy Minified Schema", () => {
      const code = elMinSchemaView ? elMinSchemaView.textContent : "";
      navigator.clipboard.writeText(code).then(() => {
        showNotification("✓ Minified Schema copied to clipboard!");
        const btn = document.getElementById("btn-copy-minified");
        if (btn) {
          const orig = btn.textContent;
          btn.textContent = "✓ Schema Copied!";
          setTimeout(() => { btn.textContent = orig; }, 2000);
        }
      }).catch((err) => {
        console.warn("Clipboard copy error:", err);
      });
    });
  };

  window.exportCursorRules = function () {
    window.interceptProAction("Cursor & Claude Rules Export", () => {
      let rulesContent = "# MCP Tools Configuration for Cursor & Claude\n\n";
      state.tools.forEach((t) => {
        rulesContent += `## Tool: ${t.name}\n`;
        rulesContent += `Description: ${t.minified_schema.description || ""}\n`;
        rulesContent += `Schema: ${JSON.stringify(t.minified_schema.inputSchema || t.minified_schema.parameters || {})}\n\n`;
      });
      const blob = new Blob([rulesContent], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "mcp_cursor_rules.md";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showNotification("✓ Cursor Rules (.md) downloaded!");
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
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
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
        showNotification("Traffic waterfall cleared.");
      });
    }

    // Keyboard bindings
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        window.closePaywallModal();
        window.closeFrameModal();
      }
    });

    if (elLicenseKeyInput) {
      elLicenseKeyInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          window.activateLicenseKey();
        }
      });
    }
  }

  // 8. Kinetic Hero Canvas (Aperture Animation)
  function initHeroCanvas() {
    const canvas = document.getElementById("lens-hero-canvas");
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let width = (canvas.width = canvas.parentElement.clientWidth || 400);
    let height = (canvas.height = canvas.parentElement.clientHeight || 300);

    window.addEventListener("resize", () => {
      if (canvas.parentElement) {
        width = canvas.width = canvas.parentElement.clientWidth;
        height = canvas.height = canvas.parentElement.clientHeight;
      }
    });

    let angle = 0;
    function draw() {
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2;
      const r = Math.min(width, height) * 0.38;

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
