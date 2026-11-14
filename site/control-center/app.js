(function () {
  "use strict";

  const API = window.API_BASE;

  // ── fetch helpers ────────────────────────────────────────────────────────
  async function apiGet(path) {
    const r = await fetch(API + path, { cache: "no-store" });
    if (!r.ok) throw new Error((await safeText(r)) || (r.status + " " + r.statusText));
    return r.json();
  }
  async function apiSend(method, path, body) {
    const r = await fetch(API + path, {
      method, headers: { "Content-Type": "application/json" },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error((await safeText(r)) || (r.status + " " + r.statusText));
    return r.json();
  }
  async function safeText(r) {
    try { const j = await r.json(); return j.detail || JSON.stringify(j); } catch (e) { return ""; }
  }

  // ── formatting ───────────────────────────────────────────────────────────
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
  function fmtMoney(v, d = 2) { if (v == null || isNaN(v)) return "—"; const n = Number(v); return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }); }
  function fmtPct(v, d = 2) { if (v == null || isNaN(v)) return "—"; const n = Number(v); return (n > 0 ? "+" : "") + n.toFixed(d) + "%"; }
  function fmtNum(v, d = 2) { if (v == null || isNaN(v)) return "—"; return Number(v).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: d }); }
  function dirClass(v) { if (v == null || isNaN(v)) return "flat"; return Number(v) > 0 ? "up" : Number(v) < 0 ? "down" : "flat"; }
  function arrow(v) { if (v == null || isNaN(v)) return ""; return Number(v) > 0 ? "▲" : Number(v) < 0 ? "▼" : ""; }
  function pill(v, d = 2) { return `<span class="pill ${dirClass(v)}">${arrow(v)} ${fmtPct(v, d)}</span>`; }
  function badge(label) { return `<span class="badge ${esc(label)}">${esc(label)}</span>`; }

  function statCard(label, value, sub, cls) {
    return `<div class="card stat"><div class="label">${esc(label)}</div><div class="value ${cls||""}">${value}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
  }

  function table(rows, columns) {
    // columns: [{key, label, num, fmt}]
    if (!rows || !rows.length) return '<p class="empty">No data.</p>';
    const thead = columns.map(c => `<th scope="col" class="${c.num ? "num" : ""}">${esc(c.label)}</th>`).join("");
    const body = rows.map(r => "<tr>" + columns.map(c => {
      const raw = r[c.key];
      const val = c.fmt ? c.fmt(raw, r) : esc(raw == null ? "—" : raw);
      return `<td class="${c.num ? "num tnum" : ""}">${val}</td>`;
    }).join("") + "</tr>").join("");
    return `<div class="table-wrap"><table><thead><tr>${thead}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function barList(rows, nameKey, valueKey, fmt) {
    if (!rows || !rows.length) return '<p class="empty">No data.</p>';
    const max = Math.max(...rows.map(r => Math.abs(r[valueKey]) || 0), 1);
    return rows.map(r => {
      const v = r[valueKey] || 0;
      const w = Math.min(100, Math.abs(v) / max * 100);
      return `<div class="bar-row"><div class="name">${esc(r[nameKey])}</div><div class="bar-track"><div class="bar-fill" style="width:${w.toFixed(1)}%"></div></div><div class="amount">${fmt ? fmt(v) : v}</div></div>`;
    }).join("");
  }

  function errorBox(err) {
    return `<div class="error-box">${esc(err.message || String(err))}</div>`;
  }

  function card(title, innerHtml, extraHeader) {
    return `<div class="card"><h2>${esc(title)}${extraHeader || ""}</h2>${innerHtml}</div>`;
  }

  // ── Theme ────────────────────────────────────────────────────────────────
  (function initTheme() {
    let stored = null;
    try { stored = localStorage.getItem("cc-theme"); } catch (e) {}
    if (stored === "light" || stored === "dark") document.documentElement.setAttribute("data-theme", stored);
    document.getElementById("theme-toggle").addEventListener("click", () => {
      const cur = document.documentElement.getAttribute("data-theme") || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      const next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("cc-theme", next); } catch (e) {}
    });
  })();

  // ── Mobile nav (hamburger drawer) ──────────────────────────────────────────
  (function initMobileNav() {
    const sidebar = document.getElementById("sidebar");
    const backdrop = document.getElementById("sidebar-backdrop");
    const toggle = document.getElementById("menu-toggle");
    function setOpen(open) {
      sidebar.classList.toggle("open", open);
      backdrop.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", String(open));
    }
    toggle.addEventListener("click", () => setOpen(!sidebar.classList.contains("open")));
    backdrop.addEventListener("click", () => setOpen(false));
    sidebar.addEventListener("click", (e) => { if (e.target.closest(".nav-item")) setOpen(false); });
    window.addEventListener("hashchange", () => setOpen(false));
  })();

  // ── Pages ────────────────────────────────────────────────────────────────
  const PAGES = [
    { id: "overview", label: "Overview", group: "Workspace" },
    { id: "portfolio", label: "Portfolio", group: "Workspace" },
    { id: "alerts", label: "Alerts", group: "Workspace" },
    { id: "newsletter", label: "Newsletter", group: "Workspace" },
    { id: "monitor", label: "Monitor", group: "Market" },
    { id: "market", label: "Market Workbench", group: "Market" },
    { id: "analytics", label: "Analytics", group: "Market" },
    { id: "factors", label: "Factors", group: "Market" },
    { id: "construction", label: "Construction", group: "Strategy" },
    { id: "backtesting", label: "Backtesting", group: "Strategy" },
    { id: "execution", label: "Execution", group: "Strategy" },
  ];

  function renderNav(activeId) {
    const groups = [...new Set(PAGES.map(p => p.group))];
    document.getElementById("nav").innerHTML = groups.map(g => {
      const items = PAGES.filter(p => p.group === g).map(p =>
        `<button class="nav-item ${p.id === activeId ? "active" : ""}" data-page="${p.id}"${p.id === activeId ? ' aria-current="page"' : ""}><span class="dot"></span>${esc(p.label)}</button>`
      ).join("");
      return `<div class="nav-group-label">${esc(g)}</div>${items}`;
    }).join("");
    document.querySelectorAll(".nav-item").forEach(btn => {
      btn.addEventListener("click", () => { location.hash = "#" + btn.dataset.page; });
    });
  }

  async function withLoading(container, fn) {
    container.innerHTML = '<div class="loading">Loading…</div>';
    try {
      await fn();
    } catch (err) {
      container.innerHTML = errorBox(err);
    }
  }

  // ── Overview ─────────────────────────────────────────────────────────────
  async function pageOverview(main) {
    await withLoading(main, async () => {
      const ov = await apiGet("/api/portfolio/overview");
      main.innerHTML =
        `<div class="page-header"><h1>Overview</h1><div class="sub">Navigate your workflow from one interface.</div></div>` +
        `<div class="grid grid-4">` +
        statCard("Holdings", ov.holdings_count) +
        statCard("Total Shares", fmtNum(ov.total_shares, 3)) +
        statCard("Newsletter Exists", ov.newsletter_exists ? "Yes" : "No") +
        statCard("HTML Size", fmtNum(ov.newsletter_html_size, 0) + " B") +
        `</div>` +
        card("Current Holdings", table(ov.holdings, [
          { key: "ticker", label: "Ticker" },
          { key: "shares", label: "Shares", num: true, fmt: v => fmtNum(v, 3) },
          { key: "cost_basis", label: "Cost Basis", num: true, fmt: v => fmtMoney(v) },
        ])) +
        card("Workflow", `<ol style="margin:0;padding-left:18px;font-size:13px;color:var(--text-secondary);line-height:2;">
            <li>Edit holdings &amp; transactions in <b>Portfolio</b></li>
            <li>Review live signals in <b>Monitor</b>, <b>Factors</b>, <b>Market Workbench</b></li>
            <li>Generate target weights in <b>Construction</b>, test them in <b>Backtesting</b></li>
            <li>Approve trades in <b>Execution</b></li>
            <li>The real daily email + public dashboard run on their own schedule — see <b>Newsletter</b></li>
          </ol>`);
    });
  }

  // ── Portfolio ────────────────────────────────────────────────────────────
  async function pagePortfolio(main) {
    main.innerHTML = `<div class="page-header"><h1>Portfolio</h1><div class="sub">Edit holdings and the transaction log — shared with the daily email pipeline.</div></div>
      <div class="tabs" role="tablist">
        <button class="tab" role="tab" aria-selected="true" data-tab="holdings">Holdings</button>
        <button class="tab" role="tab" aria-selected="false" data-tab="transactions">Transactions</button>
      </div>
      <div id="tab-body" role="tabpanel"></div>`;
    const body = main.querySelector("#tab-body");
    main.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
      main.querySelectorAll(".tab").forEach(x => x.setAttribute("aria-selected", "false"));
      t.setAttribute("aria-selected", "true");
      t.dataset.tab === "holdings" ? renderHoldingsTab(body) : renderTxnsTab(body);
    }));
    await renderHoldingsTab(body);
  }

  async function renderHoldingsTab(body) {
    await withLoading(body, async () => {
      const holdings = await apiGet("/api/portfolio/holdings");
      const rowHtml = (h, i) => `<tr data-i="${i}">
          <td><input type="text" class="h-ticker" value="${esc(h.ticker)}" aria-label="Ticker" style="width:90px;"></td>
          <td class="num"><input type="number" class="h-shares" value="${h.shares}" step="0.001" aria-label="Shares" style="width:110px;text-align:right;"></td>
          <td class="num"><input type="number" class="h-cost" value="${h.cost_basis}" step="0.01" aria-label="Cost basis" style="width:110px;text-align:right;"></td>
          <td><button class="btn danger small h-remove" aria-label="Remove ${esc(h.ticker) || "row"}">Remove</button></td>
        </tr>`;
      body.innerHTML = card("Holdings", `
        <div class="table-wrap"><table><thead><tr><th scope="col">Ticker</th><th scope="col" class="num">Shares</th><th scope="col" class="num">Cost Basis</th><th scope="col"></th></tr></thead>
        <tbody id="holdings-rows">${holdings.map(rowHtml).join("")}</tbody></table></div>
        <div class="btn-row" style="margin-top:14px;">
          <button class="btn" id="add-row">Add Row</button>
          <button class="btn primary" id="save-holdings">Save Holdings</button>
        </div>
        <div id="holdings-msg" class="small" style="margin-top:8px;"></div>
      `);
      const rowsEl = body.querySelector("#holdings-rows");
      function wireRemove() {
        rowsEl.querySelectorAll(".h-remove").forEach(b => b.onclick = () => b.closest("tr").remove());
      }
      wireRemove();
      body.querySelector("#add-row").onclick = () => {
        rowsEl.insertAdjacentHTML("beforeend", rowHtml({ ticker: "", shares: 0, cost_basis: 0 }, rowsEl.children.length));
        wireRemove();
      };
      body.querySelector("#save-holdings").onclick = async (e) => {
        const btn = e.currentTarget, msg = body.querySelector("#holdings-msg");
        const rows = [...rowsEl.querySelectorAll("tr")].map(tr => ({
          ticker: tr.querySelector(".h-ticker").value.trim().toUpperCase(),
          shares: parseFloat(tr.querySelector(".h-shares").value) || 0,
          cost_basis: parseFloat(tr.querySelector(".h-cost").value) || 0,
        })).filter(r => r.ticker);
        btn.disabled = true; msg.textContent = "Saving…"; msg.className = "small muted";
        try {
          const res = await apiSend("PUT", "/api/portfolio/holdings", rows);
          msg.textContent = `Saved ${res.saved} holding(s).`; msg.className = "small up";
        } catch (err) {
          msg.textContent = err.message; msg.className = "small down";
        } finally { btn.disabled = false; }
      };
    });
  }

  async function renderTxnsTab(body) {
    await withLoading(body, async () => {
      const txns = await apiGet("/api/portfolio/transactions");
      body.innerHTML = card("Add Transaction", `
          <div class="grid grid-4">
            <div class="field"><label for="t-date">Date</label><input type="date" id="t-date" value="${new Date().toISOString().slice(0,10)}"></div>
            <div class="field"><label for="t-ticker">Ticker</label><input type="text" id="t-ticker"></div>
            <div class="field"><label for="t-action">Action</label><select id="t-action"><option value="buy">Buy</option><option value="sell">Sell</option></select></div>
            <div class="field"><label for="t-shares">Shares</label><input type="number" id="t-shares" step="0.001"></div>
            <div class="field"><label for="t-price">Price</label><input type="number" id="t-price" step="0.01"></div>
            <div class="field" style="grid-column:span 2;"><label for="t-notes">Notes</label><input type="text" id="t-notes"></div>
          </div>
          <div class="btn-row" style="margin-top:12px;"><button class="btn primary" id="add-txn">Add Transaction</button></div>
          <div id="txn-msg" class="small" style="margin-top:8px;"></div>
        `) +
        card("Transaction Log", table(txns, [
          { key: "date", label: "Date" }, { key: "ticker", label: "Ticker" }, { key: "action", label: "Action" },
          { key: "shares", label: "Shares", num: true, fmt: v => fmtNum(v, 3) },
          { key: "price", label: "Price", num: true, fmt: v => fmtMoney(v) },
          { key: "notes", label: "Notes" },
        ]), ` <span class="count">${txns.length}</span>`);
      body.querySelector("#add-txn").onclick = async (e) => {
        const btn = e.currentTarget, msg = body.querySelector("#txn-msg");
        const payload = {
          date: body.querySelector("#t-date").value,
          ticker: body.querySelector("#t-ticker").value.trim().toUpperCase(),
          action: body.querySelector("#t-action").value,
          shares: parseFloat(body.querySelector("#t-shares").value) || 0,
          price: parseFloat(body.querySelector("#t-price").value) || 0,
          notes: body.querySelector("#t-notes").value,
        };
        if (!payload.ticker || !payload.shares || !payload.price) { msg.textContent = "Ticker, shares and price are required."; msg.className = "small down"; return; }
        btn.disabled = true; msg.textContent = "Saving…"; msg.className = "small muted";
        try {
          await apiSend("POST", "/api/portfolio/transactions", payload);
          msg.textContent = "Added."; msg.className = "small up";
          renderTxnsTab(body);
        } catch (err) {
          msg.textContent = err.message; msg.className = "small down"; btn.disabled = false;
        }
      };
    });
  }

  // ── Monitor ──────────────────────────────────────────────────────────────
  async function pageMonitor(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/monitor");
      main.innerHTML = `<div class="page-header"><h1>Monitor</h1><div class="sub">${esc(d.message || "")}</div></div>`;
      if (d.status !== "Ready") { main.innerHTML += `<p class="empty">${esc(d.message || "Unavailable")}</p>`; return; }
      main.innerHTML +=
        `<div class="grid grid-4">` +
        statCard("Benchmark", esc(d.benchmark)) +
        statCard("SPY Daily", pill(d.spy_daily)) +
        statCard("SPY Weekly", pill(d.spy_weekly)) +
        statCard("SPY YTD", pill(d.spy_ytd)) +
        `</div>` +
        card("Holdings", table(d.holdings, [
          { key: "ticker", label: "Ticker" }, { key: "sector", label: "Sector" },
          { key: "latest_price", label: "Price", num: true, fmt: v => fmtMoney(v) },
          { key: "daily_move_pct", label: "1D", num: true, fmt: v => pill(v) },
          { key: "weekly_move_pct", label: "1W", num: true, fmt: v => pill(v) },
          { key: "monthly_move_pct", label: "1M", num: true, fmt: v => pill(v) },
          { key: "ytd_move_pct", label: "YTD", num: true, fmt: v => pill(v) },
          { key: "distance_from_52w_high_pct", label: "52W", num: true, fmt: v => fmtPct(v, 1) },
          { key: "volume_vs_30d_avg", label: "Vol x30d", num: true, fmt: v => v != null ? Number(v).toFixed(2) + "x" : "—" },
        ]));
    });
  }

  // ── Market Workbench ─────────────────────────────────────────────────────
  async function pageMarket(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/market/overview");
      main.innerHTML = `<div class="page-header"><h1>Market Workbench</h1><div class="sub">Catalysts, SEC signals, macro and sector leadership.</div></div>` +
        card("Upcoming Catalysts (14d)", table(d.catalysts, [
          { key: "Date", label: "Date" }, { key: "Ticker", label: "Ticker" }, { key: "Event Type", label: "Type" }, { key: "Details", label: "Details" },
        ])) +
        card("SEC Filing Signals", table(d.sec_diff, [
          { key: "Ticker", label: "Ticker" }, { key: "Form", label: "Form" }, { key: "Tracked Language", label: "Signals" },
        ])) +
        card("Portfolio Drift vs Equal-Weight", table(d.portfolio_drift, [
          { key: "Ticker", label: "Ticker" },
          { key: "Current Weight (%)", label: "Current", num: true, fmt: v => fmtPct(v, 1) },
          { key: "Target Weight (%)", label: "Target", num: true, fmt: v => fmtPct(v, 1) },
          { key: "Drift (%)", label: "Drift", num: true, fmt: v => pill(v, 1) },
        ])) +
        `<div class="grid grid-2">` +
        card("Macro Indicators", table((d.macro && d.macro.Indicators) || [], [
          { key: "Indicator", label: "Indicator" }, { key: "Latest", label: "Latest", num: true, fmt: v => fmtNum(v) },
          { key: "Daily Change (%)", label: "1D", num: true, fmt: v => pill(v) },
        ])) +
        card("Sector Leadership", table((d.macro && d.macro["Sector Leadership"]) || [], [
          { key: "Sector", label: "Sector" },
          { key: "Weekly Move (%)", label: "1W", num: true, fmt: v => pill(v) },
          { key: "Monthly Move (%)", label: "1M", num: true, fmt: v => pill(v) },
        ])) +
        `</div>`;
    });
  }

  // ── Analytics ────────────────────────────────────────────────────────────
  async function pageAnalytics(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/analytics");
      main.innerHTML = `<div class="page-header"><h1>Analytics</h1><div class="sub">${esc(d.source_note || "")}</div></div>` +
        card("Allocation", barList(d.allocation, "ticker", "weight_pct", v => v.toFixed(1) + "%")) +
        card("Sector Exposure", barList(d.sector_exposure, "sector", "weight_pct", v => v.toFixed(1) + "%")) +
        card("Daily Attribution", table(d.daily_attribution, [
          { key: "ticker", label: "Ticker" },
          { key: "daily_pl", label: "Daily P&L", num: true, fmt: v => `<span class="${dirClass(v)}">${fmtMoney(v)}</span>` },
        ])) +
        card("Rolling Returns", table(d.rolling_returns, [
          { key: "window", label: "Window" }, { key: "return_pct", label: "Return", num: true, fmt: v => pill(v) },
        ])) +
        card("Drawdown (tail)", table((d.drawdown || []).slice(-10), [
          { key: "date", label: "Date" }, { key: "drawdown_pct", label: "Drawdown", num: true, fmt: v => pill(v) },
        ]));
    });
  }

  // ── Factors ──────────────────────────────────────────────────────────────
  async function pageFactors(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/factors");
      main.innerHTML = `<div class="page-header"><h1>Factors</h1><div class="sub">Composite momentum / volatility / relative-strength scoring.</div></div>` +
        card("Factor Signals", table(d.signals, [
          { key: "ticker", label: "Ticker" },
          { key: "composite_score", label: "Composite", num: true, fmt: v => fmtNum(v, 1) },
          { key: "signal_label", label: "Signal" },
          { key: "momentum_21d_pct", label: "Mom 21d", num: true, fmt: v => pill(v) },
          { key: "volatility_21d_pct", label: "Vol 21d", num: true, fmt: v => fmtPct(v, 1) },
          { key: "relative_strength_21d_pct", label: "RS vs SPY", num: true, fmt: v => pill(v) },
          { key: "drawdown_pct", label: "Drawdown", num: true, fmt: v => pill(v) },
        ]));
    });
  }

  // ── Construction ─────────────────────────────────────────────────────────
  async function pageConstruction(main) {
    main.innerHTML = `<div class="page-header"><h1>Construction</h1><div class="sub">Factor-driven target weights and rebalance suggestions.</div></div>
      <div class="card">
        <h2>Construction Settings</h2>
        <div class="grid grid-4">
          <div class="field"><label for="max_pos">Max Position Weight <span class="val" id="v-max_pos">22%</span></label><input type="range" id="max_pos" min="5" max="40" value="22"></div>
          <div class="field"><label for="max_sector">Max Sector Weight <span class="val" id="v-max_sector">40%</span></label><input type="range" id="max_sector" min="20" max="70" value="40"></div>
          <div class="field"><label for="min_pos">Min Position Weight <span class="val" id="v-min_pos">2%</span></label><input type="range" id="min_pos" min="0" max="10" value="2"></div>
          <div class="field"><label for="thresh">Rebalance Threshold <span class="val" id="v-thresh">3%</span></label><input type="range" id="thresh" min="1" max="10" value="3"></div>
        </div>
        <div class="btn-row" style="margin-top:14px;"><button class="btn primary" id="run-construction">Run Construction</button></div>
      </div>
      <div id="construction-result"></div>`;
    main.querySelectorAll('input[type="range"]').forEach(r => {
      const label = main.querySelector("#v-" + (r.id === "thresh" ? "thresh" : r.id));
      r.addEventListener("input", () => { label.textContent = r.value + "%"; });
    });
    main.querySelector("#run-construction").onclick = async (e) => {
      const btn = e.currentTarget, out = main.querySelector("#construction-result");
      btn.disabled = true;
      await withLoading(out, async () => {
        const params = {
          max_position_weight: +main.querySelector("#max_pos").value / 100,
          max_sector_weight: +main.querySelector("#max_sector").value / 100,
          min_position_weight: +main.querySelector("#min_pos").value / 100,
          rebalance_threshold: +main.querySelector("#thresh").value / 100,
        };
        const d = await apiSend("POST", "/api/construction", params);
        if (d.status !== "Ready") { out.innerHTML = `<p class="empty">${esc(d.message || "Unavailable")}</p>`; return; }
        const s = d.summary;
        out.innerHTML =
          `<div class="grid grid-4">` +
          statCard("Portfolio Value", fmtMoney(s.portfolio_value)) +
          statCard("Rebalance Trades", s.rebalance_trades) +
          statCard("Est. Volatility", fmtPct(s.estimated_portfolio_volatility_pct, 1)) +
          statCard("Turnover", fmtPct(s.turnover_pct, 1)) +
          `</div>` +
          card("Current vs Target Weights", table(d.targets, [
            { key: "ticker", label: "Ticker" }, { key: "sector", label: "Sector" }, { key: "action", label: "Action" },
            { key: "current_weight_pct", label: "Current", num: true, fmt: v => fmtPct(v, 1) },
            { key: "target_weight_pct", label: "Target", num: true, fmt: v => fmtPct(v, 1) },
            { key: "trade_value", label: "Trade $", num: true, fmt: v => fmtMoney(v) },
          ])) +
          card("Rebalance Suggestions", d.trades.length
            ? table(d.trades, [
                { key: "ticker", label: "Ticker" }, { key: "action", label: "Action" },
                { key: "trade_value", label: "Trade $", num: true, fmt: v => fmtMoney(v) },
                { key: "weight_drift_pct", label: "Drift", num: true, fmt: v => pill(v, 1) },
              ]) + `<div class="btn-row" style="margin-top:12px;"><button class="btn primary" id="save-reco">Save to Execution Queue</button></div><div id="reco-msg" class="small" style="margin-top:8px;"></div>`
            : '<p class="empty">No rebalance trades exceed the configured threshold.</p>') +
          card("Sector Constraint View", table(d.sector_targets, [
            { key: "sector", label: "Sector" },
            { key: "current_weight_pct", label: "Current", num: true, fmt: v => fmtPct(v, 1) },
            { key: "target_weight_pct", label: "Target", num: true, fmt: v => fmtPct(v, 1) },
          ]));
        const saveBtn = out.querySelector("#save-reco");
        if (saveBtn) saveBtn.onclick = async () => {
          const msg = out.querySelector("#reco-msg");
          saveBtn.disabled = true; msg.textContent = "Saving…"; msg.className = "small muted";
          try {
            const res = await apiSend("POST", "/api/construction/save-recommendations", { trades: d.trades });
            msg.textContent = `Saved ${res.saved} recommendation(s) — see Execution.`; msg.className = "small up";
          } catch (err) { msg.textContent = err.message; msg.className = "small down"; saveBtn.disabled = false; }
        };
      });
      btn.disabled = false;
    };
  }

  // ── Backtesting ──────────────────────────────────────────────────────────
  async function pageBacktesting(main) {
    main.innerHTML = `<div class="page-header"><h1>Backtesting</h1><div class="sub">Rolling rebalance simulation against a benchmark.</div></div>
      <div class="card">
        <h2>Backtest Settings</h2>
        <div class="grid grid-4">
          <div class="field"><label for="bt-bench">Benchmark</label><input type="text" id="bt-bench" value="SPY"></div>
          <div class="field"><label for="bt-look">Lookback Days <span class="val" id="v-bt-look">180</span></label><input type="range" id="bt-look" min="90" max="365" value="180" step="15"></div>
          <div class="field"><label for="bt-freq">Rebalance Freq (Days) <span class="val" id="v-bt-freq">21</span></label><input type="range" id="bt-freq" min="5" max="63" value="21"></div>
          <div class="field"><label for="bt-cost">Txn Cost (bps) <span class="val" id="v-bt-cost">10</span></label><input type="range" id="bt-cost" min="0" max="50" value="10"></div>
        </div>
        <div class="field" style="max-width:220px;margin-top:10px;"><label for="bt-cap">Initial Capital</label><input type="number" id="bt-cap" value="10000" step="1000"></div>
        <div class="btn-row" style="margin-top:14px;"><button class="btn primary" id="run-bt">Run Backtest</button></div>
      </div>
      <div id="bt-result"></div>`;
    main.querySelectorAll('input[type="range"]').forEach(r => {
      const map = { "bt-look": "v-bt-look", "bt-freq": "v-bt-freq", "bt-cost": "v-bt-cost" };
      const label = main.querySelector("#" + map[r.id]);
      r.addEventListener("input", () => { label.textContent = r.value; });
    });
    main.querySelector("#run-bt").onclick = async (e) => {
      const btn = e.currentTarget, out = main.querySelector("#bt-result");
      btn.disabled = true;
      await withLoading(out, async () => {
        const params = {
          benchmark: main.querySelector("#bt-bench").value.toUpperCase().trim() || "SPY",
          lookback_days: +main.querySelector("#bt-look").value,
          rebalance_frequency_days: +main.querySelector("#bt-freq").value,
          transaction_cost_bps: +main.querySelector("#bt-cost").value,
          initial_capital: +main.querySelector("#bt-cap").value || 10000,
        };
        const d = await apiSend("POST", "/api/backtesting", params);
        if (d.status !== "Ready") { out.innerHTML = `<p class="empty">${esc(d.message || "Unavailable")}</p>`; return; }
        const m = d.metrics;
        out.innerHTML =
          `<div class="grid grid-4">` +
          statCard("Strategy Return", fmtPct(m.strategy_total_return_pct), null, dirClass(m.strategy_total_return_pct)) +
          statCard("Benchmark Return", fmtPct(m.benchmark_total_return_pct)) +
          statCard("Active Return", fmtPct(m.active_return_pct), null, dirClass(m.active_return_pct)) +
          statCard("Max Drawdown", fmtPct(m.max_drawdown_pct), null, "down") +
          `</div><div class="grid grid-4">` +
          statCard("Sharpe", fmtNum(m.sharpe_ratio)) +
          statCard("Sortino", fmtNum(m.sortino_ratio)) +
          statCard("Beta", fmtNum(m.beta_to_benchmark)) +
          statCard("Ann. Alpha", fmtPct(m.annualized_alpha_pct)) +
          `</div>` +
          card("Strategy vs Benchmark (equity curve, tail)", table((d.equity_curve || []).slice(-15), [
            { key: "date", label: "Date" },
            { key: "strategy_value", label: "Strategy $", num: true, fmt: v => fmtMoney(v) },
            { key: "benchmark_value", label: "Benchmark $", num: true, fmt: v => fmtMoney(v) },
          ])) +
          card("Factor Contribution", table(d.factor_contribution, [
            { key: "ticker", label: "Ticker" },
            { key: "avg_composite_score", label: "Avg Composite", num: true, fmt: v => fmtNum(v, 1) },
            { key: "avg_momentum_score", label: "Avg Momentum", num: true, fmt: v => fmtNum(v, 1) },
          ]));
      });
      btn.disabled = false;
    };
  }

  // ── Execution ────────────────────────────────────────────────────────────
  async function pageExecution(main) {
    main.innerHTML = `<div class="page-header"><h1>Execution</h1><div class="sub">Approve/reject rebalance recommendations and view the paper-trade ledger.</div></div><div id="exec-body"></div>`;
    const body = main.querySelector("#exec-body");
    await withLoading(body, async () => {
      let summary;
      try {
        summary = await apiGet("/api/execution/summary");
      } catch (err) {
        body.innerHTML = `<div class="error-box">Execution ledger isn't available yet — this backend needs DATABASE_URL (Neon) configured. (${esc(err.message)})</div>`;
        return;
      }
      const [pending, ledger, audit] = await Promise.all([
        apiGet("/api/execution/recommendations?status=Pending"),
        apiGet("/api/execution/ledger"),
        apiGet("/api/execution/audit"),
      ]);
      body.innerHTML =
        `<div class="grid grid-4">` +
        statCard("Pending", summary.pending_recommendations) +
        statCard("Paper Trades", summary.paper_trades) +
        statCard("Traded Value", fmtMoney(summary.total_paper_traded_value)) +
        statCard("Simulated Cash", fmtMoney(summary.cash_balance)) +
        `</div>` +
        card("Simulated Cash Balance", `<div class="field" style="max-width:220px;"><label for="cash-val">Set Balance</label><input type="number" id="cash-val" value="${summary.cash_balance}" step="100"></div>
            <div class="btn-row" style="margin-top:10px;"><button class="btn" id="save-cash">Update</button></div>`) +
        card("Pending Recommendations", pending.length ? renderPendingTable(pending) : '<p class="empty">No pending recommendations. Save some from Construction first.</p>') +
        card("Paper Trade Ledger", table(ledger, [
          { key: "executed_at", label: "Executed" }, { key: "ticker", label: "Ticker" }, { key: "action", label: "Action" },
          { key: "trade_value", label: "Value", num: true, fmt: v => fmtMoney(v) },
          { key: "simulated_price", label: "Price", num: true, fmt: v => v != null ? fmtMoney(v) : "—" },
        ])) +
        card("Execution Audit Trail", table(audit, [
          { key: "created_at", label: "When" }, { key: "event_type", label: "Event" }, { key: "ticker", label: "Ticker" }, { key: "message", label: "Message" },
        ]));
      body.querySelector("#save-cash").onclick = async () => {
        await apiSend("POST", "/api/execution/cash", { value: +body.querySelector("#cash-val").value || 0 });
        pageExecution(main);
      };
      wirePendingActions(body, main);
    });
  }

  function renderPendingTable(pending) {
    const rows = pending.map(r => `<tr>
        <td>${esc(r.id)}</td><td><b>${esc(r.ticker)}</b></td><td>${esc(r.action)}</td>
        <td class="num tnum">${fmtMoney(r.trade_value)}</td><td class="num tnum">${fmtPct(r.weight_drift_pct, 1)}</td>
        <td><input type="text" class="rec-note" placeholder="note" aria-label="Decision note for ${esc(r.ticker)}" style="width:120px;"></td>
        <td><input type="number" class="rec-price" placeholder="sim. price" aria-label="Simulated execution price for ${esc(r.ticker)}" style="width:90px;"></td>
        <td class="btn-row"><button class="btn primary small rec-approve" data-id="${r.id}">Approve</button><button class="btn danger small rec-reject" data-id="${r.id}">Reject</button></td>
      </tr>`).join("");
    return `<div class="table-wrap"><table><thead><tr><th scope="col">ID</th><th scope="col">Ticker</th><th scope="col">Action</th><th scope="col" class="num">Trade $</th><th scope="col" class="num">Drift</th><th scope="col">Note</th><th scope="col">Sim. Price</th><th scope="col"></th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function wirePendingActions(body, main) {
    body.querySelectorAll(".rec-approve, .rec-reject").forEach(btn => {
      btn.onclick = async () => {
        const tr = btn.closest("tr");
        const id = btn.dataset.id;
        const note = tr.querySelector(".rec-note").value;
        const price = parseFloat(tr.querySelector(".rec-price").value) || null;
        const action = btn.classList.contains("rec-approve") ? "approve" : "reject";
        btn.disabled = true;
        try {
          await apiSend("POST", `/api/execution/recommendations/${id}/${action}`, { note, simulated_price: price });
          pageExecution(main);
        } catch (err) {
          alert(err.message);
          btn.disabled = false;
        }
      };
    });
  }

  // ── Alerts ───────────────────────────────────────────────────────────────
  async function pageAlerts(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/alerts");
      main.innerHTML = `<div class="page-header"><h1>Alerts</h1><div class="sub">Recomputed live on every visit.</div></div>` +
        `<div class="grid grid-2">` +
        statCard("Total Alerts", d.summary.total_alerts) +
        statCard("High Severity", d.summary.high_severity_alerts) +
        `</div>` +
        card("Active Alerts", d.alerts.length ? d.alerts.map(a => `
            <div class="list-row" style="display:flex;gap:10px;padding:9px 0;border-bottom:1px solid var(--border);">
              ${badge(a.severity)}
              <div style="font-size:13px;color:var(--text-secondary);">${a.ticker ? `<b>${esc(a.ticker)}</b> — ` : ""}${esc(a.message || a.title)}</div>
            </div>`).join("") : '<p class="empty">No active alerts.</p>');
    });
  }

  // ── Newsletter ───────────────────────────────────────────────────────────
  async function pageNewsletter(main) {
    await withLoading(main, async () => {
      const d = await apiGet("/api/newsletter/status");
      const last = d.last_run;
      main.innerHTML = `<div class="page-header"><h1>Newsletter</h1><div class="sub">The real daily email + public dashboard run on their own local schedule.</div></div>` +
        card("Live Dashboard", `<p style="font-size:13px;color:var(--text-secondary);">The redesigned daily brief is published at:</p>
            <p><a href="${esc(d.dashboard_url)}" target="_blank" rel="noopener">${esc(d.dashboard_url)} ↗</a></p>`) +
        card("Last Pipeline Run", last
          ? table([last], [
              { key: "date", label: "Date" },
              { key: "generate_ok", label: "Generated", fmt: v => v ? "✓" : "✗" },
              { key: "send_ok", label: "Sent", fmt: v => v == null ? "—" : (v ? "✓" : "✗") },
              { key: "deploy_ok", label: "Deployed", fmt: v => v == null ? "—" : (v ? "✓" : "✗") },
              { key: "error", label: "Error" },
            ])
          : '<p class="empty">No run recorded yet — this needs DATABASE_URL configured on the local pipeline too.</p>') +
        card("Why no \"Generate Now\" button", `<p style="font-size:13px;color:var(--text-secondary);line-height:1.6;">
            Triggering the real pipeline from a public web app would risk sending a duplicate email and needs every
            local secret (Gmail app password, API keys) duplicated on Render. Generation stays on the local machine's
            schedule — this page just shows whether it last succeeded.</p>`);
    });
  }

  const ROUTES = {
    overview: pageOverview, portfolio: pagePortfolio, monitor: pageMonitor, market: pageMarket,
    analytics: pageAnalytics, factors: pageFactors, construction: pageConstruction,
    backtesting: pageBacktesting, execution: pageExecution, alerts: pageAlerts, newsletter: pageNewsletter,
  };

  function go() {
    const id = (location.hash || "#overview").slice(1);
    const page = ROUTES[id] ? id : "overview";
    renderNav(page);
    ROUTES[page](document.getElementById("main"));
  }

  window.addEventListener("hashchange", go);
  go();
})();
