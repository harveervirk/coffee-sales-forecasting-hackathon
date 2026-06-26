/**
 * recommendations.js – Recommendations page.
 * Uses getRecommendations() from services.js.
 */
let _allRecs = [];

document.addEventListener('DOMContentLoaded', async () => {
  try {
    const data = await getRecommendations();
    _allRecs = data.recommendations || [];
    if (!_allRecs.length) {
      ['rec-summary','rec-cards','ap-immediate','ap-month','ap-quarter'].forEach(id =>
        showEmpty(id, 'No recommendations available.')
      );
      return;
    }
    renderSummary(_allRecs);
    renderCards(_allRecs);
    renderActionPlan(_allRecs);
  } catch (e) {
    const msg = e.status === 503
      ? 'Recommendations require forecast data. Run <code>python backend/manage.py generate_sales_forecast</code>.'
      : `Could not load recommendations: ${e.message}`;
    ['rec-summary','rec-cards'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = `<div class="warn-box"><i class="bi bi-clock-history me-2"></i>${msg}</div>`;
    });
    ['ap-immediate','ap-month','ap-quarter'].forEach(id =>
      showEmpty(id, 'No data available.')
    );
  }
});

/* ----------------------------------------------------------
   Filter
   ---------------------------------------------------------- */
function filterRecs() {
  const priority = document.getElementById('f-priority')?.value || '';
  const filtered = priority ? _allRecs.filter(r => r.priority === priority) : _allRecs;
  renderCards(filtered);
}

/* ----------------------------------------------------------
   Executive summary
   ---------------------------------------------------------- */
function renderSummary(recs) {
  const high   = recs.filter(r => r.priority === 'high');
  const medium = recs.filter(r => r.priority === 'medium');
  const low    = recs.filter(r => r.priority === 'low');
  const bullets = [];
  if (high.length)   bullets.push(`<li><strong>${high.length} high-priority</strong> action${high.length > 1 ? 's' : ''} requiring immediate attention</li>`);
  if (medium.length) bullets.push(`<li><strong>${medium.length} medium-priority</strong> recommendation${medium.length > 1 ? 's' : ''} for the next 30 days</li>`);
  if (low.length)    bullets.push(`<li><strong>${low.length} low-priority</strong> strategic consideration${low.length > 1 ? 's' : ''} for next quarter</li>`);

  document.getElementById('rec-summary').innerHTML = `
    <div class="insight-card">
      <h5><i class="bi bi-stars text-amber"></i> Executive Summary</h5>
      <p>The analysis has identified <strong>${recs.length} recommendation${recs.length !== 1 ? 's' : ''}</strong>
         based on forecast data and 2023 sales history:</p>
      <ul>${bullets.join('')}</ul>
      <p class="mb-0 text-muted" style="font-size:.83rem;">
        <i class="bi bi-info-circle me-1"></i>
        All recommendations are generated automatically from actual data values. See
        <a href="/forecast-centre/">Forecast Centre</a> for the underlying model metrics.
      </p>
    </div>`;
}

/* ----------------------------------------------------------
   Recommendation cards
   ---------------------------------------------------------- */
const PRIORITY_META = {
  high:   { badge:'priority-high',   card:'rec-high',   icon:'bi-fire' },
  medium: { badge:'priority-medium', card:'rec-medium', icon:'bi-dash-circle' },
  low:    { badge:'priority-low',    card:'rec-low',    icon:'bi-info-circle' },
};
const ORDER = ['high','medium','low'];

function renderCards(recs) {
  if (!recs.length) { showEmpty('rec-cards', 'No recommendations match the selected filter.'); return; }
  const sorted = [...recs].sort((a, b) => ORDER.indexOf(a.priority) - ORDER.indexOf(b.priority));
  document.getElementById('rec-cards').innerHTML = sorted.map(r => {
    const m = PRIORITY_META[r.priority] || PRIORITY_META.low;
    return `
      <div class="card rec-card ${m.card} mb-3" role="listitem">
        <div class="card-body p-4">
          <div class="d-flex align-items-start justify-content-between gap-3">
            <div class="flex-fill">
              <div class="rec-title">${r.title}</div>
              <div class="rec-message">${r.message}</div>
              ${r.evidence ? `<div class="rec-evidence"><i class="bi bi-graph-up me-1"></i><strong>Evidence:</strong> ${r.evidence}</div>` : ''}
            </div>
            <span class="priority-badge ${m.badge} flex-shrink-0">
              <i class="bi ${m.icon}"></i>${r.priority.charAt(0).toUpperCase() + r.priority.slice(1)}
            </span>
          </div>
        </div>
      </div>`;
  }).join('');
}

/* ----------------------------------------------------------
   Action plan (high=immediate, medium=30 days, low=quarter)
   ---------------------------------------------------------- */
function renderActionPlan(recs) {
  const high   = recs.filter(r => r.priority === 'high');
  const medium = recs.filter(r => r.priority === 'medium');
  const low    = recs.filter(r => r.priority === 'low');

  renderAPSection('ap-immediate', high,   'No high-priority actions identified.');
  renderAPSection('ap-month',     medium, 'No medium-priority actions for the next 30 days.');
  renderAPSection('ap-quarter',   low,    'No long-term actions for next quarter.');
}

function renderAPSection(id, recs, emptyMsg) {
  const el = document.getElementById(id);
  if (!el) return;
  if (!recs.length) { el.innerHTML = `<p class="text-muted" style="font-size:.85rem;">${emptyMsg}</p>`; return; }
  el.innerHTML = recs.map(r => `
    <div class="ap-item">
      <div class="ap-dot"></div>
      <p><strong>${r.title}.</strong> ${r.message}</p>
    </div>`).join('');
}
