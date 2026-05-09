/* ═══════════════════════════════════════════════════
   RasoSpeak v2 — UI Rendering Layer
   All DOM mutations, phase animations, stats dashboard.
   ═══════════════════════════════════════════════════ */

/* ── VIEWS ──────────────────────────────────────────── */
function switchView(v) {
  ['script', 'live', 'stats'].forEach(id => {
    document.getElementById(`view-${id}`)?.classList.toggle('active', id === v);
    document.getElementById(`nav-${id}`)?.classList.toggle('active', id === v);
  });
  if (v === 'stats') renderStatsView();
}

/* ── CHUNK LIST — SCRIPT STUDIO ─────────────────────── */
function renderChunkList() {
  const list  = document.getElementById('chunk-list');
  const count = document.getElementById('chunk-count');
  if (!list) return;
  if (count) count.textContent = S.chunks.length ? `${S.chunks.length} chunks` : '—';

  if (!S.chunks.length) {
    list.innerHTML = `<p style="color:var(--text-muted);font-size:12px;text-align:center;padding-top:24px">
      Paste a script to preview chunks here.</p>`;
    return;
  }
  list.innerHTML = S.chunks.map((c, i) => `
    <div class="chunk-card">
      <div class="chunk-num">
        <span>${i + 1} / ${S.chunks.length}</span>
        <span>${c.split(' ').length}w</span>
      </div>
      <div class="chunk-text">${escHtml(c)}</div>
    </div>
  `).join('');
}

/* ── CHUNK LIST — LIVE VIEW ─────────────────────────── */
function renderLiveChunkList() {
  const list = document.getElementById('live-chunk-list');
  const cnt  = document.getElementById('live-chunk-count');
  if (!list) return;
  if (cnt) cnt.textContent = S.chunks.length ? `${S.chunks.length} chunks` : '—';

  if (!S.chunks.length) {
    list.innerHTML = '<p style="color:var(--text-muted);font-size:11px;text-align:center;padding-top:20px">No script loaded</p>';
    return;
  }

  list.innerHTML = S.chunks.map((c, i) => {
    const r      = S.segResults[i];
    const done   = i < S.cur;
    const active = i === S.cur;
    const next   = i === S.cur + 1;
    let   cls    = done ? 'done' : active ? 'active' : next ? 'next' : '';

    const badge = r
      ? `<span style="font-family:var(--font-mono);font-size:9px;font-weight:600;color:${
          r.score >= 0.7 ? 'var(--secondary)' : r.score >= 0.45 ? 'var(--accent)' : 'var(--danger)'
        }">${Math.round(r.score * 100)}%</span>`
      : done ? '<span style="color:var(--text-muted);font-size:9px">—</span>' : '';

    const icon = active ? '▶' : done ? (r?.status === 'ok' ? '✓' : '✗') : '';

    return `
      <div class="chunk-card ${cls}" id="lc${i}" onclick="jumpToChunk(${i})" title="Jump to chunk ${i + 1}">
        <div class="chunk-num">
          <span style="color:${active ? 'var(--primary-light)' : 'var(--text-muted)'}">${icon} ${i + 1}</span>
          ${badge}
        </div>
        <div class="chunk-text">${escHtml(c)}</div>
      </div>`;
  }).join('');

  document.getElementById(`lc${S.cur}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── STAGE TEXT ─────────────────────────────────────── */
function showChunkText(expected, spoken, result) {
  const el = document.getElementById('current-text');
  if (!el) return;

  if (!spoken) {
    el.innerHTML = expected.split(/(\s+)/).map(t =>
      /^\s+$/.test(t) ? ' ' : `<span class="word-token word-current">${escHtml(t)}</span>`
    ).join('');
    return;
  }

  const spkW = keyWords(spoken);
  el.innerHTML = expected.split(/(\s+)/).map(t => {
    if (/^\s+$/.test(t)) return ' ';
    const clean = t.toLowerCase().replace(/[^a-z0-9']/g, '');
    if (clean.length <= 2 || STOP_WORDS.has(clean))
      return `<span class="word-token word-spoken">${escHtml(t)}</span>`;
    const hit = spkW.some(sw => wordSim(clean, sw) >= (S.confidence || 0.75));
    return `<span class="word-token ${hit ? 'word-spoken' : 'word-missed'}">${escHtml(t)}</span>`;
  }).join('');
}

function updateSegDisplay() {
  const numEl   = document.getElementById('seg-num');
  const totalEl = document.getElementById('seg-total');
  if (numEl)   numEl.textContent   = S.cur + 1;
  if (totalEl) totalEl.textContent = S.chunks.length || '—';
  if (S.chunks[S.cur]) showChunkText(S.chunks[S.cur], null, null);
}

/* ── COMPARE DETAIL ─────────────────────────────────── */
function showCompareDetail(result) {
  const badge = document.getElementById('acc-badge');
  if (badge) {
    badge.textContent = result.matchPct + '%';
    badge.style.color = result.status === 'ok' ? 'var(--secondary)'
      : result.status === 'warn' ? 'var(--accent)' : 'var(--danger)';
  }

  const det = document.getElementById('compare-detail');
  if (!det) return;

  const barCol = result.status === 'ok' ? 'var(--secondary)'
    : result.status === 'warn' ? 'var(--accent)' : 'var(--danger)';

  const matchHtml = (result.matchedWords || []).slice(0, 6)
    .map(w => `<span class="token-match">${escHtml(w)}</span>`).join('');
  const missHtml = (result.missedWords || []).slice(0, 5)
    .map(w => `<span class="token-miss">${escHtml(w)}</span>`).join('');

  det.innerHTML = `
    <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
      <div class="accuracy-track" style="flex:1">
        <div class="accuracy-fill" style="width:${result.matchPct}%;background:${barCol}"></div>
      </div>
    </div>
    <div class="match-tokens">${matchHtml}${missHtml}</div>`;
}

/* ── PROGRESS ───────────────────────────────────────── */
function updateProgress(done) {
  const pct  = S.chunks.length ? Math.round((done ? 1 : S.cur / S.chunks.length) * 100) : 0;
  const fill = document.getElementById('prog-fill');
  const lbl  = document.getElementById('prog-pct');
  if (fill) fill.style.width  = pct + '%';
  if (lbl)  lbl.textContent   = pct + '%';
}

/* ── PHASE SYSTEM ───────────────────────────────────── */
const PHASE_CONFIG = {
  [PHASE.IDLE]:    { label: 'Idle',                   color: 'var(--text-muted)',    status: 'muted',     glow: null,                      tabId: null },
  [PHASE.DELIVER]: { label: '🎧 Listen to earpiece…', color: 'var(--primary-light)', status: 'primary',   glow: 'rgba(124,106,245,0.07)',   tabId: 'deliver' },
  [PHASE.LISTEN]:  { label: '🎤 Speak to audience!',  color: 'var(--secondary)',     status: 'secondary', glow: 'rgba(54,217,168,0.07)',    tabId: 'listen' },
  [PHASE.COMPARE]: { label: '⚖️ Evaluating via AMD…', color: 'var(--accent)',        status: 'accent',    glow: 'rgba(247,147,30,0.06)',    tabId: 'compare' },
  [PHASE.CORRECT]: { label: '🔄 Correcting via AMD…', color: 'var(--danger)',        status: 'danger',    glow: 'rgba(255,107,107,0.07)',   tabId: 'correct' },
};

function setPhase(ph) {
  S.phase = ph;
  const cfg = PHASE_CONFIG[ph] || PHASE_CONFIG[PHASE.IDLE];

  // Phase tabs
  ['deliver', 'listen', 'compare', 'correct'].forEach(p => {
    const el = document.getElementById(`ph-${p}`);
    if (!el) return;
    const active = cfg.tabId === p;
    el.classList.toggle('active', active);
    el.style.color        = active ? cfg.color : '';
    el.style.borderBottom = active ? `2px solid ${cfg.color}` : '';
    el.style.background   = active ? `${cfg.color}12` : '';
  });

  // Ambient glow
  const glow = document.getElementById('stage-ambient');
  if (glow) glow.style.background = cfg.glow
    ? `radial-gradient(ellipse 60% 50% at 50% 50%, ${cfg.glow} 0%, transparent 70%)`
    : '';

  // Cue dot + label
  setCue(cfg.label, cfg.color, ph !== PHASE.IDLE);

  // Status pill
  setStatus(cfg.status, cfg.label.replace(/^[^\w]+/, ''));

  // Waveform colours
  animateWaveformForPhase(ph);

  // Update AMD agent indicator label
  updateAgentIndicator(ph);
}

function updateAgentIndicator(ph) {
  const el = document.getElementById('agent-indicator-label');
  if (!el) return;
  const labels = {
    [PHASE.IDLE]:    'Agents idle',
    [PHASE.DELIVER]: 'TTS → earpiece',
    [PHASE.LISTEN]:  'TranscriptionAgent (Whisper) active',
    [PHASE.COMPARE]: 'ScoringAgent (Qwen2.5-7B) running',
    [PHASE.CORRECT]: 'CoachingAgent (Qwen2.5-7B) running',
  };
  el.textContent = labels[ph] || 'AMD MI300X';
}

function setCue(txt, color, active) {
  const label = document.getElementById('cue-label');
  const dot   = document.getElementById('cue-dot');
  if (label) { label.textContent = txt; label.style.color = color || ''; }
  if (dot)   { dot.style.background = color || 'var(--text-muted)'; dot.classList.toggle('pulsing', active); }
}

const STATUS_COLORS = {
  muted:     'var(--text-muted)',
  primary:   'var(--primary-light)',
  secondary: 'var(--secondary)',
  accent:    'var(--accent)',
  danger:    'var(--danger)',
};

function setStatus(colorKey, txt) {
  const col   = STATUS_COLORS[colorKey] || STATUS_COLORS.muted;
  const dot   = document.getElementById('status-dot');
  const label = document.getElementById('status-text');
  if (dot) {
    dot.style.background = col;
    dot.style.boxShadow  = colorKey !== 'muted' ? `0 0 7px ${col}` : 'none';
    dot.classList.toggle('pulse', colorKey !== 'muted');
  }
  if (label) { label.textContent = txt; label.style.color = col; }
}

/* ── COACH LOG ──────────────────────────────────────── */
const MAX_LOG = 35;

function logCoach(type, icon, msg) {
  const log = document.getElementById('coach-log');
  if (!log) return;
  const d    = document.createElement('div');
  const time = new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  d.className  = `log-entry ${type} fade-in`;
  d.innerHTML  = `<div class="log-meta">${icon} ${time}</div><div class="log-msg">${msg}</div>`;
  log.insertBefore(d, log.firstChild);
  while (log.children.length > MAX_LOG) log.removeChild(log.lastChild);
}

function clearLog() {
  const log = document.getElementById('coach-log');
  if (log) log.innerHTML = '';
}

/* ── METRICS ────────────────────────────────────────── */
function setM(key, val) {
  const el = document.getElementById('m-' + key);
  if (el) el.textContent = val;
}

/* ── BUTTON HELPERS ─────────────────────────────────── */
function setMainBtn(icon) {
  const el = document.getElementById('btn-main-icon');
  if (el) el.textContent = icon;
}
function showEndBtn(show) {
  document.getElementById('btn-end')?.classList.toggle('hidden', !show);
}
function showTimer(show) {
  document.getElementById('session-timer')?.classList.toggle('hidden', !show);
}

/* ── SETTINGS ───────────────────────────────────────── */
function setMode(btn) {
  S.mode = btn.dataset.mode;
  if (typeof APP !== 'undefined') APP.mode = S.mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function setStrict(btn) {
  S.strict = parseInt(btn.dataset.strict);
  if (typeof APP !== 'undefined') APP.strict = S.strict;
  document.querySelectorAll('.strict-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function setChunk(n) {
  S.chunkSize = n;
  if (typeof APP !== 'undefined') APP.chunkSize = n;
  document.querySelectorAll('.chunk-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.size) === n));
  const raw = document.getElementById('script-ta')?.value.trim();
  if (raw) { buildChunks(raw); renderChunkList(); liveWC(); }
}

/* ── STATS VIEW ─────────────────────────────────────── */
function renderStatsView() {
  loadHistory();
  const history = S.sessionHistory;
  const total   = history.length;
  const avgAcc  = total ? Math.round(history.reduce((a, s) => a + s.accuracy, 0) / total) : 0;
  const avgWpm  = total ? Math.round(history.filter(s => s.wpm > 0).reduce((a, s) => a + s.wpm, 0) / Math.max(1, history.filter(s => s.wpm > 0).length)) : 0;
  const bestAcc = total ? Math.max(...history.map(s => s.accuracy)) : 0;
  const totalCorr = history.reduce((a, s) => a + (s.corrections || 0), 0);
  const amdSessions = history.filter(s => s.backend?.includes('AMD')).length;

  const el = document.getElementById('stats-content');
  if (!el) return;

  el.innerHTML = `
    <div>
      <h2 class="font-display" style="font-size:20px;font-weight:800;margin-bottom:4px">Session History</h2>
      <p style="color:var(--text-muted);font-size:12px;display:flex;align-items:center;gap:10px">
        ${total} session${total !== 1 ? 's' : ''} logged
        ${amdSessions > 0 ? `<span class="amd-badge"><span class="amd-dot"></span>${amdSessions} on AMD MI300X</span>` : ''}
      </p>
    </div>

    <div class="stats-grid">
      <div class="stat-card"><div class="stat-val" style="color:var(--primary-light)">${total}</div><div class="stat-lbl">Sessions</div></div>
      <div class="stat-card"><div class="stat-val" style="color:var(--secondary)">${avgAcc}%</div><div class="stat-lbl">Avg Accuracy</div></div>
      <div class="stat-card"><div class="stat-val" style="color:var(--accent)">${avgWpm || '—'}</div><div class="stat-lbl">Avg WPM</div></div>
      <div class="stat-card"><div class="stat-val" style="color:var(--secondary)">${bestAcc}%</div><div class="stat-lbl">Best Accuracy</div></div>
      <div class="stat-card"><div class="stat-val" style="color:var(--danger)">${totalCorr}</div><div class="stat-lbl">Total Corrections</div></div>
      <div class="stat-card"><div class="stat-val" style="color:var(--amd-red)">${amdSessions}</div><div class="stat-lbl">AMD Sessions</div></div>
    </div>

    ${total > 0 ? `
    <div style="background:var(--surface-2);border:1px solid var(--border);border-radius:16px;overflow:hidden">
      <div style="padding:14px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
        <span style="font-family:var(--font-mono);font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--text-muted)">Session Log</span>
        <button class="btn btn-ghost" style="padding:4px 12px;font-size:10px" onclick="if(confirm('Clear all history?')){clearHistory();renderStatsView();}">Clear All</button>
      </div>
      <table class="history-table">
        <thead><tr>
          <th>Date</th><th>Time</th><th>Chunks</th><th>Accuracy</th>
          <th>WPM</th><th>Corrections</th><th>Mode</th><th>Backend</th>
        </tr></thead>
        <tbody>
          ${history.map(s => `<tr>
            <td>${s.date}</td>
            <td style="color:var(--text-muted)">${s.time}</td>
            <td><strong style="color:var(--text-primary)">${s.done}</strong><span style="color:var(--text-muted)">/${s.chunks}</span></td>
            <td><strong style="color:${s.accuracy >= 80 ? 'var(--secondary)' : s.accuracy >= 60 ? 'var(--accent)' : 'var(--danger)'}">${s.accuracy}%</strong></td>
            <td style="color:var(--primary-light)">${s.wpm || '—'}</td>
            <td style="color:var(--danger)">${s.corrections || 0}</td>
            <td style="color:var(--text-muted);font-size:10px;font-family:var(--font-mono)">${s.mode || '—'}</td>
            <td>${s.backend?.includes('AMD')
              ? `<span class="amd-badge" style="padding:1px 7px;font-size:9px"><span class="amd-dot"></span>AMD</span>`
              : `<span style="font-size:10px;color:var(--text-muted);font-family:var(--font-mono)">offline</span>`}
            </td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>` : `
    <div style="text-align:center;padding:60px 20px;color:var(--text-muted)">
      <div style="font-size:40px;margin-bottom:12px">📊</div>
      <p>No sessions yet. Complete your first session to see stats here.</p>
    </div>`}`;
}

/* ── TOAST ──────────────────────────────────────────── */
let _toastTimer;
function toast(msg) {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3800);
}

/* ── UTIL ───────────────────────────────────────────── */
function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
