/**
 * scenario.js – Scenario Lab calculation utilities for CanAI Cafe Intelligence.
 *
 * All formulas are transparent and isolated from UI code.
 * Replace runScenario() in services.js with a POST /api/scenarios/ call
 * when a backend endpoint is available.
 *
 * FORMULA:
 *   scenario_revenue = baseline_revenue
 *     × (1 + traffic/100)        ← customer traffic change
 *     × (1 + price/100)          ← price-per-unit change
 *     × (1 − discount/100)       ← promotional discount applied to revenue
 *     × (1 + demand/100)         ← product demand shift
 *     × (1 + regional/100)       ← regional market growth
 *
 *   scenario_transactions = baseline_transactions × (1 + traffic/100)
 *   scenario_avg_order = scenario_revenue / scenario_transactions
 *
 * DISCLAIMER:
 *   These are estimates based on linear scaling assumptions.
 *   Real-world outcomes depend on many factors not modelled here.
 */

const SCENARIO_DEFAULTS = {
  traffic:  0,   // %: −20 to +30  (customer visit volume change)
  price:    0,   // %: −15 to +20  (average price-per-unit change)
  discount: 0,   // %:   0 to +25  (promotional discount applied to revenue)
  demand:   0,   // %: −20 to +30  (product demand mix change)
  regional: 0,   // %: −15 to +25  (regional growth/contraction)
};

/**
 * Calculate scenario projections from a baseline and slider parameters.
 * @param {{ revenue: number, transactions: number, avgOrderValue: number }} baseline
 * @param {{ traffic: number, price: number, discount: number, demand: number, regional: number }} params
 * @returns {{ revenue, transactions, avgOrderValue, pctChange, monthlyRevenue, explanation }}
 */
function calculateScenario(baseline, params) {
  const p = { ...SCENARIO_DEFAULTS, ...params };

  const trafficMult  = 1 + p.traffic  / 100;
  const priceMult    = 1 + p.price    / 100;
  const discountMult = 1 - p.discount / 100;
  const demandMult   = 1 + p.demand   / 100;
  const regionalMult = 1 + p.regional / 100;

  const overallRevMult = trafficMult * priceMult * discountMult * demandMult * regionalMult;

  const revenue      = Math.max(0, baseline.revenue * overallRevMult);
  const transactions = Math.max(0, Math.round(baseline.transactions * trafficMult));
  const avgOrderValue = transactions > 0 ? revenue / transactions : 0;
  const pctChange     = ((revenue - baseline.revenue) / baseline.revenue) * 100;

  // Build a simple 6-month monthly breakdown (equal monthly split for scenario)
  const monthlyRevenue = _buildMonthlyBreakdown(baseline.revenue, revenue);

  return {
    revenue:       Math.round(revenue),
    transactions,
    avgOrderValue: Math.round(avgOrderValue * 100) / 100,
    pctChange:     Math.round(pctChange * 10) / 10,
    monthlyRevenue,
    explanation:   _generateExplanation(p, baseline, { revenue, transactions }),
    assumptions:   _buildAssumptions(p),
  };
}

/** Distribute baseline and scenario revenue across 6 months (proportional). */
function _buildMonthlyBreakdown(baseTotal, scenarioTotal) {
  // Monthly weights representing seasonal variation (Jan–Jun)
  const weights = [0.178, 0.163, 0.167, 0.170, 0.165, 0.157];
  return ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'].map((month, i) => ({
    month,
    baseline: Math.round(baseTotal * weights[i]),
    scenario: Math.round(scenarioTotal * weights[i]),
  }));
}

/** Plain-English explanation of what the scenario implies. */
function _generateExplanation(p, baseline, result) {
  const direction = result.revenue >= baseline.revenue ? 'increase' : 'decline';
  const delta = Math.abs(result.revenue - baseline.revenue);
  const pct   = Math.abs(((result.revenue - baseline.revenue) / baseline.revenue) * 100).toFixed(1);

  const effects = [];
  if (p.traffic  !== 0) effects.push(`${p.traffic > 0 ? '+' : ''}${p.traffic}% customer traffic`);
  if (p.price    !== 0) effects.push(`${p.price > 0 ? '+' : ''}${p.price}% price adjustment`);
  if (p.discount !== 0) effects.push(`${p.discount}% promotional discount`);
  if (p.demand   !== 0) effects.push(`${p.demand > 0 ? '+' : ''}${p.demand}% demand change`);
  if (p.regional !== 0) effects.push(`${p.regional > 0 ? '+' : ''}${p.regional}% regional growth`);

  if (!effects.length) {
    return 'No changes applied. Showing baseline forecast values.';
  }

  const effectStr = effects.join(', ');
  return `With ${effectStr}, the model projects a revenue ${direction} of approximately $${formatNum(delta)} (${pct}%) compared to the baseline forecast. Projected six-month revenue: $${formatNum(result.revenue)}. Estimated transactions: ${formatNum(result.transactions)}.`;
}

/** Summarise which assumptions are active. */
function _buildAssumptions(p) {
  const lines = [];
  lines.push('Linear revenue scaling is assumed across all variables.');
  if (p.discount > 0) lines.push(`Discount of ${p.discount}% applied uniformly to all revenue.`);
  if (p.traffic !== 0) lines.push(`Transaction count scaled ${p.traffic > 0 ? 'up' : 'down'} by ${Math.abs(p.traffic)}%.`);
  lines.push('These estimates do not account for demand elasticity or competitor behaviour.');
  return lines;
}
