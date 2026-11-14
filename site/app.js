// Portfolio Intelligence dashboard — reads site/data/latest.json + history.json
// and renders the page. No build step, no framework: plain DOM + inline SVG.

(function () {
  "use strict";

  // ── Theme toggle ─────────────────────────────────────────────────────────
  function initTheme() {
    let stored = null;
    try { stored = localStorage.getItem("pi-theme"); } catch (e) {}
    if (stored === "light" || stored === "dark") {
      document.documentElement.setAttribute("data-theme", stored);
    }
    const btn = document.getElementById("theme-toggle");
    btn.addEventListener("click", function () {
      const current = document.documentElement.getAttribute("data-theme");
      const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
      const effectiveCurrent = current || (prefersDark ? "dark" : "light");
      const next = effectiveCurrent === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("pi-theme", next); } catch (e) {}
    });
  }

  // ── Entrance choreography ────────────────────────────────────────────────
  // Every card (except Headline/Executive Summary, which just read as text)
  // reveals itself the moment it scrolls into view, not only once on page
  // load — a chart or bar sitting below the fold used to finish its one-shot
  // animation before anyone scrolled down to see it. Each content type gets
  // its own native motion: numbers count up, bars grow from a baseline,
  // SVG lines draw themselves, everything else cascades in staggered rows.
  // CSS owns every curve/duration; JS only measures paths and flips classes.
  const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
  function prefersReducedMotion() {
    try { return window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) { return false; }
  }

  // Counts a number up from 0 to its real value, re-running the same format
  // function each frame so it reads correctly mid-count (money, %, etc).
  function animateCountUp(el, target, formatFn, duration) {
    if (target == null || isNaN(target)) return;
    duration = duration || 900;
    if (prefersReducedMotion()) { el.textContent = formatFn(target); return; }
    const start = performance.now();
    function tick(now) {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // strong ease-out
      el.textContent = formatFn(target * eased);
      if (t < 1) requestAnimationFrame(tick);
      else el.textContent = formatFn(target);
    }
    requestAnimationFrame(tick);
  }

  // Arms an SVG path to draw itself in: measures its real length so the
  // dasharray/offset are exact, then leaves the actual transition to CSS
  // (`.path-draw.in-view`). Safe to call on any <path>, any time after it's
  // in the DOM (sparklines are re-armed each time their card reveals).
  function armPathDraw(path) {
    if (!path) return;
    try {
      const len = path.getTotalLength();
      path.style.strokeDasharray = String(len);
      path.style.strokeDashoffset = String(len);
      path.classList.add("path-draw");
    } catch (e) { /* path not renderable yet — skip, it'll just show static */ }
  }

  // Fires once per card the first time it scrolls into view: reveals the
  // card itself (CSS handles cascade/bars via descendant selectors), counts
  // up any numbers, and draws any armed SVG lines inside it.
  function revealCard(card) {
    card.classList.add("in-view");
    card.querySelectorAll("[data-countup]").forEach(function (el) {
      const target = parseFloat(el.getAttribute("data-countup"));
      const fmt = el.getAttribute("data-countup-fmt");
      const formatFn = fmt === "pct" ? function (v) { return fmtPct(v); } : function (v) { return fmtMoney(v); };
      animateCountUp(el, target, formatFn);
    });
    card.querySelectorAll(".path-draw").forEach(function (p) { p.classList.add("in-view"); });
  }

  function initScrollReveal() {
    const cards = Array.from(document.querySelectorAll(".card")).filter(function (c) {
      return !c.classList.contains("headline-card") && !c.classList.contains("exec-summary");
    });
    cards.forEach(function (c) { c.classList.add("reveal"); });

    if (prefersReducedMotion()) {
      cards.forEach(revealCard);
      return;
    }
    const io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          revealCard(entry.target);
          io.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -10% 0px" });
    cards.forEach(function (c) { io.observe(c); });
  }

  // ── Privacy toggle (hides $ account value; resets to hidden on every load
  // so it's never accidentally left revealed from a previous visit) ─────────
  function initPrivacy() {
    const btn = document.getElementById("privacy-toggle");
    btn.addEventListener("click", function () {
      const revealed = document.body.classList.toggle("reveal-value");
      btn.textContent = revealed ? "🙈 Hide value" : "👁 Show value";
      btn.setAttribute("aria-pressed", String(revealed));
    });
  }

  // ── Formatting helpers ───────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function fmtMoney(v, opts) {
    opts = opts || {};
    if (v == null || isNaN(v)) return "—";
    const n = Number(v);
    if (opts.compact && Math.abs(n) >= 1000) {
      return (n < 0 ? "-$" : "$") + (Math.abs(n) / 1000).toFixed(1) + "K";
    }
    return (n < 0 ? "-$" : "$") + Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
  function fmtPct(v, digits) {
    if (v == null || isNaN(v)) return "—";
    digits = digits == null ? 2 : digits;
    const n = Number(v);
    return (n > 0 ? "+" : "") + n.toFixed(digits) + "%";
  }
  function dirClass(v) {
    if (v == null || isNaN(v)) return "flat";
    return Number(v) > 0 ? "up" : Number(v) < 0 ? "down" : "flat";
  }
  function arrow(v) {
    if (v == null || isNaN(v)) return "";
    return Number(v) > 0 ? "▲" : Number(v) < 0 ? "▼" : "";
  }
  function pill(v, digits) {
    const cls = dirClass(v);
    return '<span class="pill ' + cls + '">' + arrow(v) + " " + fmtPct(v, digits) + "</span>";
  }
  function dateDisplay(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, {
        month: "short", day: "numeric", year: "numeric",
        hour: "numeric", minute: "2-digit",
      });
    } catch (e) { return iso; }
  }

  // ── Inline SVG mini sparkline (single series, status-colored by direction) ─
  function sparkline(values, opts) {
    opts = opts || {};
    const w = opts.width || 96, h = opts.height || 28;
    const vals = (values || []).filter(function (v) { return v != null && !isNaN(v); });
    if (vals.length < 2) return '<span class="muted small">—</span>';
    const min = Math.min.apply(null, vals), max = Math.max.apply(null, vals);
    const range = max - min || 1;
    const stepX = w / (vals.length - 1);
    const pts = vals.map(function (v, i) {
      const x = i * stepX;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return [x, y];
    });
    const up = vals[vals.length - 1] >= vals[0];
    const color = up ? "var(--good-text)" : "var(--critical)";
    const line = pts.map(function (p, i) { return (i === 0 ? "M" : "L") + p[0].toFixed(1) + "," + p[1].toFixed(1); }).join(" ");
    const fillPath = line + " L" + w + "," + h + " L0," + h + " Z";
    return (
      '<svg class="spark" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" aria-hidden="true">' +
      '<path class="fill" d="' + fillPath + '" fill="' + color + '"></path>' +
      '<path class="line" d="' + line + '" stroke="' + color + '"></path>' +
      "</svg>"
    );
  }

  // ── Trend chart (portfolio value over time) with hover tooltip ─────────────
  function fmtAxisMoney(v) {
    if (Math.abs(v) >= 1000) return (v < 0 ? "-$" : "$") + (Math.abs(v) / 1000).toFixed(1) + "K";
    return (v < 0 ? "-$" : "$") + Math.round(Math.abs(v));
  }

  // Cumulative % return series for both the portfolio and a reconstructed SPY
  // index (compounded from each day's spy_daily_pct), both rebased to 0% at
  // the start of the window so they're directly comparable regardless of units.
  function computeCompareSeries(points) {
    const base = points[0].portfolio_value;
    let spyFactor = 1;
    return points.map(function (p, i) {
      const portfolio_pct = base ? (p.portfolio_value / base - 1) * 100 : 0;
      if (i > 0 && p.spy_daily_pct != null && !isNaN(p.spy_daily_pct)) {
        spyFactor *= (1 + p.spy_daily_pct / 100);
      }
      return { portfolio_pct: portfolio_pct, spy_pct: (spyFactor - 1) * 100 };
    });
  }

  function renderTrendChart(container, points, mode, animateIn) {
    const w = 920, h = 220, padL = 56, padR = 12, padT = 14, padB = 26;
    if (!points || points.length < 2) {
      container.innerHTML = '<p class="empty">Not enough history yet — check back tomorrow. The dashboard builds its own trend line one day at a time.</p>';
      return;
    }
    const compare = mode === "compare";
    const plotW = w - padL - padR, plotH = h - padT - padB;
    const stepX = points.length > 1 ? plotW / (points.length - 1) : 0;
    function xAt(i) { return padL + i * stepX; }

    const series = compare ? computeCompareSeries(points) : null;
    const values = compare
      ? series.map(function (p) { return p.portfolio_pct; }).concat(series.map(function (p) { return p.spy_pct; }))
      : points.map(function (p) { return p.portfolio_value; });
    const min = Math.min.apply(null, values), max = Math.max.apply(null, values);
    const range = (max - min) || Math.max(1, Math.abs(max) * 0.02 || 1);
    function yAt(v) { return padT + plotH - ((v - (min - range * 0.08)) / (range * 1.16)) * plotH; }

    function pathFor(vals) {
      return vals.map(function (v, i) { return (i === 0 ? "M" : "L") + xAt(i).toFixed(1) + "," + yAt(v).toFixed(1); }).join(" ");
    }

    const portfolioVals = compare ? series.map(function (p) { return p.portfolio_pct; }) : points.map(function (p) { return p.portfolio_value; });
    const portfolioLine = pathFor(portfolioVals);
    const portfolioFill = portfolioLine + " L" + xAt(points.length - 1).toFixed(1) + "," + (padT + plotH) + " L" + xAt(0).toFixed(1) + "," + (padT + plotH) + " Z";
    const spyLine = compare ? pathFor(series.map(function (p) { return p.spy_pct; })) : "";

    // Up to 5 gridlines + matching y-axis labels
    const gridLines = [], yLabels = [];
    for (let i = 0; i <= 4; i++) {
      const gy = padT + (plotH / 4) * i;
      gridLines.push('<line x1="' + padL + '" x2="' + (w - padR) + '" y1="' + gy + '" y2="' + gy + '" stroke="var(--grid)" stroke-width="1"></line>');
      const gv = (min - range * 0.08) + (range * 1.16) * (1 - i / 4);
      const labelText = compare ? fmtPct(gv, 0) : fmtAxisMoney(gv);
      const privacyAttr = compare ? "" : ' class="privacy-sensitive"';
      yLabels.push('<text x="' + (padL - 8) + '" y="' + (gy + 3).toFixed(1) + '" font-size="10" fill="var(--text-muted)" text-anchor="end"' + privacyAttr + ">" + esc(labelText) + "</text>");
    }

    // X-axis labels: first, middle, last
    const labelIdxs = [0, Math.floor((points.length - 1) / 2), points.length - 1];
    const xLabels = labelIdxs.map(function (i) {
      const d = points[i].date;
      const short = d ? d.slice(5) : "";
      return '<text x="' + xAt(i) + '" y="' + (h - 6) + '" font-size="10" fill="var(--text-muted)" text-anchor="middle">' + short + "</text>";
    });

    const svgId = "trend-svg-" + Math.random().toString(36).slice(2);
    const legend = compare
      ? '<div class="trend-legend"><span><i></i>Portfolio</span><span><i class="dashed"></i>S&amp;P 500</span></div>'
      : "";

    container.innerHTML =
      legend +
      '<div class="trend-wrap">' +
      '<svg id="' + svgId + '" width="100%" height="' + h + '" viewBox="0 0 ' + w + " " + h + '" preserveAspectRatio="xMidYMid meet">' +
      gridLines.join("") +
      (compare ? "" : '<path class="trend-fill" d="' + portfolioFill + '" fill="var(--accent)" opacity="0.10"></path>') +
      '<path class="portfolio-line" d="' + portfolioLine + '" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"></path>' +
      (compare ? '<path d="' + spyLine + '" fill="none" stroke="var(--text-muted)" stroke-width="1.6" stroke-dasharray="4 3" stroke-linejoin="round" stroke-linecap="round"></path>' : "") +
      '<circle class="hover-dot" r="4.5" fill="var(--accent)" stroke="var(--surface)" stroke-width="2" style="opacity:0"></circle>' +
      '<line class="hover-cross trend-crosshair" style="opacity:0"></line>' +
      yLabels.join("") +
      xLabels.join("") +
      "</svg>" +
      '<div class="trend-tooltip" id="' + svgId + '-tip"></div>' +
      "</div>";

    const svg = document.getElementById(svgId);
    const tip = document.getElementById(svgId + "-tip");
    const dot = svg.querySelector(".hover-dot");
    const cross = svg.querySelector(".hover-cross");

    // Arm the line to draw itself in when its card scrolls into view (see
    // initScrollReveal/revealCard). Toggle-triggered re-renders (animateIn
    // =false) skip arming — a value the user can click several times a visit
    // switches instantly instead of replaying a load-in every time.
    if (animateIn && !prefersReducedMotion()) {
      armPathDraw(svg.querySelector(".portfolio-line"));
      const fill = svg.querySelector(".trend-fill");
      if (fill) fill.classList.add("reveal-fade");
    }

    function nearestIndex(mx) {
      let best = 0, bestDist = Infinity;
      for (let i = 0; i < points.length; i++) {
        const d = Math.abs(xAt(i) - mx);
        if (d < bestDist) { bestDist = d; best = i; }
      }
      return best;
    }

    svg.addEventListener("mousemove", function (evt) {
      const rect = svg.getBoundingClientRect();
      const scale = w / rect.width;
      const mx = (evt.clientX - rect.left) * scale;
      const i = nearestIndex(mx);
      const p = points[i];
      const v = compare ? series[i].portfolio_pct : p.portfolio_value;
      const px = xAt(i), py = yAt(v);
      dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.style.opacity = 1;
      cross.setAttribute("x1", px); cross.setAttribute("x2", px);
      cross.setAttribute("y1", padT); cross.setAttribute("y2", padT + plotH);
      cross.style.opacity = 1;
      const pxPercent = (px / w) * rect.width;
      const pyPercent = (py / h) * rect.height;
      tip.style.left = pxPercent + "px";
      tip.style.top = pyPercent + "px";
      tip.style.opacity = 1;
      tip.innerHTML = compare
        ? "<strong>" + fmtPct(series[i].portfolio_pct) + "</strong> vs SPY " + fmtPct(series[i].spy_pct) +
          '<div class="muted" style="font-size:11px;margin-top:2px;">' + esc(p.date) + "</div>"
        : '<strong class="privacy-sensitive">' + fmtMoney(p.portfolio_value) + "</strong>" +
          '<div class="muted" style="font-size:11px;margin-top:2px;">' + esc(p.date) +
          (p.daily_pct != null ? " · " + fmtPct(p.daily_pct) : "") + "</div>";
    });
    svg.addEventListener("mouseleave", function () {
      dot.style.opacity = 0; cross.style.opacity = 0; tip.style.opacity = 0;
    });
  }

  // ── Section renderers ────────────────────────────────────────────────────
  function renderHero(data) {
    const perf = data.performance || {};
    const stat = function (label, period, suffix) {
      const p = perf[period] || {};
      const port = p.portfolio, spy = p.spy;
      const vsSpy = (port != null && spy != null) ? port - spy : null;
      const countupAttrs = port != null ? ' data-countup="' + port + '" data-countup-fmt="pct"' : "";
      // Initial text is the zero-state when it's about to count up, so there's
      // no flash of the final value before the entrance animation takes over.
      const valueText = port != null ? fmtPct(0) : fmtPct(port);
      return (
        '<div class="card stat-tile">' +
        '<div class="label">' + label + "</div>" +
        '<div class="value tnum ' + dirClass(port) + '"' + countupAttrs + '>' + valueText + "</div>" +
        '<div class="delta ' + dirClass(port) + '">' + arrow(port) + " vs SPY " + fmtPct(spy) + "</div>" +
        '<div class="vs">' + (vsSpy != null ? (vsSpy >= 0 ? "Beating SPY by " + fmtPct(Math.abs(vsSpy)).replace("+", "") : "Trailing SPY by " + fmtPct(Math.abs(vsSpy)).replace("+", "")) : "") + "</div>" +
        "</div>"
      );
    };
    return (
      '<div class="hero">' +
      '<div class="card hero-figure">' +
      '<div class="label">Portfolio value</div>' +
      '<div class="value tnum privacy-sensitive"' +
      (data.portfolio_value != null ? ' data-countup="' + data.portfolio_value + '" data-countup-fmt="money"' : "") +
      '>' + fmtMoney(data.portfolio_value != null ? 0 : data.portfolio_value) + "</div>" +
      '<div class="sub ' + dirClass((perf.today || {}).portfolio) + '">' + arrow((perf.today || {}).portfolio) + " " + fmtPct((perf.today || {}).portfolio) + " today</div>" +
      "</div>" +
      stat("Today", "today") +
      stat("This week", "week") +
      stat("This month", "month") +
      stat("Year to date", "ytd") +
      "</div>"
    );
  }

  function renderHeadline(data) {
    const h = data.headline || {};
    if (!h.title) return "";
    const titleHtml = h.url
      ? '<a href="' + esc(h.url) + '" target="_blank" rel="noopener">' + esc(h.title) + "</a>"
      : esc(h.title);
    return (
      '<div class="card headline-card">' +
      '<h2>Biggest headline</h2>' +
      '<div class="headline-title">' + (h.ticker ? "<b>" + esc(h.ticker) + ":</b> " : "") + titleHtml + "</div>" +
      '<div class="headline-meta">' + esc(h.source || "") + (h.published ? " · " + esc(h.published) : "") + "</div>" +
      "</div>"
    );
  }

  function renderExecSummary(data) {
    if (!data.executive_summary_html) return "";
    return (
      '<div class="card exec-summary">' +
      '<h2>Executive summary</h2>' +
      "<p>" + data.executive_summary_html + "</p>" +
      "</div>"
    );
  }

  function renderHoldings(data, history) {
    const holdings = (data.holdings || []).slice().sort(function (a, b) { return (b.weight_pct || 0) - (a.weight_pct || 0); });
    if (!holdings.length) return '<div class="card"><h2>Holdings</h2><p class="empty">No holdings data.</p></div>';
    const rows = holdings.map(function (h) {
      const series = (history || []).map(function (pt) { return (pt.holdings || {})[h.ticker]; });
      return (
        "<tr>" +
        '<td><div class="ticker">' + esc(h.ticker) + '</div><div class="sector-tag">' + esc(h.sector) + "</div></td>" +
        '<td class="num tnum">' + fmtMoney(h.price) + "</td>" +
        '<td class="num tnum">' + (h.weight_pct != null ? h.weight_pct.toFixed(1) + "%" : "—") + "</td>" +
        '<td class="num">' + pill(h.daily_pct) + "</td>" +
        '<td class="num">' + pill(h.weekly_pct) + "</td>" +
        '<td class="num">' + pill(h.ytd_pct) + "</td>" +
        '<td class="num tnum ' + dirClass(h.pnl_dollar) + '">' + fmtMoney(h.pnl_dollar) + (h.pnl_pct != null ? " (" + fmtPct(h.pnl_pct, 1) + ")" : "") + "</td>" +
        "<td>" + sparkline(series) + "</td>" +
        "</tr>"
      );
    }).join("");
    return (
      '<div class="card">' +
      '<h2>Holdings <span class="count">' + holdings.length + " positions</span></h2>" +
      '<table><thead><tr>' +
      "<th>Ticker</th><th class='num'>Price</th><th class='num'>Weight</th><th class='num'>1D</th><th class='num'>1W</th><th class='num'>YTD</th><th class='num'>Unrealized P&amp;L</th><th>30-day</th>" +
      "</tr></thead><tbody>" + rows + "</tbody></table>" +
      (data.cash_value ? '<p class="muted small" style="margin-top:10px;">+ ' + fmtMoney(data.cash_value) + " cash</p>" : "") +
      "</div>"
    );
  }

  function renderSectorExposure(data) {
    const sectors = data.sector_exposure || [];
    if (!sectors.length) return "";
    const max = Math.max.apply(null, sectors.map(function (s) { return s.weight_pct || 0; }));
    const rows = sectors.map(function (s) {
      const w = max ? (s.weight_pct / max) * 100 : 0;
      return (
        '<div class="bar-row">' +
        '<div class="name">' + esc(s.sector) + "</div>" +
        '<div class="bar-track"><div class="bar-fill" style="width:' + w.toFixed(1) + '%"></div></div>' +
        '<div class="amount">' + s.weight_pct.toFixed(1) + "%</div>" +
        "</div>"
      );
    }).join("");
    return '<div class="card"><h2>Sector exposure</h2>' + rows + "</div>";
  }

  function renderTrendCard(history) {
    return (
      '<div class="card">' +
      '<h2>Portfolio value — last ' + (history || []).length + ' days' +
      '<button class="chip-toggle" id="trend-compare-toggle" type="button" aria-pressed="false">vs S&amp;P 500</button>' +
      "</h2>" +
      '<div id="trend-chart"></div>' +
      "</div>"
    );
  }

  function renderTopMovers(data) {
    const movers = data.top_movers || [];
    if (!movers.length) return "";
    const rows = movers.map(function (m) {
      return (
        '<div class="list-row">' +
        '<div class="left"><b>' + esc(m.ticker) + "</b></div>" +
        '<div class="right">' + pill(parseFloat(m.daily_pct)) + "</div>" +
        "</div>"
      );
    }).join("");
    return '<div class="card"><h2>Top movers today</h2>' + rows + "</div>";
  }

  function renderNews(data) {
    const news = data.news || [];
    if (!news.length) return "";
    const rows = news.slice(0, 10).map(function (n) {
      const title = n.link ? '<a href="' + esc(n.link) + '" target="_blank" rel="noopener">' + esc(n.Title || n.title) + "</a>" : esc(n.Title || n.title);
      return (
        '<div class="news-row">' +
        '<div class="news-title">' + title + "</div>" +
        '<div class="news-meta"><span class="tkr">' + esc(n.Ticker || n.ticker) + "</span> · " + esc(n.Source || n.source || "") + (n.Published ? " · " + esc(n.Published) : "") + "</div>" +
        "</div>"
      );
    }).join("");
    return '<div class="card"><h2>Portfolio news</h2>' + rows + "</div>";
  }

  function renderAlerts(data) {
    const alerts = data.alerts || [];
    const order = { Critical: 0, Important: 1, Informational: 2 };
    const sorted = alerts.slice().sort(function (a, b) { return (order[a.tier] || 3) - (order[b.tier] || 3); });
    const rows = sorted.length
      ? sorted.map(function (a) {
          return (
            '<div class="alert-row">' +
            '<div class="alert-dot ' + esc(a.tier) + '"></div>' +
            '<div class="body"><span class="tier-label ' + esc(a.tier) + '">' + esc(a.type || a.tier) + "</span>" +
            (a.ticker ? esc(a.ticker) + " — " : "") + esc(a.detail) + "</div>" +
            "</div>"
          );
        }).join("")
      : '<p class="empty">No active alerts.</p>';
    return '<div class="card"><h2>Alerts <span class="count">' + alerts.length + "</span></h2>" + rows + "</div>";
  }

  function macroValueLine(m) {
    const parts = [];
    const isNA = function (v) { return v == null || v === "" || String(v).toUpperCase() === "N/A"; };
    if (!isNA(m.actual)) parts.push("Actual " + m.actual);
    if (!isNA(m.expected)) parts.push("Est " + m.expected);
    if (!isNA(m.prior)) parts.push("Prior " + m.prior);
    return parts.join(" · ");
  }

  function renderCatalysts(data) {
    const earnings = (data.catalysts || []).map(function (e) {
      return { label: "<b>" + esc(e.Ticker) + "</b> earnings", date: e.Date, days: e.Days, sub: "" };
    });
    const macro = (data.macro_events || []).map(function (m) {
      return {
        label: "<b>" + esc(m.event || m.Event || "") + "</b>",
        date: m.release_date || m.Date,
        days: m.days_until || m.Days,
        sub: macroValueLine(m),
      };
    });
    const combined = earnings.concat(macro).filter(function (c) { return c.date; }).slice(0, 8);
    if (!combined.length) return "";
    const rows = combined.map(function (c) {
      return (
        '<div class="list-row stacked"><div class="list-row-main"><div class="left">' + c.label +
        '</div><div class="right">' + esc(c.days || c.date) + "</div></div>" +
        (c.sub ? '<div class="list-row-sub">' + esc(c.sub) + "</div>" : "") +
        "</div>"
      );
    }).join("");
    return '<div class="card"><h2>What to watch</h2>' + rows + "</div>";
  }

  function renderRegime(data) {
    const r = data.regime || {};
    const scoreColor = function (v) {
      if (v == null) return "var(--text-muted)";
      if (v >= 66) return "var(--critical)";
      if (v >= 40) return "var(--warning)";
      return "var(--good)";
    };
    const meter = function (label, value) {
      return (
        '<div class="meter-row">' +
        '<div class="meter-head"><span class="name">' + label + '</span><span class="score tnum">' + (value != null ? value + "/100" : "—") + "</span></div>" +
        '<div class="meter-track"><div class="meter-fill" style="width:' + (value || 0) + "%;background:" + scoreColor(value) + ';"></div></div>' +
        "</div>"
      );
    };
    const list = function (items) {
      return (items || []).length ? "<ul style='margin:8px 0 0;padding-left:18px;font-size:12.5px;color:var(--text-secondary);'>" + items.map(function (i) { return "<li>" + esc(i) + "</li>"; }).join("") + "</ul>" : "";
    };
    return (
      '<div class="card">' +
      "<h2>Macro regime <span class='count'>" + esc(r.label || "—") + " · " + esc(r.confidence || "") + " confidence</span></h2>" +
      meter("Risk", r.risk_score) + meter("Inflation", r.inflation_score) + meter("Growth", r.growth_score) + meter("Liquidity", r.liquidity_score) +
      list(r.drivers) +
      (r.narrative ? '<p class="narrative">' + esc(r.narrative) + "</p>" : "") +
      "</div>"
    );
  }

  function renderRates(data) {
    const rt = data.rates || {}; const fg = data.fear_greed || {};
    const tile = function (label, value, sub) {
      return '<div><div class="label small muted">' + label + '</div><div class="value tnum" style="font-size:16px;font-weight:700;margin-top:3px;">' + value + "</div>" + (sub ? '<div class="small muted">' + sub + "</div>" : "") + "</div>";
    };
    return (
      '<div class="card">' +
      "<h2>Rates &amp; sentiment</h2>" +
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">' +
      tile("10Y Treasury", rt.ten_year_yield != null ? rt.ten_year_yield.toFixed(2) + "%" : "—") +
      tile("VIX", rt.vix != null ? rt.vix.toFixed(1) : "—") +
      tile("Yield spread", rt.spread != null ? fmtPct(rt.spread) : "—") +
      tile("Fear &amp; Greed", fg.score != null ? Math.round(fg.score) : "—", fg.rating ? String(fg.rating).replace(/_/g, " ") : "") +
      "</div></div>"
    );
  }

  function renderAnalyst(data) {
    const ratings = data.analyst_ratings || [];
    const targets = data.price_targets || [];
    if (!ratings.length && !targets.length) return "";
    const ratingRows = ratings.slice(0, 6).map(function (r) {
      return '<div class="list-row"><div class="left"><b>' + esc(r.Ticker) + "</b> " + esc(r.Firm) + " — " + esc(r.Rating) + '</div><div class="right">' + esc(r.Action) + "</div></div>";
    }).join("");
    const targetRows = targets.slice(0, 6).map(function (t) {
      return '<div class="list-row"><div class="left"><b>' + esc(t.Ticker) + "</b> " + esc(t.Current) + " → " + esc(t.Target) + '</div><div class="right">' + esc(t.Upside) + "</div></div>";
    }).join("");
    return (
      '<div class="card">' +
      "<h2>Analyst activity</h2>" + (ratingRows || '<p class="empty">No recent ratings.</p>') +
      (targetRows ? '<h2 style="margin-top:16px;">Price targets</h2>' + targetRows : "") +
      "</div>"
    );
  }

  function renderSecDividends(data) {
    const sec = data.sec_filings || [];
    const div = data.dividend_calendar || [];
    if (!sec.length && !div.length) return "";
    const secRows = sec.slice(0, 6).map(function (s) {
      return '<div class="list-row"><div class="left"><b>' + esc(s.Ticker || s.ticker) + "</b> " + esc(s.Form || s.form || "") + '</div><div class="right">' + esc(s.Date || s.date || "") + "</div></div>";
    }).join("");
    const divRows = div.slice(0, 6).map(function (d) {
      return '<div class="list-row"><div class="left"><b>' + esc(d.Ticker || d.ticker) + "</b> ex-div " + esc(d["Ann. Div"] || "") + "</div><div class=\"right\">" + esc(d.Days || d["Ex-Div Date"] || "") + "</div></div>";
    }).join("");
    return (
      '<div class="card">' +
      (secRows ? "<h2>SEC filings</h2>" + secRows : "") +
      (divRows ? '<h2 style="margin-top:16px;">Dividend calendar</h2>' + divRows : "") +
      "</div>"
    );
  }

  function renderRiskNotes(data) {
    const notes = data.risk_notes || [];
    if (!notes.length) return "";
    return '<div class="card"><h2>Portfolio risk notes</h2><ul style="margin:0;padding-left:18px;font-size:13px;color:var(--text-secondary);line-height:1.7;">' +
      notes.map(function (n) { return "<li>" + esc(n) + "</li>"; }).join("") + "</ul></div>";
  }

  // ── Main render ───────────────────────────────────────────────────────────
  function render(data, history) {
    document.getElementById("generated-at").textContent = "Updated " + dateDisplay(data.generated_at);

    const main = [
      renderHeadline(data),
      renderExecSummary(data),
      renderHoldings(data, history),
      renderSectorExposure(data),
      renderTrendCard(history),
      renderTopMovers(data),
      renderRiskNotes(data),
      renderNews(data),
    ].filter(Boolean).join("");

    const side = [
      renderAlerts(data),
      renderCatalysts(data),
      renderRegime(data),
      renderRates(data),
      renderAnalyst(data),
      renderSecDividends(data),
    ].filter(Boolean).join("");

    document.getElementById("app").innerHTML =
      renderHero(data) +
      '<div class="layout"><div class="col">' + main + '</div><div class="col">' + side + "</div></div>";

    const trendEl = document.getElementById("trend-chart");
    const compareBtn = document.getElementById("trend-compare-toggle");
    let trendMode = "value";
    if (trendEl) renderTrendChart(trendEl, history, trendMode, true); // true: arm the draw-in for when it scrolls into view
    if (compareBtn && trendEl) {
      compareBtn.addEventListener("click", function () {
        trendMode = trendMode === "value" ? "compare" : "value";
        compareBtn.setAttribute("aria-pressed", String(trendMode === "compare"));
        renderTrendChart(trendEl, history, trendMode, false); // a toggle the user can click repeatedly switches instantly
      });
    }

    // Arm every holdings sparkline the same way as the main chart, then hand
    // everything to the scroll-reveal system — it decides when each card
    // (and the paths inside it) actually plays, including these.
    if (!prefersReducedMotion()) {
      document.querySelectorAll(".spark .line").forEach(armPathDraw);
    }
    initScrollReveal();
  }

  function renderError(message) {
    document.getElementById("app").innerHTML =
      '<div class="card"><h2>Unable to load data</h2><p class="muted small">' + esc(message) + "</p></div>";
  }

  initTheme();
  initPrivacy();

  Promise.all([
    fetch("data/latest.json", { cache: "no-store" }).then(function (r) { if (!r.ok) throw new Error("latest.json " + r.status); return r.json(); }),
    fetch("data/history.json", { cache: "no-store" }).then(function (r) { return r.ok ? r.json() : []; }).catch(function () { return []; }),
  ])
    .then(function (results) { render(results[0], results[1]); })
    .catch(function (err) { renderError("No data yet — the first overnight run will populate this dashboard. (" + err.message + ")"); });
})();
