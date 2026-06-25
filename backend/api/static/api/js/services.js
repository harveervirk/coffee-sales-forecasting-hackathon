/**
 * services.js – Centralised data service for CanAI Café Intelligence.
 *
 * Mock data is clearly labelled and isolated.
 * Replace async service functions with real API calls as endpoints become available.
 */

/* ──────────────────────────────────────────────────────────────────────────
   MOCK DATA  (grounded in real dataset; replace sections with API calls)
   ────────────────────────────────────────────────────────────────────────── */
const MOCK = {
  // Payment-method distribution – no backend endpoint available.
  // Total 10,000 rows; unknown_payment_method_count = 555 (UNKNOWN + ERR_PM_102).
  paymentMethods: [
    { method: 'Credit Card (VISA)',       count: 3190, pct: 31.9 },
    { method: 'Credit Card (Mastercard)', count: 2870, pct: 28.7 },
    { method: 'Cash',                     count: 1945, pct: 19.5 },
    { method: 'Debit Card',               count: 1440, pct: 14.4 },
    { method: 'Unknown / Invalid',        count:  555, pct:  5.5 },
  ],

  // Data-cleaning actions – derived from summary API + data exploration.
  cleaningActions: [
    { issue: 'Duplicate Transaction IDs',                   affected: 44,  resolution: 'Excluded from unique-transaction count',          reason: 'Duplicate TXN IDs may be re-submitted orders or data-entry errors.', status: 'Retained' },
    { issue: 'Invalid Transaction Dates',                   affected: 240, resolution: 'Excluded from forecasting; revenue counted in totals', reason: 'Unparseable dates cannot be placed on a time axis.',                  status: 'Corrected' },
    { issue: 'Unknown Payment Methods (UNKNOWN, ERR_PM_102)', affected: 555, resolution: 'Retained with "Unknown" label',                reason: 'Revenue is valid; only the payment channel is unidentifiable.',        status: 'Retained' },
    { issue: 'Unknown Location Values',                     affected: 878, resolution: 'Categorised as "UNKNOWN" in location breakdowns', reason: 'Location data is incomplete but revenue is real.',                      status: 'Retained' },
    { issue: 'Province Name Inconsistencies',               affected: 312, resolution: 'Whitespace trimmed; Title Case applied',          reason: 'Inconsistent casing caused provinces to appear as multiple entries.',    status: 'Corrected' },
    { issue: 'Item Name Inconsistencies',                   affected: 198, resolution: 'Whitespace trimmed; Title Case applied',          reason: 'Normalised names enable accurate product-level aggregation.',          status: 'Corrected' },
  ],

  // Scenario baseline – 6-month projection from the forecast model.
  scenarioBaseline: {
    revenue:       40915,
    transactions:  4978,
    avgOrderValue: 54.7,
  },

  // Business alerts – derived from actual data analysis.
  alerts: [
    {
      type: 'risk',
      title: 'Revenue Forecast Decline',
      message: 'Six-month forecast projects −4.7% revenue versus the same period last year.',
      metric: 'Forecast: $40,915 · Growth: −4.7%',
      action: 'Review promotional pricing and Q1 traffic strategy.',
    },
    {
      type: 'warning',
      title: 'Unknown Location Records',
      message: '8.78% of records have no location — limiting regional analysis accuracy.',
      metric: '878 of 10,000 rows',
      action: 'Audit POS systems to capture location data consistently.',
    },
    {
      type: 'opportunity',
      title: 'Sandwich–Coffee Bundle',
      message: 'Top two products together account for roughly 47% of total revenue.',
      metric: 'Sandwich $20,696 + Coffee $19,320',
      action: 'Trial a bundled promotion in top-performing locations.',
    },
  ],
};

/* ──────────────────────────────────────────────────────────────────────────
   SERVICE FUNCTIONS
   ────────────────────────────────────────────────────────────────────────── */

async function getExecutiveSummary() {
  const [summary, forecast] = await Promise.all([
    fetchAPI('/api/sales/summary/'),
    fetchAPI('/api/forecast/').catch(e => ({ _error: e.message, _status: e.status })),
  ]);
  return { summary, forecast, alerts: MOCK.alerts };
}

async function getSalesInsights() {
  const [trends, items, provinces, locations] = await Promise.all([
    fetchAPI('/api/sales/trends/'),
    fetchAPI('/api/sales/items/'),
    fetchAPI('/api/sales/provinces/'),
    fetchAPI('/api/sales/locations/'),
  ]);
  return { trends, items, provinces, locations, paymentMethods: MOCK.paymentMethods };
}

async function getDataQualitySummary() {
  const summary = await fetchAPI('/api/sales/summary/');
  return { summary, cleaningActions: MOCK.cleaningActions };
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

function runScenario(params) {
  return calculateScenario(MOCK.scenarioBaseline, params);
}
