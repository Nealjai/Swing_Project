function fmtNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toFixed(digits);
}

function fmtInt(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString();
}

function renderBanner(regime, engine) {
  const banner = document.getElementById('regimeBanner');
  banner.className = `banner ${regime === 'bull' ? 'bull' : 'weak'}`;
  banner.textContent = `Regime: ${regime.toUpperCase()} | Active Engine: ${engine.toUpperCase()}`;
}

function renderSummary(meta) {
  document.getElementById('generatedAt').textContent = `Generated: ${meta.generated_at}`;
  document.getElementById('engineName').textContent = meta.engine;
  document.getElementById('regimeName').textContent = meta.regime;
  document.getElementById('universeSize').textContent = fmtInt(meta.universe_size);
  document.getElementById('candidateCount').textContent = fmtInt(meta.candidate_count);
}

function renderBenchmark(benchmark) {
  const el = document.getElementById('benchmarkStats');
  el.innerHTML = `
    <p>Symbol: <strong>${benchmark.symbol}</strong></p>
    <p>Close: <strong>${fmtNumber(benchmark.close)}</strong></p>
    <p>SMA200: <strong>${fmtNumber(benchmark.sma200)}</strong></p>
    <p>Above SMA200: <strong>${benchmark.above_sma200}</strong></p>
  `;
}

function renderTable(candidates) {
  const tbody = document.querySelector('#candidatesTable tbody');
  tbody.innerHTML = '';

  for (const c of candidates) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtInt(c.rank)}</td>
      <td>${c.symbol}</td>
      <td>${fmtNumber(c.score, 4)}</td>
      <td>${fmtNumber(c.close)}</td>
      <td>${fmtNumber(c.high_20d)}</td>
      <td>${fmtNumber(c.rsi14)}</td>
      <td>${fmtNumber(c.bb_lower)}</td>
      <td>${fmtNumber(c.sma200)}</td>
      <td>${fmtInt(c.avg_dollar_volume_20d)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderDiagnostics(diagnostics) {
  const el = document.getElementById('diagnostics');
  el.textContent = JSON.stringify(diagnostics, null, 2);
}

async function boot() {
  try {
    const res = await fetch('data/latest.json');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = await res.json();

    renderBanner(payload.meta.regime, payload.meta.engine);
    renderSummary(payload.meta);
    renderBenchmark(payload.benchmark);
    renderTable(payload.candidates || []);
    renderDiagnostics(payload.diagnostics || {});
  } catch (err) {
    const banner = document.getElementById('regimeBanner');
    banner.className = 'banner neutral';
    banner.textContent = `Failed to load data/latest.json: ${err}`;
  }
}

boot();
