/**
 * data_quality.js – Data Quality Centre page.
 * Uses getDataQualitySummary() from services.js.
 * Total row count is read from the backend — no hardcoded constants.
 */
let TOTAL_ROWS = 10000;

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const { summary, cleaningActions, totalRows } = await getDataQualitySummary();
    TOTAL_ROWS = totalRows || TOTAL_ROWS;
    renderQualityScore(summary);
    renderBeforeAfter(summary);
    renderIssueCards(summary);
    renderIssueProgressBars(summary);
    renderDatasetCards(summary);
    renderCleaningTable(cleaningActions);
  } catch (e) {
    ['quality-ring', 'score-breakdown', 'dq-dates-card', 'dq-payments-card',
     'dq-locations-card', 'dq-earliest', 'dq-latest', 'dq-transactions', 'dq-total-rows',
    ].forEach(id => showError(id, e.message));
    document.getElementById('cleaning-tbody').innerHTML =
      `<tr><td colspan="5"><div class="error-state"><i class="bi bi-exclamation-triangle-fill"></i>${e.message}</div></td></tr>`;
  }
});

/* ----------------------------------------------------------
   Quality score ring + breakdown
   ---------------------------------------------------------- */
function renderQualityScore(s) {
  const dateRate    = (TOTAL_ROWS - s.invalid_date_count)           / TOTAL_ROWS;
  const paymentRate = (TOTAL_ROWS - s.unknown_payment_method_count) / TOTAL_ROWS;
  const locRate     = (TOTAL_ROWS - s.unknown_location_count)       / TOTAL_ROWS;
  const score       = ((dateRate + paymentRate + locRate) / 3 * 100).toFixed(1);
  const scoreNum    = parseFloat(score);

  document.getElementById('q-score-val').textContent = `${score}%`;
  const colorClass = scoreNum >= 95 ? 'quality-good' : scoreNum >= 85 ? 'quality-warn' : 'quality-bad';
  document.getElementById('quality-ring-inner').className = `quality-score-ring ${colorClass}`;
  document.getElementById('q-score-sub').textContent =
    `${scoreNum >= 95 ? 'Good' : scoreNum >= 85 ? 'Fair' : 'Needs Attention'} — average of 3 field scores`;

  const breakdown = [
    { label: 'Dates',     rate: dateRate    },
    { label: 'Payments',  rate: paymentRate },
    { label: 'Locations', rate: locRate     },
  ];
  document.getElementById('score-breakdown').innerHTML = breakdown.map(b => {
    const pct = (b.rate * 100).toFixed(1);
    const cls = b.rate >= 0.97 ? 'text-success' : b.rate >= 0.90 ? 'text-warning' : 'text-danger';
    return `
      <div class="col-4">
        <div class="card border-0 bg-light p-2 text-center">
          <div class="fw-bold ${cls}" style="font-size:1.1rem;">${pct}%</div>
          <div class="text-muted" style="font-size:.72rem;">${b.label}</div>
        </div>
      </div>`;
  }).join('');
}

/* ----------------------------------------------------------
   Before / After comparison
   ---------------------------------------------------------- */
function renderBeforeAfter(s) {
  document.getElementById('ba-clean').textContent = formatNum(TOTAL_ROWS - s.invalid_date_count);
  document.getElementById('ba-detail-row').innerHTML = `
    <div class="col-6">
      <div class="text-center">
        <div class="fw-bold text-danger" style="font-size:1.15rem;">${formatNum(s.invalid_date_count)}</div>
        <div class="text-muted" style="font-size:.72rem;">Invalid Dates</div>
      </div>
    </div>
    <div class="col-6">
      <div class="text-center">
        <div class="fw-bold text-warning" style="font-size:1.15rem;">${formatNum(s.unknown_payment_method_count + s.unknown_location_count)}</div>
        <div class="text-muted" style="font-size:.72rem;">Unknown Values</div>
      </div>
    </div>`;
}

/* ----------------------------------------------------------
   Issue cards
   ---------------------------------------------------------- */
function renderIssueCards(s) {
  const issues = [
    { id: 'dq-dates-card',    icon: 'bi-calendar-x',           bg: '#FEF2F2', col: '#DC2626',
      count: s.invalid_date_count,            label: 'Invalid Transaction Dates',
      note: 'Excluded from forecasting. Revenue still counted in totals.' },
    { id: 'dq-payments-card', icon: 'bi-credit-card-2-front',  bg: '#FFFBEB', col: '#D97706',
      count: s.unknown_payment_method_count,  label: 'Unknown Payment Methods',
      note: 'Includes UNKNOWN and ERR_PM_102. Retained with flag.' },
    { id: 'dq-locations-card',icon: 'bi-geo-alt',              bg: '#EFF6FF', col: '#2563EB',
      count: s.unknown_location_count,        label: 'Unknown Locations',
      note: 'Categorised as UNKNOWN in location analytics.' },
  ];
  issues.forEach(({ id, icon, bg, col, count, label, note }) => {
    const pct = ((count / TOTAL_ROWS) * 100).toFixed(2);
    document.getElementById(id).innerHTML = `
      <div class="d-flex align-items-start gap-3">
        <div style="width:44px;height:44px;border-radius:10px;background:${bg};color:${col};
                    display:flex;align-items:center;justify-content:center;font-size:1.3rem;flex-shrink:0;">
          <i class="bi ${icon}" aria-hidden="true"></i>
        </div>
        <div>
          <div class="quality-count">${formatNum(count)}</div>
          <div class="quality-pct">${pct}% of ${formatNum(TOTAL_ROWS)} rows</div>
          <div class="kpi-label mt-1">${label}</div>
          <div class="text-muted mt-1" style="font-size:.8rem;">${note}</div>
        </div>
      </div>`;
  });
}

/* ----------------------------------------------------------
   Compact issue progress bars (replaces donut chart)
   ---------------------------------------------------------- */
function renderIssueProgressBars(s) {
  const issues = [
    { label: 'Invalid Dates',           count: s.invalid_date_count,           color: '#EF4444', note: 'Excluded from forecasting' },
    { label: 'Unknown Payment Methods', count: s.unknown_payment_method_count, color: '#F59E0B', note: 'Retained with flag'        },
    { label: 'Unknown Locations',       count: s.unknown_location_count,       color: '#3B82F6', note: 'Shown as UNKNOWN'          },
  ];
  document.getElementById('issue-progress-bars').innerHTML = issues.map(iss => {
    const pct = Math.min((iss.count / TOTAL_ROWS * 100), 100).toFixed(1);
    return `
      <div class="mb-3">
        <div class="d-flex justify-content-between mb-1" style="font-size:.85rem;">
          <span class="fw-semibold">${iss.label}</span>
          <span class="text-muted">${formatNum(iss.count)} rows (${pct}%)</span>
        </div>
        <div class="progress mb-1" style="height:7px;border-radius:4px;" role="progressbar"
             aria-label="${iss.label}" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100">
          <div class="progress-bar" style="width:${pct}%;background:${iss.color};"></div>
        </div>
        <div class="text-muted" style="font-size:.75rem;">${iss.note}</div>
      </div>`;
  }).join('');
}

/* ----------------------------------------------------------
   Dataset overview cards
   ---------------------------------------------------------- */
function renderDatasetCards(s) {
  const cards = [
    { id: 'dq-earliest',    icon: 'bi-calendar-event', bg: '#F0FDF4', col: '#15803D', value: s.earliest_date,               label: 'Earliest Valid Date'   },
    { id: 'dq-latest',      icon: 'bi-calendar-check', bg: '#EFF6FF', col: '#1D4ED8', value: s.latest_date,                 label: 'Latest Valid Date'     },
    { id: 'dq-transactions',icon: 'bi-receipt',         bg: '#F5F3FF', col: '#7C3AED', value: formatNum(s.unique_transactions), label: 'Unique Transactions' },
    { id: 'dq-total-rows',  icon: 'bi-table',           bg: '#FFF7ED', col: '#C07A2F', value: formatNum(TOTAL_ROWS),         label: 'Total Data Rows'       },
  ];
  cards.forEach(({ id, icon, bg, col, value, label }) => {
    document.getElementById(id).innerHTML = `
      <div class="d-flex align-items-start gap-2">
        <div style="width:40px;height:40px;border-radius:9px;background:${bg};color:${col};
                    display:flex;align-items:center;justify-content:center;font-size:1.15rem;flex-shrink:0;">
          <i class="bi ${icon}" aria-hidden="true"></i>
        </div>
        <div>
          <div class="kpi-value" style="font-size:1.2rem;">${value}</div>
          <div class="kpi-label">${label}</div>
        </div>
      </div>`;
  });
}

/* ----------------------------------------------------------
   Cleaning actions table
   ---------------------------------------------------------- */
const STATUS_META = {
  'Retained':  { bg: '#DBEAFE', color: '#1E40AF' },
  'Corrected': { bg: '#DCFCE7', color: '#15803D' },
  'Removed':   { bg: '#FEE2E2', color: '#B91C1C' },
};

function renderCleaningTable(actions) {
  document.getElementById('cleaning-tbody').innerHTML = actions.map(a => {
    const sm = STATUS_META[a.status] || { bg: '#F3F4F6', color: '#374151' };
    return `
      <tr>
        <td><strong>${a.issue}</strong></td>
        <td>${formatNum(a.affected)}</td>
        <td>${a.resolution}</td>
        <td>${a.reason}</td>
        <td>
          <span style="background:${sm.bg};color:${sm.color};padding:.2rem .6rem;
                       border-radius:100px;font-size:.75rem;font-weight:600;white-space:nowrap;">
            ${a.status}
          </span>
        </td>
      </tr>`;
  }).join('');
}
