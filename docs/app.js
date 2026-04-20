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

function toFiniteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function buildCandidateTagCell(candidate) {
  const c = toObject(candidate);
  const leaderScore = toFiniteNumber(c.leadership_score);
  const actionabilityScore = toFiniteNumber(c.actionability_score);

  const icons = [];

  if (leaderScore !== null && leaderScore >= 0.9) {
    icons.push('<span class="candidate-tag-icon" title="Leader (leadership_score ≥ 0.90)" aria-label="Leader">🏆</span>');
  }

  if (actionabilityScore !== null && actionabilityScore >= 0.58) {
    icons.push('<span class="candidate-tag-icon" title="Actionable (actionability_score ≥ 0.58)" aria-label="Actionable">⚡</span>');
  } else if (actionabilityScore !== null && actionabilityScore >= 0.5) {
    icons.push('<span class="candidate-tag-icon" title="Watch (0.50 ≤ actionability_score < 0.58)" aria-label="Watch">👀</span>');
  }

  if (!icons.length) {
    return '<span class="candidate-tag-none" aria-label="No tag">-</span>';
  }

  return `<span class="candidate-tag-icons">${icons.join(' ')}</span>`;
}

function computeSmaSeries(values, period) {
  const src = toArray(values).map(toFiniteNumber);
  const out = new Array(src.length).fill(null);
  if (!Number.isInteger(period) || period <= 0) return out;

  let rollingSum = 0;
  let validCount = 0;

  for (let i = 0; i < src.length; i += 1) {
    const current = src[i];
    if (current !== null) {
      rollingSum += current;
      validCount += 1;
    }

    const dropIdx = i - period;
    if (dropIdx >= 0) {
      const dropped = src[dropIdx];
      if (dropped !== null) {
        rollingSum -= dropped;
        validCount -= 1;
      }
    }

    if (i >= period - 1 && validCount === period) {
      out[i] = rollingSum / period;
    }
  }

  return out;
}

function computeEmaSeries(values, period) {
  const src = toArray(values).map(toFiniteNumber);
  const out = new Array(src.length).fill(null);
  if (!Number.isInteger(period) || period <= 0) return out;

  const alpha = 2 / (period + 1);
  let ema = null;

  for (let i = 0; i < src.length; i += 1) {
    const current = src[i];
    if (current === null) continue;

    if (ema === null) {
      ema = current;
    } else {
      ema = alpha * current + (1 - alpha) * ema;
    }

    out[i] = ema;
  }

  return out;
}

let state = {
  payload: null,
  selectedSymbol: null,
  selectedYfSymbol: null,
  priceChart: null,
  listViewChart: null,
  benchmarkChart: null,
  backtestChart: null,
  marketConditionChart: null,
  screenerChart: null,
  screenerChartSeries: {},
  screenerChartSeriesMeta: {},
  screenerChartSymbol: null,
  screenerViewMode: 'list',
  marketCondition: {
    loaded: false,
    loading: false,
    data: null,
    error: null,
    rendered: false,
  },
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
    sma100: true,
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

function renderFilterFunnel(meta, rawDiagnostics) {
  const host = document.getElementById('filterFunnel');
  if (!host) return;

  const diagnostics = toObject(rawDiagnostics);
  const counts = toObject(diagnostics.counts);

  const initialUniverse = counts.initial_universe ?? meta.universe_size ?? counts.rows_with_metrics ?? null;
  const passedInitialFilters =
    counts.initial_filter_passed ?? counts.rows_with_metrics ?? diagnostics.rows_with_metrics ?? null;
  const passedRsFilter = counts.rs_filter_passed ?? null;
  const passedPatternFilter = counts.pattern_filter_passed ?? null;
  const finalCandidates = counts.ranked_candidates_count ?? counts.raw_candidates_count ?? meta.candidate_count ?? null;

  host.innerHTML = `
    <p>Initial Universe: <strong>${fmtInt(initialUniverse)}</strong></p>
    <p>Passed Initial Filters: <strong>${fmtInt(passedInitialFilters)}</strong></p>
    <p>Passed RS Filter: <strong>${fmtInt(passedRsFilter)}</strong></p>
    <p>Passed Pattern Filter: <strong>${fmtInt(passedPatternFilter)}</strong></p>
    <p>Final Candidates: <strong>${fmtInt(finalCandidates)}</strong></p>
  `;
}

function tabKeyToPanelId(key) {
  const normalized = String(key || '')
    .split('-')
    .filter(Boolean)
    .map((part) => `${part[0]?.toUpperCase() || ''}${part.slice(1)}`)
    .join('');
  return `tab${normalized}`;
}

function panelIdToTabKey(panelId) {
  const core = String(panelId || '').replace(/^tab/, '');
  if (!core) return '';
  return core
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .toLowerCase();
}

function activateTab(buttons, panels, key) {
  if (!key) return;
  for (const b of buttons) b.classList.toggle('active', b.dataset.tab === key);

  const targetPanelId = tabKeyToPanelId(key);
  for (const p of panels) p.classList.toggle('active', p.id === targetPanelId);

  if (key === 'history') {
    void loadBacktestSummaryIfNeeded();
  }

  if (key === 'market-condition') {
    void renderMarketCondition();
  }
}

function getInitialTabKey(buttons, panels) {
  const hash = String(window.location.hash || '').replace(/^#/, '').toLowerCase();
  if (hash && buttons.some((b) => b.dataset.tab === hash)) return hash;

  const activeButton = buttons.find((b) => b.classList.contains('active'));
  if (activeButton?.dataset?.tab) return activeButton.dataset.tab;

  const activePanel = panels.find((p) => p.classList.contains('active'));
  if (activePanel?.id?.startsWith('tab') && activePanel.id.length > 3) {
    const key = panelIdToTabKey(activePanel.id);
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

function normalizeRegimeKey(rawRegime, spyClose = null, sma200 = null) {
  const regime = String(rawRegime || '')
    .trim()
    .toLowerCase();

  if (regime === 'bull' || regime === 'risk-on' || regime === 'uptrend') return 'bull';
  if (regime === 'weak' || regime === 'bear' || regime === 'risk-off' || regime === 'downtrend') return 'weak';

  const close = Number(spyClose);
  const sma = Number(sma200);
  if (Number.isFinite(close) && Number.isFinite(sma)) {
    return close > sma ? 'bull' : 'weak';
  }

  return 'weak';
}

function getHowItWorksEngineCards() {
  return [
    {
      key: 'bull',
      title: 'Bull Engine',
      tagline: 'Finding Breakout Leaders',
      purpose:
        'This engine looks for stocks in strong uptrends that are consolidating and getting ready for their next major price move.',
      checks: [
        'Strong Uptrend: Stock is already outperforming the market.',
        'Price Consolidation: Looks for classic Cup with Handle or Volatility Contraction patterns.',
        'Breakout Readiness: Scores proximity to pivot with volume confirmation.',
      ],
    },
    {
      key: 'weak',
      title: 'Weak Engine',
      tagline: 'Spotting Potential Rebounds',
      purpose:
        'This engine looks for fundamentally sound stocks that have been sold off too aggressively and may be ready for a short-term bounce.',
      checks: [
        'Oversold Condition: RSI(14) below 30.',
        'Price Extension: Trading below the lower Bollinger Band region.',
        'Seller Exhaustion: Volume spike suggests capitulation may be near completion.',
      ],
    },
  ];
}

function renderHowItWorksEngineCards(cards, activeEngineKey) {
  const host = document.getElementById('howItWorksEngineCards');
  if (!host) return;

  host.innerHTML = toArray(cards)
    .map((card) => {
      const key = String(card.key || '').toLowerCase();
      const isActive = key === String(activeEngineKey || '').toLowerCase();
      return `
        <article class="how-it-works-engine-card ${esc(key)} ${isActive ? 'active' : ''}">
          <div class="how-it-works-engine-head">
            <h3>${esc(card.title)}</h3>
            <span class="how-it-works-engine-tagline">${esc(card.tagline)}</span>
          </div>
          <p class="how-it-works-engine-purpose">${esc(card.purpose)}</p>
          <h4>What it looks for</h4>
          <ul class="how-it-works-checklist">
            ${toArray(card.checks)
              .map((item) => `<li>${esc(item)}</li>`)
              .join('')}
          </ul>
          ${isActive ? '<span class="how-it-works-active-badge">Active</span>' : ''}
        </article>
      `;
    })
    .join('');
}

function renderHowItWorks(payload, marketPayload = null) {
  const meta = toObject(payload?.meta);
  const benchmark = toObject(payload?.benchmark);
  const market = toObject(marketPayload);

  const regimeFromMarket = market.regime_label || market.regime;
  const derivedRegimeKey = normalizeRegimeKey(
    regimeFromMarket || meta.regime,
    market.spy_close ?? benchmark.close,
    market.spy_sma200 ?? benchmark.sma200,
  );

  const regimeLabel = derivedRegimeKey === 'bull' ? 'Bull' : 'Weak';
  const engineFromMarket = String(market.engine || '')
    .trim()
    .toLowerCase();
  const engineFromMeta = String(meta.engine || '')
    .trim()
    .toLowerCase();
  const resolvedEngine = engineFromMarket || engineFromMeta || derivedRegimeKey;
  const activeEngine = resolvedEngine === 'bull' || resolvedEngine === 'weak' ? resolvedEngine : derivedRegimeKey;
  const engineLabel = activeEngine === 'bull' ? 'Bull Engine' : 'Weak Engine';

  const heroRegime = document.getElementById('howItWorksHeroRegime');
  const heroEngine = document.getElementById('howItWorksHeroEngine');
  if (heroRegime) {
    heroRegime.textContent = `${regimeLabel} Regime`;
    heroRegime.className = `regime-badge ${derivedRegimeKey}`;
  }
  if (heroEngine) heroEngine.textContent = engineLabel;

  const heroSubheadline = document.getElementById('howItWorksHeroSubheadline');
  if (heroSubheadline) {
    heroSubheadline.innerHTML = `The <strong>${esc(engineLabel)}</strong> engine is active. Here’s what that means.`;
  }

  renderHowItWorksEngineCards(getHowItWorksEngineCards(), activeEngine);

  const workflowEl = document.getElementById('howItWorksWorkflowSteps');
  if (workflowEl) {
    const steps = [
      'Check SPY close versus 200-day SMA.',
      'Classify market regime as Bull or Weak.',
      'Activate the matching scanning engine.',
      'Filter and scan the stock universe.',
      'Score candidates for leadership and actionability.',
      'Rank and display top results for review.',
    ];
    workflowEl.innerHTML = steps.map((step) => `<li>${esc(step)}</li>`).join('');
  }

  const interpretationEl = document.getElementById('howItWorksInterpretationText');
  if (interpretationEl) {
    interpretationEl.innerHTML =
      'A scanner result is <strong>not</strong> a buy signal. It is a filtered, high-potential idea that passed the active engine’s checks. Use it to focus your due diligence and risk planning.';
  }
}

function renderStrategy(payload) {
  renderHowItWorks(payload, state.marketCondition.data);
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
    tr.innerHTML = '<td colspan="8">No candidates produced in this run.</td>';
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
      <td class="candidate-tag-cell">${buildCandidateTagCell(c)}</td>
      <td>${fmtNumber(c.close)}</td>
      <td>${fmtNumber(c.risk?.stop_loss)}</td>
      <td>${fmtNumber(c.risk?.take_profit)}</td>
    `;

    tr.addEventListener('click', () => {
      state.selectedSymbol = String(c.symbol || '');
      state.selectedYfSymbol = String(c.yf_symbol || '');
      highlightSelectedRow();
      renderSelectedDetails(c);
      void renderListViewChartForSymbol(c.yf_symbol || c.symbol);
      updateScreenerDetailsPanel(state.selectedSymbol || state.selectedYfSymbol);
      if (state.screenerViewMode === 'chart') {
        void renderScreenerChartForSymbol(state.selectedYfSymbol);
      }
    });

    tbody.appendChild(tr);
  }
}

function highlightSelectedRow() {
  const rows = Array.from(document.querySelectorAll('#candidatesTable tbody tr'));
  for (const row of rows) {
    row.classList.toggle('active', row.dataset.yfSymbol === state.selectedYfSymbol);
  }
  highlightCompressedSymbolRow();
}

function getScreenerViewElements() {
  return {
    listBtn: document.getElementById('view-switch-list') || document.getElementById('screenerListViewBtn'),
    chartBtn: document.getElementById('view-switch-chart') || document.getElementById('screenerChartViewBtn'),
    listView: document.getElementById('screenerListView'),
    chartView: document.getElementById('screenerChartView'),
  };
}

function setScreenerView(mode, renderChartIfNeeded = true) {
  const { listBtn, chartBtn, listView, chartView } = getScreenerViewElements();
  const safeMode = mode === 'chart' ? 'chart' : 'list';
  const isList = safeMode === 'list';

  state.screenerViewMode = safeMode;

  if (listView) listView.style.display = isList ? 'block' : 'none';
  if (chartView) chartView.style.display = isList ? 'none' : 'block';

  if (listBtn) {
    listBtn.classList.toggle('active', isList);
    listBtn.setAttribute('aria-pressed', String(isList));
  }
  if (chartBtn) {
    chartBtn.classList.toggle('active', !isList);
    chartBtn.setAttribute('aria-pressed', String(!isList));
  }

  if (!isList && renderChartIfNeeded) {
    void renderDefaultScreenerChartIfNeeded();
  }
}

function initScreenerViewSwitching() {
  const { listBtn, chartBtn } = getScreenerViewElements();

  if (listBtn && !listBtn.dataset.boundScreenerSwitch) {
    listBtn.addEventListener('click', () => setScreenerView('list'));
    listBtn.dataset.boundScreenerSwitch = '1';
  }

  if (chartBtn && !chartBtn.dataset.boundScreenerSwitch) {
    chartBtn.addEventListener('click', () => setScreenerView('chart'));
    chartBtn.dataset.boundScreenerSwitch = '1';
  }

  const listActive = !!listBtn?.classList.contains('active');
  const chartActive = !!chartBtn?.classList.contains('active');
  if (chartActive && !listActive) {
    setScreenerView('chart', false);
  } else {
    setScreenerView('list', false);
  }
}

function getCompressedSymbolTableElements() {
  const table = document.getElementById('compressed-symbol-table') || document.querySelector('.compressed-symbol-table');
  const body = table?.querySelector('tbody') || document.getElementById('compressedSymbolListBody');
  return { table, body };
}

function highlightCompressedSymbolRow() {
  const { body } = getCompressedSymbolTableElements();
  if (!body) return;
  const rows = Array.from(body.querySelectorAll('tr'));
  for (const row of rows) {
    row.classList.toggle('active', row.dataset.yfSymbol === state.selectedYfSymbol);
  }
}

function renderCompressedSymbolList(candidates) {
  const { table, body } = getCompressedSymbolTableElements();
  if (!body) return;

  const safeCandidates = toArray(candidates);
  body.innerHTML = '';

  if (!safeCandidates.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>No symbols</td>';
    body.appendChild(tr);
    return;
  }

  for (const c of safeCandidates) {
    const tr = document.createElement('tr');
    tr.dataset.yfSymbol = String(c.yf_symbol || c.symbol || '');
    tr.dataset.symbol = String(c.symbol || c.yf_symbol || '');
    tr.innerHTML = `<td>${esc(c.symbol || c.yf_symbol || '-')}</td>`;
    body.appendChild(tr);
  }

  if (table && !table.dataset.boundScreenerSymbols) {
    table.addEventListener('click', (evt) => {
      const row = evt.target?.closest?.('tbody tr');
      if (!row) return;
      const yfSymbol = String(row.dataset.yfSymbol || row.dataset.symbol || '');
      if (!yfSymbol) return;
      state.selectedYfSymbol = yfSymbol;
      state.selectedSymbol = String(row.dataset.symbol || yfSymbol);
      highlightSelectedRow();
      const selected = getCandidateByYfSymbol(yfSymbol);
      if (selected) {
        renderSelectedDetails(selected);
        void renderListViewChartForSymbol(selected.yf_symbol || selected.symbol);
      }
      updateScreenerDetailsPanel(state.selectedSymbol || state.selectedYfSymbol);
      void renderScreenerChartForSymbol(yfSymbol);
    });
    table.dataset.boundScreenerSymbols = '1';
  }

  highlightCompressedSymbolRow();
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

function setScreenerDetailField(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function updateScreenerDetailsPanel(symbol) {
  const panel = document.getElementById('screener-details-panel') || document.querySelector('.screener-details-panel');
  if (!panel) return;

  const normalized = String(symbol || '').trim();
  const candidates = toArray(window.screenerData?.candidates);
  const candidate =
    candidates.find((c) => String(c?.symbol || '') === normalized || String(c?.yf_symbol || '') === normalized) || null;

  const c = toObject(candidate);
  const risk = toObject(c.risk);
  const fundamentals = toObject(c.fundamentals);

  panel.dataset.symbol = String(c.symbol || c.yf_symbol || normalized || '');

  setScreenerDetailField('chartDetailCurrentPrice', fmtNumber(c.close));
  setScreenerDetailField('chartDetailStopLoss', fmtNumber(risk.stop_loss));
  setScreenerDetailField('chartDetailTakeProfit', fmtNumber(risk.take_profit));
  setScreenerDetailField('chartDetailAtr14', fmtNumber(risk.atr14));
  setScreenerDetailField('chartDetailRoe', fmtPct(fundamentals.roe));
  setScreenerDetailField('chartDetailPe', fmtNumber(fundamentals.pe));
  setScreenerDetailField('chartDetailRevGrowthQoq', fmtPct(fundamentals.revenue_growth_qoq));
  setScreenerDetailField('chartDetailRevGrowthYoy', fmtPct(fundamentals.revenue_growth_yoy));
  setScreenerDetailField('chartDetailEngine', String(c.engine || '-'));
  setScreenerDetailField('chartDetailScore', fmtNumber(c.score, 4));
}

function getListViewChartContainer() {
  return document.getElementById('listViewChartContainer');
}

function getListViewIndicatorControlsRoot() {
  return document.getElementById('listViewIndicatorControls');
}

function getChartViewIndicatorControlsRoot() {
  return document.getElementById('chartViewIndicatorControls');
}

function syncIndicatorControlState(root, inputName) {
  if (!root) return;

  const boxes = Array.from(root.querySelectorAll(`input[type="checkbox"][name="${inputName}"]`));
  for (const box of boxes) {
    const key = normalizeScreenerIndicatorKey(box.value);
    box.checked = !!state.indicatorVisibility[key];
  }
}

function bindIndicatorControls(root, inputName, onVisibilityChange) {
  if (!root) return;

  const boundAttr = `data-bound-${inputName}`;
  if (!root.getAttribute(boundAttr)) {
    root.addEventListener('change', (evt) => {
      const target = evt.target;
      if (!target || target.tagName !== 'INPUT') return;

      const key = normalizeScreenerIndicatorKey(target.value);
      if (!key) return;

      state.indicatorVisibility[key] = !!target.checked;
      onVisibilityChange?.(key, !!target.checked);

      syncListViewIndicatorControlState();
      syncScreenerIndicatorControlState();
    });

    root.setAttribute(boundAttr, '1');
  }

  syncIndicatorControlState(root, inputName);
}

function updateChartLegend(chart, legendId) {
  const legend = document.getElementById(legendId);
  if (!legend) return;

  const legendItems = toArray(chart?.__legendItems);
  const excludedSeriesIds = new Set(['candles', 'close']);
  const excludedLabels = new Set(['candles', 'adj close']);

  const visibleItems = legendItems.filter((item) => {
    const entry = toObject(item);
    const entryId = String(entry.id || '').toLowerCase();
    const entryLabel = String(entry.label || '').toLowerCase();
    const defaultVisible = entry.defaultVisible ?? true;

    if (excludedSeriesIds.has(entryId) || excludedLabels.has(entryLabel)) {
      return false;
    }

    return getSeriesVisible(entry.series, defaultVisible);
  });

  legend.innerHTML = visibleItems
    .map((item) => {
      const entry = toObject(item);
      const color = String(entry.color || '#94a3b8');
      return `<span class="legend-item"><span class="legend-color" style="background:${esc(color)}"></span><span class="legend-label">${esc(entry.label || '-')}</span></span>`;
    })
    .join('');
}

function updateListViewChartLegend(chart) {
  updateChartLegend(chart, 'listViewChartLegend');
}

function destroyListViewChart() {
  if (state.listViewChart) {
    state.listViewChart.remove();
    state.listViewChart = null;
  }
  updateListViewChartLegend(null);
}

function syncListViewIndicatorControlState() {
  syncIndicatorControlState(getListViewIndicatorControlsRoot(), 'listChartIndicator');
}

function bindListViewIndicatorControls() {
  bindIndicatorControls(getListViewIndicatorControlsRoot(), 'listChartIndicator', (key, visible) => {
    const series = toObject(state.listViewChart?.__seriesMap)[key];
    if (series && typeof series.applyOptions === 'function') {
      series.applyOptions({ visible });
      updateListViewChartLegend(state.listViewChart);
    }

    const chartSeries = toObject(state.screenerChart?.__seriesMap || state.screenerChartSeries)[key];
    if (chartSeries && typeof chartSeries.applyOptions === 'function') {
      chartSeries.applyOptions({ visible });
      updateScreenerChartLegend(state.screenerChart);
    }
  });
}

async function renderListViewChartForSymbol(symbolOrYfSymbol) {
  const selected = getCandidateByYfSymbol(symbolOrYfSymbol) || getCandidateBySymbol(symbolOrYfSymbol);
  if (!selected) return;

  const container = getListViewChartContainer();
  if (!container) return;

  state.selectedYfSymbol = String(selected.yf_symbol || selected.symbol || '');
  state.selectedSymbol = String(selected.symbol || selected.yf_symbol || '');

  const titleEl = document.getElementById('priceChartTitle');
  if (titleEl) {
    titleEl.textContent = `${state.selectedSymbol || '-'} Price Chart (3Y)`;
  }

  bindListViewIndicatorControls();

  await loadLightweightChartsIfNeeded();

  const raw = await fetch3YDailyData(state.selectedYfSymbol);
  const history = normalizeOhlcvHistoryRows(raw);

  destroyListViewChart();
  container.innerHTML = '';

  if (!history.length) {
    container.innerHTML = `<p class="muted">No 3Y daily candle data available for ${esc(state.selectedSymbol || '-')}.</p>`;
    return;
  }

  state.listViewChart = renderLightweightCandleChart({
    container,
    historyRows: history,
    lineSeries: [
      {
        id: 'sma20',
        key: 'sma20',
        color: '#f59e0b',
        lineWidth: 1.8,
        label: 'SMA20',
        visible: !!state.indicatorVisibility.sma20,
      },
      {
        id: 'sma50',
        key: 'sma50',
        color: '#22c55e',
        lineWidth: 1.8,
        label: 'SMA50',
        visible: !!state.indicatorVisibility.sma50,
      },
      {
        id: 'sma100',
        key: 'sma100',
        color: '#8b5cf6',
        lineWidth: 1.8,
        label: 'SMA100',
        visible: !!state.indicatorVisibility.sma100,
      },
      {
        id: 'sma200',
        key: 'sma200',
        color: '#e879f9',
        lineWidth: 1.8,
        label: 'SMA200',
        visible: !!state.indicatorVisibility.sma200,
      },
      {
        id: 'volume',
        key: 'volume',
        type: 'histogram',
        color: 'rgba(148, 163, 184, 0.35)',
        label: 'Volume',
        visible: !!state.indicatorVisibility.volume,
        pane: 1,
      },
    ],
  });

  updateListViewChartLegend(state.listViewChart);

  if (!container.dataset.listViewChartResizeBound) {
    window.addEventListener('resize', () => {
      if (!state.listViewChart) return;
      const listContainer = getListViewChartContainer();
      if (!listContainer) return;
      state.listViewChart.applyOptions({ width: Math.max(listContainer.clientWidth || 0, 640) });
    });
    container.dataset.listViewChartResizeBound = '1';
  }
}

function destroyChart(chartRef) {
  if (chartRef && typeof chartRef.destroy === 'function') {
    chartRef.destroy();
  }
}

function renderBenchmarkChart() {
  const charts = toObject(state.payload?.charts);
  const benchmark = toObject(charts.benchmark);
  const series = toObject(benchmark.series);

  const labels = toArray(series.dates);
  const ctx = document.getElementById('benchmarkChart');
  destroyChart(state.benchmarkChart);

  if (!ctx || !labels.length) {
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
    sma20: true,
    sma50: true,
    sma100: true,
    sma200: true,
    ema9: false,
    ema21: false,
    bb_lower: false,
    volume: false,
  };
  syncListViewIndicatorControlState();
  bindListViewIndicatorControls();
  syncScreenerIndicatorControlState();
  bindScreenerIndicatorControls();

  const first = candidates[0];
  state.selectedSymbol = String(first.symbol || '');
  state.selectedYfSymbol = String(first.yf_symbol || '');
  highlightSelectedRow();
  renderSelectedDetails(first);
  void renderListViewChartForSymbol(first.yf_symbol || first.symbol);
  renderCompressedSymbolList(candidates);
  updateScreenerDetailsPanel(state.selectedSymbol || state.selectedYfSymbol);
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

function getMarketConditionChartContainer() {
  return document.getElementById('spy-chart-container') || document.getElementById('marketConditionSpyChart');
}

function getLightweightChartsApi() {
  if (typeof window === 'undefined') return null;
  return window.LightweightCharts || null;
}

let lightweightChartsLoadPromise = null;

function loadLightweightChartsIfNeeded() {
  if (getLightweightChartsApi()) return Promise.resolve(getLightweightChartsApi());
  if (lightweightChartsLoadPromise) return lightweightChartsLoadPromise;

  lightweightChartsLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-lib="lightweight-charts"]');
    if (existing) {
      existing.addEventListener('load', () => resolve(getLightweightChartsApi()), { once: true });
      existing.addEventListener('error', () => reject(new Error('Failed to load lightweight-charts library.')), {
        once: true,
      });
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js';
    script.async = true;
    script.dataset.lib = 'lightweight-charts';
    script.onload = () => resolve(getLightweightChartsApi());
    script.onerror = () => reject(new Error('Failed to load lightweight-charts library.'));
    document.head.appendChild(script);
  });

  return lightweightChartsLoadPromise;
}

function destroyMarketConditionChart() {
  if (state.marketConditionChart) {
    state.marketConditionChart.remove();
    state.marketConditionChart = null;
  }
}

function normalizeOhlcvHistoryRows(rawHistory) {
  if (Array.isArray(rawHistory)) return rawHistory;

  const history = toObject(rawHistory);
  const dates = toArray(history.dates?.length ? history.dates : history.Date);
  const open = toArray(history.open?.length ? history.open : history.Open);
  const high = toArray(history.high?.length ? history.high : history.High);
  const low = toArray(history.low?.length ? history.low : history.Low);
  const close = toArray(history.close?.length ? history.close : history.Close);
  const volume = toArray(history.volume?.length ? history.volume : history.Volume);
  const rawSma20 = toArray(history.sma20?.length ? history.sma20 : history.SMA20);
  const rawSma50 = toArray(history.sma50?.length ? history.sma50 : history.SMA50);
  const rawSma100 = toArray(history.sma100?.length ? history.sma100 : history.SMA100);
  const rawSma200 = toArray(history.sma200?.length ? history.sma200 : history.SMA200);
  const rawEma9 = toArray(history.ema9?.length ? history.ema9 : history.EMA9);
  const rawEma21 = toArray(history.ema21?.length ? history.ema21 : history.EMA21);
  const bbLower = toArray(history.bb_lower?.length ? history.bb_lower : history.BB_LOWER);

  const sma20 = rawSma20.length ? rawSma20 : computeSmaSeries(close, 20);
  const sma50 = rawSma50.length ? rawSma50 : computeSmaSeries(close, 50);
  const sma100 = rawSma100.length ? rawSma100 : computeSmaSeries(close, 100);
  const sma200 = rawSma200.length ? rawSma200 : computeSmaSeries(close, 200);
  const ema9 = rawEma9.length ? rawEma9 : computeEmaSeries(close, 9);
  const ema21 = rawEma21.length ? rawEma21 : computeEmaSeries(close, 21);

  const rows = [];
  for (let i = 0; i < dates.length; i += 1) {
    const date = String(dates[i] || '').slice(0, 10);
    if (!date) continue;
    rows.push({
      date,
      open: open[i],
      high: high[i],
      low: low[i],
      close: close[i],
      volume: volume[i],
      sma20: sma20[i],
      sma50: sma50[i],
      sma100: sma100[i],
      sma200: sma200[i],
      ema9: ema9[i],
      ema21: ema21[i],
      bb_lower: bbLower[i],
    });
  }

  return rows;
}

function toSeriesDataPairs(historyRows, key) {
  return toArray(historyRows)
    .map((row) => {
      const item = toObject(row);
      const time = String(item.date || item.time || '').slice(0, 10);
      const value = Number(item[key]);
      if (!time || !Number.isFinite(value)) return null;
      return { time, value };
    })
    .filter(Boolean);
}

function toCandles(historyRows) {
  return toArray(historyRows)
    .map((row) => {
      const item = toObject(row);
      const time = String(item.date || item.time || '').slice(0, 10);
      const open = Number(item.open);
      const high = Number(item.high);
      const low = Number(item.low);
      const close = Number(item.close);
      if (!time || !Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
        return null;
      }
      return { time, open, high, low, close };
    })
    .filter(Boolean);
}

function toMarkerSeries(rawMarkers, shape, color, position, defaultText = '') {
  return toArray(rawMarkers)
    .map((row) => {
      const item = toObject(row);
      const time = String(item.date || item.time || '').slice(0, 10);
      if (!time) return null;
      return {
        time,
        position,
        color,
        shape,
        text: String(item.text || item.label || defaultText || ''),
      };
    })
    .filter(Boolean);
}

function renderLightweightCandleChart({
  container,
  historyRows,
  lineSeries = [],
  markers = [],
  width = Math.max(container?.clientWidth || 0, 640),
  height = 420,
  candleVisible = true,
}) {
  const LW = getLightweightChartsApi();
  if (!LW) throw new Error('lightweight-charts API not available.');

  const chart = LW.createChart(container, {
    width,
    height,
    layout: {
      background: { color: '#0f172a' },
      textColor: '#cbd5e1',
    },
    grid: {
      vertLines: { color: 'rgba(148, 163, 184, 0.15)' },
      horzLines: { color: 'rgba(148, 163, 184, 0.15)' },
    },
    crosshair: { mode: LW.CrosshairMode.Normal },
    rightPriceScale: { borderColor: 'rgba(148, 163, 184, 0.3)' },
    timeScale: { borderColor: 'rgba(148, 163, 184, 0.3)' },
  });

  const seriesMap = {};
  const legendItems = [];

  const candleSeries = chart.addCandlestickSeries({
    upColor: '#22c55e',
    downColor: '#ef4444',
    borderVisible: false,
    wickUpColor: '#22c55e',
    wickDownColor: '#ef4444',
    visible: candleVisible,
  });

  candleSeries.setData(toCandles(historyRows));
  seriesMap.candles = candleSeries;
  legendItems.push({
    id: 'candles',
    label: 'Candles',
    color: '#64748b',
    series: candleSeries,
    defaultVisible: !!candleVisible,
  });

  for (const def of toArray(lineSeries)) {
    const item = toObject(def);
    if (!item.key) continue;

    const isHistogram = String(item.type || '').toLowerCase() === 'histogram';

    let s;
    if (isHistogram) {
      const histogramOptions = {
        color: item.color || 'rgba(148, 163, 184, 0.35)',
        priceLineVisible: item.priceLineVisible ?? false,
        lastValueVisible: item.lastValueVisible ?? false,
        visible: item.visible ?? true,
        priceScaleId: item.priceScaleId || '',
        priceFormat: item.priceFormat || { type: 'volume' },
      };

      if (Number.isInteger(item.pane) && item.pane >= 0) {
        try {
          s = chart.addHistogramSeries(histogramOptions, item.pane);
        } catch (_err) {
          s = chart.addHistogramSeries(histogramOptions);
        }
      } else {
        s = chart.addHistogramSeries(histogramOptions);
      }
    } else {
      s = chart.addLineSeries({
        color: item.color || '#60a5fa',
        lineWidth: item.lineWidth ?? 2,
        priceLineVisible: item.priceLineVisible ?? false,
        lastValueVisible: item.lastValueVisible ?? false,
        visible: item.visible ?? true,
        lineStyle: item.lineStyle,
      });
    }

    s.setData(toSeriesDataPairs(historyRows, item.key));
    const itemId = item.id || item.key;
    seriesMap[itemId] = s;
    legendItems.push({
      id: itemId,
      label: item.label || String(item.key || itemId || '-'),
      color: item.legendColor || item.color || '#94a3b8',
      series: s,
      defaultVisible: item.visible ?? true,
    });
  }

  if (toArray(markers).length) {
    candleSeries.setMarkers(
      toArray(markers).sort((a, b) => String(a.time).localeCompare(String(b.time))),
    );
  }

  chart.__seriesMap = seriesMap;
  chart.__legendItems = legendItems;
  chart.timeScale().fitContent();
  return chart;
}

function ensureMarketConditionLegend(container) {
  const parent = container?.parentElement;
  if (!parent) return;

  let legend = parent.querySelector('.market-chart-legend');
  if (!legend) {
    legend = document.createElement('div');
    legend.className = 'market-chart-legend';
    parent.insertBefore(legend, container);
  }

  legend.innerHTML = `
    <span class="market-chart-legend-item"><i style="background:#64748b"></i>Candles</span>
    <span class="market-chart-legend-item"><i style="background:#f59e0b"></i>50-day MA</span>
    <span class="market-chart-legend-item"><i style="background:#a855f7"></i>200-day MA</span>
    <span class="market-chart-legend-item"><i style="background:#22c55e"></i>FTD (F)</span>
    <span class="market-chart-legend-item"><i style="background:#ef4444"></i>Distribution Day (D)</span>
  `;
}

function updateMarketConditionIndicatorStyles(data) {
  const regimeEl = document.getElementById('marketConditionRegime');
  const vixEl = document.getElementById('marketConditionVixPrice');

  if (regimeEl) {
    const regime = String(data.regime_label || data.regime || '').trim().toLowerCase();
    regimeEl.className = 'indicator-value regime';
    if (regime === 'bull' || regime === 'risk-on' || regime === 'uptrend') {
      regimeEl.classList.add('regime-bull');
    } else if (regime === 'bear' || regime === 'weak' || regime === 'risk-off' || regime === 'downtrend') {
      regimeEl.classList.add('regime-bear');
    } else {
      regimeEl.classList.add('regime-choppy');
    }
  }

  if (vixEl) {
    const vixValue = Number(data.vix_close);
    vixEl.className = 'indicator-value';
    if (Number.isFinite(vixValue) && vixValue > 22) {
      vixEl.classList.add('warning');
    }
  }
}

function renderMarketConditionChart(container, history, data, chartMarkers) {
  if (!container) {
    throw new Error('Market Condition chart container not found (expected #spy-chart-container or #marketConditionSpyChart).');
  }

  container.innerHTML = '';
  destroyMarketConditionChart();

  const ddMarkerRaw = toArray(data.distribution_day_markers).length
    ? data.distribution_day_markers
    : chartMarkers.distribution_days;
  const ftdMarkerRaw = toArray(data.ftd_markers).length ? data.ftd_markers : chartMarkers.follow_through_days;

  const ddMarkers = toMarkerSeries(ddMarkerRaw, 'arrowDown', '#ef4444', 'aboveBar', 'D');
  const ftdMarkers = toMarkerSeries(ftdMarkerRaw, 'arrowUp', '#22c55e', 'belowBar', 'F');

  const chart = renderLightweightCandleChart({
    container,
    historyRows: history,
    lineSeries: [
      { key: 'sma50', color: '#f59e0b', lineWidth: 2 },
      { key: 'sma200', color: '#a855f7', lineWidth: 2 },
    ],
    markers: [...ddMarkers, ...ftdMarkers],
  });

  ensureMarketConditionLegend(container);
  state.marketConditionChart = chart;

  if (!container.dataset.marketChartResizeBound) {
    window.addEventListener('resize', () => {
      if (!state.marketConditionChart) return;
      const currentContainer = getMarketConditionChartContainer();
      if (!currentContainer) return;
      state.marketConditionChart.applyOptions({ width: Math.max(currentContainer.clientWidth || 0, 640) });
    });
    container.dataset.marketChartResizeBound = '1';
  }
}

function getScreenerChartContainer() {
  return document.getElementById('screenerChartContainer');
}

function getSeriesVisible(series, fallbackVisible = true) {
  if (!series || typeof series.options !== 'function') return fallbackVisible;
  const options = toObject(series.options());
  if (typeof options.visible === 'boolean') return options.visible;
  return fallbackVisible;
}

function updateScreenerChartLegend(chart) {
  updateChartLegend(chart, 'screener-chart-legend');
}

function destroyScreenerChart() {
  if (state.screenerChart) {
    state.screenerChart.remove();
    state.screenerChart = null;
  }
  state.screenerChartSeries = {};
  state.screenerChartSeriesMeta = {};
  updateScreenerChartLegend(null);
}

function normalizeScreenerIndicatorKey(rawKey) {
  const key = String(rawKey || '').trim();
  if (key === 'bbLower') return 'bb_lower';
  return key;
}

function getScreenerIndicatorControlsRoot() {
  return getChartViewIndicatorControlsRoot();
}

function syncScreenerIndicatorControlState() {
  syncIndicatorControlState(getScreenerIndicatorControlsRoot(), 'chartIndicator');
}

function bindScreenerIndicatorControls() {
  bindIndicatorControls(getScreenerIndicatorControlsRoot(), 'chartIndicator', (key, visible) => {
    const series = toObject(state.screenerChart?.__seriesMap || state.screenerChartSeries)[key];
    if (series && typeof series.applyOptions === 'function') {
      series.applyOptions({ visible });
      updateScreenerChartLegend(state.screenerChart);
    }

    const listSeries = toObject(state.listViewChart?.__seriesMap)[key];
    if (listSeries && typeof listSeries.applyOptions === 'function') {
      listSeries.applyOptions({ visible });
      updateListViewChartLegend(state.listViewChart);
    }
  });
}

function getCandidateBySymbol(symbol) {
  return toArray(state.payload?.candidates).find((c) => String(c.symbol) === String(symbol)) || null;
}

async function fetch3YDailyData(symbol) {
  const rawSymbol = String(symbol || '').trim();
  if (!rawSymbol) return [];

  const safeSymbol = rawSymbol.replaceAll('/', '_');
  const url = `data/daily/${encodeURIComponent(safeSymbol)}.json?t=${Date.now()}`;

  try {
    const res = await fetch(url, {
      cache: 'no-store',
      headers: {
        'Cache-Control': 'no-cache',
      },
    });

    if (!res.ok) {
      if (res.status === 404) {
        console.warn(`No 3Y daily data file found for ${rawSymbol} at ${url}.`);
        return [];
      }
      throw new Error(`HTTP ${res.status} ${res.statusText}`);
    }

    return await res.json();
  } catch (err) {
    console.error(`Failed to fetch 3Y daily data for ${rawSymbol}:`, err);
    return [];
  }
}

async function renderScreenerChartForSymbol(symbolOrYfSymbol) {
  const selected = getCandidateByYfSymbol(symbolOrYfSymbol) || getCandidateBySymbol(symbolOrYfSymbol);
  if (!selected) return;

  const container = getScreenerChartContainer();
  if (!container) return;

  state.screenerChartSymbol = String(selected.yf_symbol || selected.symbol || symbolOrYfSymbol || '');
  state.selectedYfSymbol = String(selected.yf_symbol || selected.symbol || '');
  state.selectedSymbol = String(selected.symbol || selected.yf_symbol || '');
  highlightSelectedRow();
  updateScreenerDetailsPanel(state.selectedSymbol || state.selectedYfSymbol);
  bindScreenerIndicatorControls();

  const titleEl = document.querySelector('.screener-chart-pane .chart-header h2');
  if (titleEl) {
    titleEl.textContent = `${state.selectedSymbol || '-'} Price Chart (3Y)`;
  }

  if (typeof fetch3YDailyData !== 'function') {
    container.innerHTML = '<p class="muted">3Y daily data fetcher not wired yet.</p>';
    destroyScreenerChart();
    return;
  }

  await loadLightweightChartsIfNeeded();

  const raw = await fetch3YDailyData(state.screenerChartSymbol);
  const history = normalizeOhlcvHistoryRows(raw);

  destroyScreenerChart();
  container.innerHTML = '';

  if (!history.length) {
    container.innerHTML = `<p class="muted">No 3Y daily candle data available for ${esc(state.selectedSymbol || '-')}.</p>`;
    return;
  }

  state.screenerChart = renderLightweightCandleChart({
    container,
    historyRows: history,
    lineSeries: [
      {
        id: 'sma20',
        key: 'sma20',
        color: '#f59e0b',
        lineWidth: 1.8,
        label: 'SMA20',
        visible: !!state.indicatorVisibility.sma20,
      },
      {
        id: 'sma50',
        key: 'sma50',
        color: '#22c55e',
        lineWidth: 1.8,
        label: 'SMA50',
        visible: !!state.indicatorVisibility.sma50,
      },
      {
        id: 'sma100',
        key: 'sma100',
        color: '#8b5cf6',
        lineWidth: 1.8,
        label: 'SMA100',
        visible: !!state.indicatorVisibility.sma100,
      },
      {
        id: 'sma200',
        key: 'sma200',
        color: '#e879f9',
        lineWidth: 1.8,
        label: 'SMA200',
        visible: !!state.indicatorVisibility.sma200,
      },
      {
        id: 'volume',
        key: 'volume',
        type: 'histogram',
        color: 'rgba(148, 163, 184, 0.35)',
        label: 'Volume',
        visible: !!state.indicatorVisibility.volume,
        pane: 1,
      },
    ],
  });
  state.screenerChartSeries = toObject(state.screenerChart?.__seriesMap);
  state.screenerChartSeriesMeta = toObject(state.screenerChart?.__legendItems);
  syncScreenerIndicatorControlState();

  updateScreenerChartLegend(state.screenerChart);

  if (!container.dataset.screenerChartResizeBound) {
    window.addEventListener('resize', () => {
      if (!state.screenerChart) return;
      const chartContainer = getScreenerChartContainer();
      if (!chartContainer) return;
      state.screenerChart.applyOptions({ width: Math.max(chartContainer.clientWidth || 0, 640) });
    });
    container.dataset.screenerChartResizeBound = '1';
  }
}

async function renderDefaultScreenerChartIfNeeded() {
  if (state.screenerChart) return;
  const candidates = toArray(state.payload?.candidates);
  if (!candidates.length) return;

  const first = candidates[0];
  const defaultSymbol = String(first.yf_symbol || first.symbol || '');
  if (!defaultSymbol) return;
  await renderScreenerChartForSymbol(defaultSymbol);
}

async function renderMarketCondition() {
  if (state.marketCondition.rendered || state.marketCondition.loading) return;

  state.marketCondition.loading = true;

  try {
    let payload = state.marketCondition.data;

    if (!payload) {
      const urls = [
        `docs/data/market_condition.json?t=${Date.now()}`,
        `data/market_condition.json?t=${Date.now()}`,
      ];

      let lastErr = null;
      for (const url of urls) {
        try {
          const res = await fetch(url, {
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' },
          });
          if (!res.ok) {
            lastErr = new Error(`HTTP ${res.status} ${res.statusText}`);
            continue;
          }
          payload = await res.json();
          break;
        } catch (err) {
          lastErr = err;
        }
      }

      if (!payload) {
        throw lastErr || new Error('Unable to load market condition data.');
      }

      state.marketCondition.data = payload;
      state.marketCondition.loaded = true;
      state.marketCondition.error = null;
    }

    const data = toObject(payload);
    const history = normalizeOhlcvHistoryRows(data.spy_history);
    const chartMarkers = toObject(data.chart_markers);

    const ftdDates = toArray(data.follow_through_day_dates).length
      ? toArray(data.follow_through_day_dates)
      : toArray(data.ftd_dates);

    const ftdCount = ftdDates.length || data.ftd_count;

    document.getElementById('marketConditionRegime').textContent = String(data.regime_label || data.regime || '-');
    document.getElementById('marketConditionSpyPrice').textContent = fmtNumber(data.spy_close);
    document.getElementById('marketConditionVixPrice').textContent = fmtNumber(data.vix_close);
    document.getElementById('marketConditionDistributionDays').textContent = fmtInt(
      data.distribution_day_count_25d ?? data.distribution_day_count,
    );
    document.getElementById('marketConditionFtdCount').textContent = fmtInt(ftdCount);
    updateMarketConditionIndicatorStyles(data);
    renderHowItWorks(state.payload, data);

    const container = getMarketConditionChartContainer();
    if (!container) {
      throw new Error('Market Condition chart container not found (expected #spy-chart-container or #marketConditionSpyChart).');
    }

    if (!history.length) {
      container.innerHTML = '<p class="muted">No SPY history available for market condition chart.</p>';
      state.marketCondition.rendered = true;
      return;
    }

    await loadLightweightChartsIfNeeded();
    renderMarketConditionChart(container, history, data, chartMarkers);
    state.marketCondition.rendered = true;
  } catch (err) {
    state.marketCondition.error = String(err?.message || err);
    const container = getMarketConditionChartContainer();
    if (container) {
      container.innerHTML = `<p class="error-text">Failed to load Market Condition data/chart: ${esc(state.marketCondition.error)}</p>`;
    }
  } finally {
    state.marketCondition.loading = false;
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
    initScreenerViewSwitching();

    const payload = await loadPayload();
    state.payload = payload;
    window.screenerData = payload;

    const meta = toObject(payload.meta);

    renderBanner(meta.regime, meta.engine);
    renderSummary(meta, payload.diagnostics || {});
    renderFilterFunnel(meta, payload.diagnostics || {});
    renderStrategy(payload);
    renderCandidateTable(payload.candidates || []);
    renderDiagnostics(payload.diagnostics || {});
    renderBenchmarkChart();
    initSelection();

    // Keep this aligned with the screener tab behavior: always load data on boot.
    // Backtesting tab still renders only when opened, but data is guaranteed available.
    void loadBacktestSummaryIfNeeded();
    void renderMarketCondition();
  } catch (err) {
    showLoadError(String(err?.message || err), String(err?.stack || ''));
  }
}

boot();
