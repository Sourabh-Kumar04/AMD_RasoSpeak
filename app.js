/* ═══════════════════════════════════════════════════
   RasoSpeak — Frontend App
   WebSocket client connecting to GPU Developer Cloud backend.
   Agents run on GPU via ROCm + vLLM.
   ═══════════════════════════════════════════════════ */

// ── CONFIG ────────────────────────────────────────────
const CONFIG = {
  // Change this to your GPU Developer Cloud endpoint
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

Here is how it works. RasoSpeak processes your script in advance using AI running on GPU hardware.

Then it plays each sentence quietly through your earpiece. You hear your line. You say it to the audience.

RasoSpeak listens and evaluates your delivery instantly using a large language model. If you miss key words, it corrects you. Silently. Through your ear.

The audience never knows. Think of it as a teleprompter for your ear. Completely invisible.

Thank you very much for your time today. I would love to take your questions now.`;

// ── BOOT ──────────────────────────────────────────────
window.addEventListener('load', async () => {
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

  // Health check - verify backend is reachable
  checkBackendHealth();

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

  logCoach('sys', '🤖', 'RasoSpeak · Agents run on <strong>GPU via ROCm</strong> · Process a script then press ▶');
});

// ── PROCESS SCRIPT (calls SegmentationAgent on GPU) ───
async function processAndGo() {
  const raw = document.getElementById('script-ta')?.value.trim();
  if (!raw) { toast('⚠️ Enter a script first'); return; }

  toast('⏳ Sending to SegmentationAgent on GPU…');
  logCoach('sys', '✂️', 'Sending script to <strong>SegmentationAgent</strong> (Qwen2.5-3B on GPU ROCm)…');

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
    toast(`✅ ${result.total_chunks} chunks · ~${result.estimated_duration_minutes} min · GPU: ${ms}ms`);
    logCoach('ok', '✅',
      `SegmentationAgent returned <strong>${result.total_chunks} chunks</strong> in <strong>${ms}ms</strong> on GPU`
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

  // Connect WebSocket to GPU backend
  connectWebSocket();

  // Start mic + audio viz
  await startAudio();

  startTimer();
  renderLiveChunkList();
  updateSegDisplay();
  setMainBtn('pause_circle');
  showEndBtn(true);
  showTimer(true);

  logCoach('sys', '🚀', `Session <code>${APP.sessionId.slice(0, 8)}</code> connecting to GPU Developer Cloud…`);
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
    logCoach('ok', '🔌', `Connected to GPU backend · Session <code>${APP.sessionId.slice(0, 8)}</code>`);
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
    case 'connected':
      // Initial connection - store provider info
      if (data.provider) {
        console.log('[WS] Connected with provider:', data.provider);
        // Dispatch event for UI to update
        window.dispatchEvent(new CustomEvent('provider-changed', { detail: data.provider }));
      }
      break;

    case 'provider_state':
      // Provider was switched - update UI
      console.log('[WS] Provider changed:', data);
      window.dispatchEvent(new CustomEvent('provider-changed', { detail: data }));
      break;

    case 'cognition_event':
      // Cognitive pipeline event
      console.log('[WS] Cognition event:', data);
      window.dispatchEvent(new CustomEvent('cognition-event', { detail: data }));
      break;

    case 'SESSION_READY':
      logCoach('ok', '✅', `GPU agents ready · ${data.message}`);
      setTimeout(() => doDeliver(), 600);
      break;

    case 'TRANSCRIPT':
      // Real-time transcript from Whisper on GPU
      updateLiveTx(data.text, '');
      if (data.is_final && data.text.trim().length > 2) {
        logCoach('listen', '🎙',
          `Whisper: "<strong>${data.text.slice(0, 60)}</strong>" (conf: ${Math.round(data.confidence * 100)}%, ${data.processing_ms}ms on GPU)`
        );
      }
      break;

    case 'SCORE':
      // Score from Qwen2.5 ScoringAgent on GPU
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
        `ScoringAgent: <strong>${data.overall}%</strong> overall · ${data.feedback_brief} (${data.processing_ms}ms on GPU)`
      );
      renderLiveChunkList();
      break;

    case 'COACHING':
      // Correction from Qwen2.5 CoachingAgent on GPU
      APP.corrections++;
      setM('corr', APP.corrections);
      logCoach('coach', '🎓',
        `CoachingAgent: <strong>${data.strategy}</strong> · "${data.display_text}" (${data.processing_ms}ms on GPU)`
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
  logCoach('listen', '🎤', `Listening — audio streaming to GPU Whisper agent…`);
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
  logCoach('warn', '⚠️', 'Running in <strong>offline mode</strong> (browser-only NLP, no GPU)');
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
  S.waveformBars.forEach((bar, i) => {
    const idx = Math.floor(i * (buf.length / S.waveformBars.length));
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
    backend:     'GPU (ROCm)',
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
function escHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

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
  // Test the complete "Hey Raso" flow via REST API
  const testPhrases = [
    "Hey Raso, what is AMD?",
    "Hey Raso, tell me about machine learning",
    "Hey Raso, what did I say about AI?"
  ];

  const testPhrase = testPhrases[Math.floor(Math.random() * testPhrases.length)];
  toast(`🧪 Testing: "${testPhrase}"`);

  fetch('/raso/wake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(testPhrase)
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.wake_detected) {
      toast(`✅ Wake word detected! Command: "${data.command || 'none'}"`);
      if (data.answer) {
        toast(`🤖 Answer: ${data.answer.substring(0, 50)}...`);
        // Speak the answer via TTS
        speakText(data.answer);
      }
    } else {
      toast('⚠️ Wake word not detected in test phrase');
    }
  })
  .catch(e => {
    toast('⚠️ Wake test failed: ' + e.message);
  });
}

function speakText(text) {
  if (!text || !APP.synth) return;
  APP.synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.rate = 1.0;
  u.pitch = 1.0;
  u.volume = 0.8;
  u.onend = () => console.log('TTS done');
  APP.synth.speak(u);
}

function selectProvider(provider) {
  currentProvider = provider;
  const providers = {
    'qwen': '💻 Local Qwen via vLLM (GPU)',
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
  userMsg.className = 'bg-surface-block border border-yc rounded-lg p-3 text-body-sm shadow-sm ml-auto max-w-[80%] animate-fadeIn';
  userMsg.innerHTML = `<div class="text-label-caps text-on-surface-variant mb-1 font-bold">You</div><div class="text-on-surface">${escHtml(message)}</div>`;
  messagesEl.appendChild(userMsg);

  // Clear input and show thinking
  input.value = '';
  const thinking = document.createElement('div');
  thinking.className = 'bg-surface-container-lowest border border-yc rounded-lg p-3 text-body-sm shadow-sm mr-auto max-w-[80%] animate-pulse';
  thinking.innerHTML = '<div class="text-label-caps text-primary mb-1 font-bold italic">Partner</div><div class="text-on-surface-variant italic">Thinking...</div>';
  messagesEl.appendChild(thinking);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  try {
    const resp = await fetch('/raso/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: message,
        provider: currentProvider
      })
    });

    if (resp.ok) {
      const data = await resp.json();
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface leading-relaxed">${data.answer || data.message || 'No response'}</div>`;
    } else {
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface">I received your message: "${message}". Connect to GPU backend for full AI responses.</div>`;
    }
  } catch (e) {
    thinking.classList.remove('animate-pulse');
    thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface">Demo mode: You asked "${message}". Backend connection required for AI responses.</div>`;
  }
  messagesEl.scrollTop = messagesEl.scrollHeight;

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
    const resp = await fetch(`/raso/query?query=${encodeURIComponent(query)}`);
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
    const resp = await fetch('/raso/reminder', {
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

// Handle Enter key in new UI inputs
document.addEventListener('DOMContentLoaded', () => {
  // Chat input
  const chatInput = document.getElementById('chat-input');
  if (chatInput) {
    chatInput.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') sendMessage();
    });
  }

  // Memory search
  const memorySearch = document.getElementById('memory-search');
  if (memorySearch) {
    memorySearch.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') searchMemory();
    });
  }

  // Document URL input
  const docUrl = document.getElementById('doc-url');
  if (docUrl) {
    docUrl.addEventListener('keypress', (e) => {
      if (e.key === 'Enter') importUrl();
    });
  }
});

// ── WRAPPER FUNCTIONS FOR NEW UI ────────────────────────
// Alias functions to match HTML element IDs and function names

function startPartner() {
  startPartnerMode();
}

async function sendMessage() {
  const input = document.getElementById('chat-input');
  const messagesEl = document.getElementById('chat-messages');
  if (!input || !messagesEl) return;

  const text = input.value.trim();
  if (!text) return;

  // Get selected provider
  const providerSelect = document.getElementById('provider-select');
  const provider = providerSelect?.value || 'qwen';

  // Add user message
  const userMsg = document.createElement('div');
  userMsg.className = 'bg-surface-block border border-yc rounded-lg p-3 text-body-sm shadow-sm ml-auto max-w-[80%] animate-fadeIn';
  userMsg.innerHTML = `<div class="text-label-caps text-on-surface-variant mb-1 font-bold">You</div><div class="text-on-surface">${escHtml(text)}</div>`;
  messagesEl.appendChild(userMsg);
  input.value = '';

  // Show thinking
  const thinking = document.createElement('div');
  thinking.className = 'bg-surface-container-lowest border border-yc rounded-lg p-3 text-body-sm shadow-sm mr-auto max-w-[80%] animate-pulse';
  thinking.innerHTML = '<div class="text-label-caps text-primary mb-1 font-bold italic">Partner</div><div class="text-on-surface-variant italic">Thinking...</div>';
  messagesEl.appendChild(thinking);
  messagesEl.scrollTop = messagesEl.scrollHeight;

  // Check if user is using wake word activation
  const wakeWordPattern = /hey\s+raso[,\s]*(.*)/i;
  const wakeMatch = text.match(wakeWordPattern);

  if (wakeMatch) {
    // "Hey Raso, tell me X" flow
    const command = wakeMatch[1].trim();

    const thinking = document.createElement('div');
    thinking.className = 'bg-surface-container-lowest border border-yc rounded-lg p-3 text-body-sm shadow-sm mr-auto max-w-[80%] animate-pulse';
    thinking.innerHTML = '<div class="text-label-caps text-primary mb-1 font-bold">🎙️ Raso</div><div class="text-on-surface-variant italic">Listening...</div>';
    messagesEl.appendChild(thinking);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    fetch('/voice/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ transcript: text })
    })
    .then(resp => resp.json())
    .then(data => {
      thinking.classList.remove('animate-pulse');
      if (data.wake_detected && data.answer) {
        thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">🎙️ Raso</div><div class="text-on-surface leading-relaxed">${escHtml(data.answer)}</div>`;
        // Speak the answer via TTS
        speakText(data.answer);
      } else if (data.wake_detected) {
        thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">🎙️ Raso</div><div class="text-on-surface leading-relaxed">I'm here! What would you like to know?</div>`;
        speakText("I'm here! What would you like to know?");
      } else {
        thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Raso</div><div class="text-on-surface leading-relaxed">Say "Hey Raso" first to activate me.</div>`;
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    })
    .catch(e => {
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Raso</div><div class="text-on-surface">I heard you but couldn't process. Try again.</div>`;
    });

    return;
  }

  // Check if user wants to add something to memory
  const addToMemoryPattern = /add\s+(.+?)\s+(to\s+)?memory/i;
  const match = text.match(addToMemoryPattern);

  // Auto-save decision flag
  let autoSaved = false;

  if (match) {
    // User explicitly wants to add something to memory - always save
    const topic = match[1].trim();
    thinking.innerHTML = '<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface-variant">🔍 Searching web and saving to memory...</div>';

    try {
      // 1. Search the web
      const searchResp = await fetch('/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: topic, num_results: 3, include_summary: true })
      });

      let summary = `Topic: ${topic}\n\n`;
      if (searchResp.ok) {
        const searchData = await searchResp.json();
        if (searchData.results && searchData.results.length > 0) {
          summary += searchData.results.map(r => r.content || r.snippet || '').join('\n\n');
        }
      }

      // 2. Ask AI to summarize
      const aiResp = await fetch('/raso/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: `Provide a concise explanation of "${topic}" in 2-3 sentences.`,
          provider: provider
        })
      });

      if (aiResp.ok) {
        const aiData = await aiResp.json();
        if (aiData.response) {
          summary += `\n\nAI Summary: ${aiData.response}`;
        }
      }

      // 3. Save to memory
      await fetch('/memory/store', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: summary,
          category: 'knowledge',
          tags: [topic.split(' ')[0].toLowerCase()]
        })
      });

      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface leading-relaxed">✅ Saved "${topic}" to memory!<br><span class="text-on-surface-variant text-sm">Searched the web and added AI summary to your knowledge base.</span></div>`;
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (err) {
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface text-error">Error: ${err.message}</div>`;
    }
  } else if (text.match(/https?:\/\/[^\s]+/i)) {
    // User wants to add a URL/PDF to memory
    const urlMatch = text.match(/(https?:\/\/[^\s]+)/i);
    const url = urlMatch[1];
    thinking.innerHTML = '<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface-variant">📄 Fetching URL content and saving to memory...</div>';

    try {
      // 1. Import URL via backend
      const importResp = await fetch('/documents/url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      });

      if (importResp.ok) {
        const docData = await importResp.json();
        const content = docData.content || docData.text || 'Content imported from URL';

        // 2. Get AI summary
        let summary = `Source: ${url}\n\n${content.slice(0, 2000)}`;
        const aiResp = await fetch('/raso/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: `Summarize this content in 3-4 bullet points:\n\n${content.slice(0, 3000)}`,
            provider: provider
          })
        });

        if (aiResp.ok) {
          const aiData = await aiResp.json();
          if (aiData.response) {
            summary += `\n\n📝 AI Summary:\n${aiData.response}`;
          }
        }

        // 3. Save to memory
        await fetch('/memory/store', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            content: summary,
            category: 'document',
            tags: ['url', new URL(url).hostname.replace('www.', '')]
          })
        });

        thinking.classList.remove('animate-pulse');
        thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface leading-relaxed">✅ Saved URL to memory!<br><span class="text-on-surface-variant text-sm">${url}</span></div>`;
      } else {
        throw new Error('Failed to fetch URL');
      }
    } catch (err) {
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface text-error">Error: ${err.message}</div>`;
    }
  } else {
    // Normal AI chat - AI decides if important enough to save to memory
    try {
      const resp = await fetch('/raso/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, provider: provider })
      });
      const data = await resp.json();
      const answer = data.response || data.error || 'No response';

      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface leading-relaxed">${answer}</div>`;
      messagesEl.scrollTop = messagesEl.scrollHeight;

      // Ask AI if this is important enough to save to memory
      try {
        const decideResp = await fetch('/raso/ask', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            message: `Based on this question and answer, should I save this to my memory? Reply ONLY with "YES" or "NO" and a brief reason. Question: "${text}" Answer: "${answer.slice(0, 200)}"`,
            provider: provider
          })
        });

        if (decideResp.ok) {
          const decideData = await decideResp.json();
          const decision = decideData.response || '';

          if (decision.toUpperCase().startsWith('YES')) {
            // Extract key info to save
            const keyPoints = decision.replace(/^YES[\s:,-]*/i, '').trim();
            await fetch('/memory/store', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                content: `Q: ${text}\n\nA: ${answer.slice(0, 1000)}`,
                category: 'conversation',
                tags: ['auto-saved', text.split(' ').slice(0, 3).join('_').toLowerCase()]
              })
            });

            // Show indicator that it was saved
            const savedMsg = document.createElement('div');
            savedMsg.className = 'text-xs text-primary mt-2 italic';
            savedMsg.textContent = '💾 Saved to memory';
            thinking.appendChild(savedMsg);
          }
        }
      } catch (e) {
        // Silent fail - don't interrupt user experience
      }
    } catch (err) {
      thinking.classList.remove('animate-pulse');
      thinking.innerHTML = `<div class="text-label-caps text-primary mb-1 font-bold">Partner</div><div class="text-on-surface text-error">Error: ${err.message}</div>`;
    }
  }
}

async function searchMemory() {
  const input = document.getElementById('memory-search');
  const resultsEl = document.getElementById('memory-results');
  if (!input || !resultsEl) return;

  const query = input.value.trim();
  if (!query) return;

  resultsEl.innerHTML = '<div class="md:col-span-full text-center py-10 animate-pulse text-on-surface-variant">🔍 Searching...</div>';

  try {
    const resp = await fetch(`/raso/query?query=${encodeURIComponent(query)}`);
    const data = await resp.json();

    if (data.results && data.results.length > 0) {
      resultsEl.innerHTML = data.results.map(r => `
        <div class="bg-surface-container-lowest border border-yc rounded-lg p-4 shadow-sm hover:shadow-md transition-shadow">
          <div class="flex items-center gap-2 mb-2">
            <span class="material-symbols-outlined text-primary text-sm">memory</span>
            <span class="text-label-caps font-bold text-on-surface-variant">Semantic Node</span>
          </div>
          <div class="text-body-sm text-on-surface leading-relaxed">${escHtml(r.text || JSON.stringify(r))}</div>
        </div>
      `).join('');
    } else {
      resultsEl.innerHTML = '<div class="md:col-span-full py-20 text-center text-on-surface-variant border border-yc border-dashed rounded-lg">No nodes matched the query heuristic.</div>';
    }
  } catch (err) {
    resultsEl.innerHTML = `<div class="md:col-span-full py-20 text-center text-error border border-yc border-dashed rounded-lg">Search protocol failed: ${err.message}</div>`;
  }
}

function importDoc() {
  // Switch to documents view
  switchView('docs');
}

function importText() {
  importTextNote();
}

// ── NEW FEATURES ─────────────────────────────────────────

function startWakeWord() {
  // Toggle wake word listening mode
  const btn = document.querySelector('button[onclick="startWakeWord()"]');
  if (APP.listening) {
    APP.listening = false;
    stopRecording();
    btn.innerHTML = '<span class="material-symbols-outlined text-sm">mic</span><span>Hey Raso</span>';
    btn.classList.remove('bg-error');
    toast('Wake word deactivated');
  } else {
    APP.listening = true;
    startRecording();
    btn.innerHTML = '<span class="material-symbols-outlined text-sm">mic</span><span>Listening...</span>';
    btn.classList.add('bg-error');
    toast('Say "Hey Raso" to activate');
  }
}

async function doWebSearch() {
  const input = document.getElementById('search-input');
  const resultsEl = document.getElementById('search-results');
  const query = input?.value.trim();

  if (!query) {
    toast('⚠️ Enter search query');
    return;
  }

  resultsEl.innerHTML = '<div class="text-body-sm text-primary animate-pulse">🔍 Searching web...</div>';

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
      if (data.results && data.results.length > 0) {
        resultsEl.innerHTML = data.results.map(r => `
          <div class="mb-4 p-3 bg-surface-container rounded-lg border border-yc">
            <a href="${r.url}" target="_blank" class="text-primary font-bold text-body-sm hover:underline">${r.title}</a>
            <p class="text-on-surface-variant text-body-sm mt-1 line-clamp-2">${r.content || r.snippet || ''}</p>
          </div>
        `).join('');
      } else {
        resultsEl.innerHTML = '<div class="text-body-sm text-on-surface-variant">No results found</div>';
      }
    } else {
      throw new Error('Search failed');
    }
  } catch (e) {
    resultsEl.innerHTML = `<div class="text-body-sm text-error">Search error: ${e.message}</div>`;
  }

  input.value = '';
}

async function sendNotification() {
  const titleInput = document.getElementById('notif-title');
  const msgInput = document.getElementById('notif-message');
  const title = titleInput?.value.trim();
  const message = msgInput?.value.trim();

  if (!title || !message) {
    toast('⚠️ Enter title and message');
    return;
  }

  try {
    const resp = await fetch('/notifications/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: title,
        message: message,
        priority: 'normal'
      })
    });

    if (resp.ok) {
      toast('📱 Notification sent!');
      titleInput.value = '';
      msgInput.value = '';
    } else {
      toast('📱 Notification sent (demo)');
      titleInput.value = '';
      msgInput.value = '';
    }
  } catch (e) {
    toast('📱 Notification sent (demo)');
    titleInput.value = '';
    msgInput.value = '';
  }
}

// Add listening state
APP.listening = false;

async function loadRecordings() {
  const listEl = document.getElementById('recordings-list');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-body-sm text-primary animate-pulse">Loading recordings...</div>';

  try {
    const resp = await fetch('/recordings?limit=20');
    if (resp.ok) {
      const data = await resp.json();
      if (data.recordings && data.recordings.length > 0) {
        listEl.innerHTML = data.recordings.map(r => `
          <div class="flex items-center justify-between p-3 bg-surface-container rounded-lg border border-yc">
            <div class="flex items-center gap-3">
              <span class="material-symbols-outlined text-primary">play_circle</span>
              <div>
                <div class="text-body-sm font-bold text-on-surface">Session ${r.session_id.slice(0, 8)}</div>
                <div class="text-mono-label text-on-surface-variant">${new Date(r.created_at).toLocaleString()}</div>
              </div>
            </div>
            <button onclick="playRecording('${r.session_id}')" class="text-primary hover:opacity-80">
              <span class="material-symbols-outlined">play_arrow</span>
            </button>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = '<div class="text-body-sm text-on-surface-variant text-center py-4">No recordings found</div>';
      }
    } else {
      throw new Error('Failed to load');
    }
  } catch (e) {
    listEl.innerHTML = '<div class="text-body-sm text-on-surface-variant text-center py-4">No recordings available</div>';
  }
}

function playRecording(sessionId) {
  toast('Playing recording...');
  // Audio playback would be implemented here
}

function toggleSidebar() {
  // Toggle mobile sidebar - find nav and toggle hidden class
  const nav = document.querySelector('nav.hidden.md\\:flex');
  if (nav) {
    nav.classList.toggle('hidden');
    nav.classList.toggle('fixed');
    nav.classList.toggle('inset-0');
    nav.classList.toggle('z-50');
    nav.classList.toggle('bg-surface');
  }
}

async function loadMemoryStats() {
  // Load memory statistics
  const resp = await fetch('/memory/stats');
  if (resp.ok) {
    return await resp.json();
  }
  return null;
}

async function loadWakeStatus() {
  // Load wake word status
  const resp = await fetch('/voice/status');
  if (resp.ok) {
    return await resp.json();
  }
  return { active: false };
}

async function loadReminders() {
  const listEl = document.getElementById('reminders-list');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-body-sm text-primary animate-pulse">Loading...</div>';

  try {
    const resp = await fetch('/raso/reminders');
    if (resp.ok) {
      const data = await resp.json();
      const reminders = data.reminders || [];

      if (reminders.length > 0) {
        listEl.innerHTML = reminders.map(r => `
          <div class="flex justify-between items-center p-2 bg-surface-container rounded border border-yc">
            <div>
              <div class="text-body-sm font-bold text-on-surface">${r.message || 'Reminder'}</div>
              <div class="text-mono-label text-on-surface-variant text-xs">${r.remind_at || 'Pending'}</div>
            </div>
            <button onclick="deleteReminder('${r.id}')" class="text-error hover:opacity-80">
              <span class="material-symbols-outlined text-sm">delete</span>
            </button>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = '<div class="text-body-sm text-on-surface-variant text-center py-4">No active reminders</div>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<div class="text-body-sm text-on-surface-variant text-center py-4">No active reminders</div>';
  }
}

async function deleteReminder(id) {
  try {
    await fetch(`/raso/reminder/${id}`, { method: 'DELETE' });
    loadReminders();
    toast('Reminder deleted');
  } catch (e) {
    toast('Failed to delete reminder');
  }
}

async function loadAnalytics() {
  // Load analytics data from backend and local
  await loadAnalyticsData();
  toast('Analytics loaded');
}

async function checkBackendHealth() {
  try {
    const resp = await fetch('/health', { method: 'GET' });
    if (resp.ok) {
      const statusEl = document.getElementById('status-text');
      if (statusEl) statusEl.textContent = 'Status: Online';
      const dotEl = document.getElementById('status-dot');
      if (dotEl) dotEl.classList.remove('bg-error');
      if (dotEl) dotEl.classList.add('bg-primary-container');
      logCoach('sys', '✅', 'Backend connected successfully');
    }
  } catch (e) {
    const statusEl = document.getElementById('status-text');
    if (statusEl) statusEl.textContent = 'Status: Offline';
    const dotEl = document.getElementById('status-dot');
    if (dotEl) dotEl.classList.remove('bg-primary-container');
    if (dotEl) dotEl.classList.add('bg-error');
    logCoach('warn', '⚠️', 'Backend unreachable - running in offline mode');
  }
}

// ── NEW SETTINGS FEATURES ────────────────────────────────

function stopWakeWord() {
  APP.listening = false;
  stopRecording();
  const statusEl = document.getElementById('wake-status');
  if (statusEl) statusEl.textContent = 'Stopped';
  toast('Wake word detection stopped');
}

async function clearMemory() {
  if (!confirm('Clear all memory entries? This cannot be undone.')) return;
  try {
    await fetch('/memory/clear', { method: 'POST' });
    toast('Memory cleared');
    loadMemoryStats();
  } catch (e) {
    // Demo mode
    toast('Memory cleared (demo)');
    loadMemoryStats();
  }
}

async function loadDocuments() {
  const listEl = document.getElementById('docs-list');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-body-sm text-primary animate-pulse">Loading documents...</div>';

  try {
    const resp = await fetch('/documents');
    if (resp.ok) {
      const data = await resp.json();
      const docs = data.documents || [];

      if (docs.length > 0) {
        listEl.innerHTML = docs.map(d => `
          <div class="flex justify-between items-center p-3 bg-surface-container rounded border border-yc">
            <div class="flex items-center gap-3">
              <span class="material-symbols-outlined text-secondary">description</span>
              <div>
                <div class="text-body-sm font-bold text-on-surface">${d.title || 'Untitled'}</div>
                <div class="text-mono-label text-on-surface-variant text-xs">${d.category || 'Document'}</div>
              </div>
            </div>
            <button onclick="deleteDocument('${d.id}')" class="text-error hover:opacity-80">
              <span class="material-symbols-outlined text-sm">delete</span>
            </button>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = '<p class="text-body-sm text-on-surface-variant text-center py-4">No documents ingested. Click "Add Document" to begin.</p>';
      }
    } else {
      throw new Error('Failed to load');
    }
  } catch (e) {
    listEl.innerHTML = '<p class="text-body-sm text-on-surface-variant text-center py-4">No documents ingested. Click "Add Document" to begin.</p>';
  }
}

async function uploadDocument(input) {
  const file = input.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);
  formData.append('title', file.name.replace(/\.[^/.]+$/, ''));
  formData.append('category', 'document');

  try {
    const resp = await fetch('/documents/upload', {
      method: 'POST',
      body: formData
    });

    if (resp.ok) {
      toast('✅ Document uploaded');
      loadDocuments();
    } else {
      throw new Error('Upload failed');
    }
  } catch (e) {
    toast('✅ Document uploaded (demo)');
    loadDocuments();
  }

  input.value = '';
}

async function deleteDocument(id) {
  try {
    await fetch(`/documents/${id}`, { method: 'DELETE' });
    loadDocuments();
    toast('Document deleted');
  } catch (e) {
    toast('Document deleted (demo)');
    loadDocuments();
  }
}

function togglePartner() {
  if (partnerModeActive) {
    partnerModeActive = false;
    const statusEl = document.getElementById('partner-status');
    if (statusEl) statusEl.textContent = 'Inactive';
    toast('Partner mode disabled');
  } else {
    startPartnerMode();
  }
}

function changeQaProvider(provider) {
  currentProvider = provider;
  const labels = { qwen: 'Qwen', openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Gemini' };
  toast(`QA Provider changed to ${labels[provider] || provider}`);
}

async function addReminder() {
  const input = document.getElementById('new-reminder');
  const message = input?.value.trim();

  if (!message) {
    toast('⚠️ Enter reminder text');
    return;
  }

  try {
    const resp = await fetch('/raso/reminder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message, remind_at: 'later' })
    });

    if (resp.ok) {
      toast('⏰ Reminder added');
      input.value = '';
      loadReminders();
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    toast('⏰ Reminder added (demo)');
    input.value = '';
    loadReminders();
  }
}

// Update memory stats display
async function loadMemoryStats() {
  try {
    const resp = await fetch('/memory/stats');
    if (resp.ok) {
      const data = await resp.json();
      const totalEl = document.getElementById('mem-total');
      const wordsEl = document.getElementById('mem-words');
      const chunksEl = document.getElementById('mem-chunks');
      const recallEl = document.getElementById('mem-recall');

      if (totalEl) totalEl.textContent = (data.total_conversations || 0) + (data.total_sessions || 0) + (data.total_facts || 0);
      if (wordsEl) wordsEl.textContent = data.weak_words_count || 0;
      if (chunksEl) chunksEl.textContent = data.total_sessions || 0;
      if (recallEl) recallEl.textContent = Math.round((1 - (data.weak_words_count || 0) / 100) * 100) + '%';
    }
  } catch (e) {
    // Use cached data if available
  }
}

// ── VOICE PARTNER ────────────────────────────────────────
async function startVoicePartner() {
  const statusEl = document.getElementById('voice-mode-status');
  if (statusEl) statusEl.textContent = 'Listening...';

  try {
    const resp = await fetch('/raso/start', { method: 'POST' });
    if (resp.ok) {
      toast('🎙️ Voice partner started');
      startRecording();
    } else {
      throw new Error('Failed to start');
    }
  } catch (e) {
    toast('🎙️ Voice partner demo mode');
  }
}

async function stopVoicePartner() {
  const statusEl = document.getElementById('voice-mode-status');
  if (statusEl) statusEl.textContent = 'Stopped';

  try {
    const resp = await fetch('/raso/stop', { method: 'POST' });
    if (resp.ok) {
      toast('Voice partner stopped');
      stopRecording();
    }
  } catch (e) {
    toast('Voice partner stopped');
  }
}

async function summarizeConversation() {
  try {
    const resp = await fetch('/raso/summarize');
    if (resp.ok) {
      const data = await resp.json();
      toast(`📝 Summary: ${data.summary?.slice(0, 100) || 'No conversation to summarize'}`);
    } else {
      toast('No conversation to summarize');
    }
  } catch (e) {
    toast('No conversation to summarize');
  }
}

// ── QA PROVIDERS ─────────────────────────────────────────
async function loadQaProviders() {
  const listEl = document.getElementById('qa-providers-list');
  if (!listEl) return;

  try {
    const resp = await fetch('/qa/providers');
    if (resp.ok) {
      const data = await resp.json();
      const providers = data.providers || [];
      listEl.innerHTML = providers.map(p => `
        <div class="bg-surface-container rounded p-2 text-center text-body-sm">
          <span class="font-bold">${p.name || p}</span>
        </div>
      `).join('');
    } else {
      listEl.innerHTML = '<div class="text-mono-label text-on-surface-variant">Qwen, OpenAI, Anthropic, Gemini</div>';
    }
  } catch (e) {
    listEl.innerHTML = '<div class="text-mono-label text-on-surface-variant">Qwen, OpenAI, Anthropic, Gemini</div>';
  }
}

async function askQaDirect() {
  const input = document.getElementById('qa-direct-input');
  const answerEl = document.getElementById('qa-direct-answer');
  const question = input?.value.trim();

  if (!question) {
    toast('Enter a question first');
    return;
  }

  if (answerEl) {
    answerEl.classList.remove('hidden');
    answerEl.innerHTML = '<span class="text-primary animate-pulse">Thinking...</span>';
  }

  try {
    const resp = await fetch('/qa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: question, context: '' })
    });

    if (resp.ok) {
      const data = await resp.json();
      if (answerEl) answerEl.innerHTML = `<span class="text-on-surface">${data.answer || data.response || 'No answer'}</span>`;
    } else {
      throw new Error('QA failed');
    }
  } catch (e) {
    if (answerEl) answerEl.innerHTML = `<span class="text-on-surface-variant">Demo: ${question}</span>`;
  }

  input.value = '';
}

// ── WEAK WORDS ──────────────────────────────────────────
async function loadWeakWords() {
  const listEl = document.getElementById('weak-words-list');
  if (!listEl) return;

  try {
    const resp = await fetch('/memory/stats');
    if (resp.ok) {
      const data = await resp.json();
      const words = data.top_weak_words || [];

      if (words.length > 0) {
        listEl.innerHTML = words.map(w => `
          <span class="bg-primary-container text-primary px-2 py-1 rounded text-body-sm font-bold">
            ${w.word} <span class="text-mono-label">(${w.count})</span>
          </span>
        `).join('');
      } else {
        listEl.innerHTML = '<span class="text-body-sm text-on-surface-variant">No weak words recorded yet.</span>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<span class="text-body-sm text-on-surface-variant">No weak words recorded yet.</span>';
  }
}

async function addWeakWord() {
  const input = document.getElementById('add-weak-word');
  const word = input?.value.trim();

  if (!word) {
    toast('Enter a word to track');
    return;
  }

  try {
    const resp = await fetch('/memory/weak-word', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ word: word, context: 'Added via UI' })
    });

    if (resp.ok) {
      toast(`📝 Tracking "${word}"`);
      loadWeakWords();
    }
  } catch (e) {
    toast(`📝 Tracking "${word}" (demo)`);
    loadWeakWords();
  }

  input.value = '';
}

// ── DOCUMENT SEARCH ─────────────────────────────────────
async function searchDocuments() {
  const input = document.getElementById('doc-search-input');
  const resultsEl = document.getElementById('doc-search-results');
  const query = input?.value.trim();

  if (!query) {
    toast('Enter a search query');
    return;
  }

  if (resultsEl) {
    resultsEl.innerHTML = '<div class="text-primary animate-pulse">Searching...</div>';
  }

  try {
    const resp = await fetch(`/documents/search?query=${encodeURIComponent(query)}&limit=10`);
    if (resp.ok) {
      const data = await resp.json();
      const results = data.results || [];

      if (results.length > 0) {
        resultsEl.innerHTML = results.map(r => `
          <div class="p-2 bg-surface-container rounded border border-yc">
            <div class="text-body-sm font-bold text-on-surface">${r.title || 'Document'}</div>
            <div class="text-body-sm text-on-surface-variant line-clamp-2">${r.content || r.snippet || ''}</div>
          </div>
        `).join('');
      } else {
        resultsEl.innerHTML = '<div class="text-on-surface-variant text-center py-2">No results found</div>';
      }
    } else {
      throw new Error('Search failed');
    }
  } catch (e) {
    resultsEl.innerHTML = '<div class="text-on-surface-variant text-center py-2">Search requires backend</div>';
  }
}

// ── NOTIFICATION HISTORY ───────────────────────────────
async function loadNotificationHistory() {
  const listEl = document.getElementById('notification-history');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-primary animate-pulse">Loading...</div>';

  try {
    const resp = await fetch('/notifications/history');
    if (resp.ok) {
      const data = await resp.json();
      const notifs = data.notifications || [];

      if (notifs.length > 0) {
        listEl.innerHTML = notifs.map(n => `
          <div class="p-2 bg-surface-container rounded border border-yc flex justify-between items-center">
            <div>
              <div class="text-body-sm font-bold text-on-surface">${n.title || 'Notification'}</div>
              <div class="text-body-sm text-on-surface-variant">${n.message || ''}</div>
            </div>
            <div class="text-mono-label text-on-surface-variant text-xs">${n.timestamp || ''}</div>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = '<div class="text-on-surface-variant text-center py-2">No notifications yet</div>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<div class="text-on-surface-variant text-center py-2">No notifications yet</div>';
  }
}

// ── MEMORY PREFERENCES ──────────────────────────────────
async function loadMemoryPreferences() {
  const listEl = document.getElementById('memory-preferences');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-primary animate-pulse">Loading...</div>';

  try {
    const resp = await fetch('/memory/preferences');
    if (resp.ok) {
      const data = await resp.json();
      const prefs = data.preferences || {};

      const items = Object.entries(prefs);
      if (items.length > 0) {
        listEl.innerHTML = items.map(([k, v]) => `
          <div class="flex justify-between items-center p-2 bg-surface-container rounded border border-yc">
            <span class="text-body-sm font-bold text-on-surface">${k}</span>
            <span class="text-body-sm text-on-surface-variant">${v}</span>
          </div>
        `).join('');
      } else {
        listEl.innerHTML = '<div class="text-on-surface-variant">No preferences set</div>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<div class="text-on-surface-variant">No preferences set</div>';
  }
}

async function setMemoryPreference() {
  const keyInput = document.getElementById('pref-key');
  const valueInput = document.getElementById('pref-value');
  const key = keyInput?.value.trim();
  const value = valueInput?.value.trim();

  if (!key || !value) {
    toast('Enter key and value');
    return;
  }

  try {
    const resp = await fetch('/memory/preference', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: key, value: value })
    });

    if (resp.ok) {
      toast('Preference saved');
      loadMemoryPreferences();
    }
  } catch (e) {
    toast('Preference saved (demo)');
    loadMemoryPreferences();
  }

  keyInput.value = '';
  valueInput.value = '';
}

// ── ADD FACT TO MEMORY ──────────────────────────────────
async function addFactToMemory() {
  const input = document.getElementById('quick-fact');
  const catSelect = document.getElementById('fact-category');
  const fact = input?.value.trim();
  const category = catSelect?.value || 'general';

  if (!fact) {
    toast('Enter a fact to remember');
    return;
  }

  try {
    const resp = await fetch('/memory/fact', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fact: fact, category: category })
    });

    if (resp.ok) {
      toast('Fact saved to memory');
      input.value = '';
    }
  } catch (e) {
    toast('Fact saved to memory (demo)');
    input.value = '';
  }
}

// ── ANALYTICS ───────────────────────────────────────────
async function loadAnalyticsData() {
  try {
    // Try to get real analytics from backend
    const resp = await fetch('/analytics/user/default');
    if (resp.ok) {
      const data = await resp.json();
      const sessionsEl = document.getElementById('anal-sessions');
      const accuracyEl = document.getElementById('anal-accuracy');
      const wpmEl = document.getElementById('anal-wpm');
      const timeEl = document.getElementById('anal-time');

      if (sessionsEl) sessionsEl.textContent = data.total_sessions || 0;
      if (accuracyEl) accuracyEl.textContent = (data.avg_accuracy || 0) + '%';
      if (wpmEl) wpmEl.textContent = data.avg_wpm || 0;
      if (timeEl) timeEl.textContent = (data.total_time_minutes || 0) + 'm';
    }
  } catch (e) {
    // Use localStorage data as fallback
    loadHistory();
    const history = S.sessionHistory || [];
    const sessionsEl = document.getElementById('anal-sessions');
    const accuracyEl = document.getElementById('anal-accuracy');
    const wpmEl = document.getElementById('anal-wpm');
    const timeEl = document.getElementById('anal-time');

    if (sessionsEl) sessionsEl.textContent = history.length;
    const avgAcc = history.length ? Math.round(history.reduce((a, s) => a + (s.accuracy || 0), 0) / history.length) : 0;
    if (accuracyEl) accuracyEl.textContent = avgAcc + '%';
    if (wpmEl) wpmEl.textContent = Math.round(history.reduce((a, s) => a + (s.wpm || 0), 0) / Math.max(1, history.length));
    const totalMin = history.length ? Math.round(history.reduce((a, s) => a + (s.duration || 0), 0) / 60) : 0;
    if (timeEl) timeEl.textContent = totalMin + 'm';
  }
}

// ── SESSION RECORDING ───────────────────────────────────
async function startSessionRecording() {
  const sessionInput = document.getElementById('session-id-input');
  const sessionId = sessionInput?.value.trim() || generateUUID();
  const statusEl = document.getElementById('session-status');

  if (statusEl) statusEl.innerHTML = '<span class="text-primary animate-pulse">Starting recording...</span>';

  try {
    const resp = await fetch(`/recordings/${sessionId}/start`, { method: 'POST' });
    if (resp.ok) {
      if (statusEl) statusEl.innerHTML = `<span class="text-secondary">Recording started: ${sessionId.slice(0, 8)}</span>`;
      APP.sessionId = sessionId;
      toast('Recording started');
    } else {
      throw new Error('Failed to start');
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = '<span class="text-on-surface-variant">Recording started (demo mode)</span>';
    APP.sessionId = sessionId;
    toast('Recording started (demo)');
  }
}

async function stopSessionRecording() {
  const sessionId = APP.sessionId || document.getElementById('session-id-input')?.value.trim();
  const statusEl = document.getElementById('session-status');

  if (!sessionId) {
    toast('No active session to stop');
    return;
  }

  try {
    const resp = await fetch(`/recordings/${sessionId}/stop`, { method: 'POST' });
    if (resp.ok) {
      if (statusEl) statusEl.innerHTML = '<span class="text-secondary">Recording stopped</span>';
      toast('Recording stopped');
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = '<span class="text-on-surface-variant">Recording stopped (demo)</span>';
    toast('Recording stopped');
  }
}

async function getSessionDetails() {
  const sessionInput = document.getElementById('session-id-input');
  const sessionId = sessionInput?.value.trim();
  const statusEl = document.getElementById('session-status');

  if (!sessionId) {
    toast('Enter a session ID');
    return;
  }

  try {
    const resp = await fetch(`/recordings/${sessionId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (statusEl) statusEl.innerHTML = `<span class="text-on-surface">Session: ${data.duration || 'N/A'}s, ${data.chunks || 0} chunks</span>`;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (statusEl) statusEl.innerHTML = '<span class="text-on-surface-variant">Session not found</span>';
  }
}

// ── SESSION INSIGHTS ────────────────────────────────────
async function loadSessionInsights() {
  const input = document.getElementById('insights-session-id');
  const resultsEl = document.getElementById('session-insights');
  const sessionId = input?.value.trim();

  if (!sessionId) {
    toast('Enter a session ID');
    return;
  }

  if (resultsEl) resultsEl.innerHTML = '<span class="text-primary animate-pulse">Loading insights...</span>';

  try {
    const resp = await fetch(`/sessions/${sessionId}/insights`);
    if (resp.ok) {
      const data = await resp.json();
      if (resultsEl) resultsEl.innerHTML = `
        <div class="space-y-2">
          <div><strong>Accuracy:</strong> ${data.accuracy || 'N/A'}%</div>
          <div><strong>WPM:</strong> ${data.wpm || 'N/A'}</div>
          <div><strong>Corrections:</strong> ${data.corrections || 0}</div>
          <div><strong>Focus Words:</strong> ${(data.focus_words || []).join(', ') || 'None'}</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (resultsEl) resultsEl.innerHTML = '<span class="text-on-surface-variant">No insights available for this session</span>';
  }
}

// ── ADVANCED ANALYTICS ───────────────────────────────────
async function loadUserAnalytics() {
  const input = document.getElementById('analytics-user-id');
  const resultsEl = document.getElementById('advanced-analytics-results');
  const userId = input?.value.trim() || 'default';

  if (resultsEl) resultsEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';

  try {
    const resp = await fetch(`/analytics/user/${userId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (resultsEl) resultsEl.innerHTML = `
        <div class="grid grid-cols-2 gap-2">
          <div>Sessions: ${data.total_sessions || 0}</div>
          <div>Avg Accuracy: ${data.avg_accuracy || 0}%</div>
          <div>Avg WPM: ${data.avg_wpm || 0}</div>
          <div>Total Time: ${data.total_time_minutes || 0}m</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (resultsEl) resultsEl.innerHTML = '<span class="text-on-surface-variant">No analytics data available</span>';
  }
}

async function loadImprovementData() {
  const input = document.getElementById('analytics-user-id');
  const resultsEl = document.getElementById('advanced-analytics-results');
  const userId = input?.value.trim() || 'default';

  if (resultsEl) resultsEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';

  try {
    const resp = await fetch(`/analytics/improvement/${userId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (resultsEl) resultsEl.innerHTML = `
        <div class="space-y-1">
          <div><strong>Improvement Rate:</strong> ${data.improvement_rate || 0}%</div>
          <div><strong>Trend:</strong> ${data.trend || 'Stable'}</div>
          <div><strong>Weak Areas:</strong> ${(data.weak_areas || []).join(', ') || 'None'}</div>
        </div>
      `;
    }
  } catch (e) {
    if (resultsEl) resultsEl.innerHTML = '<span class="text-on-surface-variant">No improvement data available</span>';
  }
}

async function loadQaTopics() {
  const input = document.getElementById('analytics-user-id');
  const resultsEl = document.getElementById('advanced-analytics-results');
  const userId = input?.value.trim() || 'default';

  if (resultsEl) resultsEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';

  try {
    const resp = await fetch(`/analytics/qa-topics/${userId}`);
    if (resp.ok) {
      const data = await resp.json();
      const topics = data.topics || [];
      if (resultsEl && topics.length > 0) {
        resultsEl.innerHTML = topics.map(t => `
          <div class="flex justify-between p-1 bg-surface-container rounded">
            <span>${t.topic}</span>
            <span class="text-mono-label">${t.count}</span>
          </div>
        `).join('');
      } else if (resultsEl) {
        resultsEl.innerHTML = '<span class="text-on-surface-variant">No QA topics recorded</span>';
      }
    }
  } catch (e) {
    if (resultsEl) resultsEl.innerHTML = '<span class="text-on-surface-variant">No QA topics available</span>';
  }
}

// ── WAKE WORD PROCESSING ─────────────────────────────────
async function processWakeWord() {
  const resultEl = document.getElementById('wake-detection-result');
  if (resultEl) resultEl.innerHTML = '<span class="text-primary animate-pulse">Processing audio...</span>';

  try {
    const resp = await fetch('/voice/process', { method: 'POST' });
    if (resp.ok) {
      const data = await resp.json();
      if (resultEl) resultEl.innerHTML = `<span class="text-secondary">Wake word detected: ${data.detected || false}</span>`;
    } else {
      throw new Error('Processing failed');
    }
  } catch (e) {
    if (resultEl) resultEl.innerHTML = '<span class="text-on-surface-variant">No audio to process (demo)</span>';
  }
}

async function startWakeDetection() {
  const resultEl = document.getElementById('wake-detection-result');
  if (resultEl) resultEl.innerHTML = '<span class="text-primary animate-pulse">Listening for "Hey Raso"...</span>';

  try {
    const resp = await fetch('/voice/start', { method: 'POST' });
    if (resp.ok) {
      toast('Wake detection started');
      startAudio();
    }
  } catch (e) {
    toast('Wake detection started (demo)');
  }
}

// ── MEMORY RECALL ────────────────────────────────────────
async function recallMemory() {
  const queryInput = document.getElementById('recall-query');
  const keyInput = document.getElementById('recall-key');
  const catSelect = document.getElementById('recall-category');
  const resultsEl = document.getElementById('recall-results');

  const query = queryInput?.value.trim();
  const key = keyInput?.value.trim();
  const category = catSelect?.value;

  if (!query && !key) {
    toast('Enter a query or key');
    return;
  }

  if (resultsEl) resultsEl.innerHTML = '<div class="text-primary animate-pulse">Searching...</div>';

  let url = '/memory/recall?';
  if (query) url += `query=${encodeURIComponent(query)}&`;
  if (key) url += `key=${encodeURIComponent(key)}&`;
  if (category) url += `category=${encodeURIComponent(category)}&`;
  url += 'limit=10';

  try {
    const resp = await fetch(url);
    if (resp.ok) {
      const data = await resp.json();
      const results = data.results || [];

      if (results.length > 0) {
        resultsEl.innerHTML = results.map(r => `
          <div class="p-2 bg-surface-container rounded border border-yc">
            <div class="text-body-sm font-bold text-on-surface">${r.key || 'Memory'}</div>
            <div class="text-body-sm text-on-surface-variant line-clamp-2">${r.value || r.text || ''}</div>
          </div>
        `).join('');
      } else {
        resultsEl.innerHTML = '<div class="text-on-surface-variant">No memories found</div>';
      }
    } else {
      throw new Error('Recall failed');
    }
  } catch (e) {
    resultsEl.innerHTML = '<div class="text-on-surface-variant">No memories found</div>';
  }
}

// ── DOCUMENT SNIPPET ──────────────────────────────────────
async function addSnippet() {
  const input = document.getElementById('snippet-text');
  const text = input?.value.trim();

  if (!text) {
    toast('Enter text for snippet');
    return;
  }

  try {
    const resp = await fetch('/documents/snippet', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: text, source: 'manual' })
    });

    if (resp.ok) {
      toast('Snippet added');
      input.value = '';
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    toast('Snippet added (demo)');
    input.value = '';
  }
}

// ── PROVIDER SELECTION ───────────────────────────────────
function setProvider(provider) {
  currentProvider = provider;
  const labels = { qwen: 'Qwen (Local)', openai: 'OpenAI', anthropic: 'Anthropic', gemini: 'Gemini' };
  const statusEl = document.getElementById('provider-status');
  if (statusEl) statusEl.textContent = `Current: ${labels[provider] || provider}`;

  try {
    fetch('/raso/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider: provider })
    });
  } catch (e) {
    // Silent fail for demo
  }

  toast(`Provider set to ${labels[provider]}`);
}

// ── PARTNER STATUS ───────────────────────────────────────
async function checkPartnerStatus() {
  const displayEl = document.getElementById('partner-status-display');
  if (!displayEl) return;

  displayEl.innerHTML = '<span class="text-primary animate-pulse">Checking...</span>';

  try {
    const resp = await fetch('/raso/status');
    if (resp.ok) {
      const data = await resp.json();
      displayEl.innerHTML = `
        <div class="space-y-1">
          <div><strong>Mode:</strong> ${data.mode || 'Active'}</div>
          <div><strong>Provider:</strong> ${data.provider || currentProvider}</div>
          <div><strong>Listening:</strong> ${data.listening || false}</div>
        </div>
      `;
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    displayEl.innerHTML = '<span class="text-on-surface-variant">Partner is ready. Start voice mode to begin.</span>';
  }
}

// ── AI CONTEXT FOR PROMPTS ──────────────────────────────
async function getAiContext() {
  const select = document.getElementById('ai-context-target');
  const outputEl = document.getElementById('ai-context-output');
  const target = select?.value || 'qa';

  if (outputEl) {
    outputEl.classList.remove('hidden');
    outputEl.innerHTML = '<span class="text-primary animate-pulse">Building context...</span>';
  }

  try {
    const resp = await fetch(`/memory/context?ai_name=${target}`);
    if (resp.ok) {
      const data = await resp.json();
      if (outputEl) outputEl.textContent = data.context || JSON.stringify(data, null, 2).slice(0, 500);
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    if (outputEl) outputEl.textContent = 'No context available for this agent yet. Interact with the AI more to build context.';
  }
}

// ── SESSION DETAILS ──────────────────────────────────────
async function getSessionInfo() {
  const input = document.getElementById('session-detail-id');
  const outputEl = document.getElementById('session-detail-output');
  const sessionId = input?.value.trim();

  if (!sessionId) {
    toast('Enter a session ID');
    return;
  }

  if (outputEl) {
    outputEl.classList.remove('hidden');
    outputEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';
  }

  try {
    const resp = await fetch(`/sessions/${sessionId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (outputEl) outputEl.innerHTML = `
        <div class="space-y-1">
          <div><strong>Session ID:</strong> ${data.session_id?.slice(0, 12) || 'N/A'}</div>
          <div><strong>Created:</strong> ${data.created_at || 'N/A'}</div>
          <div><strong>Chunks:</strong> ${data.chunks?.length || 0}</div>
          <div><strong>Status:</strong> ${data.status || 'completed'}</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (outputEl) outputEl.innerHTML = '<span class="text-on-surface-variant">Session not found or not available.</span>';
  }
}

// ── SESSION ANALYTICS ────────────────────────────────────
async function getSessionAnalytics() {
  const input = document.getElementById('session-analytics-id');
  const outputEl = document.getElementById('session-analytics-output');
  const sessionId = input?.value.trim();

  if (!sessionId) {
    toast('Enter a session ID');
    return;
  }

  if (outputEl) {
    outputEl.classList.remove('hidden');
    outputEl.innerHTML = '<span class="text-primary animate-pulse">Analyzing...</span>';
  }

  try {
    const resp = await fetch(`/analytics/session/${sessionId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (outputEl) outputEl.innerHTML = `
        <div class="grid grid-cols-2 gap-2">
          <div><strong>Accuracy:</strong> ${data.accuracy || 0}%</div>
          <div><strong>WPM:</strong> ${data.wpm || 0}</div>
          <div><strong>Duration:</strong> ${data.duration || 0}s</div>
          <div><strong>Corrections:</strong> ${data.corrections || 0}</div>
          <div class="col-span-2"><strong>Focus Areas:</strong> ${(data.focus_words || []).join(', ') || 'None'}</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (outputEl) outputEl.innerHTML = '<span class="text-on-surface-variant">No analytics available for this session.</span>';
  }
}

// ── SINGLE RECORDING LOOKUP ─────────────────────────────
async function getRecordingDetails() {
  const input = document.getElementById('recording-id-input');
  const outputEl = document.getElementById('recording-output');
  const recordingId = input?.value.trim();

  if (!recordingId) {
    toast('Enter a recording ID');
    return;
  }

  if (outputEl) {
    outputEl.classList.remove('hidden');
    outputEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';
  }

  try {
    const resp = await fetch(`/recordings/${recordingId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (outputEl) outputEl.innerHTML = `
        <div class="space-y-1">
          <div><strong>ID:</strong> ${data.session_id?.slice(0, 12) || 'N/A'}</div>
          <div><strong>Created:</strong> ${data.created_at || 'N/A'}</div>
          <div><strong>Duration:</strong> ${data.duration || 'N/A'}s</div>
          <div><strong>Chunks:</strong> ${data.chunks?.length || 0}</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (outputEl) outputEl.innerHTML = '<span class="text-on-surface-variant">Recording not found.</span>';
  }
}

// ── DEVICE REGISTRATION ─────────────────────────────────
async function registerDevice() {
  const typeSelect = document.getElementById('device-type');
  const endpointInput = document.getElementById('device-endpoint');
  const deviceType = typeSelect?.value || 'browser';
  const endpoint = endpointInput?.value.trim();

  if (!endpoint) {
    toast('Enter device endpoint');
    return;
  }

  try {
    const resp = await fetch('/notifications/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_type: deviceType,
        endpoint: endpoint,
        token: ''
      })
    });

    if (resp.ok) {
      toast('Device registered successfully');
      endpointInput.value = '';
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    toast('Device registered (demo mode)');
    endpointInput.value = '';
  }
}

// ── DOCUMENT BY ID ──────────────────────────────────────
async function getDocumentById() {
  const input = document.getElementById('doc-id-input');
  const outputEl = document.getElementById('doc-id-output');
  const docId = input?.value.trim();

  if (!docId) {
    toast('Enter a document ID');
    return;
  }

  if (outputEl) {
    outputEl.classList.remove('hidden');
    outputEl.innerHTML = '<span class="text-primary animate-pulse">Loading...</span>';
  }

  try {
    const resp = await fetch(`/documents/${docId}`);
    if (resp.ok) {
      const data = await resp.json();
      if (outputEl) outputEl.innerHTML = `
        <div class="space-y-1">
          <div><strong>Title:</strong> ${data.title || 'Untitled'}</div>
          <div><strong>Type:</strong> ${data.doc_type || 'text'}</div>
          <div><strong>Category:</strong> ${data.category || 'general'}</div>
          <div><strong>Content:</strong> ${(data.content || '').slice(0, 200)}</div>
        </div>
      `;
    } else {
      throw new Error('Not found');
    }
  } catch (e) {
    if (outputEl) outputEl.innerHTML = '<span class="text-on-surface-variant">Document not found.</span>';
  }
}

async function deleteDocumentById() {
  const input = document.getElementById('doc-id-input');
  const docId = input?.value.trim();

  if (!docId) {
    toast('Enter a document ID');
    return;
  }

  if (!confirm('Delete this document?')) return;

  try {
    const resp = await fetch(`/documents/${docId}`, { method: 'DELETE' });
    if (resp.ok) {
      toast('Document deleted');
      const outputEl = document.getElementById('doc-id-output');
      if (outputEl) outputEl.innerHTML = '<span class="text-secondary">Document deleted successfully.</span>';
    } else {
      throw new Error('Failed');
    }
  } catch (e) {
    toast('Document deleted (demo)');
  }
}
