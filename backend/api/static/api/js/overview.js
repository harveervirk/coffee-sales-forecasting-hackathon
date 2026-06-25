/**
 * overview.js – Executive Overview page
 */
document.addEventListener('DOMContentLoaded', async () => {
  try {
    const { summary, forecast, alerts } = await getExecutiveSummary();
    renderKPIs(summary);
    renderForecastKPIs(forecast);
    renderAlerts(alerts);
    renderMonthlyChart();
    renderForecastChart(forecast);
    renderExecSummary(summary, forecast);
  } catch (e) {
    ['kpi-row', 'forecast-kpi-row', 'alerts-row', 'exec-summary'].forEach(id =>
      showError(id, `Could not load data: ${e.message}`)
    );
  }
});

/* ----------------------------------------------------------
   KPI Cards
   ---------------------------------------------------------- */
function renderKPIs(s) {
  const cards = [
    { icon:'bi-currency-dollar', bg:'#FFF7ED', col:'#C07A2F', value: formatCAD(s.total_revenue),           label:'Total Revenue',           sub:'All 2023 transactions' },
    { icon:'bi-receipt',         bg:'#EFF6FF', col:'#1D4ED8', value: formatNum(s.unique_transactions),      label:'Unique Transactions',     sub:'By Transaction ID' },
    { icon:'bi-calculator',      bg:'#F5F3FF', col:'#7C3AED', value: formatCAD(s.average_transaction_value),label:'Avg Transaction Value',   sub:'Per transaction' },
    { icon:'bi-box-seam',        bg:'#F0FDF4', col:'#15803D', value: formatNum(s.total_quantity),           label:'Units Sold',              sub:'Total quantity' },
    { icon:'bi-star-fill',       bg:'#FFFBEB', col:'#D97706', value: s.top_item,                            label:'Best-Selling Item',       sub:'By revenue' },
    { icon:'bi-geo-alt-fill',    bg:'#FFF1F2', col:'#BE123C', value: s.top_province,                       label:'Top Province',            sub:'By revenue' },
  ];
  document.getElementById('kpi-row').innerHTML = cards.map(c => `
    <div class="col-6 col-md-4 col-xl-2">
      <div class="card kpi-card h-100 p-3">
        <div class="d-flex align-items-start gap-2">
          <div class="kpi-icon" style="background:${c.bg};color:${c.col};">
            <i class="bi ${c.icon}" aria-hidden="true"></i>
          </div>
          <div class="flex-fill" style="min-width:0;">
            <div class="kpi-value" style="word-break:break-word;">${c.value}</div>
            <div class="kpi-label">${c.label}</div>
            <div class="kpi-sub">${c.sub}</div>
          </div>
        </div>
      </div>
    </div>`).join('');
}

/* ----------------------------------------------------------
   Forecast KPI cards (3 only)
   ---------------------------------------------------------- */
function renderForecastKPIs(fc) {
  if (!fc || fc._error) {
    const msg = fc?._status === 503
      ? 'Run <code>python backend/manage.py generate_sales_forecast</code> to generate forecast data.'
      : 'Forecast data unavailable.';
    document.getElementById('forecast-kpi-row').innerHTML =
      `<div class="col-12"><div class="warn-box"><i class="bi bi-clock-history me-2"></i>${msg}</div></div>`;
    return;
  }
  const g = fc.expected_growth_percent;
  const cards = [
    { icon:'bi-cpu',        bg:'#F0FDF4', col:'#15803D',
      value: fc.selected_model, label:'Selected Model' },
    { icon:'bi-cash-stack', bg:'#FFF7ED', col:'#C07A2F',
      value: formatCAD(fc.forecast_total_revenue), label:'6-Month Forecast Revenue' },
    { icon:'bi-bar-chart-steps', bg:'#EFF6FF', col:'#1D4ED8',
      value: `<span class="${growthClass(g)}"><i class="bi ${growthIcon(g)}"></i> ${formatPct(g)}</span>`,
      label:'Growth vs Prior Year' },
  ];
  document.getElementById('forecast-kpi-row').innerHTML = cards.map(c => `
    <div class="col-12 col-md-4">
      <div class="card forecast-card h-100 p-3">
        <div class="d-flex align-items-start gap-2">
          <div class="kpi-icon" style="background:${c.bg};color:${c.col};">
            <i class="bi ${c.icon}" aria-hidden="true"></i>
          </div>
          <div>
            <div class="fc-value">${c.value}</div>
            <div class="fc-label">${c.label}</div>
          </div>
        </div>
      </div>
    </div>`).join('');
}

/* ----------------------------------------------------------
   Business Alerts
   ---------------------------------------------------------- */
const ALERT_ICONS = {
  risk:        'bi-exclamation-octagon-fill',
  warning:     'bi-exclamation-triangle-fill',
  opportunity: 'bi-rocket-takeoff-fill',
  info:        'bi-info-circle-fill',
};
function renderAlerts(alerts) {
  document.getElementById('alerts-row').innerHTML = alerts.map(a => `
    <div class="col-md-4">
      <div class="alert-card alert-${a.type}">
        <div class="d-flex align-items-start gap-2">
          <div class="alert-icon flex-shrink-0">
            <i class="bi ${ALERT_ICONS[a.type] || 'bi-bell'}" aria-hidden="true"></i>
          </div>
          <div>
            <div class="alert-title">${a.title}</div>
            <div class="alert-message">${a.message}</div>
            <div class="alert-metric"><i class="bi bi-graph-up me-1" aria-hidden="true"></i>${a.metric}</div>
            <div class="alert-action mt-1"><i class="bi bi-arrow-right me-1" aria-hidden="true"></i>${a.action}</div>
          </div>
        </div>
      </div>
    </div>`).join('');
}

/* ----------------------------------------------------------
   Monthly Revenue Chart (single colour)
   ---------------------------------------------------------- */
async function renderMonthlyChart() {
  try {
    const trends = await fetchAPI('/api/sales/trends/');
    buildBarChart('monthly-chart', trends.map(r => r.month),
      [{ label:'Revenue', data: trends.map(r => r.total_revenue),
         backgroundColor: COLORS.coffee + 'CC', borderRadius: 4 }],
      { isCurrency: true, yLabel: 'CAD' });
  } catch {
    showError('monthly-chart', 'Could not load trend data.');
  }
}

/* ----------------------------------------------------------
   Forecast Chart
   ---------------------------------------------------------- */
function renderForecastChart(fc) {
  const wrap = document.getElementById('forecast-chart-wrap');
  const canvas = document.getElementById('forecast-chart');
  if (!fc || fc._error) {
    wrap.innerHTML = `<div class="warn-box"><i class="bi bi-clock-history me-2"></i>Forecast not yet generated.</div>`;
    return;
  }
  wrap.style.display = 'none';
  canvas.style.display = 'block';
  const mf = fc.monthly_forecast;
  buildLineChart('forecast-chart', mf.map(r => r.month),
    [
      { label:'Lower Bound', data: mf.map(r => r.lower_bound),
        borderColor:'rgba(210,105,30,.3)', borderDash:[5,5], fill:false, pointRadius:0, tension:.3, borderWidth:1.5 },
      { label:'Upper Bound', data: mf.map(r => r.upper_bound),
        borderColor:'rgba(210,105,30,.3)', borderDash:[5,5], backgroundColor:'rgba(210,105,30,.08)',
        fill:'-1', pointRadius:0, tension:.3, borderWidth:1.5 },
      { label:'Forecast Revenue', data: mf.map(r => r.forecast_revenue),
        borderColor: COLORS.coffee, fill:false, pointRadius:4, tension:.3, borderWidth:2.5 },
    ],
    { isCurrency:true, yLabel:'CAD',
      extra:{ plugins:{ legend:{ display:true, position:'bottom' } } } });
}

/* ----------------------------------------------------------
   Executive Summary (2 concise paragraphs)
   ---------------------------------------------------------- */
function renderExecSummary(s, fc) {
  let html = `
    <div class="insight-card">
      <h5 class="mb-3"><i class="bi bi-stars text-amber me-2" aria-hidden="true"></i>Executive Summary</h5>
      <p class="mb-2">
        The café network recorded <strong>${formatCAD(s.total_revenue)}</strong> in revenue across
        <strong>${formatNum(s.unique_transactions)}</strong> transactions at an average of
        <strong>${formatCAD(s.average_transaction_value)}</strong> per transaction.
        <strong>${s.top_item}</strong> was the top-revenue product and
        <strong>${s.top_province}</strong> was the leading province.
      </p>`;

  if (fc && !fc._error) {
    const g = fc.expected_growth_percent;
    const peak = fc.monthly_forecast.reduce((a, b) => a.forecast_revenue > b.forecast_revenue ? a : b);
    html += `
      <p class="mb-0">
        The <strong>${fc.selected_model}</strong> model forecasts
        <strong>${formatCAD(fc.forecast_total_revenue)}</strong> over the next six months —
        a <strong><span class="${growthClass(g)}">${formatPct(g)}</span></strong> change versus the prior year.
        The peak forecast month is <strong>${peak.month}</strong> at
        <strong>${formatCAD(peak.forecast_revenue)}</strong>.
        See <a href="/recommendations/">Recommendations</a> for priority actions.
      </p>`;
  } else {
    html += `<p class="mb-0 text-muted">Run the forecast command to add six-month projections to this summary.</p>`;
  }

  html += `</div>`;
  document.getElementById('exec-summary').innerHTML = html;
}
