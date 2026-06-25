/**
 * scenario_page.js – Scenario Lab page controller.
 * Delegates all maths to scenario.js (calculateScenario).
 * Uses MOCK.scenarioBaseline from services.js as the starting point.
 */

let _params = { traffic:0, price:0, discount:0, demand:0, regional:0 };
const BASELINE = MOCK.scenarioBaseline;

document.addEventListener('DOMContentLoaded', () => {
  renderScenario(calculateScenario(BASELINE, _params));
  renderBaselineChart(calculateScenario(BASELINE, _params));
});

/* ----------------------------------------------------------
   Slider update (fires on every input event)
   ---------------------------------------------------------- */
function updateSlider(key, value) {
  _params[key] = Number(value);
  const sign = value > 0 ? '+' : '';
  document.getElementById(`v-${key}`).textContent = `${sign}${value}%`;
  // Live preview (re-renders as slider moves)
  const result = calculateScenario(BASELINE, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

/* ----------------------------------------------------------
   Apply / Reset
   ---------------------------------------------------------- */
function applyScenario() {
  const result = calculateScenario(BASELINE, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

function resetScenario() {
  _params = { traffic:0, price:0, discount:0, demand:0, regional:0 };
  ['traffic','price','discount','demand','regional'].forEach(k => {
    const slider = document.getElementById(`s-${k}`);
    if (slider) slider.value = 0;
    const valueEl = document.getElementById(`v-${k}`);
    if (valueEl) valueEl.textContent = '0%';
  });
  const result = calculateScenario(BASELINE, _params);
  renderScenario(result);
  renderBaselineChart(result);
}

/* ----------------------------------------------------------
   Render results
   ---------------------------------------------------------- */
function renderScenario(result) {
  document.getElementById('sc-revenue').textContent = formatCAD(result.revenue);
  document.getElementById('sc-transactions').textContent = formatNum(result.transactions);
  document.getElementById('sc-avg-order').textContent = formatCAD(result.avgOrderValue);

  // Pct change badge
  const pct = result.pctChange;
  const pctEl = document.getElementById('sc-pct');
  pctEl.innerHTML = pct === 0
    ? '<span class="text-muted">0.0%</span>'
    : `<span class="${growthClass(pct)}"><i class="bi ${growthIcon(pct)}"></i> ${formatPct(pct)}</span>`;

  // Update colour on ALL scenario result cards
  document.querySelectorAll('.sc-scenario').forEach(card => {
    const isFullHeight = card.classList.contains('h-100');
    card.className = (pct < 0 ? 'scenario-result-card sc-negative' : 'scenario-result-card sc-scenario')
      + (isFullHeight ? ' h-100' : '');
    // preserve any inline style already on the element (e.g. text-align:left)
  });

  // Summary label
  document.getElementById('sc-label-growth').textContent = result.explanation.split('.')[0] + '.';

  // Full explanation
  document.getElementById('sc-explanation').textContent = result.explanation;

  // Assumptions list
  document.getElementById('sc-assumptions').innerHTML =
    result.assumptions.map(a => `<li>${a}</li>`).join('');
}

/* ----------------------------------------------------------
   Grouped bar chart: Baseline vs Scenario
   ---------------------------------------------------------- */
function renderBaselineChart(result) {
  const months  = result.monthlyRevenue.map(r => r.month);
  const base    = result.monthlyRevenue.map(r => r.baseline);
  const scenario= result.monthlyRevenue.map(r => r.scenario);
  const scenarioBg = result.pctChange < 0 ? COLORS.red + 'BB' : COLORS.green + 'BB';

  destroyChart('scenario-chart');
  const chart = new Chart(document.getElementById('scenario-chart'), {
    type:'bar',
    data:{
      labels: months,
      datasets:[
        { label:'Baseline Forecast', data: base,
          backgroundColor: COLORS.coffee + '88', borderRadius:4 },
        { label:'Scenario',          data: scenario,
          backgroundColor: scenarioBg, borderRadius:4 },
      ],
    },
    options:{
      responsive:true, maintainAspectRatio:true,
      plugins:{
        legend:{ display:true, position:'bottom' },
        tooltip: commonTooltip(true),
      },
      scales: commonScales('Month','Revenue (CAD)',true),
    },
  });
  registerChart('scenario-chart', chart);
}
