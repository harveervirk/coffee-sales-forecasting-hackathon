/**
 * forecast.js – Forecast Centre page
 * Uses getForecastData() from services.js.
 */
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const { forecast: fc, metrics } = await getForecastData();
    renderSummaryCards(fc);
    renderForecastChart(fc);
    renderForecastTable(fc);
    renderModelComparison(metrics);
    renderMetricsTable(metrics.models);
    renderMetricsChart(metrics.models);
  } catch (e) {
    const is503 = e.status === 503;
    const msg   = is503
      ? 'Forecast not yet generated. Run <code>python backend/manage.py generate_sales_forecast</code>.'
      : `Error loading forecast: ${e.message}`;
    ['fc-summary-row','fc-chart-wrap','fc-tbody','model-cards-row','metrics-tbody'].forEach(id =>
      (document.getElementById(id) || {}).innerHTML =
        `<div class="col-12"><div class="warn-box"><i class="bi bi-clock-history me-2"></i>${msg}</div></div>`
    );
  }
});

/* ----------------------------------------------------------
   Summary cards
   ---------------------------------------------------------- */
function renderSummaryCards(fc) {
  const g = fc.expected_growth_percent;
  const cards = [
    { icon:'bi-cpu',            bg:'#F0FDF4', col:'#15803D', value: fc.selected_model,                label:'Selected Model' },
    { icon:'bi-cash-stack',     bg:'#FFF7ED', col:'#C07A2F', value: formatCAD(fc.forecast_total_revenue), label:'6-Month Forecast Revenue' },
    { icon:'bi-bar-chart-steps',bg:'#EFF6FF', col:'#1D4ED8',
      value:`<span class="${growthClass(g)}"><i class="bi ${growthIcon(g)}"></i> ${formatPct(g)}</span>`,
      label:'Expected Growth vs Prior Year' },
    { icon:'bi-calendar-range', bg:'#F5F3FF', col:'#7C3AED',
      value:`${fc.forecast_start_date}<br><small class="text-muted">to</small><br>${fc.forecast_end_date}`,
      label:'Forecast Period' },
  ];
  document.getElementById('fc-summary-row').innerHTML = cards.map(c => `
    <div class="col-6 col-xl-3">
      <div class="card forecast-card h-100 p-3">
        <div class="d-flex align-items-start gap-2">
          <div class="kpi-icon" style="background:${c.bg};color:${c.col};">
            <i class="bi ${c.icon}" aria-hidden="true"></i>
          </div>
          <div><div class="fc-value" style="font-size:1.05rem;">${c.value}</div><div class="fc-label">${c.label}</div></div>
        </div>
      </div>
    </div>`).join('');
}

/* ----------------------------------------------------------
   Forecast chart
   ---------------------------------------------------------- */
function renderForecastChart(fc) {
  const wrap = document.getElementById('fc-chart-wrap');
  wrap.style.display = 'none';
  const canvas = document.getElementById('fc-chart');
  canvas.style.display = 'block';
  const mf = fc.monthly_forecast;
  buildLineChart('fc-chart', mf.map(r => r.month),
    [
      { label:'Lower Bound', data: mf.map(r => r.lower_bound),
        borderColor:'rgba(210,105,30,.4)', borderDash:[6,4], fill:false,
        pointRadius:0, tension:.3, borderWidth:1.5 },
      { label:'Upper Bound', data: mf.map(r => r.upper_bound),
        borderColor:'rgba(210,105,30,.4)', borderDash:[6,4],
        backgroundColor:'rgba(210,105,30,.12)', fill:'-1',
        pointRadius:0, tension:.3, borderWidth:1.5 },
      { label:'Forecast Revenue', data: mf.map(r => r.forecast_revenue),
        borderColor: COLORS.coffee, fill:false,
        pointRadius:5, pointHoverRadius:9, tension:.3, borderWidth:3 },
    ],
    { isCurrency:true, yLabel:'Revenue (CAD)',
      extra:{ plugins:{ legend:{ display:true, position:'bottom' } } } });
}

/* ----------------------------------------------------------
   Forecast table
   ---------------------------------------------------------- */
function renderForecastTable(fc) {
  document.getElementById('fc-tbody').innerHTML = fc.monthly_forecast.map(r => {
    const width = r.upper_bound - r.lower_bound;
    return `
      <tr>
        <td><strong>${r.month}</strong></td>
        <td>${formatCAD(r.forecast_revenue)}</td>
        <td>${formatCAD(r.lower_bound)}</td>
        <td>${formatCAD(r.upper_bound)}</td>
        <td>${formatCAD(width)}</td>
      </tr>`;
  }).join('');
}

/* ----------------------------------------------------------
   Model comparison cards
   ---------------------------------------------------------- */
const MODEL_META = {
  'Holt-Winters': {
    type: 'Statistical', icon:'bi-graph-up',
    desc: 'Captures level, trend, and weekly seasonality. Additive components via statsmodels.',
  },
  'Seasonal Naive': {
    type: 'Baseline', icon:'bi-calendar-week',
    desc: 'Predicts each day as equal to 7 days earlier. Interpretable weekly-pattern baseline.',
  },
};
function renderModelComparison(metrics) {
  const apiModels = metrics.models || [];

  const cards = apiModels.map(m => {
    const meta = MODEL_META[m.model] || { type:'Model', icon:'bi-cpu', desc:'' };
    return `
      <div class="col-md-6">
        <div class="card model-card ${m.selected ? 'model-selected' : ''} h-100 p-4">
          <div class="d-flex align-items-center justify-content-between mb-2">
            <div class="mc-name"><i class="bi ${meta.icon} me-2 text-coffee" aria-hidden="true"></i>${m.model}</div>
            ${m.selected ? '<span class="selected-badge"><i class="bi bi-check-circle-fill"></i> Selected</span>' : ''}
          </div>
          <div class="mc-type">${meta.type} Model</div>
          <p class="text-muted" style="font-size:.85rem;">${meta.desc}</p>
          <div class="row g-2 mt-auto">
            <div class="col-4 text-center"><div class="mc-metric"><strong>${formatCAD(m.mae)}</strong><br>MAE</div></div>
            <div class="col-4 text-center"><div class="mc-metric"><strong>${formatCAD(m.rmse)}</strong><br>RMSE</div></div>
            <div class="col-4 text-center"><div class="mc-metric"><strong>${Number(m.mape).toFixed(1)}%</strong><br>MAPE</div></div>
          </div>
        </div>
      </div>`;
  });

  document.getElementById('model-cards-row').innerHTML = cards.join('');
}

/* ----------------------------------------------------------
   Metrics table
   ---------------------------------------------------------- */
function renderMetricsTable(models) {
  document.getElementById('metrics-tbody').innerHTML = models.map(m => `
    <tr ${m.selected ? 'class="table-success"' : ''}>
      <td>${m.model} ${m.selected ? '<span class="selected-badge ms-1"><i class="bi bi-check-circle-fill"></i> Selected</span>' : ''}</td>
      <td>${formatCAD(m.mae)}</td>
      <td>${formatCAD(m.rmse)}</td>
      <td>${Number(m.mape).toFixed(2)}%</td>
      <td>${m.selected ? '<i class="bi bi-check-circle-fill text-success"></i>' : '<i class="bi bi-circle text-muted"></i>'}</td>
    </tr>`).join('');
}

/* ----------------------------------------------------------
   Metrics bar chart
   ---------------------------------------------------------- */
function renderMetricsChart(models) {
  destroyChart('metrics-chart');
  const chart = new Chart(document.getElementById('metrics-chart'), {
    type:'bar',
    data:{
      labels: models.map(m => m.model),
      datasets:[
        { label:'MAE',  data: models.map(m => m.mae),  backgroundColor: COLORS.coffee + 'CC', borderRadius:4 },
        { label:'RMSE', data: models.map(m => m.rmse), backgroundColor: COLORS.amber  + 'CC', borderRadius:4 },
      ],
    },
    options:{
      responsive:true, maintainAspectRatio:true,
      plugins:{ legend:{ display:true, position:'bottom' }, tooltip: commonTooltip(true) },
      scales: commonScales('','Error (CAD)',true),
    },
  });
  registerChart('metrics-chart', chart);
}
