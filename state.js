/* ═══════════════════════════════════════════════════
   RasoSpeak v2 — State Management
   Shared state used by both UI layer and offline fallback.
   ═══════════════════════════════════════════════════ */

const PHASE = Object.freeze({
  IDLE:    'idle',
  DELIVER: 'deliver',
  LISTEN:  'listen',
  COMPARE: 'compare',
  CORRECT: 'correct',
});

/* ── CORE STATE (v1-compatible keys kept for UI layer) ── */
const S = {
  // Script
  chunks:    [],
  cur:       0,
  chunkSize: 8,

  // Session
  running:  false,
  paused:   false,
  phase:    PHASE.IDLE,

  // Offline speech (fallback when AMD backend unreachable)
  rec:        null,
  synth:      window.speechSynthesis,
  voices:     [],
  finalBuf:   '',
  interimBuf: '',

  // Audio
  audioCtx:     null,
  analyser:     null,
  stream:       null,
  rafId:        null,

  // Timers
  silTimer:     null,
  lisTimer:     null,
  timerIv:      null,
  sessionStart: null,

  // Settings
  mode:       'hint',
  strict:     3,
  confidence: 0.75,

  // Session metrics
  totalWords:  0,
  corrections: 0,
  segsDone:    0,
  wpmHist:     [],
  lastWordTime:null,
  accHist:     [],
  wpmAll:      [],
  skipped:     0,

  // Per-chunk results
  segResults: {},

  // Waveform bars (DOM refs)
  waveformBars: [],

  // History (loaded from localStorage)
  sessionHistory: [],

  // AMD backend connection state
  backendMode: 'online',   // 'online' | 'offline'
  agentStatus: {
    transcription: 'unknown',
    scoring:       'unknown',
    coaching:      'unknown',
    segmentation:  'unknown',
    memory:        'unknown',
  },
};

/* ── RESET SESSION METRICS ──────────────────────────── */
function resetSessionMetrics() {
  S.cur          = 0;
  S.running      = false;
  S.paused       = false;
  S.phase        = PHASE.IDLE;
  S.finalBuf     = '';
  S.interimBuf   = '';
  S.sessionStart = null;
  S.totalWords   = 0;
  S.corrections  = 0;
  S.segsDone     = 0;
  S.skipped      = 0;
  S.wpmHist      = [];
  S.wpmAll       = [];
  S.lastWordTime = null;
  S.accHist      = [];
  S.segResults   = {};
}

/* ── HISTORY PERSISTENCE ────────────────────────────── */
function loadHistory() {
  try {
    S.sessionHistory = JSON.parse(localStorage.getItem('rs_history') || '[]');
  } catch (e) {
    S.sessionHistory = [];
  }
}

function clearHistory() {
  try { localStorage.removeItem('rs_history'); } catch (e) {}
  S.sessionHistory = [];
}
