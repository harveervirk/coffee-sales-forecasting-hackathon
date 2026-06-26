/**
 * scenario_page.js – Scenario Lab page controller.
 * Delegates all maths to scenario.js (calculateScenario).
 * Baseline is loaded from the forecast and summary APIs — no hardcoded values.
 */

let _params   = { traffic: 0, price: 0, discount: 0, demand: 0, regional: 0 };
let _baseline = null;

document.addEventListener('DOMContentLoaded', async () => {
  try {
    _baseline = await getScenarioBaseline();
    const initial = calculateScenario(_baseline, _params);
    renderScenario(initial);
    renderBaselineChart(initial);
  } catch (e) {
    ['sc-revenue', 'sc-transactions', 'sc-avg-order', 'sc-pct'].forEach(id =>
      showError(id, `Could not load baseline: ${e.message}`)
    );
  }
});

/* ----------------------------------------------------------
   Slider update (fires on every input event)
   ---------------------------------------------------------- */
function updateSlider(key, value) {
  _params[key] = Number(value);
  const sign = value > 0 ? '+' : '';
  document.getElementById(`v-${key}`).textContent = `${sign}${value}%`;
  if (!_baseline) return;
  const result = calculateScenario(_baseline, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

/* ----------------------------------------------------------
   Apply / Reset
   ---------------------------------------------------------- */
function applyScenario() {
  if (!_baseline) return;
  const result = calculateScenario(_baseline, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

function resetScenario() {
  _params = { traffic: 0, price: 0, discount: 0, demand: 0, regional: 0 };
  ['traffic', 'price', 'discount', 'demand', 'regional'].forEach(k => {
    const slider  = document.getElementById(`s-${k}`);
    const valueEl = document.getElementById(`v-${k}`);
    if (slider)  slider.value = 0;
    if (valueEl) valueEl.textContent = '0%';
  });
  if (!_baseline) return;
  const result = calculateScenario(_baseline, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

/* ----------------------------------------------------------
   Render results
   ---------------------------------------------------------- */
function renderScenario(result) {
  document.getElementById('sc-revenue').textContent      = formatCAD(result.revenue);
  document.getElementById('sc-transactions').textContent = formatNum(result.transactions);
  document.getElementById('sc-avg-order').textContent    = formatCAD(result.avgOrderValue);

  const pct   = result.pctChange;
  const pctEl = document.getElementById('sc-pct');
  pctEl.innerHTML = pct === 0
    ? '<span class="text-muted">0.0%</span>'
    : `<span class="${growthClass(pct)}"><i class="bi ${growthIcon(pct)}"></i> ${formatPct(pct)}</span>`;

  document.querySelectorAll('.sc-scenario').forEach(card => {
    const isFullHeight = card.classList.contains('h-100');
    card.className = (pct < 0 ? 'scenario-result-card sc-negative' : 'scenario-result-card sc-scenario')
      + (isFullHeight ? ' h-100' : '');
  });

  document.getElementById('sc-label-growth').textContent = result.explanation.split('.')[0] + '.';
  document.getElementById('sc-explanation').textContent  = result.explanation;
  document.getElementById('sc-assumptions').innerHTML    =
    result.assumptions.map(a => `<li>${a}</li>`).join('');
}

/* ----------------------------------------------------------
   Grouped bar chart: Baseline vs Scenario
   ---------------------------------------------------------- */
function renderBaselineChart(result) {
  const months      = result.monthlyRevenue.map(r => r.month);
  const base        = result.monthlyRevenue.map(r => r.baseline);
  const scenario    = result.monthlyRevenue.map(r => r.scenario);
  const scenarioBg  = result.pctChange < 0 ? COLORS.red + 'BB' : COLORS.green + 'BB';

  destroyChart('scenario-chart');
  const chart = new Chart(document.getElementById('scenario-chart'), {
    type: 'bar',
    data: {
      labels: months,
      datasets: [
        { label: 'Baseline Forecast', data: base,     backgroundColor: COLORS.coffee + '88', borderRadius: 4 },
        { label: 'Scenario',          data: scenario,  backgroundColor: scenarioBg,           borderRadius: 4 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: true,
      plugins: {
        legend:  { display: true, position: 'bottom' },
        tooltip: commonTooltip(true),
      },
      scales: commonScales('Month', 'Revenue (CAD)', true),
    },
  });
  registerChart('scenario-chart', chart);
}
