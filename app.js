/* ═══════════════════════════════════════════════════
   RasoSpeak — Frontend App
   WebSocket client connecting to AMD Developer Cloud backend.
   Agents run on MI300X GPU via ROCm + vLLM.
   ═══════════════════════════════════════════════════ */

// ── CONFIG ────────────────────────────────────────────
const CONFIG = {
  // Change this to your AMD Developer Cloud endpoint
  WS_URL:   (location.protocol === 'https:' ? 'wss:' : 'ws:') +
            '//' + (location.hostname === 'localhost'
              ? 'localhost:8000'
              : location.host) + '/ws',
  REST_URL: location.origin + '/segment',
};

// ── STATE ─────────────────────────────────────────────
const APP = {
  ws:           null,
  sessionId:    null,
  mediaRecorder:null,
  audioChunks:  [],
  recording:    false,
  chunkIndex:   0,
  chunks:       [],   // SegmentResult from backend
  running:      false,
  paused:       false,
  mode:         'hint',
  strict:       3,
  chunkSize:    8,
  voices:       [],
  synth:        window.speechSynthesis,
  timerIv:      null,
  sessionStart: null,
  corrections:  0,
  done:         0,
  accSamples:   [],
  wpmSamples:   [],
  waveformBars: [],
  analyser:     null,
  audioCtx:     null,
  stream:       null,
  rafId:        null,
};

const SAMPLE_SCRIPT = `Good morning everyone. Thank you so much for being here today.

I want to talk about something that affects every single presenter in this room. That moment when you forget your next line.

It happens to all of us. Mid-sentence, the words just vanish completely.

Today I am introducing a solution. It is called RasoSpeak. Your invisible AI speech coach.

Here is how it works. RasoSpeak processes your script in advance using AI running on AMD hardware.

Then it plays each sentence quietly through your earpiece. You hear your line. You say it to the audience.

RasoSpeak listens and evaluates your delivery instantly using a large language model. If you miss key words, it corrects you. Silently. Through your ear.

The audience never knows. Think of it as a teleprompter for your ear. Completely invisible.

Thank you very much for your time today. I would love to take your questions now.`;

// ── BOOT ──────────────────────────────────────────────
window.addEventListener('load', () => {
  populateVoices();
  if (speechSynthesis.onvoiceschanged !== undefined)
    speechSynthesis.onvoiceschanged = populateVoices;

  buildWaveform();
  loadHistory();

  const ta = document.getElementById('script-ta');
  if (ta) {
    ta.addEventListener('input', liveWC);
    ta.value = SAMPLE_SCRIPT;
    liveWC();
  }

  switchView('live');
  setPhase(PHASE.IDLE);
  updateProgress();

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
    const map = {
      ' ':           toggleSession,
      'ArrowRight':  nextChunk,
      'ArrowLeft':   prevChunk,
      'r':           repeatChunk,
      'Escape':      () => { if (APP.running) stopSession(); },
    };
    if (map[e.key]) { e.preventDefault(); map[e.key](); }
  });

  logCoach('sys', '🤖', 'RasoSpeak · Agents run on <strong>AMD MI300X via ROCm</strong> · Process a script then press ▶');
});

// ── MODAL ─────────────────────────────────────────────
function closeModal() {
  const el = document.getElementById('modal-overlay');
  if (el) {
    el.style.opacity    = '0';
    el.style.transition = 'opacity 0.3s ease';
    setTimeout(() => el.style.display = 'none', 320);
  }
}

// ── PROCESS SCRIPT (calls SegmentationAgent on AMD) ───
async function processAndGo() {
  const raw = document.getElementById('script-ta')?.value.trim();
  if (!raw) { toast('⚠️ Enter a script first'); return; }

  toast('⏳ Sending to SegmentationAgent on AMD MI300X…');
  logCoach('sys', '✂️', 'Sending script to <strong>SegmentationAgent</strong> (Qwen2.5-3B on AMD ROCm)…');

  try {
    const resp = await fetch(CONFIG.REST_URL, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        script:            raw,
        target_chunk_size: APP.chunkSize,
        style:             'presentation',
      }),
    });

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const result = await resp.json();

    APP.chunks = result.chunks;
    S.chunks   = result.chunks.map(c => c.text);  // compat with v1 UI
    S.segResults = {};
    S.cur = 0;

    switchView('live');
    renderLiveChunkList();
    updateSegDisplay();
    updateProgress();

    const ms = result.processing_ms;
    toast(`✅ ${result.total_chunks} chunks · ~${result.estimated_duration_minutes} min · AMD: ${ms}ms`);
    logCoach('ok', '✅',
      `SegmentationAgent returned <strong>${result.total_chunks} chunks</strong> in <strong>${ms}ms</strong> on AMD MI300X`
    );

  } catch (err) {
    // Fallback to client-side chunking if backend unreachable
    logCoach('warn', '⚠️', `Backend unreachable (${err.message}) — using client-side chunking`);
    buildChunks(raw);
    APP.chunks = S.chunks.map((text, i) => ({
      id: i + 1, text, word_count: text.split(' ').length,
      type: 'statement', emphasis_words: [], suggested_pace: 'normal',
      breathing_pause_after: true,
    }));
    switchView('live');
    renderLiveChunkList();
    updateSegDisplay();
    toast(`✅ ${S.chunks.length} chunks (client-side fallback)`);
  }
}

// ── SESSION MANAGEMENT ────────────────────────────────
function toggleSession() {
  if (!S.chunks.length) { toast('⚠️ Process a script first'); switchView('script'); return; }
  if (!APP.running)      startSession();
  else if (APP.paused)   resumeSession();
  else                   pauseSession();
}

async function startSession() {
  APP.sessionId    = generateUUID();
  APP.running      = true;
  APP.paused       = false;
  APP.sessionStart = Date.now();
  APP.corrections  = 0;
  APP.done         = 0;
  APP.accSamples   = [];
  APP.wpmSamples   = [];
  S.cur            = 0;
  S.segResults     = {};
  resetSessionMetrics();

  // Connect WebSocket to AMD backend
  connectWebSocket();

  // Start mic + audio viz
  await startAudio();

  startTimer();
  renderLiveChunkList();
  updateSegDisplay();
  setMainBtn('pause_circle');
  showEndBtn(true);
  showTimer(true);

  logCoach('sys', '🚀', `Session <code>${APP.sessionId.slice(0, 8)}</code> connecting to AMD Developer Cloud…`);
}

function pauseSession() {
  APP.paused = true;
  APP.synth.cancel();
  stopRecording();
  setPhase(PHASE.IDLE);
  setMainBtn('play_arrow');
  setStatus('muted', 'Paused');
  logCoach('sys', '⏸', 'Paused.');
}

function resumeSession() {
  APP.paused = false;
  setMainBtn('pause_circle');
  logCoach('sys', '▶️', 'Resumed.');
  doDeliver();
}

function stopSession() {
  if (!APP.running) return;

  // Tell backend to end session + generate insights
  if (APP.ws && APP.ws.readyState === WebSocket.OPEN) {
    APP.ws.send(JSON.stringify({ type: 'SESSION_END', data: {} }));
  }

  APP.running = false;
  APP.paused  = false;
  if (APP.ws) { try { APP.ws.close(); } catch (e) {} APP.ws = null; }

  stopRecording();
  APP.synth.cancel();
  stopAudio();
  stopTimer();

  setPhase(PHASE.IDLE);
  setMainBtn('play_arrow');
  showEndBtn(false);
  showTimer(false);
  resetWaveform();

  const avgAcc = APP.accSamples.length
    ? Math.round(APP.accSamples.reduce((a, b) => a + b, 0) / APP.accSamples.length)
    : 0;

  persistSession();
  toast(`⏹ Session ended · ${avgAcc}% avg accuracy`);
  logCoach('sys', '⏹', `Session ended · <strong>${APP.done} chunks</strong> · <strong>${avgAcc}%</strong> avg accuracy`);
}

// ── WEBSOCKET CLIENT ──────────────────────────────────
let _wsReconnectAttempts = 0;
const _maxReconnectAttempts = 5;

function connectWebSocket() {
  const url = `${CONFIG.WS_URL}/${APP.sessionId}`;
  APP.ws = new WebSocket(url);

  APP.ws.onopen = () => {
    _wsReconnectAttempts = 0;
    logCoach('ok', '🔌', `Connected to AMD backend · Session <code>${APP.sessionId.slice(0, 8)}</code>`);
    // Send session config
    APP.ws.send(JSON.stringify({
      type: 'SESSION_START',
      data: {
        config: {
          mode:       APP.mode,
          strict:     APP.strict,
          chunk_size: APP.chunkSize,
          language:   'en',
        }
      }
    }));
  };

  APP.ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      handleWSMessage(msg);
    } catch (e) {
      console.warn('WS parse error:', e);
    }
  };

  APP.ws.onerror = (e) => {
    logCoach('warn', '⚠️', 'WebSocket error');
  };

  APP.ws.onclose = (event) => {
    // Don't reconnect on clean close (code 1000)
    if (event.code === 1000) {
      logCoach('sys', '🔌', 'WebSocket connection closed cleanly.');
      return;
    }
    // Reconnect with exponential backoff
    if (_wsReconnectAttempts < _maxReconnectAttempts && APP.running) {
      const delay = Math.min(1000 * Math.pow(2, _wsReconnectAttempts), 15000);
      _wsReconnectAttempts++;
      logCoach('warn', '🔄', `Reconnecting in ${delay/1000}s... (${_wsReconnectAttempts}/${_maxReconnectAttempts})`);
      setTimeout(() => {
        if (APP.running && !APP.paused) {
          connectWebSocket();
        }
      }, delay);
    } else {
      logCoach('error', '❌', 'Connection lost — please refresh the page.');
      startOfflineSession();
    }
  };
}

function handleWSMessage(msg) {
  const { type, data } = msg;

  switch (type) {
    case 'SESSION_READY':
      logCoach('ok', '✅', `AMD agents ready · ${data.message}`);
      setTimeout(() => doDeliver(), 600);
      break;

    case 'TRANSCRIPT':
      // Real-time transcript from Whisper on AMD MI300X
      updateLiveTx(data.text, '');
      if (data.is_final && data.text.trim().length > 2) {
        logCoach('listen', '🎙',
          `Whisper: "<strong>${data.text.slice(0, 60)}</strong>" (conf: ${Math.round(data.confidence * 100)}%, ${data.processing_ms}ms on AMD)`
        );
      }
      break;

    case 'SCORE':
      // Score from Qwen2.5 ScoringAgent on AMD
      S.segResults[data.chunk_index] = { score: data.overall / 100, status: data.passed ? 'ok' : 'warn' };
      APP.accSamples.push(data.overall);
      showCompareDetail({
        matchPct:      data.overall,
        status:        data.passed ? 'ok' : data.overall > 40 ? 'warn' : 'miss',
        matchedWords:  [],
        missedWords:   data.missing_concepts || [],
      });
      setM('acc', data.overall + '%');
      logCoach(data.passed ? 'ok' : 'warn',
        data.passed ? '✅' : '⚠️',
        `ScoringAgent: <strong>${data.overall}%</strong> overall · ${data.feedback_brief} (${data.processing_ms}ms on AMD)`
      );
      renderLiveChunkList();
      break;

    case 'COACHING':
      // Correction from Qwen2.5 CoachingAgent on AMD
      APP.corrections++;
      setM('corr', APP.corrections);
      logCoach('coach', '🎓',
        `CoachingAgent: <strong>${data.strategy}</strong> · "${data.display_text}" (${data.processing_ms}ms on AMD)`
      );
      // Speak correction through earpiece (TTS still runs in browser)
      if (data.tts_text && data.strategy !== 'replay') {
        speak(data.tts_text, () => {});
      } else if (data.strategy === 'replay' && S.chunks[S.cur]) {
        speak(S.chunks[S.cur], () => {});
      }
      if (data.auto_skip) {
        setTimeout(() => doAdvance(), 2000);
      }
      break;

    case 'ADVANCE':
      APP.done++;
      setM('done', APP.done);
      S.cur = data.next_index;
      updateSegDisplay();
      updateProgress();
      renderLiveChunkList();
      setTimeout(() => doDeliver(), 900);
      break;

    case 'SESSION_SUMMARY':
      handleSessionSummary(data);
      break;

    case 'ERROR':
      logCoach('warn', '❌', `Backend error: ${data.message}`);
      break;
  }
}

// ── COACHING LOOP (frontend side) ─────────────────────
function doDeliver() {
  if (!APP.running || APP.paused || S.cur >= S.chunks.length) return;
  setPhase(PHASE.DELIVER);

  const chunkData = APP.chunks[S.cur] || {};
  const text      = chunkData.text || S.chunks[S.cur] || '';
  const pace      = chunkData.suggested_pace || 'normal';

  showChunkText(text, null, null);
  renderLiveChunkList();
  logCoach('deliver', '🔊', `Chunk ${S.cur + 1}: <strong>"${text}"</strong>`);

  // Speak through earpiece (TTS in browser — earpiece is audio output device)
  speak(text, () => {
    if (APP.running && !APP.paused) setTimeout(() => doListen(), 500);
  }, pace);
}

function doListen() {
  if (!APP.running || APP.paused) return;
  setPhase(PHASE.LISTEN);
  startRecording(); // Start sending audio to backend
  logCoach('listen', '🎤', `Listening — audio streaming to AMD Whisper agent…`);
}

function doAdvance() {
  if (S.cur >= S.chunks.length - 1) {
    setPhase(PHASE.IDLE);
    logCoach('ok', '🎉', '<strong>Presentation complete!</strong> All chunks delivered.');
    toast('🎉 Presentation complete!');
    speak('Presentation complete. Well done!');
    setTimeout(() => stopSession(), 2500);
    return;
  }
  S.cur++;
  updateSegDisplay();
  updateProgress();
  setTimeout(() => { if (APP.running && !APP.paused) doDeliver(); }, 900);
}

// ── AUDIO RECORDING → BACKEND ─────────────────────────
async function startRecording() {
  if (!APP.stream) return;

  const options      = { mimeType: 'audio/webm;codecs=opus' };
  APP.mediaRecorder  = new MediaRecorder(APP.stream, options);
  APP.audioChunks    = [];
  APP.recording      = true;

  APP.mediaRecorder.ondataavailable = async (e) => {
    if (!APP.recording || !APP.ws || e.data.size === 0) return;
    APP.audioChunks.push(e.data);

    // Convert to base64 and send to backend
    const blob   = new Blob(APP.audioChunks, { type: 'audio/webm' });
    const b64    = await blobToBase64(blob);
    const isFinal = false; // We'll finalize on silence

    if (APP.ws.readyState === WebSocket.OPEN) {
      APP.ws.send(JSON.stringify({
        type: 'AUDIO_CHUNK',
        data: {
          chunk_index:   S.cur,
          audio_b64:     b64.split(',')[1],  // strip data URL prefix
          sample_rate:   16000,
          expected_text: S.chunks[S.cur] || '',
          is_final:      isFinal,
        }
      }));
    }
  };

  // Send audio every 1 second
  APP.mediaRecorder.start(1000);

  // Auto-stop after proportional listen window
  const words    = (S.chunks[S.cur] || '').split(/\s+/).length;
  const listenMs = Math.max(6000, words * 1000);
  setTimeout(() => stopRecording(), listenMs);
}

function stopRecording() {
  APP.recording = false;
  if (APP.mediaRecorder && APP.mediaRecorder.state !== 'inactive') {
    APP.mediaRecorder.stop();
  }
}

async function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror   = reject;
    reader.readAsDataURL(blob);
  });
}

// ── OFFLINE FALLBACK (if backend unreachable) ─────────
function startOfflineSession() {
  logCoach('warn', '⚠️', 'Running in <strong>offline mode</strong> (browser-only NLP, no AMD GPU)');
  // Import v1 coach loop
  if (typeof startRec === 'function') startRec();
  setTimeout(() => doDeliver(), 600);
}

// ── SESSION SUMMARY ───────────────────────────────────
function handleSessionSummary(data) {
  const stats    = data.stats || {};
  const insights = data.insights || {};

  logCoach('ok', '📊', `
    Session complete · <strong>${stats.chunks_done || 0} chunks</strong> · 
    <strong>${stats.avg_accuracy || 0}%</strong> accuracy · 
    <strong>${stats.total_corrections || 0}</strong> corrections
  `);

  if (insights.overall_assessment) {
    logCoach('coach', '🎓', `AI Coach says: <em>"${insights.overall_assessment}"</em>`);
  }
  if (insights.focus_words?.length) {
    logCoach('coach', '📌', `Practice these words: <strong>${insights.focus_words.join(', ')}</strong>`);
  }
  toast(`Session complete · ${stats.avg_accuracy || 0}% accuracy`);
}

// ── TTS ───────────────────────────────────────────────
function populateVoices() {
  const all = APP.synth.getVoices();
  APP.voices = all;
  const sel  = document.getElementById('sel-voice');
  if (!sel) return;
  sel.innerHTML = '<option value="">Auto (best English)</option>';
  all.filter(v => v.lang.startsWith('en')).forEach(v => {
    const o = document.createElement('option');
    o.value       = all.indexOf(v);
    o.textContent = v.name.replace(/^(Google|Microsoft)\s+/, '').slice(0, 34);
    sel.appendChild(o);
  });
}

function getVoice() {
  const vi = document.getElementById('sel-voice')?.value;
  if (vi !== '' && vi !== undefined && APP.voices[parseInt(vi)])
    return APP.voices[parseInt(vi)];
  return (
    APP.voices.find(v => v.name.includes('Google') && v.lang === 'en-US') ||
    APP.voices.find(v => v.lang === 'en-US') ||
    APP.voices.find(v => v.lang.startsWith('en')) ||
    null
  );
}

function getSpeed() {
  return parseFloat(document.getElementById('sel-speed')?.value || '0.85');
}

function speak(text, onDone, pace) {
  if (APP.synth.speaking) APP.synth.cancel();
  const u     = new SpeechSynthesisUtterance(text);
  const voice = getVoice();
  if (voice) u.voice = voice;
  u.rate   = pace === 'slow' ? getSpeed() * 0.85
           : pace === 'fast' ? getSpeed() * 1.1
           : getSpeed();
  u.pitch  = 0.96;
  u.volume = 0.92;
  u.lang   = 'en-US';
  const kv = setInterval(() => {
    if (!APP.synth.speaking) clearInterval(kv);
    else if (APP.synth.paused) APP.synth.resume();
  }, 5000);
  u.onend = u.onerror = () => { clearInterval(kv); if (onDone) onDone(); };
  APP.synth.speak(u);
}

// ── AUDIO VIZ ─────────────────────────────────────────
async function startAudio() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    APP.stream   = stream;
    APP.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const src    = APP.audioCtx.createMediaStreamSource(stream);
    const an     = APP.audioCtx.createAnalyser(); an.fftSize = 256;
    src.connect(an); APP.analyser = an;
    driveWaveform();
  } catch (e) {
    console.warn('Mic access:', e.message);
    toast('⚠️ Microphone permission denied');
  }
}

function stopAudio() {
  if (APP.rafId)    { cancelAnimationFrame(APP.rafId); APP.rafId = null; }
  if (APP.stream)   { APP.stream.getTracks().forEach(t => t.stop()); APP.stream = null; }
  if (APP.audioCtx) { try { APP.audioCtx.close(); } catch (e) {} APP.audioCtx = null; }
  APP.analyser = null;
}

function driveWaveform() {
  if (!APP.analyser) return;
  APP.rafId = requestAnimationFrame(driveWaveform);
  const buf = new Uint8Array(APP.analyser.frequencyBinCount);
  APP.analyser.getByteTimeDomainData(buf);
  APP.waveformBars.forEach((bar, i) => {
    const idx = Math.floor(i * (buf.length / APP.waveformBars.length));
    const v   = buf[idx] ?? 128;
    bar.style.height = Math.max(3, ((v - 128) / 128) * 38 + 6) + 'px';
  });
}

// ── TIMER ─────────────────────────────────────────────
function startTimer() {
  clearInterval(APP.timerIv);
  APP.timerIv = setInterval(() => {
    if (!APP.running || APP.paused) return;
    const e = Math.floor((Date.now() - APP.sessionStart) / 1000);
    const m = String(Math.floor(e / 60)).padStart(2, '0');
    const s = String(e % 60).padStart(2, '0');
    const time = `${m}:${s}`;
    // Update both header and footer timers
    document.getElementById('header-timer').textContent = time;
    document.getElementById('footer-timer').textContent = time;
  }, 1000);
}
function stopTimer() { clearInterval(APP.timerIv); }

// ── MANUAL NAV ────────────────────────────────────────
function prevChunk() {
  if (!S.chunks.length || S.cur <= 0) return;
  APP.synth.cancel(); stopRecording();
  S.cur--; updateSegDisplay(); updateProgress(); renderLiveChunkList();
  if (APP.running && !APP.paused) doDeliver();
}
function nextChunk() {
  if (!S.chunks.length || S.cur >= S.chunks.length - 1) return;
  APP.synth.cancel(); stopRecording();
  S.cur++; updateSegDisplay(); updateProgress(); renderLiveChunkList();
  if (APP.running && !APP.paused) doDeliver();
}
function repeatChunk() {
  if (!APP.running || !S.chunks.length) return;
  APP.synth.cancel(); stopRecording();
  logCoach('coach', '🔁', `Manually repeating chunk ${S.cur + 1}.`);
  doDeliver();
}

// ── SETTINGS ──────────────────────────────────────────
function setMode(btn) {
  APP.mode = btn.dataset.mode;
  S.mode   = APP.mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function setStrict(btn) {
  APP.strict = parseInt(btn.dataset.strict);
  S.strict   = APP.strict;
  document.querySelectorAll('.strict-btn').forEach(b => b.classList.toggle('active', b === btn));
}
function setChunk(n) {
  APP.chunkSize = n;
  S.chunkSize   = n;
  document.querySelectorAll('.chunk-btn').forEach(b => b.classList.toggle('active', parseInt(b.dataset.size) === n));
  const raw = document.getElementById('script-ta')?.value.trim();
  if (raw) { buildChunks(raw); renderChunkList(); liveWC(); }
}

// ── PERSISTENCE ───────────────────────────────────────
function persistSession() {
  if (!APP.sessionStart) return;
  const avgAcc = APP.accSamples.length
    ? Math.round(APP.accSamples.reduce((a, b) => a + b, 0) / APP.accSamples.length)
    : 0;
  const entry = {
    id:          Date.now(),
    date:        new Date().toLocaleDateString(),
    time:        new Date().toLocaleTimeString('en', { hour: '2-digit', minute: '2-digit' }),
    duration:    Math.round((Date.now() - APP.sessionStart) / 1000),
    chunks:      S.chunks.length,
    done:        APP.done,
    corrections: APP.corrections,
    accuracy:    avgAcc,
    mode:        APP.mode,
    strict:      APP.strict,
    backend:     'AMD MI300X (ROCm)',
  };
  try {
    const hist = JSON.parse(localStorage.getItem('rs_history') || '[]');
    hist.unshift(entry);
    if (hist.length > 20) hist.length = 20;
    localStorage.setItem('rs_history', JSON.stringify(hist));
    S.sessionHistory = hist;
  } catch (e) {}
}

function loadHistory() {
  try { S.sessionHistory = JSON.parse(localStorage.getItem('rs_history') || '[]'); }
  catch (e) { S.sessionHistory = []; }
}

function clearHistory() {
  try { localStorage.removeItem('rs_history'); } catch (e) {}
  S.sessionHistory = [];
}

// ── SCRIPT STUDIO HELPERS ─────────────────────────────
function processScript() { liveWC(); }

function loadSample() {
  const ta = document.getElementById('script-ta');
  if (ta) { ta.value = SAMPLE_SCRIPT; liveWC(); }
  toast('📝 Sample script loaded');
}

function clearAll() {
  const ta = document.getElementById('script-ta');
  if (ta) ta.value = '';
  S.chunks     = [];
  APP.chunks   = [];
  renderChunkList();
  const wc = document.getElementById('wc');
  if (wc) wc.textContent = '0 words · 0 chunks · ~0 min';
}

// ── UTILS ─────────────────────────────────────────────
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0;
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
  });
}

function updateLiveTx(final, interim) {
  const el = document.getElementById('live-tx');
  if (!el) return;
  const tail = (final || '').trim().split(/\s+/).slice(-40).join(' ');
  el.innerHTML =
    `<span style="color:var(--text-primary)">${tail}</span>` +
    (interim ? `<span style="color:var(--text-muted);font-style:italic"> ${interim}</span>` : '');
  el.scrollTop = el.scrollHeight;
}

// ══════════════════════════════════════════════════════
// AI PARTNER VIEW FUNCTIONS
// ══════════════════════════════════════════════════════

let currentProvider = 'qwen';
let partnerModeActive = false;

function startPartnerMode() {
  partnerModeActive = true;
  const statusEl = document.getElementById('partner-status');
  if (statusEl) {
    statusEl.innerHTML = '<div class="status-dot" style="background:var(--secondary)"></div><span style="font-family:var(--font-mono);font-size:11px">Active</span>';
  }
  toast('🎙️ Partner mode started — say "Hey Raso" to activate');
}

function testWakeWord() {
  toast('🧪 Say "Hey Raso" to test wake word detection');
  // Simulate wake word detection for demo
  setTimeout(() => {
    toast('👂 Wake word "Hey Raso" detected!');
  }, 2000);
}

function selectProvider(provider) {
  currentProvider = provider;
  const providers = {
    'qwen': '💻 Local Qwen via vLLM (AMD MI300X)',
    'openai': '🔵 OpenAI ChatGPT',
    'anthropic': '🟣 Anthropic Claude',
    'gemini': '🟢 Google Gemini'
  };

  document.querySelectorAll('.provider-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.provider === provider);
  });

  const currentEl = document.getElementById('current-provider');
  if (currentEl) {
    currentEl.textContent = `Current: ${providers[provider]}`;
  }

  toast(`🤖 Switched to ${providers[provider]}`);
}

async function askPartner() {
  const input = document.getElementById('partner-input');
  const messagesEl = document.getElementById('partner-messages');
  const message = input?.value.trim();

  if (!message) {
    toast('⚠️ Enter a question first');
    return;
  }

  // Check for provider switch commands in the message
  if (message.toLowerCase().includes('use chatgpt') || message.toLowerCase().includes('switch to chatgpt')) {
    selectProvider('openai');
    input.value = '';
    return;
  }
  if (message.toLowerCase().includes('use qwen') || message.toLowerCase().includes('switch to qwen')) {
    selectProvider('qwen');
    input.value = '';
    return;
  }
  if (message.toLowerCase().includes('use claude') || message.toLowerCase().includes('use anthropic')) {
    selectProvider('anthropic');
    input.value = '';
    return;
  }
  if (message.toLowerCase().includes('use gemini') || message.toLowerCase().includes('switch to gemini')) {
    selectProvider('gemini');
    input.value = '';
    return;
  }

  // Add user message to conversation
  const userMsg = document.createElement('div');
  userMsg.className = 'partner-msg partner-msg-user';
  userMsg.innerHTML = `<span style="color:var(--text-primary);font-size:12px">${escHtml(message)}</span>`;
  messagesEl.appendChild(userMsg);

  // Clear input and show thinking
  input.value = '';
  const thinking = document.createElement('div');
  thinking.className = 'partner-msg partner-msg-ai';
  thinking.innerHTML = '<span style="color:var(--text-muted);font-size:12px">🤔 Thinking...</span>';
  messagesEl.appendChild(thinking);
  messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;

  try {
    const resp = await fetch('/partner/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        provider: currentProvider
      })
    });

    if (resp.ok) {
      const data = await resp.json();
      thinking.innerHTML = `<span style="color:var(--text);font-size:12px;line-height:1.6">${data.answer || data.message || 'No response'}</span>`;
    } else {
      // Fallback response for demo
      thinking.innerHTML = `<span style="color:var(--text);font-size:12px;line-height:1.6">I received your message: "${message}". Connect to AMD backend for full AI responses.</span>`;
    }
  } catch (e) {
    // Demo mode fallback
    thinking.innerHTML = `<span style="color:var(--text);font-size:12px;line-height:1.6">Demo mode: You asked "${message}". Backend connection required for AI responses.</span>`;
  }
  messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;

  input.value = '';
}

async function queryMemory() {
  const input = document.getElementById('memory-query');
  const resultsEl = document.getElementById('memory-results');
  const query = input?.value.trim();

  if (!query) {
    toast('⚠️ Enter a search query');
    return;
  }

  resultsEl.innerHTML = '<span style="color:var(--text-muted);font-size:12px">🔍 Searching memory...</span>';

  try {
    const resp = await fetch(`/partner/query?query=${encodeURIComponent(query)}`);
    if (resp.ok) {
      const data = await resp.json();
      resultsEl.innerHTML = `<span style="color:var(--text);font-size:12px;line-height:1.6">${data.summary || data.message || 'No memories found'}</span>`;
    } else {
      resultsEl.innerHTML = `<span style="color:var(--text);font-size:12px">Demo: Searching for "${query}" in your conversation history...</span>`;
    }
  } catch (e) {
    resultsEl.innerHTML = `<span style="color:var(--text-muted);font-size:12px">No memories found for "${query}"</span>`;
  }
}

function showMemoryStats() {
  toast('📊 Memory stats: Tracking all conversations');
}

async function importTextNote() {
  const input = document.getElementById('import-text');
  const content = input?.value.trim();

  if (!content) {
    toast('⚠️ Enter text to import');
    return;
  }

  try {
    const resp = await fetch('/documents/text', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: content,
        title: 'Imported Note',
        category: 'note'
      })
    });

    if (resp.ok) {
      toast('✅ Note imported to memory');
      input.value = '';
    }
  } catch (e) {
    toast('✅ Note imported (demo mode)');
    input.value = '';
  }
}

async function importUrl() {
  const input = document.getElementById('import-url');
  const url = input?.value.trim();

  if (!url) {
    toast('⚠️ Enter a URL');
    return;
  }

  toast('📄 Fetching URL...');

  try {
    const resp = await fetch(`/documents/url?url=${encodeURIComponent(url)}`);
    if (resp.ok) {
      const data = await resp.json();
      toast(`✅ Imported: ${data.title || 'Document'}`);
      input.value = '';
    }
  } catch (e) {
    toast('✅ URL imported (demo mode)');
    input.value = '';
  }
}

function listDocuments() {
  toast('📋 Documents: Shows all imported documents');
}

async function setReminder() {
  const msgInput = document.getElementById('reminder-msg');
  const timeInput = document.getElementById('reminder-time');
  const message = msgInput?.value.trim();
  const remindAt = timeInput?.value || 'in 1 hour';

  if (!message) {
    toast('⚠️ Enter reminder message');
    return;
  }

  try {
    const resp = await fetch('/partner/reminder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        remind_at: remindAt
      })
    });

    if (resp.ok) {
      toast(`⏰ Reminder set: ${message}`);
      msgInput.value = '';
    }
  } catch (e) {
    toast(`⏰ Reminder set (demo): ${message}`);
    msgInput.value = '';
  }
}

async function sendNotification() {
  const titleInput = document.getElementById('notif-title');
  const msgInput = document.getElementById('notif-msg');
  const title = titleInput?.value.trim();
  const message = msgInput?.value.trim();

  if (!message) {
    toast('⚠️ Enter notification message');
    return;
  }

  try {
    const resp = await fetch('/notifications/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title || 'RasoSpeak',
        message: message,
        priority: 'normal'
      })
    });

    if (resp.ok) {
      toast('📱 Notification sent');
      titleInput.value = '';
      msgInput.value = '';
    }
  } catch (e) {
    toast('📱 Notification sent (demo mode)');
    titleInput.value = '';
    msgInput.value = '';
  }
}

async function webSearch() {
  const input = document.getElementById('web-search-input');
  const resultsEl = document.getElementById('search-results');
  const query = input?.value.trim();

  if (!query) {
    toast('⚠️ Enter search query');
    return;
  }

  resultsEl.innerHTML = '<span style="color:var(--text-muted);font-size:12px">🔍 Searching web...</span>';

  try {
    const resp = await fetch('/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: query,
        num_results: 5,
        include_summary: true
      })
    });

    if (resp.ok) {
      const data = await resp.json();
      resultsEl.innerHTML = `<span style="color:var(--text);font-size:12px;line-height:1.6">${data.summary || 'No results found'}</span>`;
    } else {
      resultsEl.innerHTML = `<span style="color:var(--text-muted);font-size:12px">Demo: Search results for "${query}" would appear here</span>`;
    }
  } catch (e) {
    resultsEl.innerHTML = `<span style="color:var(--text-muted);font-size:12px">Web search requires backend connection</span>`;
  }

  input.value = '';
}

// Handle Enter key in partner inputs
document.addEventListener('DOMContentLoaded', () => {
  const partnerInput = document.getElementById('partner-input');
  if (partnerInput) {
    partnerInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') askPartner();
    });
  }

  const memoryQuery = document.getElementById('memory-query');
  if (memoryQuery) {
    memoryQuery.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') queryMemory();
    });
  }

  const webSearchInput = document.getElementById('web-search-input');
  if (webSearchInput) {
    webSearchInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') webSearch();
    });
  }
});
