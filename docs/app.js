function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(digits);
}

function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString();
}

function fmtPct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${(Number(value) * 100).toFixed(digits)}%`;
}

function esc(value) {
  const span = document.createElement('span');
  span.textContent = String(value ?? '-');
  return span.innerHTML;
}

function toArray(value) {
  return Array.isArray(value) ? value : [];
}

function toObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

let state = {
  payload: null,
  selectedSymbol: null,
  selectedYfSymbol: null,
  priceChart: null,
  benchmarkChart: null,
  indicatorVisibility: {
    close: true,
    sma20: true,
    sma50: true,
    sma200: true,
    ema9: false,
    ema21: false,
    bb_lower: false,
    volume: false,
  },
};

function renderBanner(regime, engine) {
  const banner = document.getElementById('regimeBanner');
  const safeRegime = String(regime || 'unknown').toLowerCase();
  banner.className = `banner ${safeRegime === 'bull' ? 'bull' : safeRegime === 'weak' ? 'weak' : 'neutral'}`;
  banner.textContent = `Regime: ${String(regime || '-').toUpperCase()} | Active Engine: ${String(engine || '-').toUpperCase()}`;
}

function renderSummary(meta, diagnostics) {
  const generated = meta.generated_at || '-';
  const counts = toObject(toObject(diagnostics).counts);
  document.getElementById('generatedAt').textContent = `Generated (UTC): ${generated}`;
  document.getElementById('engineName').textContent = meta.engine || '-';
  document.getElementById('regimeName').textContent = meta.regime || '-';
  document.getElementById('universeSize').textContent = fmtInt(meta.universe_size);

  const rankedCount = counts.ranked_candidates_count ?? meta.candidate_count;
  const rawCount = counts.raw_candidates_count ?? meta.candidate_count;
  document.getElementById('candidateCount').textContent = `${fmtInt(rankedCount)} ranked / ${fmtInt(rawCount)} raw`;
}

function renderTabs() {
  const buttons = Array.from(document.querySelectorAll('.tab-btn'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));

  for (const btn of buttons) {
    btn.addEventListener('click', () => {
      const key = btn.dataset.tab;
      for (const b of buttons) b.classList.toggle('active', b === btn);
      for (const p of panels) p.classList.toggle('active', p.id === `tab${key[0].toUpperCase()}${key.slice(1)}`);
    });
  }
}

function renderStrategy(payload) {
  const strategy = toObject(payload.strategy);
  const benchmark = toObject(payload.benchmark);
  const meta = toObject(payload.meta);

  const strategyName = strategy.name || 'US Market Regime Dual-Engine Screener';
  const strategySummary = strategy.summary || 'Daily static scanner for US-listed stocks using SPY 200MA regime switching.';
  document.getElementById('strategyName').textContent = strategyName;
  document.getElementById('strategySummary').textContent = strategySummary;

  const benchmarkEl = document.getElementById('benchmarkStats');
  benchmarkEl.innerHTML = `
    <p>Symbol: <strong>${esc(benchmark.symbol)}</strong></p>
    <p>Close: <strong>${fmtNumber(benchmark.close)}</strong></p>
    <p>SMA200: <strong>${fmtNumber(benchmark.sma200)}</strong></p>
    <p>Above SMA200: <strong>${esc(benchmark.above_sma200)}</strong></p>
  `;

  const regimeText = String(meta.regime || '').toLowerCase() === 'bull'
    ? 'SPY is above SMA200, so the market is treated as bull/trend-friendly. The Bull engine is active.'
    : 'SPY is below SMA200, so the market is treated as weak/risk-off. The Weak engine is active.';
  document.getElementById('marketRegimeSummary').textContent = regimeText;

  const engines = toObject(strategy.engines);
  const activeEngine = String(meta.engine || '').toLowerCase();
  const enginePlaybook = document.getElementById('enginePlaybook');

  const engineRows = [
    {
      key: 'bull',
      title: engines.bull?.title || 'Bull: Breakout Momentum Engine',
      rules: toArray(engines.bull?.rules),
      tp: engines.bull?.take_profit || 'Take profit: resistance_level + 1x ATR14 (fallback close + 3x ATR14)',
      sl: engines.bull?.stop_loss || 'Stop loss: bb_lower - 1x ATR14',
    },
    {
      key: 'weak',
      title: engines.weak?.title || 'Weak: Oversold Rebound Engine',
      rules: toArray(engines.weak?.rules),
      tp: engines.weak?.take_profit || 'Take profit: resistance_level + 1x ATR14 (fallback close + 3x ATR14)',
      sl: engines.weak?.stop_loss || 'Stop loss: bb_lower - 1x ATR14',
    },
  ];

  enginePlaybook.innerHTML = engineRows
    .map((item) => {
      const isActive = item.key === activeEngine;
      const ruleList = item.rules.length
        ? `<ul class="reason-list">${item.rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>`
        : '<p>-</p>';
      return `
        <div class="engine-card ${isActive ? 'active' : ''}">
          <h3>${esc(item.title)}${isActive ? `<span class="tag ${esc(item.key)}">active</span>` : ''}</h3>
          ${ruleList}
          <p>${esc(item.tp)} | ${esc(item.sl)}</p>
        </div>
      `;
    })
    .join('');

  const active = engineRows.find((row) => row.key === activeEngine) || engineRows[0];
  document.getElementById('activeEngineRules').innerHTML = `
    <strong>Now running: ${esc(active.title)}</strong>
    <ul class="reason-list">${active.rules.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>
  `;

  const scannerSettings = toObject(payload.scanner_settings);
  const settingsSource = Object.keys(scannerSettings).length ? scannerSettings : toObject(meta.settings);
  const settingsEl = document.getElementById('scannerSettings');

  const settingsRows = Object.entries(settingsSource);
  settingsEl.innerHTML = settingsRows.length
    ? settingsRows
        .map(
          ([k, v]) => `
          <div class="setting-item">
            <div class="label">${esc(k)}</div>
            <div>${esc(v)}</div>
          </div>
        `,
        )
        .join('')
    : '<p>No settings data found.</p>';

  document.getElementById('riskNotice').textContent =
    strategy.risk_notice ||
    'Risk guidance and signals are for research only. They are not investment advice. Always size positions and respect stop loss.';
}

function renderDiagnostics(rawDiagnostics) {
  const diagnostics = toObject(rawDiagnostics);
  const counts = toObject(diagnostics.counts);
  const preferredSkipped = toArray(diagnostics.skipped_tickers);
  const skippedTickers = preferredSkipped.length ? preferredSkipped : toArray(diagnostics.skipped);
  const warnings = toArray(diagnostics.warnings);
  const errors = toArray(diagnostics.errors);

  const summary = document.getElementById('diagnosticsSummary');
  summary.innerHTML = `
    <p>Downloaded symbols: <strong>${fmtInt(counts.downloaded_symbols ?? diagnostics.downloaded_symbols)}</strong></p>
    <p>Cached symbols: <strong>${fmtInt(counts.cached_symbols ?? diagnostics.cached_symbols)}</strong></p>
    <p>Rows with metrics: <strong>${fmtInt(counts.rows_with_metrics ?? diagnostics.rows_with_metrics)}</strong></p>
    <p>Skipped tickers: <strong>${fmtInt(counts.missing_or_skipped_count ?? diagnostics.missing_or_skipped_count ?? skippedTickers.length)}</strong></p>
    <p>Raw candidates: <strong>${fmtInt(counts.raw_candidates_count)}</strong> | Ranked shown: <strong>${fmtInt(counts.ranked_candidates_count)}</strong></p>
    <p>Warnings: <strong>${fmtInt(warnings.length)}</strong> | Errors: <strong>${fmtInt(errors.length)}</strong></p>
  `;

  const detail = {
    counts: {
      downloaded_symbols: counts.downloaded_symbols ?? diagnostics.downloaded_symbols ?? null,
      cached_symbols: counts.cached_symbols ?? diagnostics.cached_symbols ?? null,
      rows_with_metrics: counts.rows_with_metrics ?? diagnostics.rows_with_metrics ?? null,
      missing_or_skipped_count:
        counts.missing_or_skipped_count ?? diagnostics.missing_or_skipped_count ?? skippedTickers.length,
      raw_candidates_count: counts.raw_candidates_count ?? null,
      ranked_candidates_count: counts.ranked_candidates_count ?? null,
    },
    skipped_tickers: skippedTickers,
    warnings,
    errors,
  };

  document.getElementById('diagnostics').textContent = JSON.stringify(detail, null, 2);
}

function getCandidateByYfSymbol(yfSymbol) {
  return toArray(state.payload?.candidates).find((c) => String(c.yf_symbol) === String(yfSymbol)) || null;
}

function renderCandidateTable(candidates) {
  const tbody = document.querySelector('#candidatesTable tbody');
  tbody.innerHTML = '';

  const safeCandidates = toArray(candidates);
  if (!safeCandidates.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="7">No candidates produced in this run.</td>';
    tbody.appendChild(tr);
    return;
  }

  for (const c of safeCandidates) {
    const tr = document.createElement('tr');
    tr.dataset.yfSymbol = String(c.yf_symbol || '');
    tr.innerHTML = `
      <td>${fmtInt(c.rank)}</td>
      <td>${esc(c.symbol)}</td>
      <td>${esc(c.engine)}</td>
      <td>${fmtNumber(c.score, 4)}</td>
      <td>${fmtNumber(c.close)}</td>
      <td>${fmtNumber(c.risk?.stop_loss)}</td>
      <td>${fmtNumber(c.risk?.take_profit)}</td>
    `;

    tr.addEventListener('click', () => {
      state.selectedSymbol = String(c.symbol || '');
      state.selectedYfSymbol = String(c.yf_symbol || '');
      highlightSelectedRow();
      renderSelectedDetails(c);
      renderSymbolChart(c);
    });

    tbody.appendChild(tr);
  }
}

function highlightSelectedRow() {
  const rows = Array.from(document.querySelectorAll('#candidatesTable tbody tr'));
  for (const row of rows) {
    row.classList.toggle('active', row.dataset.yfSymbol === state.selectedYfSymbol);
  }
}

function renderSelectedDetails(candidate) {
  const c = toObject(candidate);
  const risk = toObject(c.risk);
  const fundamentals = toObject(c.fundamentals);

  document.getElementById('selectedSymbolTitle').textContent = `${String(c.symbol || '-')} details`;

  const meta = document.getElementById('selectedSymbolMeta');
  meta.innerHTML = `
    <div class="meta-item">
      <div class="meta-label">Current Price (Close)</div>
      <div class="meta-value">${fmtNumber(c.close)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Stop Loss</div>
      <div class="meta-value sl">${fmtNumber(risk.stop_loss)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">Take Profit</div>
      <div class="meta-value tp">${fmtNumber(risk.take_profit)}</div>
    </div>
    <div class="meta-item">
      <div class="meta-label">ATR14</div>
      <div class="meta-value">${fmtNumber(risk.atr14)}</div>
    </div>
  `;

  const fundamentalsEl = document.getElementById('selectedFundamentals');
  fundamentalsEl.innerHTML = `
    <div class="fund-item">
      <div class="fund-label">ROE</div>
      <div class="fund-value">${fmtPct(fundamentals.roe)}</div>
    </div>
    <div class="fund-item">
      <div class="fund-label">P/E</div>
      <div class="fund-value">${fmtNumber(fundamentals.pe)}</div>
    </div>
    <div class="fund-item">
      <div class="fund-label">Revenue Growth QoQ</div>
      <div class="fund-value">${fmtPct(fundamentals.revenue_growth_qoq)}</div>
    </div>
    <div class="fund-item">
      <div class="fund-label">Revenue Growth YoY</div>
      <div class="fund-value">${fmtPct(fundamentals.revenue_growth_yoy)}</div>
    </div>
    <div class="fund-item">
      <div class="fund-label">Engine</div>
      <div class="fund-value">${esc(c.engine || '-')}</div>
    </div>
    <div class="fund-item">
      <div class="fund-label">Score</div>
      <div class="fund-value">${fmtNumber(c.score, 4)}</div>
    </div>
  `;
}

function getChartConfigForSymbol(symbolOrYfSymbol) {
  const charts = toObject(state.payload?.charts);
  const symbols = toObject(charts.symbols);
  return toObject(symbols[symbolOrYfSymbol]);
}

function createToggle(id, label, checked) {
  const wrapper = document.createElement('label');
  wrapper.innerHTML = `<input type="checkbox" data-indicator="${esc(id)}" ${checked ? 'checked' : ''} /> ${esc(label)}`;
  return wrapper;
}

function renderIndicatorToggles() {
  const host = document.getElementById('chartToggles');
  host.innerHTML = '';

  const defs = [
    ['close', 'Close'],
    ['sma20', 'SMA20'],
    ['sma50', 'SMA50'],
    ['sma200', 'SMA200'],
    ['ema9', 'EMA9'],
    ['ema21', 'EMA21'],
    ['bb_lower', 'BB Lower'],
    ['volume', 'Volume'],
  ];

  for (const [key, label] of defs) {
    host.appendChild(createToggle(key, label, !!state.indicatorVisibility[key]));
  }

  host.addEventListener('change', (evt) => {
    const target = evt.target;
    if (!target || target.tagName !== 'INPUT') return;
    const key = target.getAttribute('data-indicator');
    if (!key) return;
    state.indicatorVisibility[key] = target.checked;
    const selected = getCandidateByYfSymbol(state.selectedYfSymbol);
    if (selected) renderSymbolChart(selected);
  });
}

function destroyChart(chartRef) {
  if (chartRef) chartRef.destroy();
}

function renderSymbolChart(candidate) {
  const chartCfg = getChartConfigForSymbol(String(candidate.yf_symbol || ''));
  const labels = toArray(chartCfg.dates);

  const ctx = document.getElementById('priceChart');
  destroyChart(state.priceChart);

  if (!labels.length) {
    document.getElementById('priceChartTitle').textContent = `${String(candidate.symbol || '-')} | 1Y chart unavailable`;
    state.priceChart = null;
    return;
  }

  document.getElementById('priceChartTitle').textContent = `${String(candidate.symbol || '-')} | Price & Indicators (1Y)`;

  const datasets = [
    {
      type: 'line',
      label: 'Adj Close',
      data: toArray(chartCfg.adj_close),
      borderColor: '#3b82f6',
      borderWidth: 2,
      pointRadius: 0,
      hidden: !state.indicatorVisibility.close,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'SMA20',
      data: toArray(chartCfg.sma20),
      borderColor: '#f59e0b',
      borderWidth: 1.8,
      borderDash: [8, 4],
      pointRadius: 0,
      hidden: !state.indicatorVisibility.sma20,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'SMA50',
      data: toArray(chartCfg.sma50),
      borderColor: '#22c55e',
      borderWidth: 1.8,
      borderDash: [4, 4],
      pointRadius: 0,
      hidden: !state.indicatorVisibility.sma50,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'SMA200',
      data: toArray(chartCfg.sma200),
      borderColor: '#e879f9',
      borderWidth: 1.8,
      borderDash: [2, 4],
      pointRadius: 0,
      hidden: !state.indicatorVisibility.sma200,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'EMA9',
      data: toArray(chartCfg.ema9),
      borderColor: '#06b6d4',
      borderWidth: 1.7,
      pointRadius: 0,
      hidden: !state.indicatorVisibility.ema9,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'EMA21',
      data: toArray(chartCfg.ema21),
      borderColor: '#84cc16',
      borderWidth: 1.7,
      pointRadius: 0,
      hidden: !state.indicatorVisibility.ema21,
      yAxisID: 'y',
    },
    {
      type: 'line',
      label: 'BB Lower',
      data: toArray(chartCfg.bb_lower),
      borderColor: '#ef4444',
      borderWidth: 1.6,
      borderDash: [2, 2],
      pointRadius: 0,
      hidden: !state.indicatorVisibility.bb_lower,
      yAxisID: 'y',
    },
    {
      type: 'bar',
      label: 'Volume',
      data: toArray(chartCfg.volume),
      backgroundColor: 'rgba(148, 163, 184, 0.35)',
      borderColor: 'rgba(148, 163, 184, 0.6)',
      borderWidth: 0.4,
      hidden: !state.indicatorVisibility.volume,
      yAxisID: 'yVol',
    },
  ];

  state.priceChart = new Chart(ctx, {
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      scales: {
        x: {
          ticks: { color: '#cbd5e1', maxTicksLimit: 10 },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
        y: {
          type: 'linear',
          position: 'left',
          stack: 'chartStack',
          stackWeight: 3,
          ticks: { color: '#cbd5e1' },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
        yVol: {
          type: 'linear',
          position: 'right',
          stack: 'chartStack',
          stackWeight: 1,
          beginAtZero: true,
          ticks: { color: '#94a3b8', maxTicksLimit: 3 },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: {
        legend: {
          labels: { color: '#e2e8f0' },
        },
      },
    },
  });
}

function renderBenchmarkChart() {
  const charts = toObject(state.payload?.charts);
  const benchmark = toObject(charts.benchmark);
  const series = toObject(benchmark.series);

  const labels = toArray(series.dates);
  const ctx = document.getElementById('benchmarkChart');
  destroyChart(state.benchmarkChart);

  if (!labels.length) {
    state.benchmarkChart = null;
    return;
  }

  state.benchmarkChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: `${String(benchmark.symbol || 'SPY')} Adj Close`,
          data: toArray(series.adj_close),
          borderColor: '#60a5fa',
          borderWidth: 2,
          pointRadius: 0,
        },
        {
          label: 'SMA200',
          data: toArray(series.sma200),
          borderColor: '#f59e0b',
          borderDash: [8, 4],
          borderWidth: 1.6,
          pointRadius: 0,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      scales: {
        x: {
          ticks: { color: '#cbd5e1', maxTicksLimit: 10 },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
        y: {
          ticks: { color: '#cbd5e1' },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
      },
      plugins: {
        legend: { labels: { color: '#e2e8f0' } },
      },
    },
  });
}

function initSelection() {
  const candidates = toArray(state.payload?.candidates);
  if (!candidates.length) return;

  const defaults = toObject(toObject(state.payload?.charts).default_visibility);
  state.indicatorVisibility = {
    ...state.indicatorVisibility,
    ...defaults,
  };

  const first = candidates[0];
  state.selectedSymbol = String(first.symbol || '');
  state.selectedYfSymbol = String(first.yf_symbol || '');
  highlightSelectedRow();
  renderSelectedDetails(first);
  renderIndicatorToggles();
  renderSymbolChart(first);
}

function showLoadError(message, stack = '') {
  const banner = document.getElementById('regimeBanner');
  banner.className = 'banner neutral';
  banner.textContent = 'Failed to load screener output';

  const errEl = document.getElementById('loadError');
  errEl.classList.remove('hidden');
  errEl.textContent = stack ? `${message}\n${stack}` : message;
}

async function loadPayload() {
  const url = `data/latest.json?t=${Date.now()}`;
  const res = await fetch(url, {
    cache: 'no-store',
    headers: {
      'Cache-Control': 'no-cache',
    },
  });

  if (!res.ok) {
    let bodyText = '';
    try {
      bodyText = await res.text();
    } catch (err) {
      bodyText = `unable to read response body: ${String(err)}`;
    }
    throw new Error(`HTTP ${res.status} ${res.statusText} while fetching ${url}\n${bodyText.slice(0, 800)}`);
  }

  return res.json();
}

async function boot() {
  try {
    renderTabs();

    const payload = await loadPayload();
    state.payload = payload;

    const meta = toObject(payload.meta);

    renderBanner(meta.regime, meta.engine);
    renderSummary(meta, payload.diagnostics || {});
    renderStrategy(payload);
    renderCandidateTable(payload.candidates || []);
    renderDiagnostics(payload.diagnostics || {});
    renderBenchmarkChart();
    initSelection();
  } catch (err) {
    showLoadError(String(err?.message || err), String(err?.stack || ''));
  }
}

boot();
