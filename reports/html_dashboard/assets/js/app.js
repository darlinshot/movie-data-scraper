/* Interactive HTML dashboard prototype.
 * Reads only data/analytics/movie_analytics.csv. No analytical rules are rebuilt:
 * all eligibility, quality and review states come from exported CSV columns.
 */

(() => {
  'use strict';

  const CSV_PATH = '../../data/analytics/movie_analytics.csv';

  const EXPECTED_COLUMNS = [
    'movie_id', 'canonical_title', 'original_title_raw', 'release_year',
    'genre_raw', 'genre_token_path', 'genre_grouped', 'director_raw',
    'director_norm_key', 'source_url_dtp', 'raw_source_row_dtp',
    'bov_match_status', 'match_score', 'match_reason', 'bov_url',
    'bov_title_raw', 'mapping_validation_status', 'mapping_validation_reason',
    'mapping_human_reviewed', 'mapping_reviewed_at', 'mapping_reviewer',
    'review_status', 'review_priority', 'dtp_revenue_raw', 'dtp_revenue_vnd',
    'dtp_revenue_quality', 'bov_revenue_raw', 'bov_revenue_vnd',
    'bov_revenue_quality', 'bov_quarantined_revenue_raw',
    'bov_quarantined_revenue_vnd', 'bov_candidate_revenue_raw',
    'bov_candidate_revenue_vnd', 'revenue_gap_pct', 'magnitude_gap_warning',
    'revenue_conflict_flag', 'revenue_comparability_class',
    'comparability_reason', 'revenue_scope_verified', 'bov_evidence_available',
    'include_revenue_comparison', 'include_revenue_eda', 'revenue_eda_basis',
    'ticket_candidate_count', 'ticket_found_count', 'ticket_needs_review_count',
    'ticket_verified_admissions', 'ticket_data_status', 'ticket_context_status',
    'ticket_evidence_urls', 'has_missing_core_data', 'has_revenue_gap_warning',
    'has_pending_review', 'data_quality_status'
  ];

  const EXPECTED = {
    rows: 92,
    match: { matched: 81, needs_review: 1, not_found: 10 },
    dtpQuality: { rounded: 90, lower_bound: 2 },
    revenueComparisons: 79,
    gapWarnings: 21,
    pendingReview: 6,
    ticketCandidates: 16,
    verifiedAdmissions: 0,
    verifiedRevenueScopes: 0,
    scatterRows: 77
  };

  const MATCH_ORDER = ['matched', 'needs_review', 'not_found'];
  const REVIEW_ORDER = ['auto_accepted', 'pending', 'not_applicable'];
  const LOWER_BOUND_IDS = new Set(['M0001', 'M0024']);
  const RESTRICTED_SCATTER_IDS = new Set(['M0001', 'M0024', 'M0016', 'M0043']);
  const HIGH_PRIORITY_SCATTER_IDS = new Set(['M0020', 'M0029', 'M0030', 'M0077']);
  const MISSING = '__missing__';

  const COLORS = {
    blue: '#2563eb',
    blueSoft: '#bfdbfe',
    green: '#16a34a',
    amber: '#d97706',
    amberSoft: '#fcd34d',
    red: '#dc2626',
    violet: '#7c3aed',
    slate: '#94a3b8',
    navy: '#1e293b'
  };

  const STATUS_COLORS = {
    matched: COLORS.green,
    needs_review: COLORS.amber,
    not_found: COLORS.red
  };

  const LABELS = {
    matched: 'Matched',
    needs_review: 'Needs review',
    not_found: 'Not found',
    auto_accepted: 'Auto accepted',
    pending: 'Pending',
    not_applicable: 'Not applicable',
    high: 'High',
    normal: 'Normal',
    rounded: 'Rounded',
    lower_bound: 'Lower bound',
    matcher_accepted: 'Matcher accepted',
    known_false_positive_quarantined: 'Known false positive — quarantined',
    candidate_held: 'Candidate held',
    no_mapping: 'No mapping',
    sequel_number_error: 'Sequel-number false positive',
    candidate_held_review: 'Candidate held — unverified',
    scope_unknown: 'Scope unknown',
    unverified_candidates: 'Unverified candidates',
    no_candidates: 'No candidates',
    cinema_candidate_unverified: 'Cinema candidate unverified',
    event_attendance_quarantined: 'Event attendance quarantined'
  };

  const BINS = [
    { label: '< 10b', min: 0, max: 10_000_000_000 },
    { label: '10–<50b', min: 10_000_000_000, max: 50_000_000_000 },
    { label: '50–<100b', min: 50_000_000_000, max: 100_000_000_000 },
    { label: '100–<200b', min: 100_000_000_000, max: 200_000_000_000 },
    { label: '200–<400b', min: 200_000_000_000, max: 400_000_000_000 },
    { label: '≥400b', min: 400_000_000_000, max: null }
  ];

  const PAGE_META = {
    overview: {
      title: 'Movie Overview',
      subtitle: 'High-level view of the approved movie records and diagnostic matcher status.'
    },
    year: {
      title: 'Release Year Analysis',
      subtitle: 'Chronological year-only distributions. No full dates or revenue trends are inferred.'
    },
    genre: {
      title: 'Genre & Director Profile',
      subtitle: 'Non-additive genre tokens and original director names from the approved CSV.'
    },
    quality: {
      title: 'Data Quality & Matching',
      subtitle: 'Matcher status, mapping eligibility and workflow state kept deliberately separate.'
    },
    revenue: {
      title: 'Exploratory Revenue Analysis',
      subtitle: 'Source-separated, unverified revenue observations. No official totals or rankings.'
    }
  };

  const state = {
    loaded: false,
    rows: [],
    page: 'overview',
    filters: { search: '', year: '', match: '', genre: '', director: '' },
    sort: {
      overview: { key: 'canonical_title', dir: 'asc' },
      year: { key: 'year', dir: 'asc' },
      pending: { key: 'movie_id', dir: 'asc' },
      priority: { key: 'movie_id', dir: 'asc' },
      restricted: { key: 'movie_id', dir: 'asc' },
      lower: { key: 'movie_id', dir: 'asc' }
    }
  };

  const numberFormat = new Intl.NumberFormat('en-US');
  let toastTimer = null;

  const byId = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function escapeAttr(value) {
    return escapeHtml(value).replace(/\n/g, '&#10;');
  }

  function fmt(value) {
    return numberFormat.format(value);
  }

  function label(value, fallback = 'Not provided') {
    if (value === '' || value == null) return fallback;
    return LABELS[value] || value;
  }

  function humanize(value) {
    if (value === '' || value == null) return 'Not provided';
    return String(value)
      .replace(/_/g, ' ')
      .replace(/\b\w/g, (char) => char.toUpperCase());
  }

  function countBy(rows, field) {
    const result = Object.create(null);
    rows.forEach((row) => {
      const key = row[field] === '' ? MISSING : row[field];
      result[key] = (result[key] || 0) + 1;
    });
    return result;
  }

  function isTrueFlag(value) {
    return String(value) === '1';
  }

  function asNumber(value) {
    if (value === '' || value == null) return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function genreTokens(row) {
    return String(row.genre_token_path || '')
      .split('|')
      .map((token) => token.trim())
      .filter(Boolean);
  }

  function directorKey(row) {
    return String(row.director_raw || '').trim() ? String(row.director_raw).trim() : MISSING;
  }

  function directorDisplay(row) {
    const key = directorKey(row);
    return key === MISSING ? 'Missing director' : key;
  }

  function yearKey(row) {
    return String(row.release_year || '').trim() ? String(row.release_year).trim() : MISSING;
  }

  function yearDisplay(row) {
    const key = yearKey(row);
    return key === MISSING ? 'Missing year' : key;
  }

  function displayValue(value, fallback = 'Not provided') {
    if (value === '' || value == null) {
      return `<span class="status-pill missing">${escapeHtml(fallback)}</span>`;
    }
    return escapeHtml(value);
  }

  function pill(text, tone = '') {
    return `<span class="status-pill ${escapeHtml(tone)}">${escapeHtml(text)}</span>`;
  }

  function matchPill(status) {
    return pill(label(status), status || 'missing');
  }

  function scoreCell(row) {
    const score = asNumber(row.match_score);
    if (score == null) return '<span class="status-pill missing">Not provided</span>';
    return `${score.toFixed(1)} <span class="kpi-note" style="display:inline">fuzzy only</span>`;
  }

  function gapCell(row) {
    const gap = asNumber(row.revenue_gap_pct);
    if (gap == null) return '<span class="status-pill missing">Not calculated</span>';
    return `${gap.toFixed(1)}%`;
  }

  function reasonLabel(value) {
    if (!value) return '<span class="status-pill missing">Not provided</span>';
    const mapped = LABELS[value] || humanize(value);
    return `${escapeHtml(mapped)} <span class="kpi-note" style="display:inline">(${escapeHtml(value)})</span>`;
  }

  function restrictedEvidence(row) {
    const quarantined = row.bov_quarantined_revenue_raw;
    const candidate = row.bov_candidate_revenue_raw;
    if (quarantined) return `${escapeHtml(quarantined)} <span class="status-pill quarantined">Audit only</span>`;
    if (candidate) return `${escapeHtml(candidate)} <span class="status-pill candidate_held">Audit only</span>`;
    return '<span class="status-pill missing">Not provided</span>';
  }

  function parseCsv(text) {
    const source = String(text).replace(/^\uFEFF/, '');
    const rows = [];
    let row = [];
    let field = '';
    let quoted = false;

    for (let index = 0; index < source.length; index += 1) {
      const char = source[index];

      if (quoted) {
        if (char === '"') {
          if (source[index + 1] === '"') {
            field += '"';
            index += 1;
          } else {
            quoted = false;
          }
        } else {
          field += char;
        }
        continue;
      }

      if (char === '"') {
        quoted = true;
      } else if (char === ',') {
        row.push(field);
        field = '';
      } else if (char === '\n' || char === '\r') {
        if (char === '\r' && source[index + 1] === '\n') index += 1;
        row.push(field);
        rows.push(row);
        row = [];
        field = '';
      } else {
        field += char;
      }
    }

    if (quoted) throw new Error('CSV contains an unterminated quoted field.');
    if (field !== '' || row.length) {
      row.push(field);
      rows.push(row);
    }
    return rows.filter((item) => !(item.length === 1 && item[0] === ''));
  }

  function validateDataset(headers, rows) {
    if (headers.length !== EXPECTED_COLUMNS.length) {
      throw new Error(`Expected ${EXPECTED_COLUMNS.length} columns, found ${headers.length}.`);
    }
    if (headers.some((header, index) => header !== EXPECTED_COLUMNS[index])) {
      throw new Error('CSV column names or order do not match the approved analytics schema.');
    }
    if (rows.length !== EXPECTED.rows) {
      throw new Error(`Expected ${EXPECTED.rows} movie records, found ${rows.length}.`);
    }

    const ids = rows.map((row) => row.movie_id);
    if (new Set(ids).size !== ids.length) throw new Error('movie_id is not unique.');

    const matchCounts = countBy(rows, 'bov_match_status');
    Object.entries(EXPECTED.match).forEach(([key, expected]) => {
      if ((matchCounts[key] || 0) !== expected) {
        throw new Error(`Match status ${key}: expected ${expected}, found ${matchCounts[key] || 0}.`);
      }
    });

    const qualityCounts = countBy(rows, 'dtp_revenue_quality');
    Object.entries(EXPECTED.dtpQuality).forEach(([key, expected]) => {
      if ((qualityCounts[key] || 0) !== expected) {
        throw new Error(`DTP revenue quality ${key}: expected ${expected}, found ${qualityCounts[key] || 0}.`);
      }
    });

    const checks = [
      ['accepted BOV comparisons', rows.filter((row) => isTrueFlag(row.include_revenue_comparison)).length, EXPECTED.revenueComparisons],
      ['revenue gap warnings', rows.filter((row) => isTrueFlag(row.has_revenue_gap_warning)).length, EXPECTED.gapWarnings],
      ['pending workflow records', rows.filter((row) => isTrueFlag(row.has_pending_review)).length, EXPECTED.pendingReview],
      ['unverified ticket candidates', rows.filter((row) => row.ticket_data_status === 'unverified_candidates').length, EXPECTED.ticketCandidates]
    ];
    checks.forEach(([name, actual, expected]) => {
      if (actual !== expected) throw new Error(`${name}: expected ${expected}, found ${actual}.`);
    });

    const verifiedAdmissions = rows.filter((row) => row.ticket_verified_admissions !== '').length;
    if (verifiedAdmissions !== EXPECTED.verifiedAdmissions) {
      throw new Error(`Verified admissions: expected ${EXPECTED.verifiedAdmissions}, found ${verifiedAdmissions}.`);
    }
    const verifiedScopes = rows.filter((row) => isTrueFlag(row.revenue_scope_verified)).length;
    if (verifiedScopes !== EXPECTED.verifiedRevenueScopes) {
      throw new Error(`Verified revenue scopes: expected ${EXPECTED.verifiedRevenueScopes}, found ${verifiedScopes}.`);
    }
    if (rows.some((row) => isTrueFlag(row.mapping_human_reviewed))) {
      throw new Error('Unexpected human-reviewed mapping in the approved dataset.');
    }

    const byIdValue = (id) => rows.find((row) => row.movie_id === id);
    const m0016 = byIdValue('M0016');
    const m0043 = byIdValue('M0043');
    if (!m0016 || m0016.mapping_validation_status !== 'known_false_positive_quarantined') {
      throw new Error('M0016 quarantine state is missing or inconsistent.');
    }
    if (!m0043 || m0043.mapping_validation_status !== 'candidate_held') {
      throw new Error('M0043 candidate-held state is missing or inconsistent.');
    }
    LOWER_BOUND_IDS.forEach((id) => {
      const row = byIdValue(id);
      if (!row || row.dtp_revenue_quality !== 'lower_bound') {
        throw new Error(`${id} lower-bound state is missing or inconsistent.`);
      }
    });

    const scatterBase = rows.filter((row) => (
      isTrueFlag(row.include_revenue_comparison)
      && row.dtp_revenue_quality === 'rounded'
      && !RESTRICTED_SCATTER_IDS.has(row.movie_id)
      && asNumber(row.dtp_revenue_vnd) != null
      && asNumber(row.bov_revenue_vnd) != null
    ));
    if (scatterBase.length !== EXPECTED.scatterRows) {
      throw new Error(`Diagnostic scatter base: expected ${EXPECTED.scatterRows}, found ${scatterBase.length}.`);
    }
    HIGH_PRIORITY_SCATTER_IDS.forEach((id) => {
      if (!scatterBase.some((row) => row.movie_id === id)) {
        throw new Error(`Expected high-priority scatter point ${id} is missing.`);
      }
    });
  }

  async function loadDataset() {
    byId('loading-state').hidden = false;
    byId('error-state').hidden = true;
    byId('pages').hidden = true;

    try {
      const response = await fetch(CSV_PATH, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status} while loading ${CSV_PATH}`);
      const text = await response.text();
      const parsed = parseCsv(text);
      if (parsed.length < 2) throw new Error('CSV is empty or has no data rows.');

      const headers = parsed[0].map((header) => header.trim());
      const rows = parsed.slice(1).map((values) => {
        const row = {};
        headers.forEach((header, index) => {
          row[header] = values[index] == null ? '' : values[index];
        });
        return row;
      });

      validateDataset(headers, rows);
      state.rows = rows;
      state.loaded = true;

      byId('loading-state').hidden = true;
      byId('pages').hidden = false;
      byId('dataset-meta').textContent = `${rows.length} movies · ${headers.length} fields · validated`;
      byId('sidebar-dataset').textContent = `${rows.length} movies · ${headers.length} fields · validated`;
      initControls();
      setPage(pageFromHash(), false);
      renderAll();
    } catch (error) {
      byId('loading-state').hidden = true;
      byId('pages').hidden = true;
      byId('error-state').hidden = false;
      byId('error-message').textContent = error instanceof Error ? error.message : String(error);
      console.error('Dashboard dataset load failed:', error);
    }
  }

  function initControls() {
    populateFilter('filter-year', uniqueYears(), 'All years');
    populateFilter('filter-match', MATCH_ORDER, 'All statuses', label);
    populateFilter('filter-genre', allGenres(), 'All genres');
    populateFilter('filter-director', allDirectors(), 'All directors', (value) => (
      value === MISSING ? 'Missing director' : value
    ));

    Object.entries(state.filters).forEach(([key, value]) => {
      const control = byId(`filter-${key === 'match' ? 'match' : key}`);
      if (control) control.value = value;
    });

    byId('filter-search').addEventListener('input', (event) => {
      setFilter('search', event.target.value, false);
    });
    ['year', 'match', 'genre', 'director'].forEach((key) => {
      byId(`filter-${key}`).addEventListener('change', (event) => {
        setFilter(key, event.target.value, true);
      });
    });
  }

  function populateFilter(id, values, placeholder, labeller = (value) => value) {
    const select = byId(id);
    select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + values.map((value) => (
      `<option value="${escapeAttr(value)}">${escapeHtml(labeller(value))}</option>`
    )).join('');
  }

  function uniqueYears() {
    return [...new Set(state.rows.map(yearKey).filter((value) => value !== MISSING))]
      .sort((a, b) => Number(a) - Number(b));
  }

  function allGenres() {
    return [...new Set(state.rows.flatMap(genreTokens))].sort((a, b) => a.localeCompare(b, 'vi'));
  }

  function allDirectors() {
    const names = [...new Set(state.rows.map(directorKey))];
    return names.sort((a, b) => {
      if (a === MISSING) return 1;
      if (b === MISSING) return -1;
      return a.localeCompare(b, 'vi');
    });
  }

  function setFilter(key, value, announce = false) {
    state.filters[key] = value == null ? '' : String(value);
    const controlId = `filter-${key}`;
    const control = byId(controlId);
    if (control && control.value !== state.filters[key]) control.value = state.filters[key];
    renderAll();
    if (announce && state.filters[key]) {
      showToast('Filter applied');
    }
  }

  function resetFilters() {
    state.filters = { search: '', year: '', match: '', genre: '', director: '' };
    Object.keys(state.filters).forEach((key) => {
      const control = byId(`filter-${key}`);
      if (control) control.value = '';
    });
    renderAll();
    showToast('All filters cleared');
  }

  function showToast(message) {
    const toast = byId('toast');
    toast.textContent = message;
    toast.hidden = false;
    if (toastTimer) window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => { toast.hidden = true; }, 1600);
  }

  function setPage(page, updateHash = true) {
    if (!PAGE_META[page]) return;
    state.page = page;
    document.querySelectorAll('.nav-item').forEach((item) => {
      item.classList.toggle('active', item.dataset.page === page);
    });
    document.querySelectorAll('.page').forEach((item) => {
      item.classList.toggle('active', item.dataset.page === page);
    });
    byId('page-title').textContent = PAGE_META[page].title;
    byId('page-subtitle').textContent = PAGE_META[page].subtitle;
    if (updateHash && window.location.hash !== `#${page}`) {
      window.history.replaceState(null, '', `#${page}`);
    }
  }

  function pageFromHash() {
    const candidate = window.location.hash.replace(/^#/, '');
    return PAGE_META[candidate] ? candidate : 'overview';
  }

  function getFilteredRows() {
    const filters = state.filters;
    const query = filters.search.trim().toLocaleLowerCase('vi');

    return state.rows.filter((row) => {
      if (query) {
        const haystack = [row.canonical_title, row.original_title_raw, row.movie_id]
          .join(' ')
          .toLocaleLowerCase('vi');
        if (!haystack.includes(query)) return false;
      }
      if (filters.year && yearKey(row) !== filters.year) return false;
      if (filters.match && row.bov_match_status !== filters.match) return false;
      if (filters.genre && !genreTokens(row).includes(filters.genre)) return false;
      if (filters.director && directorKey(row) !== filters.director) return false;
      return true;
    });
  }

  function activeFilterChips() {
    const chips = [];
    const filters = state.filters;
    if (filters.search) chips.push(['search', `Search: “${filters.search}”`]);
    if (filters.year) chips.push(['year', `Year: ${filters.year === MISSING ? 'Missing year' : filters.year}`]);
    if (filters.match) chips.push(['match', `Status: ${label(filters.match)}`]);
    if (filters.genre) chips.push(['genre', `Genre: ${filters.genre}`]);
    if (filters.director) chips.push(['director', `Director: ${filters.director === MISSING ? 'Missing director' : filters.director}`]);
    return chips;
  }

  function updateActiveFilters() {
    const chips = activeFilterChips();
    byId('active-filters').innerHTML = chips.map(([key, text]) => (
      `<span class="filter-chip">${escapeHtml(text)}<button type="button" aria-label="Clear ${escapeAttr(key)} filter" data-clear-filter="${escapeAttr(key)}">×</button></span>`
    )).join('');
  }

  function renderAll() {
    if (!state.loaded) return;
    const rows = getFilteredRows();
    updateActiveFilters();
    renderOverview(rows);
    renderYear(rows);
    renderGenre(rows);
    renderQuality(rows);
    renderRevenue(rows);
  }

  function kpiHtml(labelText, value, note, tone = '') {
    return `<article class="kpi ${escapeHtml(tone)}">
      <div class="kpi-label">${escapeHtml(labelText)}</div>
      <div class="kpi-value">${escapeHtml(value)}</div>
      <div class="kpi-note">${escapeHtml(note)}</div>
    </article>`;
  }

  function renderKpis(containerId, cards) {
    byId(containerId).innerHTML = cards
      .map(([labelText, value, note, tone]) => kpiHtml(labelText, value, note, tone))
      .join('');
  }

  function chartEmpty(message) {
    return `<div class="chart-empty"><div><strong>No data to display</strong>${escapeHtml(message)}</div></div>`;
  }

  function interactionAttrs(item) {
    if (!item || !item.filterKey) return '';
    return ` data-filter-key="${escapeAttr(item.filterKey)}" data-filter-value="${escapeAttr(item.filterValue)}"`;
  }

  function tooltipAttr(text) {
    return ` data-tooltip="${escapeAttr(text)}"`;
  }

  function legendHtml(items, circle = false) {
    if (!items || !items.length) return '';
    return `<div class="legend-row">${items.map((item) => `
      <span class="legend-item"><span class="legend-swatch ${circle ? 'circle' : ''}" style="background:${escapeAttr(item.color)}"></span>${escapeHtml(item.label)}</span>
    `).join('')}</div>`;
  }

  function polar(cx, cy, radius, degrees) {
    const radians = degrees * Math.PI / 180;
    return [cx + radius * Math.cos(radians), cy + radius * Math.sin(radians)];
  }

  function donutSlice(cx, cy, outer, inner, start, end, color, attrs, tooltip) {
    const sweep = end - start;
    if (sweep >= 359.99) {
      return `<circle cx="${cx}" cy="${cy}" r="${(outer + inner) / 2}" fill="none" stroke="${color}" stroke-width="${outer - inner}"${attrs}${tooltip}></circle>`;
    }
    const [x1, y1] = polar(cx, cy, outer, start);
    const [x2, y2] = polar(cx, cy, outer, end);
    const [x3, y3] = polar(cx, cy, inner, end);
    const [x4, y4] = polar(cx, cy, inner, start);
    const large = sweep > 180 ? 1 : 0;
    const path = `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${outer} ${outer} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} L ${x3.toFixed(2)} ${y3.toFixed(2)} A ${inner} ${inner} 0 ${large} 0 ${x4.toFixed(2)} ${y4.toFixed(2)} Z`;
    return `<path d="${path}" fill="${color}" stroke="#ffffff" stroke-width="2"${attrs}${tooltip}></path>`;
  }

  function donutChart(containerId, items, options = {}) {
    const total = items.reduce((sum, item) => sum + item.value, 0);
    if (!total) {
      byId(containerId).innerHTML = chartEmpty(options.emptyMessage || 'No records match the current filters.');
      return;
    }

    const cx = 172;
    const cy = 150;
    const outer = 92;
    const inner = 58;
    let angle = -90;
    let segments = '';

    items.forEach((item) => {
      if (!item.value) return;
      const sweep = (item.value / total) * 360;
      const attrs = interactionAttrs(item);
      const tooltip = tooltipAttr(`${item.label}: ${fmt(item.value)} ${options.centerLabel || 'records'} (${(item.value / total * 100).toFixed(1)}%)${item.tooltip ? `\n${item.tooltip}` : ''}`);
      segments += donutSlice(cx, cy, outer, inner, angle, angle + sweep, item.color, attrs, tooltip);
      angle += sweep;
    });

    const legend = items.map((item, index) => {
      const y = 58 + index * 40;
      const percent = total ? (item.value / total * 100).toFixed(1) : '0.0';
      const attrs = interactionAttrs(item);
      const tooltip = tooltipAttr(`${item.label}: ${fmt(item.value)} (${percent}%)`);
      return `<g class="${attrs ? 'interactive' : ''}"${attrs}${tooltip}>
        <rect x="320" y="${y - 13}" width="292" height="32" rx="6" fill="transparent"></rect>
        <rect x="330" y="${y - 6}" width="10" height="10" rx="2" fill="${item.color}"></rect>
        <text x="350" y="${y + 3}" class="svg-title">${escapeHtml(item.label)}</text>
        <text x="600" y="${y + 3}" class="svg-value" text-anchor="end">${fmt(item.value)} · ${percent}%</text>
      </g>`;
    }).join('');

    byId(containerId).innerHTML = `<svg viewBox="0 0 640 300" role="img" aria-label="${escapeAttr(options.ariaLabel || 'Distribution chart')}">
      ${segments}
      <text x="${cx}" y="${cy - 3}" text-anchor="middle" style="font-size:26px;font-weight:730;fill:#111827">${fmt(total)}</text>
      <text x="${cx}" y="${cy + 18}" text-anchor="middle" class="svg-subtitle">${escapeHtml(options.centerLabel || 'records')}</text>
      ${legend}
    </svg>`;
  }

  function niceMax(value) {
    if (!value || value <= 0) return 1;
    const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
    const normalized = value / magnitude;
    const step = normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
    return step * magnitude;
  }

  function tickLabel(value) {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(value % 1_000_000 ? 1 : 0)}m`;
    if (value >= 1_000) return `${(value / 1_000).toFixed(value % 1_000 ? 1 : 0)}k`;
    return String(Math.round(value));
  }

  function verticalBars(containerId, items, options = {}) {
    if (!items.length || items.every((item) => !item.value)) {
      byId(containerId).innerHTML = chartEmpty(options.emptyMessage || 'No records match the current filters.');
      return;
    }

    const width = 700;
    const height = 330;
    const margin = { top: 24, right: 16, bottom: options.rotate ? 88 : 48, left: 52 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const bottom = margin.top + plotH;
    const max = niceMax(Math.max(...items.map((item) => item.value)));
    const band = plotW / items.length;
    const barWidth = Math.min(options.barWidth || 44, Math.max(8, band * 0.68));
    const ticks = 4;

    let grid = '';
    for (let index = 0; index <= ticks; index += 1) {
      const value = max / ticks * index;
      const y = bottom - (value / max) * plotH;
      grid += `<line x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}" class="svg-grid"></line>`;
      grid += `<text x="${margin.left - 9}" y="${(y + 3).toFixed(2)}" text-anchor="end" class="svg-tick">${tickLabel(value)}</text>`;
    }

    let bars = '';
    items.forEach((item, index) => {
      const center = margin.left + band * (index + 0.5);
      const barHeight = (item.value / max) * plotH;
      const x = center - barWidth / 2;
      const y = bottom - barHeight;
      const attrs = interactionAttrs(item);
      const tooltip = tooltipAttr(`${item.label}: ${fmt(item.value)} ${options.unit || 'movies'}${item.tooltip ? `\n${item.tooltip}` : ''}`);
      bars += `<g class="${attrs ? 'interactive' : ''}"${attrs}${tooltip}>
        <rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${Math.max(barHeight, 0.5).toFixed(2)}" rx="3" fill="${item.color}" class="svg-bar"></rect>
        <rect x="${(center - band / 2).toFixed(2)}" y="${margin.top}" width="${band.toFixed(2)}" height="${plotH}" fill="transparent"></rect>
      </g>`;
      if (options.showValues !== false) {
        bars += `<text x="${center.toFixed(2)}" y="${(y - 6).toFixed(2)}" text-anchor="middle" class="svg-value">${fmt(item.value)}</text>`;
      }
      const labelY = options.rotate ? bottom + 20 : bottom + 19;
      const transform = options.rotate ? ` transform="rotate(-45 ${center.toFixed(2)} ${labelY})"` : '';
      bars += `<text x="${center.toFixed(2)}" y="${labelY}" text-anchor="${options.rotate ? 'end' : 'middle'}" class="${options.rotate ? 'svg-tick-rotated' : 'svg-tick'}"${transform}>${escapeHtml(item.shortLabel || item.label)}</text>`;
    });

    byId(containerId).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(options.ariaLabel || 'Bar chart')}">
      ${grid}
      <line x1="${margin.left}" y1="${bottom}" x2="${width - margin.right}" y2="${bottom}" class="svg-axis"></line>
      ${bars}
    </svg>${legendHtml(options.legend || [])}`;
  }

  function truncate(text, length) {
    const value = String(text);
    return value.length > length ? `${value.slice(0, length - 1)}…` : value;
  }

  function horizontalBars(containerId, items, options = {}) {
    if (!items.length || items.every((item) => !item.value)) {
      byId(containerId).innerHTML = chartEmpty(options.emptyMessage || 'No records match the current filters.');
      return;
    }

    const width = 640;
    const rowHeight = options.rowHeight || 30;
    const height = Math.max(260, items.length * rowHeight + 74);
    const margin = { top: 26, right: 62, bottom: 34, left: options.labelWidth || 172 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const max = niceMax(Math.max(...items.map((item) => item.value)));
    const ticks = 4;

    let grid = '';
    for (let index = 0; index <= ticks; index += 1) {
      const value = max / ticks * index;
      const x = margin.left + (value / max) * plotW;
      grid += `<line x1="${x.toFixed(2)}" y1="${margin.top - 4}" x2="${x.toFixed(2)}" y2="${margin.top + plotH}" class="svg-grid"></line>`;
      grid += `<text x="${x.toFixed(2)}" y="${height - 12}" text-anchor="middle" class="svg-tick">${tickLabel(value)}</text>`;
    }

    let bars = '';
    items.forEach((item, index) => {
      const y = margin.top + index * rowHeight;
      const barWidth = (item.value / max) * plotW;
      const attrs = interactionAttrs(item);
      const tooltip = tooltipAttr(`${item.label}: ${fmt(item.value)} ${options.unit || 'movies'}${item.tooltip ? `\n${item.tooltip}` : ''}`);
      bars += `<g class="${attrs ? 'interactive' : ''}"${attrs}${tooltip}>
        <text x="${margin.left - 10}" y="${y + 14}" text-anchor="end" class="svg-tick">${escapeHtml(truncate(item.label, options.truncate || 24))}</text>
        <rect x="${margin.left}" y="${y + 2}" width="${Math.max(barWidth, 0.5).toFixed(2)}" height="18" rx="3" fill="${item.color}" class="svg-bar"></rect>
        <text x="${(margin.left + barWidth + 7).toFixed(2)}" y="${y + 15}" class="svg-value">${fmt(item.value)}</text>
        <rect x="0" y="${y}" width="${width}" height="${rowHeight}" fill="transparent"></rect>
      </g>`;
    });

    byId(containerId).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(options.ariaLabel || 'Horizontal bar chart')}">
      ${grid}${bars}
    </svg>${legendHtml(options.legend || [])}`;
  }

  function stackedBars(containerId, groups, statuses, options = {}) {
    const hasValues = groups.some((group) => group.segments.some((segment) => segment.value));
    if (!groups.length || !hasValues) {
      byId(containerId).innerHTML = chartEmpty(options.emptyMessage || 'No records match the current filters.');
      return;
    }

    const width = 700;
    const height = 330;
    const rotate = groups.length > 8;
    const margin = { top: 24, right: 16, bottom: rotate ? 88 : 48, left: 52 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const bottom = margin.top + plotH;
    const totals = groups.map((group) => group.segments.reduce((sum, segment) => sum + segment.value, 0));
    const max = niceMax(Math.max(...totals));
    const band = plotW / groups.length;
    const barWidth = Math.min(44, Math.max(8, band * 0.68));
    const ticks = 4;

    let grid = '';
    for (let index = 0; index <= ticks; index += 1) {
      const value = max / ticks * index;
      const y = bottom - (value / max) * plotH;
      grid += `<line x1="${margin.left}" y1="${y.toFixed(2)}" x2="${width - margin.right}" y2="${y.toFixed(2)}" class="svg-grid"></line>`;
      grid += `<text x="${margin.left - 9}" y="${(y + 3).toFixed(2)}" text-anchor="end" class="svg-tick">${tickLabel(value)}</text>`;
    }

    let bars = '';
    groups.forEach((group, groupIndex) => {
      const center = margin.left + band * (groupIndex + 0.5);
      const x = center - barWidth / 2;
      let runningY = bottom;
      group.segments.forEach((segment) => {
        if (!segment.value) return;
        const segmentHeight = (segment.value / max) * plotH;
        runningY -= segmentHeight;
        const tooltip = tooltipAttr(`${group.label} · ${segment.label}: ${fmt(segment.value)} movies`);
        bars += `<rect x="${x.toFixed(2)}" y="${runningY.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${segmentHeight.toFixed(2)}" fill="${segment.color}" class="svg-segment"${tooltip}></rect>`;
      });
      const attrs = interactionAttrs(group);
      const breakdown = group.segments
        .filter((segment) => segment.value)
        .map((segment) => `${segment.label}: ${fmt(segment.value)}`)
        .join('\n');
      bars += `<rect class="interactive" x="${(center - band / 2).toFixed(2)}" y="${margin.top}" width="${band.toFixed(2)}" height="${plotH}" fill="transparent"${attrs}${tooltipAttr(`${group.label}: ${fmt(totals[groupIndex])} movies\n${breakdown}\nClick to filter by year`)}></rect>`;
      bars += `<text x="${center.toFixed(2)}" y="${(runningY - 6).toFixed(2)}" text-anchor="middle" class="svg-value">${fmt(totals[groupIndex])}</text>`;
      const labelY = rotate ? bottom + 20 : bottom + 19;
      const transform = rotate ? ` transform="rotate(-45 ${center.toFixed(2)} ${labelY})"` : '';
      bars += `<text x="${center.toFixed(2)}" y="${labelY}" text-anchor="${rotate ? 'end' : 'middle'}" class="${rotate ? 'svg-tick-rotated' : 'svg-tick'}"${transform}>${escapeHtml(group.label)}</text>`;
    });

    byId(containerId).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeAttr(options.ariaLabel || 'Stacked bar chart')}">
      ${grid}
      <line x1="${margin.left}" y1="${bottom}" x2="${width - margin.right}" y2="${bottom}" class="svg-axis"></line>
      ${bars}
    </svg>${legendHtml(statuses.map((status) => ({ label: status.label, color: status.color })), false)}`;
  }

  function superscript(value) {
    const map = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³', 4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };
    return String(value).split('').map((char) => map[char] || char).join('');
  }

  function scatterChart(containerId, rows) {
    const points = rows.map((row) => ({
      row,
      x: asNumber(row.dtp_revenue_vnd),
      y: asNumber(row.bov_revenue_vnd)
    })).filter((point) => point.x != null && point.y != null && point.x > 0 && point.y > 0);

    if (!points.length) {
      byId(containerId).innerHTML = chartEmpty('No exact-value diagnostic comparison is available for the current filters.');
      return;
    }

    const width = 760;
    const height = 420;
    const margin = { top: 42, right: 24, bottom: 64, left: 76 };
    const plotW = width - margin.left - margin.right;
    const plotH = height - margin.top - margin.bottom;
    const allValues = points.flatMap((point) => [point.x, point.y]);
    const minLog = Math.max(6, Math.floor(Math.log10(Math.min(...allValues))));
    const maxLog = Math.max(minLog + 1, Math.ceil(Math.log10(Math.max(...allValues))));
    const logSpan = maxLog - minLog;

    const xScale = (value) => margin.left + ((Math.log10(value) - minLog) / logSpan) * plotW;
    const yScale = (value) => margin.top + ((maxLog - Math.log10(value)) / logSpan) * plotH;

    let grid = '';
    for (let exponent = minLog; exponent <= maxLog; exponent += 1) {
      const value = Math.pow(10, exponent);
      const x = xScale(value);
      const y = yScale(value);
      grid += `<line x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${margin.top + plotH}" class="svg-grid"></line>`;
      grid += `<line x1="${margin.left}" y1="${y.toFixed(2)}" x2="${margin.left + plotW}" y2="${y.toFixed(2)}" class="svg-grid"></line>`;
      grid += `<text x="${x.toFixed(2)}" y="${height - 38}" text-anchor="middle" class="svg-tick">10${superscript(exponent)}</text>`;
      grid += `<text x="${margin.left - 10}" y="${(y + 3).toFixed(2)}" text-anchor="end" class="svg-tick">10${superscript(exponent)}</text>`;
    }

    const bandUpper = [];
    const bandLower = [];
    for (let index = 0; index <= 80; index += 1) {
      const value = Math.pow(10, minLog + (logSpan * index / 80));
      bandUpper.push(`${xScale(value).toFixed(2)},${yScale(value * 1.1).toFixed(2)}`);
      bandLower.push(`${xScale(value).toFixed(2)},${yScale(value * 0.9).toFixed(2)}`);
    }
    const bandPoints = bandUpper.concat(bandLower.reverse()).join(' ');
    const identityStart = Math.pow(10, minLog);
    const identityEnd = Math.pow(10, maxLog);

    const ordered = [...points].sort((a, b) => Number(a.row.review_priority === 'high') - Number(b.row.review_priority === 'high'));
    let circles = '';
    let labels = '';
    ordered.forEach((point) => {
      const isHigh = point.row.review_priority === 'high';
      const isWarning = isTrueFlag(point.row.magnitude_gap_warning);
      const cx = xScale(point.x);
      const cy = yScale(point.y);
      const fill = isHigh ? COLORS.amber : COLORS.blue;
      const stroke = isWarning ? COLORS.red : '#ffffff';
      const strokeWidth = isWarning ? 2.2 : 1.1;
      const radius = isHigh ? 6 : 4.4;
      const tooltip = tooltipAttr([
        `${point.row.movie_id} — ${point.row.canonical_title}`,
        `DTP: ${point.row.dtp_revenue_raw}`,
        `BOV: ${point.row.bov_revenue_raw}`,
        `Gap: ${asNumber(point.row.revenue_gap_pct) == null ? 'Not calculated' : `${Number(point.row.revenue_gap_pct).toFixed(1)}%`}`,
        `Review priority: ${label(point.row.review_priority)}`,
        'Diagnostic only — revenue scope unverified'
      ].join('\n'));
      circles += `<circle cx="${cx.toFixed(2)}" cy="${cy.toFixed(2)}" r="${radius}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" class="svg-point interactive"${tooltip}></circle>`;
      if (isHigh) {
        labels += `<text x="${(cx + 8).toFixed(2)}" y="${(cy - 7).toFixed(2)}" class="svg-tick" style="font-weight:700;fill:#92400e">${escapeHtml(point.row.movie_id)}</text>`;
      }
    });

    byId(containerId).innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Diagnostic scatter plot of DTP and BOV revenue">
      <defs><clipPath id="scatter-clip"><rect x="${margin.left}" y="${margin.top}" width="${plotW}" height="${plotH}"></rect></clipPath></defs>
      <text x="${margin.left}" y="18" class="svg-subtitle">${points.length} exact-value observations · lower bounds and restricted mappings excluded</text>
      ${grid}
      <g clip-path="url(#scatter-clip)">
        <polygon points="${bandPoints}" fill="${COLORS.amberSoft}" opacity="0.28"></polygon>
        <line x1="${xScale(identityStart).toFixed(2)}" y1="${yScale(identityStart).toFixed(2)}" x2="${xScale(identityEnd).toFixed(2)}" y2="${yScale(identityEnd).toFixed(2)}" stroke="${COLORS.slate}" stroke-width="1.4" stroke-dasharray="6 5"></line>
        ${circles}${labels}
      </g>
      <line x1="${margin.left}" y1="${margin.top + plotH}" x2="${margin.left + plotW}" y2="${margin.top + plotH}" class="svg-axis"></line>
      <line x1="${margin.left}" y1="${margin.top}" x2="${margin.left}" y2="${margin.top + plotH}" class="svg-axis"></line>
      <text x="${margin.left + plotW / 2}" y="${height - 8}" text-anchor="middle" class="svg-subtitle">DTP revenue (VND, log scale)</text>
      <text x="16" y="${margin.top + plotH / 2}" text-anchor="middle" class="svg-subtitle" transform="rotate(-90 16 ${margin.top + plotH / 2})">BOV revenue (VND, log scale)</text>
    </svg>${legendHtml([
      { label: 'Valid comparison', color: COLORS.blue },
      { label: 'High-priority review', color: COLORS.amber },
      { label: 'Gap warning ring', color: COLORS.red }
    ], true)}`;
  }

  function compareValues(first, second, direction) {
    const firstMissing = first == null || first === '';
    const secondMissing = second == null || second === '';
    if (firstMissing && secondMissing) return 0;
    if (firstMissing) return 1;
    if (secondMissing) return -1;

    let result;
    if (typeof first === 'number' && typeof second === 'number') {
      result = first - second;
    } else {
      result = String(first).localeCompare(String(second), 'vi', { numeric: true, sensitivity: 'base' });
    }
    return direction === 'desc' ? -result : result;
  }

  function renderTable(containerId, columns, data, emptyMessage = 'No records match the current filters.') {
    const sort = state.sort[containerId];
    const key = sort && sort.key;
    const direction = sort && sort.dir === 'desc' ? 'desc' : 'asc';
    const sortColumn = columns.find((column) => column.key === key);
    const sorted = [...data];
    if (sortColumn && sortColumn.value) {
      sorted.sort((first, second) => compareValues(sortColumn.value(first), sortColumn.value(second), direction));
    }

    if (!sorted.length) {
      byId(containerId).innerHTML = `<div class="table-empty">${escapeHtml(emptyMessage)}</div>`;
      return;
    }

    const head = columns.map((column) => {
      const isSorted = column.key === key;
      const arrow = isSorted ? `<span class="sort-arrow">${direction === 'asc' ? '▲' : '▼'}</span>` : '';
      const content = `<button type="button" data-table-sort="${escapeAttr(containerId)}" data-key="${escapeAttr(column.key)}">${escapeHtml(column.label)}${arrow}</button>`;
      return `<th class="${column.align === 'right' ? 'cell-numeric' : ''}">${content}</th>`;
    }).join('');

    const body = sorted.map((row) => `<tr>${columns.map((column) => {
      const content = column.cell ? column.cell(row) : displayValue(row[column.key]);
      return `<td class="${column.align === 'right' ? 'cell-numeric' : ''}">${content}</td>`;
    }).join('')}</tr>`).join('');

    byId(containerId).innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function yearGroups(rows) {
    const keys = [...new Set(rows.map(yearKey))];
    keys.sort((first, second) => {
      if (first === MISSING) return 1;
      if (second === MISSING) return -1;
      return Number(first) - Number(second);
    });
    return keys.map((key) => {
      const groupRows = rows.filter((row) => yearKey(row) === key);
      return { key, label: key === MISSING ? 'Missing year' : key, rows: groupRows };
    });
  }

  function statusItems(rows) {
    const counts = countBy(rows, 'bov_match_status');
    return MATCH_ORDER.map((key) => ({
      label: label(key),
      value: counts[key] || 0,
      color: STATUS_COLORS[key],
      filterKey: 'match',
      filterValue: key,
      tooltip: key === 'matched' ? 'Diagnostic matcher result only; not human-confirmed identity.' : ''
    }));
  }

  function renderOverview(rows) {
    const counts = countBy(rows, 'bov_match_status');
    renderKpis('overview-kpis', [
      ['Total movies', fmt(rows.length), 'All rows in the current filter selection', ''],
      ['Matched', fmt(counts.matched || 0), 'Diagnostic matcher status only', 'green'],
      ['Needs review', fmt(counts.needs_review || 0), 'Matcher review flag, not a human decision', 'amber'],
      ['Not found', fmt(counts.not_found || 0), 'No BOV page found by the matcher', 'red']
    ]);

    donutChart('chart-overview-status', statusItems(rows), {
      centerLabel: 'movies',
      ariaLabel: 'Movie matching status distribution'
    });

    const yearItems = yearGroups(rows).map((group) => ({
      label: group.label,
      shortLabel: group.label === 'Missing year' ? 'Missing' : group.label,
      value: group.rows.length,
      color: group.key === MISSING ? COLORS.slate : COLORS.blue,
      filterKey: 'year',
      filterValue: group.key,
      tooltip: 'Click to filter by release year'
    }));
    verticalBars('chart-overview-year', yearItems, { rotate: yearItems.length > 8, unit: 'movies' });

    byId('overview-row-count').textContent = `${fmt(rows.length)} rows`;
    renderTable('table-overview', [
      { key: 'canonical_title', label: 'Movie title', cell: (row) => `<span class="cell-title">${escapeHtml(row.canonical_title)}</span>` },
      { key: 'release_year', label: 'Year', value: (row) => yearKey(row), cell: (row) => (row.release_year ? escapeHtml(row.release_year) : pill('Missing', 'missing')) },
      { key: 'genre', label: 'Genre tokens', value: (row) => genreTokens(row).join('|'), cell: (row) => genreTokens(row).length ? escapeHtml(genreTokens(row).join(' · ')) : pill('Not provided', 'missing') },
      { key: 'director', label: 'Director', value: (row) => directorKey(row), cell: (row) => (directorKey(row) === MISSING ? pill('Missing director', 'missing') : escapeHtml(directorDisplay(row))) },
      { key: 'bov_match_status', label: 'Matching status', value: (row) => label(row.bov_match_status), cell: (row) => matchPill(row.bov_match_status) }
    ], rows, 'No movie records match the current filters.');
  }

  function renderYear(rows) {
    const groups = yearGroups(rows);
    const knownYears = groups.filter((group) => group.key !== MISSING);
    const missingCount = groups.find((group) => group.key === MISSING)?.rows.length || 0;
    const counts = countBy(rows, 'bov_match_status');

    renderKpis('year-kpis', [
      ['Total movies', fmt(rows.length), 'Current filter selection', ''],
      ['Distinct release years', fmt(knownYears.length), 'Year-only labels; no full dates', 'blue'],
      ['Matched', fmt(counts.matched || 0), 'Diagnostic matcher status', 'green'],
      ['Missing year', fmt(missingCount), 'Shown explicitly, never converted to zero', 'amber']
    ]);

    const yearItems = groups.map((group) => ({
      label: group.label,
      shortLabel: group.key === MISSING ? 'Missing' : group.label,
      value: group.rows.length,
      color: group.key === MISSING ? COLORS.slate : COLORS.blue,
      filterKey: 'year',
      filterValue: group.key,
      tooltip: 'Click to filter by year'
    }));
    verticalBars('chart-year-count', yearItems, { rotate: yearItems.length > 8, unit: 'movies' });

    const statuses = MATCH_ORDER.map((key) => ({ key, label: label(key), color: STATUS_COLORS[key] }));
    const stackedGroups = groups.map((group) => ({
      key: group.key,
      label: group.key === MISSING ? 'Missing' : group.label,
      filterKey: 'year',
      filterValue: group.key,
      segments: statuses.map((status) => ({
        label: status.label,
        color: status.color,
        value: group.rows.filter((row) => row.bov_match_status === status.key).length
      }))
    }));
    stackedBars('chart-year-stacked', stackedGroups, statuses, {
      ariaLabel: 'Release year by matching status'
    });

    const yearRows = groups.map((group) => {
      const groupCounts = countBy(group.rows, 'bov_match_status');
      return {
        key: group.key,
        label: group.label,
        movies: group.rows.length,
        matched: groupCounts.matched || 0,
        needs_review: groupCounts.needs_review || 0,
        not_found: groupCounts.not_found || 0
      };
    });
    renderTable('table-year', [
      { key: 'year', label: 'Release year', value: (row) => row.key, cell: (row) => (row.key === MISSING ? pill('Missing year', 'missing') : escapeHtml(row.label)) },
      { key: 'movies', label: 'Movies', align: 'right', value: (row) => row.movies, cell: (row) => fmt(row.movies) },
      { key: 'matched', label: 'Matched', align: 'right', value: (row) => row.matched, cell: (row) => fmt(row.matched) },
      { key: 'needs_review', label: 'Needs review', align: 'right', value: (row) => row.needs_review, cell: (row) => fmt(row.needs_review) },
      { key: 'not_found', label: 'Not found', align: 'right', value: (row) => row.not_found, cell: (row) => fmt(row.not_found) }
    ], yearRows, 'No release-year groups match the current filters.');
  }

  function genreCounts(rows) {
    const counts = Object.create(null);
    rows.forEach((row) => genreTokens(row).forEach((token) => {
      counts[token] = (counts[token] || 0) + 1;
    }));
    return counts;
  }

  function directorCounts(rows) {
    const counts = Object.create(null);
    rows.forEach((row) => {
      const key = directorKey(row);
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }

  function topWithOther(counts, limit, missingKey = MISSING) {
    const entries = Object.entries(counts).sort((first, second) => {
      if (first[0] === missingKey) return -1;
      if (second[0] === missingKey) return 1;
      return second[1] - first[1] || first[0].localeCompare(second[0], 'vi');
    });
    const selected = entries.slice(0, limit);
    const selectedKeys = new Set(selected.map(([key]) => key));
    const remainder = entries.filter(([key]) => !selectedKeys.has(key));
    const result = selected.map(([key, value]) => ({
      key,
      label: key === missingKey ? 'Missing director' : key,
      value,
      color: key === missingKey ? COLORS.slate : COLORS.blue,
      filterKey: key === missingKey ? 'director' : '',
      filterValue: key,
      tooltip: key === missingKey ? 'Missing director values are explicit; they are not zero.' : ''
    }));
    if (remainder.length) {
      result.push({
        key: '__other__',
        label: `Other (${remainder.length} ${missingKey === MISSING ? 'genres' : 'directors'})`,
        value: remainder.reduce((sum, [, value]) => sum + value, 0),
        color: COLORS.slate,
        tooltip: 'Presentation roll-up only; not an invented category.'
      });
    }
    return result;
  }

  function renderGenre(rows) {
    const genres = genreCounts(rows);
    const directors = directorCounts(rows);
    const genreAssignments = Object.values(genres).reduce((sum, value) => sum + value, 0);
    const missingDirectorCount = directors[MISSING] || 0;

    renderKpis('genre-kpis', [
      ['Distinct genre tokens', fmt(Object.keys(genres).length), 'Parsed from genre_token_path', ''],
      ['Genre assignments', fmt(genreAssignments), 'Non-additive; multi-genre films count more than once', 'blue'],
      ['Directors represented', fmt(Object.keys(directors).filter((key) => key !== MISSING).length), 'Original names preserved', 'green'],
      ['Missing directors', fmt(missingDirectorCount), 'Displayed explicitly, never as zero', 'amber']
    ]);

    const genreItems = topWithOther(genres, 12, '__no_genre__').map((item) => ({
      ...item,
      filterKey: item.key === '__other__' ? '' : 'genre',
      filterValue: item.key,
      tooltip: item.tooltip ? `${item.tooltip}\nGenre counts are non-additive.` : 'Genre counts are non-additive.'
    }));
    horizontalBars('chart-genre', genreItems, {
      labelWidth: 170,
      truncate: 26,
      unit: 'movie contributions',
      ariaLabel: 'Genre token frequency'
    });

    const directorItems = topWithOther(directors, 10, MISSING);
    horizontalBars('chart-director-profile', directorItems, {
      labelWidth: 190,
      truncate: 28,
      unit: 'movies',
      ariaLabel: 'Director profile'
    });

    const namedDirectors = Object.entries(directors)
      .filter(([key]) => key !== MISSING)
      .sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0], 'vi'))
      .slice(0, 8)
      .map(([name, value]) => ({
        label: name,
        shortLabel: truncate(name, 12),
        value,
        color: COLORS.violet,
        filterKey: 'director',
        filterValue: name,
        tooltip: 'Click to filter by this original director name'
      }));
    verticalBars('chart-director-top', namedDirectors, {
      rotate: true,
      unit: 'movies',
      ariaLabel: 'Top directors by movie count'
    });
  }

  function renderQuality(rows) {
    const flags = [
      ['has_missing_core_data', 'Missing core data', 'Exported flag'],
      ['has_revenue_gap_warning', 'Revenue gap warning', 'Numerical warning only'],
      ['has_pending_review', 'Pending review', 'Workflow state, not a human decision'],
      ['ticket_data_status', 'Unverified ticket candidates', 'No admissions are summed']
    ].map(([field, name, note]) => {
      const value = field === 'ticket_data_status'
        ? rows.filter((row) => row[field] === 'unverified_candidates').length
        : rows.filter((row) => isTrueFlag(row[field])).length;
      return { label: name, value, color: field === 'has_revenue_gap_warning' ? COLORS.amber : COLORS.blue, tooltip: note };
    });

    const reviewCounts = countBy(rows, 'review_status');
    const reviewColors = { auto_accepted: COLORS.blue, pending: COLORS.amber, not_applicable: COLORS.slate };
    const reviewItems = REVIEW_ORDER.map((key) => ({
      label: label(key),
      value: reviewCounts[key] || 0,
      color: reviewColors[key],
      tooltip: key === 'pending' ? 'Pending is a workflow state; no human decision is recorded.' : ''
    }));

    const warningCount = rows.filter((row) => isTrueFlag(row.has_revenue_gap_warning)).length;
    const warningItems = [
      { label: 'Warning', value: warningCount, color: COLORS.amber, tooltip: 'Numerical magnitude warning only' },
      { label: 'No warning', value: rows.length - warningCount, color: COLORS.green, tooltip: 'No numerical magnitude warning' }
    ];

    renderKpis('quality-kpis', [
      ['Missing core data', fmt(flags[0].value), 'Exported has_missing_core_data flag', 'red'],
      ['Revenue gap warnings', fmt(flags[1].value), 'Numerical warnings, not confirmed conflicts', 'amber'],
      ['Pending review', fmt(flags[2].value), 'Workflow state; 0 human-reviewed mappings', 'amber'],
      ['Ticket candidates', fmt(flags[3].value), 'Unverified evidence; 0 verified admissions', 'violet']
    ]);

    donutChart('chart-quality-status', statusItems(rows), {
      centerLabel: 'movies',
      ariaLabel: 'Matching status distribution'
    });
    horizontalBars('chart-quality-flags', flags, {
      labelWidth: 180,
      truncate: 28,
      unit: 'movies',
      ariaLabel: 'Independent data quality flags'
    });
    donutChart('chart-quality-review', reviewItems, {
      centerLabel: 'records',
      ariaLabel: 'Review workflow status'
    });
    horizontalBars('chart-quality-warning', warningItems, {
      labelWidth: 90,
      unit: 'movies',
      ariaLabel: 'Revenue warning count'
    });

    const pendingRows = rows.filter((row) => isTrueFlag(row.has_pending_review));
    renderTable('table-pending', [
      { key: 'movie_id', label: 'ID', cell: (row) => `<span class="cell-id">${escapeHtml(row.movie_id)}</span>` },
      { key: 'canonical_title', label: 'Title', cell: (row) => `<span class="cell-title">${escapeHtml(row.canonical_title)}</span>` },
      { key: 'review_priority', label: 'Priority', value: (row) => label(row.review_priority), cell: (row) => pill(label(row.review_priority), row.review_priority) },
      { key: 'mapping_validation_status', label: 'Mapping validation', value: (row) => label(row.mapping_validation_status), cell: (row) => pill(label(row.mapping_validation_status), row.mapping_validation_status) },
      { key: 'match_score', label: 'Fuzzy score', align: 'right', value: (row) => asNumber(row.match_score), cell: scoreCell }
    ], pendingRows, 'No pending workflow records match the current filters.');

    const priorityRows = rows.filter((row) => row.review_priority === 'high');
    renderTable('table-priority', [
      { key: 'movie_id', label: 'ID', cell: (row) => `<span class="cell-id">${escapeHtml(row.movie_id)}</span>` },
      { key: 'canonical_title', label: 'Title', cell: (row) => `<span class="cell-title">${escapeHtml(row.canonical_title)}</span>` },
      { key: 'mapping_validation_status', label: 'Mapping', value: (row) => label(row.mapping_validation_status), cell: (row) => pill(label(row.mapping_validation_status), row.mapping_validation_status) },
      { key: 'mapping_validation_reason', label: 'Reason', cell: reasonLabel }
    ], priorityRows, 'No high-priority review records match the current filters.');

    const restrictedRows = rows.filter((row) => (
      row.mapping_validation_status === 'known_false_positive_quarantined'
      || row.mapping_validation_status === 'candidate_held'
    ));
    renderTable('table-restricted', [
      { key: 'movie_id', label: 'ID', cell: (row) => `<span class="cell-id">${escapeHtml(row.movie_id)}</span>` },
      { key: 'canonical_title', label: 'Title', cell: (row) => `<span class="cell-title">${escapeHtml(row.canonical_title)}</span>` },
      { key: 'mapping_validation_status', label: 'State', value: (row) => label(row.mapping_validation_status), cell: (row) => pill(label(row.mapping_validation_status), row.mapping_validation_status) },
      { key: 'mapping_validation_reason', label: 'Reason', cell: reasonLabel },
      { key: 'restricted', label: 'BOV evidence (audit only)', value: (row) => row.bov_quarantined_revenue_raw || row.bov_candidate_revenue_raw, cell: restrictedEvidence }
    ], restrictedRows, 'No restricted mapping evidence matches the current filters.');
  }

  function renderRevenue(rows) {
    const roundedRows = rows.filter((row) => (
      isTrueFlag(row.include_revenue_eda)
      && row.dtp_revenue_quality === 'rounded'
      && asNumber(row.dtp_revenue_vnd) != null
    ));
    const comparisonRows = rows.filter((row) => isTrueFlag(row.include_revenue_comparison));
    const lowerRows = rows.filter((row) => row.dtp_revenue_quality === 'lower_bound');
    const warningRows = rows.filter((row) => isTrueFlag(row.has_revenue_gap_warning));
    const scatterRows = rows.filter((row) => (
      isTrueFlag(row.include_revenue_comparison)
      && row.dtp_revenue_quality === 'rounded'
      && !RESTRICTED_SCATTER_IDS.has(row.movie_id)
      && asNumber(row.dtp_revenue_vnd) != null
      && asNumber(row.bov_revenue_vnd) != null
    ));

    renderKpis('revenue-kpis', [
      ['DTP rounded observations', fmt(roundedRows.length), 'No BOV revenue; lower bounds excluded', 'blue'],
      ['Accepted BOV comparisons', fmt(comparisonRows.length), 'Exported flag; 0 verified revenue scopes', 'green'],
      ['Lower-bound DTP', fmt(lowerRows.length), 'Shown with ≥; never treated as exact', 'amber'],
      ['Magnitude gap warnings', fmt(warningRows.length), 'Diagnostic only; not confirmed conflicts', 'red']
    ]);

    const histogramItems = BINS.map((bin) => ({
      label: bin.label,
      value: roundedRows.filter((row) => {
        const value = asNumber(row.dtp_revenue_vnd);
        if (value == null) return false;
        return value >= bin.min && (bin.max == null || value < bin.max);
      }).length,
      color: COLORS.blue,
      tooltip: 'Fixed display bin; rounded DTP only; scope unverified'
    }));
    verticalBars('chart-revenue-hist', histogramItems, {
      unit: 'rounded DTP observations',
      ariaLabel: 'DTP revenue distribution histogram'
    });

    renderTable('table-lower-bound', [
      { key: 'movie_id', label: 'ID', cell: (row) => `<span class="cell-id">${escapeHtml(row.movie_id)}</span>` },
      { key: 'canonical_title', label: 'Title', cell: (row) => `<span class="cell-title">${escapeHtml(row.canonical_title)}</span>` },
      { key: 'dtp_revenue_raw', label: 'Raw DTP text', cell: (row) => escapeHtml(row.dtp_revenue_raw || 'Not provided') },
      { key: 'dtp_revenue_vnd', label: 'Lower-bound display', align: 'right', value: (row) => asNumber(row.dtp_revenue_vnd), cell: (row) => (asNumber(row.dtp_revenue_vnd) == null ? pill('Not provided', 'missing') : `<strong>≥${fmt(asNumber(row.dtp_revenue_vnd))} ₫</strong>`) },
      { key: 'dtp_revenue_quality', label: 'Quality', cell: () => pill('Lower bound', 'lower_bound') }
    ], lowerRows, 'No lower-bound DTP observations match the current filters.');

    scatterChart('chart-revenue-scatter', scatterRows);
  }

  function handleChartClick(event) {
    const target = event.target.closest('[data-filter-key]');
    if (!target) return;
    const key = target.getAttribute('data-filter-key');
    const value = target.getAttribute('data-filter-value');
    if (!key || !Object.prototype.hasOwnProperty.call(state.filters, key)) return;
    const next = state.filters[key] === value ? '' : value;
    setFilter(key, next, true);
  }

  function handleSortClick(event) {
    const target = event.target.closest('[data-table-sort]');
    if (!target) return;
    const tableId = target.getAttribute('data-table-sort');
    const key = target.getAttribute('data-key');
    const current = state.sort[tableId];
    if (!current) return;
    if (current.key === key) {
      current.dir = current.dir === 'asc' ? 'desc' : 'asc';
    } else {
      current.key = key;
      current.dir = 'asc';
    }
    renderAll();
  }

  function showTooltip(event) {
    const target = event.target.closest('[data-tooltip]');
    if (!target) return;
    const tooltip = byId('tooltip');
    tooltip.textContent = target.getAttribute('data-tooltip') || '';
    tooltip.hidden = false;
    positionTooltip(event);
  }

  function moveTooltip(event) {
    const tooltip = byId('tooltip');
    if (tooltip.hidden) return;
    positionTooltip(event);
  }

  function positionTooltip(event) {
    const tooltip = byId('tooltip');
    const padding = 14;
    const width = tooltip.offsetWidth;
    const height = tooltip.offsetHeight;
    let left = event.clientX + padding;
    let top = event.clientY + padding;
    if (left + width > window.innerWidth - 8) left = event.clientX - width - padding;
    if (top + height > window.innerHeight - 8) top = event.clientY - height - padding;
    tooltip.style.left = `${Math.max(8, left)}px`;
    tooltip.style.top = `${Math.max(8, top)}px`;
  }

  function hideTooltip() {
    byId('tooltip').hidden = true;
  }

  document.addEventListener('click', (event) => {
    const nav = event.target.closest('.nav-item');
    if (nav) {
      setPage(nav.dataset.page);
      return;
    }
    if (event.target.closest('#reset-filters')) {
      resetFilters();
      return;
    }
    const clear = event.target.closest('[data-clear-filter]');
    if (clear) {
      setFilter(clear.getAttribute('data-clear-filter'), '', true);
      return;
    }
    handleChartClick(event);
    handleSortClick(event);
  });

  document.addEventListener('mouseover', showTooltip);
  document.addEventListener('mousemove', moveTooltip);
  document.addEventListener('mouseout', (event) => {
    if (event.target.closest('[data-tooltip]')) hideTooltip();
  });
  window.addEventListener('scroll', hideTooltip, { passive: true });
  window.addEventListener('hashchange', () => {
    if (state.loaded) setPage(pageFromHash(), false);
  });

  loadDataset();
})();
