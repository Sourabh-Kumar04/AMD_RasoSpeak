/* ═══════════════════════════════════════════════════
   RasoSpeak — UI Rendering Layer
   All DOM mutations, phase animations, stats dashboard.
   ═══════════════════════════════════════════════════ */

/* ── VIEWS ──────────────────────────────────────────── */
function switchView(v) {
  ['script', 'live', 'stats', 'partner'].forEach(id => {
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
    list.innerHTML = `<p class="text-on-surface-variant text-body-sm text-center py-6">
      Paste a script to preview chunks here.</p>`;
    return;
  }
  list.innerHTML = S.chunks.map((c, i) => `
    <div class="bg-surface-container-lowest border border-yc rounded p-3 mb-2 shadow-sm">
      <div class="flex justify-between items-center mb-1 text-mono-label text-on-surface-variant">
        <span>${i + 1} / ${S.chunks.length}</span>
        <span>${c.split(' ').length}w</span>
      </div>
      <div class="text-body-sm text-on-surface">${escHtml(c)}</div>
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
    list.innerHTML = '<p class="text-on-surface-variant text-body-sm text-center py-4">No script loaded</p>';
    return;
  }

  list.innerHTML = S.chunks.map((c, i) => {
    const r      = S.segResults[i];
    const done   = i < S.cur;
    const active = i === S.cur;
    const next   = i === S.cur + 1;
    let   cls    = active ? 'border-primary-container bg-surface-block shadow-md scale-[1.02]' : done ? 'opacity-50 grayscale' : 'border-yc';

    const badge = r
      ? `<span class="text-mono-label font-bold ${
          r.score >= 0.7 ? 'text-primary' : r.score >= 0.45 ? 'text-secondary' : 'text-error'
        }">${Math.round(r.score * 100)}%</span>`
      : done ? '<span class="text-on-surface-variant text-mono-label">—</span>' : '';

    const icon = active ? '▶' : done ? (r?.status === 'ok' ? '✓' : '✗') : '';

    return `
      <div class="border rounded p-3 mb-2 transition-all cursor-pointer ${cls}" id="lc${i}" onclick="jumpToChunk(${i})">
        <div class="flex justify-between items-center mb-1 text-mono-label">
          <span class="${active ? 'text-primary font-bold' : 'text-on-surface-variant'}">${icon} ${i + 1}</span>
          ${badge}
        </div>
        <div class="text-body-sm ${active ? 'text-on-surface font-semibold' : 'text-on-surface-variant'}">${escHtml(c)}</div>
      </div>`;
  }).join('');

  document.getElementById(`lc${S.cur}`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── STAGE TEXT ─────────────────────────────────────── */
function showChunkText(expected, spoken, result) {
  const el = document.getElementById('current-chunk'); // Updated ID to match index.html
  if (!el) return;

  if (!spoken) {
    el.innerHTML = expected.split(/(\s+)/).map(t =>
      /^\s+$/.test(t) ? ' ' : `<span class="px-0.5 rounded text-on-surface-variant opacity-30">${escHtml(t)}</span>`
    ).join('');
    return;
  }

  const spkW = keyWords(spoken);
  el.innerHTML = expected.split(/(\s+)/).map(t => {
    if (/^\s+$/.test(t)) return ' ';
    const clean = t.toLowerCase().replace(/[^a-z0-9']/g, '');
    if (clean.length <= 2 || STOP_WORDS.has(clean))
      return `<span class="text-on-surface font-semibold">${escHtml(t)}</span>`;
    const hit = spkW.some(sw => wordSim(clean, sw) >= (S.confidence || 0.75));
    return `<span class="${hit ? 'text-primary font-bold' : 'text-error line-through decoration-2'}">${escHtml(t)}</span>`;
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
  const fill = document.getElementById('progress-bar');
  const lbl  = document.getElementById('progress-text');
  if (fill) fill.style.width  = pct + '%';
  if (lbl)  lbl.textContent   = (done ? S.chunks.length : S.cur) + ' / ' + S.chunks.length + ' chunks';
}

/* ── PHASE SYSTEM ───────────────────────────────────── */
const PHASE_CONFIG = {
  [PHASE.IDLE]:    { label: 'Idle',                   color: 'var(--on-surface-variant)', status: 'muted',     glow: null,                      tabId: null },
  [PHASE.DELIVER]: { label: '🎧 Listen to earpiece…', color: 'var(--primary)',         status: 'primary',   glow: 'rgba(163,62,0,0.05)',      tabId: 'deliver' },
  [PHASE.LISTEN]:  { label: '🎤 Speak to audience!',  color: 'var(--secondary)',       status: 'secondary', glow: 'rgba(93,95,90,0.05)',      tabId: 'listen' },
  [PHASE.COMPARE]: { label: '⚖️ Evaluating via GPU…', color: 'var(--primary-container)', status: 'accent',    glow: 'rgba(255,102,0,0.05)',     tabId: 'compare' },
  [PHASE.CORRECT]: { label: '🔄 Correcting via GPU…', color: 'var(--error)',           status: 'danger',    glow: 'rgba(186,26,26,0.05)',     tabId: 'correct' },
};

function setPhase(ph) {
  S.phase = ph;
  const cfg = PHASE_CONFIG[ph] || PHASE_CONFIG[PHASE.IDLE];

  // Ambient glow
  const glow = document.getElementById('stage-ambient');
  if (glow) {
    let glowColor = "transparent";
    if (ph === PHASE.DELIVER) glowColor = "rgba(163,62,0,0.05)";
    else if (ph === PHASE.LISTEN) glowColor = "rgba(93,95,90,0.05)";
    else if (ph === PHASE.COMPARE) glowColor = "rgba(255,102,0,0.05)";
    else if (ph === PHASE.CORRECT) glowColor = "rgba(186,26,26,0.05)";
    
    glow.style.background = glowColor !== "transparent"
      ? `radial-gradient(ellipse 60% 50% at 50% 50%, ${glowColor} 0%, transparent 70%)`
      : '';
  }

  // Status dot + text
  const dot = document.getElementById('status-dot');
  const txt = document.getElementById('status-text');
  if (dot) dot.className = `w-2 h-2 rounded-full ${ph === PHASE.IDLE ? 'bg-outline' : 'bg-primary-container animate-pulse'}`;
  if (txt) txt.textContent = `Status: ${cfg.label.replace(/^[^\w]+/, '')}`;

  // Update GPU agent indicator label
  updateAgentIndicator(ph);
  
  // Waveform colours
  if (typeof animateWaveformForPhase === 'function') animateWaveformForPhase(ph);
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
  el.textContent = labels[ph] || 'GPU Accelerator';
}

function setCue(txt, color, active) {
  const label = document.getElementById('cue-label');
  const dot   = document.getElementById('cue-dot');
  if (label) { label.textContent = txt; label.style.color = color || ''; }
  if (dot)   { dot.style.background = color || 'var(--text-muted)'; dot.classList.toggle('pulsing', active); }
}

const STATUS_COLORS = {
  muted:     'var(--on-surface-variant)',
  primary:   'var(--primary)',
  secondary: 'var(--secondary)',
  accent:    'var(--primary-container)',
  danger:    'var(--error)',
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
  const log = document.getElementById('live-transcript');
  if (!log) return;
  const d    = document.createElement('div');
  const time = new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  
  let typeClasses = "";
  if (type === 'ok') typeClasses = "bg-[#E8F5E9] text-[#2E7D32]";
  else if (type === 'warn') typeClasses = "bg-[#FFF8E1] text-[#F57F17]";
  else if (type === 'error' || type === 'miss') typeClasses = "bg-[#FFEBEE] text-[#C62828]";
  else typeClasses = "bg-[#F3E5F5] text-[#7B1FA2]";

  d.className  = `flex items-start gap-3 p-2 border-b border-yc hover:bg-surface-block transition-colors animate-fadeIn`;
  d.innerHTML  = `
    <span class="text-[10px] text-on-surface-variant shrink-0 pt-0.5">${time}</span>
    <span class="px-1.5 py-0.5 rounded text-[9px] uppercase font-bold tracking-wider shrink-0 ${typeClasses}">${icon}</span>
    <span class="text-body-sm text-on-surface break-words">${msg}</span>
  `;
  log.insertBefore(d, log.firstChild);
  while (log.children.length > MAX_LOG) log.removeChild(log.lastChild);
}

function clearLog() {
  const log = document.getElementById('live-transcript');
  if (log) log.innerHTML = '';
}

/* ── METRICS ────────────────────────────────────────── */
function setM(key, val) {
  const el = document.getElementById('m-' + key);
  if (el) el.textContent = val;
}

/* ── BUTTON HELPERS ─────────────────────────────────── */
function setMainBtn(icon) {
  const el = document.getElementById('play-icon');
  if (el) el.textContent = icon;
}
function showEndBtn(show) {
  document.getElementById('btn-end')?.classList.toggle('hidden', !show);
}
function showTimer(show) {
  document.getElementById('header-timer')?.classList.toggle('hidden', !show);
  document.getElementById('footer-timer')?.classList.toggle('hidden', !show);
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
  const gpuSessions = history.filter(s => s.backend?.includes('GPU')).length;

  const el = document.getElementById('stats-container');
  if (!el) return;

  el.innerHTML = `
    <div class="md:col-span-full mb-6">
      <div class="flex justify-between items-end">
        <div>
          <h2 class="text-headline-lg text-on-surface">Session Analytics</h2>
          <p class="text-body-md text-on-surface-variant">${total} sessions recorded on GPU infrastructure.</p>
        </div>
        <button class="text-label-caps font-bold text-primary hover:underline" onclick="if(confirm('Clear all history?')){clearHistory();renderStatsView();}">Clear History</button>
      </div>
    </div>

    <div class="md:col-span-4 bg-surface-block border border-yc rounded p-6 flex flex-col gap-1">
      <span class="text-label-caps text-on-surface-variant">Avg Accuracy</span>
      <span class="text-headline-lg text-primary">${avgAcc}%</span>
    </div>
    <div class="md:col-span-4 bg-surface-block border border-yc rounded p-6 flex flex-col gap-1">
      <span class="text-label-caps text-on-surface-variant">Best Performance</span>
      <span class="text-headline-lg text-on-surface">${bestAcc}%</span>
    </div>
    <div class="md:col-span-4 bg-surface-block border border-yc rounded p-6 flex flex-col gap-1">
      <span class="text-label-caps text-on-surface-variant">GPU Utilized</span>
      <span class="text-headline-lg text-on-surface">${gpuSessions}</span>
    </div>

    <div class="md:col-span-full bg-surface-container-lowest border border-yc rounded-lg overflow-hidden mt-6">
      <table class="w-full text-left text-body-sm">
        <thead class="bg-surface-block border-b border-yc text-label-caps text-on-surface-variant">
          <tr>
            <th class="px-4 py-3">Date</th>
            <th class="px-4 py-3">Chunks</th>
            <th class="px-4 py-3">Accuracy</th>
            <th class="px-4 py-3">WPM</th>
            <th class="px-4 py-3">Mode</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-yc">
          ${history.map(s => `
            <tr class="hover:bg-surface-container-low transition-colors">
              <td class="px-4 py-3 font-medium">${s.date} <span class="text-[10px] text-on-surface-variant ml-2">${s.time}</span></td>
              <td class="px-4 py-3">${s.done}/${s.chunks}</td>
              <td class="px-4 py-3 font-bold ${s.accuracy >= 80 ? 'text-primary' : 'text-error'}">${s.accuracy}%</td>
              <td class="px-4 py-3">${s.wpm || '—'}</td>
              <td class="px-4 py-3 text-on-surface-variant text-[10px] uppercase font-bold">${s.mode || '—'}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      ${total === 0 ? '<div class="p-12 text-center text-on-surface-variant">No session telemetry found.</div>' : ''}
    </div>
  `;
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
