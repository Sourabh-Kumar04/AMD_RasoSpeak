/* ═══════════════════════════════════════════════════
   RasoSpeak — Client-Side NLP (Offline Fallback)
   Used ONLY when the AMD backend is unreachable.
   In online mode, all NLP runs on AMD MI300X via vLLM.
   ═══════════════════════════════════════════════════ */

/* ── STOP WORDS ─────────────────────────────────────── */
const STOP_WORDS = new Set([
  'the','a','an','and','or','but','in','on','at','to','for','of','with',
  'by','is','are','was','were','be','been','have','has','had','do','does',
  'did','will','would','could','should','may','might','this','that','these',
  'those','it','its','we','our','you','your','they','their','he','his','she',
  'her','me','my','us','i','not','no','so','too','very','also','just','what',
  'how','when','where','who','can','all','more','into','from','than','then',
  'about','up','out','if','as','am','now','any','one','two','some','each',
  'get','got','let','put','see','say','said','go','went','come','came',
]);

/* ── SMART CHUNK BUILDER ────────────────────────────── */
function buildChunks(text) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (!normalized) { S.chunks = []; S.segResults = {}; return []; }

  const words  = normalized.split(' ');
  const target = S.chunkSize;
  const chunks = [];
  let i = 0;

  while (i < words.length) {
    let end = Math.min(i + target, words.length);

    // Try to extend/contract to a sentence boundary within ±4 words
    if (end < words.length) {
      const lo = Math.max(i + 2, end - 4);
      const hi = Math.min(end + 4, words.length);
      for (let j = lo; j < hi; j++) {
        if (/[.!?]["']?$/.test(words[j - 1])) { end = j; break; }
      }
    }

    // Absorb tiny orphan chunks (< 3 words)
    if (words.length - end < 3 && end < words.length && chunks.length) {
      chunks[chunks.length - 1] += ' ' + words.slice(end).join(' ');
      break;
    }

    const chunk = words.slice(i, end).join(' ').trim();
    if (chunk) chunks.push(chunk);
    i = end;
  }

  S.chunks     = chunks;
  S.segResults = {};
  return chunks;
}

/* ── KEYWORD EXTRACTOR ──────────────────────────────── */
function keyWords(text) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s']/g, '')
    .split(/\s+/)
    .filter(w => w.length > 2 && !STOP_WORDS.has(w));
}

/* ── WORD SIMILARITY ────────────────────────────────── */
function wordSim(a, b) {
  if (a === b)                             return 1.0;
  if (a.length < 2 || b.length < 2)       return 0;
  if (a.startsWith(b) || b.startsWith(a)) return 0.9;
  const [long, short] = a.length > b.length ? [a, b] : [b, a];
  if (long.includes(short))               return 0.85;

  const dist    = levenshtein(a, b);
  const maxLen  = Math.max(a.length, b.length);
  return Math.max(0, 1 - dist / maxLen) * 0.9;
}

function levenshtein(a, b) {
  if (Math.abs(a.length - b.length) > 5) return 99;
  const m = a.length, n = b.length;
  const dp = Array.from({ length: m + 1 }, (_, i) =>
    Array.from({ length: n + 1 }, (_, j) => i === 0 ? j : j === 0 ? i : 0)
  );
  for (let i = 1; i <= m; i++)
    for (let j = 1; j <= n; j++)
      dp[i][j] = a[i-1] === b[j-1]
        ? dp[i-1][j-1]
        : 1 + Math.min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]);
  return dp[m][n];
}

/* ── TEXT COMPARISON (offline fallback) ─────────────── */
function compareTexts(spoken, expected) {
  if (!spoken || spoken.trim().length < 2) {
    return {
      score: 0, status: 'miss', matchPct: 0,
      feedback: 'No speech detected. Did you speak?',
      missedWords: keyWords(expected), matchedWords: [], extraWords: [],
    };
  }

  const expW = keyWords(expected);
  const spkW = keyWords(spoken);

  if (!expW.length) {
    return { score: 1, status: 'ok', matchPct: 100, feedback: 'OK.',
      missedWords: [], matchedWords: [], extraWords: [] };
  }

  let matched = 0;
  const matchedWords = [], missedWords = [];
  expW.forEach(ew => {
    const hit = spkW.some(sw => wordSim(ew, sw) >= (S.confidence || 0.75));
    if (hit) { matched++; matchedWords.push(ew); }
    else       { missedWords.push(ew); }
  });

  const extraWords   = spkW.filter(sw => !expW.some(ew => wordSim(ew, sw) >= 0.75));
  const leniency     = (4 - S.strict) * 0.06;
  const score        = Math.min(1, Math.max(0, matched / expW.length + leniency));
  const matchPct     = Math.round(score * 100);
  const threshold    = getThreshold();

  let feedback = '';
  if (score >= 0.9)       feedback = 'Excellent match!';
  else if (score >= 0.75) feedback = `Good. Missed: ${missedWords.slice(0, 3).join(', ')}.`;
  else if (score >= 0.5)  feedback = `Partial. Missing: ${missedWords.slice(0, 4).join(', ')}.`;
  else                    feedback = `Low match. Expected: ${missedWords.slice(0, 4).join(', ')}.`;

  const status = score >= threshold ? 'ok' : score >= threshold * 0.6 ? 'warn' : 'miss';
  return { score, status, matchPct, feedback, missedWords, matchedWords, extraWords };
}

/* ── COVERAGE ───────────────────────────────────────── */
function coverage(spoken, expected) {
  const spkW = keyWords(spoken), expW = keyWords(expected);
  if (!expW.length) return 1;
  return expW.filter(ew => spkW.some(sw => wordSim(ew, sw) >= 0.75)).length / expW.length;
}

/* ── THRESHOLD ──────────────────────────────────────── */
// lenient(2)=0.40 | normal(3)=0.52 | strict(4)=0.64
function getThreshold() {
  return 0.28 + (S.strict - 2) * 0.12;
}

/* ── LIVE WORD COUNT ────────────────────────────────── */
function liveWC() {
  const t   = document.getElementById('script-ta')?.value.trim() || '';
  const wc  = t ? t.split(/\s+/).length : 0;
  buildChunks(t);
  const est = wc > 0 ? Math.max(1, Math.round(wc / 130)) : 0;
  const el  = document.getElementById('wc');
  if (el) el.textContent = `${wc.toLocaleString()} words · ${S.chunks.length} chunks · ~${est} min`;
  renderChunkList();
}
