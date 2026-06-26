/**
 * services.js – Centralised data service for CanAI Café Intelligence.
 * All data is fetched from backend API endpoints; no static mock data.
 */

/* ──────────────────────────────────────────────────────────────────────────
   Internal helpers
   ────────────────────────────────────────────────────────────────────────── */

/**
 * Build business alerts dynamically from real summary and forecast data.
 * No hardcoded values — every metric comes from the API.
 */
function _buildAlerts(summary, forecast) {
  const alerts = [];
  const totalRows = summary.total_rows || summary.unique_transactions;

  // Revenue forecast alert (only if forecast is available)
  if (forecast && !forecast._error) {
    const g = forecast.expected_growth_percent;
    alerts.push({
      type: g < 0 ? 'risk' : 'opportunity',
      title: `Revenue Forecast ${g >= 0 ? 'Growth' : 'Decline'}`,
      message: `Six-month forecast projects ${g >= 0 ? '+' : ''}${Number(g).toFixed(1)}% revenue versus the same period last year.`,
      metric: `Forecast: ${formatCADFull(forecast.forecast_total_revenue)} · Growth: ${g >= 0 ? '+' : ''}${Number(g).toFixed(1)}%`,
      action: g < 0
        ? 'Review promotional pricing and Q1 traffic strategy.'
        : 'Continue current strategy and explore expansion opportunities.',
    });
  }

  // Unknown location data quality alert
  if (summary.unknown_location_count > 0) {
    const pct = totalRows > 0
      ? (summary.unknown_location_count / totalRows * 100).toFixed(2)
      : 'N/A';
    alerts.push({
      type: 'warning',
      title: 'Unknown Location Records',
      message: `${pct}% of records have no location — limiting regional analysis accuracy.`,
      metric: `${formatNum(summary.unknown_location_count)} of ${formatNum(totalRows)} rows`,
      action: 'Audit POS systems to capture location data consistently.',
    });
  }

  // Top-item bundle opportunity alert
  if (summary.top_item) {
    alerts.push({
      type: 'opportunity',
      title: `${summary.top_item} Bundle Opportunity`,
      message: `${summary.top_item} is the best-selling item. Bundle promotions with top products could increase average order value.`,
      metric: `Top item: ${summary.top_item} · Avg order: ${formatCADFull(summary.average_transaction_value)}`,
      action: 'Trial a bundled promotion in top-performing locations.',
    });
  }

  return alerts;
}

/* ──────────────────────────────────────────────────────────────────────────
   SERVICE FUNCTIONS
   ────────────────────────────────────────────────────────────────────────── */

async function getExecutiveSummary() {
  const [summary, forecast] = await Promise.all([
    fetchAPI('/api/sales/summary/'),
    fetchAPI('/api/forecast/').catch(e => ({ _error: e.message, _status: e.status })),
  ]);
  return { summary, forecast, alerts: _buildAlerts(summary, forecast) };
}

async function getSalesInsights() {
  const [trends, items, provinces, locations, paymentMethods] = await Promise.all([
    fetchAPI('/api/sales/trends/'),
    fetchAPI('/api/sales/items/'),
    fetchAPI('/api/sales/provinces/'),
    fetchAPI('/api/sales/locations/'),
    fetchAPI('/api/sales/payments/'),
  ]);
  return { trends, items, provinces, locations, paymentMethods };
}

async function getDataQualitySummary() {
  const [summary, dqReport] = await Promise.all([
    fetchAPI('/api/sales/summary/'),
    fetchAPI('/api/data-quality/'),
  ]);
  return {
    summary,
    cleaningActions: dqReport.cleaning_actions,
    totalRows: dqReport.total_rows,
  };
}

async function getForecastData() {
  const [forecast, metrics] = await Promise.all([
    fetchAPI('/api/forecast/'),
    fetchAPI('/api/forecast/metrics/'),
  ]);
  return { forecast, metrics };
}

async function getRecommendations() {
  return fetchAPI('/api/recommendations/');
}

/**
 * Fetch the scenario baseline from real API data.
 * Revenue comes from the six-month forecast; transaction count and average
 * order value are derived from the 2023 summary.
 */
async function getScenarioBaseline() {
  const [summary, forecast] = await Promise.all([
    fetchAPI('/api/sales/summary/'),
    fetchAPI('/api/forecast/').catch(e => ({ _error: e.message })),
  ]);

  const avgOrderValue = summary.average_transaction_value;

  if (forecast && !forecast._error) {
    const revenue = forecast.forecast_total_revenue;
    const transactions = Math.max(1, Math.round(revenue / avgOrderValue));
    return { revenue, transactions, avgOrderValue };
  }

  // Fallback when forecast CSVs have not been generated yet:
  // estimate H1 using half of the 2023 annual revenue.
  const revenue = Math.round(summary.total_revenue / 2);
  const transactions = Math.max(1, Math.round(revenue / avgOrderValue));
  return { revenue, transactions, avgOrderValue };
}

/** Kept for compatibility — delegates to calculateScenario in scenario.js. */
function runScenario(baseline, params) {
  return calculateScenario(baseline, params);
}
