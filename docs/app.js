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

function fmtPctPoints(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${Number(value).toFixed(digits)}%`;
}

function fmtDollar(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `$${Number(value).toFixed(digits)}`;
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
  backtestChart: null,
  backtest: {
    loaded: false,
    loading: false,
    data: null,
    error: null,
  },
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

function activateTab(buttons, panels, key) {
  if (!key) return;
  for (const b of buttons) b.classList.toggle('active', b.dataset.tab === key);
  for (const p of panels) p.classList.toggle('active', p.id === `tab${key[0].toUpperCase()}${key.slice(1)}`);
  if (key === 'history') {
    void loadBacktestSummaryIfNeeded();
  }
}

function getInitialTabKey(buttons, panels) {
  const hash = String(window.location.hash || '').replace(/^#/, '').toLowerCase();
  if (hash && buttons.some((b) => b.dataset.tab === hash)) return hash;

  const activeButton = buttons.find((b) => b.classList.contains('active'));
  if (activeButton?.dataset?.tab) return activeButton.dataset.tab;

  const activePanel = panels.find((p) => p.classList.contains('active'));
  if (activePanel?.id?.startsWith('tab') && activePanel.id.length > 3) {
    const key = `${activePanel.id[3].toLowerCase()}${activePanel.id.slice(4)}`;
    if (buttons.some((b) => b.dataset.tab === key)) return key;
  }

  return buttons[0]?.dataset?.tab || 'screener';
}

function renderTabs() {
  const buttons = Array.from(document.querySelectorAll('.tab-btn'));
  const panels = Array.from(document.querySelectorAll('.tab-panel'));

  for (const btn of buttons) {
    btn.addEventListener('click', () => {
      activateTab(buttons, panels, btn.dataset.tab);
    });
  }

  const initialTab = getInitialTabKey(buttons, panels);
  activateTab(buttons, panels, initialTab);
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

function getMetricValue(statsObj, keys) {
  const obj = toObject(statsObj);
  for (const key of keys) {
    if (obj[key] !== undefined && obj[key] !== null) return obj[key];
  }
  return null;
}

function renderBacktestStatus(message, isError = false) {
  const statusEl = document.getElementById('backtestStatus');
  const errEl = document.getElementById('backtestError');
  if (!statusEl || !errEl) return;

  statusEl.textContent = message || '';
  if (isError) {
    errEl.classList.remove('hidden');
    errEl.textContent =
      'Backtest summary unavailable. Run scripts/run_backtest.py locally to generate docs/data/backtest_summary.json, then refresh this page.';
  } else {
    errEl.classList.add('hidden');
    errEl.textContent = '';
  }
}

function getEngineStats(byEngine, engineLabel) {
  const section = toObject(byEngine);
  return toObject(section[engineLabel] ?? section[engineLabel.toLowerCase()] ?? section[engineLabel.toUpperCase()]);
}

function renderBacktestEngineCards(payload) {
  const host = document.getElementById('backtestEngineStats');
  if (!host) return;

  const byEngine = toObject(toObject(toObject(payload).stats).by_engine);
  const engines = [
    { label: 'Bull', css: 'bull' },
    { label: 'Weak', css: 'weak' },
  ];

  host.innerHTML = engines
    .map((engine) => {
      const stats = getEngineStats(byEngine, engine.label);
      return `
        <section class="backtest-engine-card ${engine.css}">
          <h3>${esc(engine.label)} Engine</h3>
          <div class="backtest-metric-grid">
            <div class="backtest-metric"><span>Total trades</span><strong>${fmtInt(getMetricValue(stats, ['total_trades', 'trades']))}</strong></div>
            <div class="backtest-metric"><span>Win rate</span><strong>${fmtPctPoints(getMetricValue(stats, ['win_rate']))}</strong></div>
            <div class="backtest-metric"><span>Profit factor</span><strong>${fmtNumber(getMetricValue(stats, ['profit_factor']), 2)}</strong></div>
            <div class="backtest-metric"><span>Expectancy</span><strong>${fmtPctPoints(getMetricValue(stats, ['expectancy_pct', 'expectancy']))}</strong></div>
            <div class="backtest-metric"><span>Avg win</span><strong>${fmtPctPoints(getMetricValue(stats, ['avg_win_pct']))}</strong></div>
            <div class="backtest-metric"><span>Avg loss</span><strong>${fmtPctPoints(getMetricValue(stats, ['avg_loss_pct']))}</strong></div>
            <div class="backtest-metric"><span>Avg hold days</span><strong>${fmtNumber(getMetricValue(stats, ['avg_hold_days']), 2)}</strong></div>
            <div class="backtest-metric"><span>Max consecutive losses</span><strong>${fmtInt(getMetricValue(stats, ['max_consecutive_losses']))}</strong></div>
          </div>
        </section>
      `;
    })
    .join('');
}

function renderBacktestPortfolioCards(payload) {
  const host = document.getElementById('backtestPortfolioStats');
  if (!host) return;

  const portfolio = toObject(payload.portfolio);
  const assumptions = toObject(portfolio.assumptions);
  const metrics = toObject(portfolio.metrics);

  host.innerHTML = `
    <section class="backtest-portfolio-card">
      <div class="backtest-metric-grid">
        <div class="backtest-metric"><span>Initial capital</span><strong>${fmtDollar(getMetricValue(assumptions, ['initial_capital']))}</strong></div>
        <div class="backtest-metric"><span>Total return</span><strong>${fmtPctPoints(getMetricValue(metrics, ['total_return_pct']))}</strong></div>
        <div class="backtest-metric"><span>CAGR</span><strong>${fmtPctPoints(getMetricValue(metrics, ['cagr_pct']))}</strong></div>
        <div class="backtest-metric"><span>Max drawdown</span><strong>${fmtPctPoints(getMetricValue(metrics, ['max_drawdown_pct']))}</strong></div>
        <div class="backtest-metric"><span>Exposure</span><strong>${fmtPctPoints(getMetricValue(metrics, ['exposure_pct']))}</strong></div>
        <div class="backtest-metric"><span>Months halted</span><strong>${fmtInt(getMetricValue(metrics, ['months_halted']))}</strong></div>
        <div class="backtest-metric"><span>Sharpe</span><strong>${fmtNumber(getMetricValue(metrics, ['sharpe']), 3)}</strong></div>
        <div class="backtest-metric"><span>Sortino</span><strong>${fmtNumber(getMetricValue(metrics, ['sortino']), 3)}</strong></div>
      </div>
    </section>
  `;
}

function buildPortfolioCurveSeries(payload) {
  const portfolio = toObject(payload.portfolio);
  const curve = toObject(portfolio.curve);
  const dates = toArray(curve.dates);
  const equity = toArray(curve.equity).map((v) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  });
  const drawdown = toArray(curve.drawdown_pct).map((v) => {
    const n = Number(v);
    return Number.isFinite(n) ? -Math.abs(n) : null;
  });
  return { dates, equity, drawdown };
}

function renderBacktestEquityChart(payload) {
  const canvas = document.getElementById('backtestEquityChart');
  const noteEl = document.getElementById('backtestChartNote');
  if (!canvas || !noteEl) return;

  destroyChart(state.backtestChart);

  const series = buildPortfolioCurveSeries(payload);
  if (!series.dates.length) {
    noteEl.textContent = 'No portfolio equity curve data found.';
    state.backtestChart = null;
    return;
  }

  const assumptions = toObject(toObject(payload.portfolio).assumptions);
  noteEl.textContent = `Portfolio curve uses assumptions: initial=${fmtDollar(assumptions.initial_capital)}, max_positions=${fmtInt(assumptions.max_positions)}, slippage=${fmtPctPoints((Number(assumptions.slippage_pct_each_side) || 0) * 100, 3)} each side, commission=${fmtDollar(assumptions.commission_per_side)} per side.`;

  state.backtestChart = new Chart(canvas, {
    type: 'line',
    data: {
      labels: series.dates,
      datasets: [
        {
          label: 'Equity ($)',
          data: series.equity,
          borderColor: '#22c55e',
          backgroundColor: 'rgba(34, 197, 94, 0.14)',
          borderWidth: 2,
          tension: 0.15,
          pointRadius: 0,
          yAxisID: 'yEquity',
        },
        {
          label: 'Drawdown %',
          data: series.drawdown,
          borderColor: '#f97316',
          backgroundColor: 'rgba(249, 115, 22, 0.12)',
          borderWidth: 1.6,
          tension: 0.1,
          pointRadius: 0,
          yAxisID: 'yDD',
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
        yEquity: {
          type: 'linear',
          position: 'left',
          ticks: {
            color: '#cbd5e1',
            callback: (value) => `$${Number(value).toLocaleString()}`,
          },
          grid: { color: 'rgba(148, 163, 184, 0.12)' },
        },
        yDD: {
          type: 'linear',
          position: 'right',
          ticks: {
            color: '#fbbf24',
            callback: (value) => `${value}%`,
          },
          grid: { drawOnChartArea: false },
        },
      },
      plugins: {
        legend: { labels: { color: '#e2e8f0' } },
      },
    },
  });
}

function renderBacktestAnnualTable(payload) {
  const tbody = document.querySelector('#backtestAnnualTable tbody');
  if (!tbody) return;

  const stats = toObject(toObject(payload).stats);
  const byYearEngine = toObject(stats.by_year_engine ?? stats.by_year_by_engine);
  const years = Object.keys(byYearEngine).sort();

  if (!years.length) {
    tbody.innerHTML = '<tr><td colspan="5">No annual breakdown available.</td></tr>';
    return;
  }

  tbody.innerHTML = years
    .map((year) => {
      const row = toObject(byYearEngine[year]);
      const bull = getEngineStats(row, 'Bull');
      const weak = getEngineStats(row, 'Weak');
      return `
        <tr>
          <td>${esc(year)}</td>
          <td>${fmtPctPoints(getMetricValue(bull, ['win_rate']))}</td>
          <td>${fmtPctPoints(getMetricValue(bull, ['expectancy_pct', 'expectancy']))}</td>
          <td>${fmtPctPoints(getMetricValue(weak, ['win_rate']))}</td>
          <td>${fmtPctPoints(getMetricValue(weak, ['expectancy_pct', 'expectancy']))}</td>
        </tr>
      `;
    })
    .join('');
}

function renderBacktestMonthlyTable(payload) {
  const tbody = document.querySelector('#backtestMonthlyTable tbody');
  if (!tbody) return;

  const monthly = toArray(toObject(toObject(payload).portfolio).monthly_returns);
  if (!monthly.length) {
    tbody.innerHTML = '<tr><td colspan="2">No monthly return table available.</td></tr>';
    return;
  }

  tbody.innerHTML = monthly
    .map((row) => {
      const item = toObject(row);
      return `
        <tr>
          <td>${esc(item.month ?? '-')}</td>
          <td>${fmtPctPoints(item.return_pct)}</td>
        </tr>
      `;
    })
    .join('');
}

function pickFirstString(obj, keys, fallback = '-') {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return fallback;
}

function renderBacktestMethodology(payload) {
  const host = document.getElementById('backtestMethodology');
  if (!host) return;

  const meta = toObject(payload.meta);
  const diagnostics = toObject(payload.diagnostics);
  const config = toObject(diagnostics.config);

  const testPeriod = `${pickFirstString(meta, ['start_date'], config.start_date || '-')} to ${pickFirstString(meta, ['end_date'], config.end_date || '-')}`;
  const universeSize = meta.symbol_count ?? diagnostics.counts?.symbols_excluding_benchmark ?? '-';
  const symbolMode = pickFirstString(meta, ['symbol_mode'], '-');
  const warmup = config.warmup_bars ?? meta.warmup_bars ?? '-';

  const entryRules = pickFirstString(meta, ['entry_rules', 'entry_rule'], 'Signals generated by strategy engines; entries use next session open when conditions pass.');
  const exitRules = pickFirstString(meta, ['exit_rules', 'exit_rule'], 'Exits follow strategy risk targets (stop-loss / take-profit) from engine outputs.');
  const regimeLogic = pickFirstString(
    meta,
    ['regime_filter_logic', 'regime_logic'],
    'Regime filter uses SPY vs SMA200: Bull engine above SMA200, Weak engine below SMA200.',
  );

  const nextOpenEntry = pickFirstString(meta, ['next_open_entry'], 'Enabled');
  const signalVsPnl = pickFirstString(
    meta,
    ['signal_price_vs_pnl_price', 'price_basis_note'],
    'Signals use adjusted-close indicators; P&L uses raw close/open execution prices from trade simulation.',
  );

  const pAssump = toObject(meta.portfolio_assumptions ?? toObject(toObject(payload).portfolio).assumptions);

  host.innerHTML = `
    <p><strong>Test period:</strong> ${esc(testPeriod)}</p>
    <p><strong>Universe size:</strong> ${esc(universeSize)}</p>
    <p><strong>Universe mode:</strong> ${esc(symbolMode)}</p>
    <p><strong>Entry rules:</strong> ${esc(entryRules)}</p>
    <p><strong>Exit rules:</strong> ${esc(exitRules)}</p>
    <p><strong>Regime filter logic:</strong> ${esc(regimeLogic)}</p>
    <p><strong>Warmup:</strong> ${esc(warmup)} bars</p>
    <p><strong>Next-open entry:</strong> ${esc(nextOpenEntry)}</p>
    <p><strong>Adjusted-close signals vs raw-close P&L:</strong> ${esc(signalVsPnl)}</p>
    <p><strong>Portfolio assumptions:</strong> initial ${fmtDollar(pAssump.initial_capital)}, max positions ${fmtInt(pAssump.max_positions)}, slippage ${fmtPctPoints((Number(pAssump.slippage_pct_each_side) || 0) * 100, 3)} each side, commission ${fmtDollar(pAssump.commission_per_side)} each side, monthly DD halt at ${fmtPctPoints(pAssump.monthly_drawdown_limit_pct)}, per-trade risk cap ${fmtPctPoints(pAssump.monthly_risk_per_trade_pct)} of month-start equity.</p>
  `;
}

function renderBacktest(payload) {
  renderBacktestEngineCards(payload);
  renderBacktestPortfolioCards(payload);
  renderBacktestEquityChart(payload);
  renderBacktestMonthlyTable(payload);
  renderBacktestAnnualTable(payload);
  renderBacktestMethodology(payload);

  const generatedAt = toObject(payload.meta).generated_at || '-';
  renderBacktestStatus(`Loaded backtest summary generated at (UTC): ${generatedAt}`);
}

async function loadBacktestSummaryIfNeeded() {
  if (state.backtest.loaded || state.backtest.loading) return;

  state.backtest.loading = true;
  renderBacktestStatus('Loading backtest summary...');

  const url = `data/backtest_summary.json?t=${Date.now()}`;
  try {
    const res = await fetch(url, {
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
      },
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status} ${res.statusText}`);
    }

    const payload = await res.json();
    state.backtest.loaded = true;
    state.backtest.data = payload;
    state.backtest.error = null;
    renderBacktest(payload);
  } catch (err) {
    state.backtest.error = String(err?.message || err);
    renderBacktestStatus(`Failed to load docs/data/backtest_summary.json (${state.backtest.error}).`, true);

    const statsHost = document.getElementById('backtestEngineStats');
    if (statsHost) statsHost.innerHTML = '<p class="muted">No backtest metrics available.</p>';

    const portfolioHost = document.getElementById('backtestPortfolioStats');
    if (portfolioHost) portfolioHost.innerHTML = '<p class="muted">No portfolio metrics available.</p>';

    const annualTbody = document.querySelector('#backtestAnnualTable tbody');
    if (annualTbody) annualTbody.innerHTML = '<tr><td colspan="5">No annual breakdown available.</td></tr>';

    const monthlyTbody = document.querySelector('#backtestMonthlyTable tbody');
    if (monthlyTbody) monthlyTbody.innerHTML = '<tr><td colspan="2">No monthly returns available.</td></tr>';

    const methodology = document.getElementById('backtestMethodology');
    if (methodology) methodology.innerHTML = '<p class="muted">Methodology unavailable because backtest summary could not be loaded.</p>';

    const noteEl = document.getElementById('backtestChartNote');
    if (noteEl) noteEl.textContent = 'No equity curve available.';

    destroyChart(state.backtestChart);
    state.backtestChart = null;
  } finally {
    state.backtest.loading = false;
  }
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

    // Keep this aligned with the screener tab behavior: always load data on boot.
    // Backtesting tab still renders only when opened, but data is guaranteed available.
    void loadBacktestSummaryIfNeeded();
  } catch (err) {
    showLoadError(String(err?.message || err), String(err?.stack || ''));
  }
}

boot();
