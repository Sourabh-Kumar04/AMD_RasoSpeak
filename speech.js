/* ═══════════════════════════════════════════════════
   RasoSpeak — Offline Speech Layer
   Browser TTS (always used for earpiece delivery)
   Browser STT (fallback when AMD Whisper unavailable)
   Web Audio API (always used for waveform viz)
   ═══════════════════════════════════════════════════ */

/* ── TTS — always runs in browser (earpiece output) ─── */
function populateVoices() {
  const all = S.synth.getVoices();
  S.voices  = all;
  const sel = document.getElementById('sel-voice');
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
  if (vi !== '' && vi !== undefined && S.voices[parseInt(vi)])
    return S.voices[parseInt(vi)];
  return (
    S.voices.find(v => v.name.includes('Google') && v.lang === 'en-US') ||
    S.voices.find(v => v.lang === 'en-US') ||
    S.voices.find(v => v.lang.startsWith('en')) ||
    null
  );
}

function getSpeed() {
  return parseFloat(document.getElementById('sel-speed')?.value || '0.85');
}

function speak(text, onDone, pace) {
  if (S.synth.speaking) S.synth.cancel();
  const u     = new SpeechSynthesisUtterance(text);
  const voice = getVoice();
  if (voice) u.voice = voice;
  u.rate   = pace === 'slow' ? getSpeed() * 0.84
           : pace === 'fast' ? getSpeed() * 1.1
           : getSpeed();
  u.pitch  = 0.96;
  u.volume = 0.92;
  u.lang   = 'en-US';

  // Chrome keepalive fix
  const kv = setInterval(() => {
    if (!S.synth.speaking) clearInterval(kv);
    else if (S.synth.paused) S.synth.resume();
  }, 5000);
  u.onend = u.onerror = () => { clearInterval(kv); if (onDone) onDone(); };
  S.synth.speak(u);
}

/* ── OFFLINE STT — browser Web Speech API ───────────── */
function startRec() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast('⚠️ Speech recognition needs Chrome or Edge'); return; }

  const r          = new SR();
  r.continuous     = true;
  r.interimResults = true;
  r.lang           = 'en-US';
  r.maxAlternatives = 3;

  r.onresult = (e) => {
    if (S.phase !== PHASE.LISTEN) return;
    let interim = '', newFinal = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) {
        let best = e.results[i][0].transcript;
        for (let j = 1; j < e.results[i].length; j++) {
          if (e.results[i][j].transcript.trim().length > best.trim().length)
            best = e.results[i][j].transcript;
        }
        newFinal   += best + ' ';
        S.finalBuf += best + ' ';
      } else {
        interim      = e.results[i][0].transcript;
        S.interimBuf = interim;
      }
    }
    updateLiveTx(S.finalBuf, interim);
    if (newFinal.trim()) {
      trackWPM(newFinal.trim().split(/\s+/).length);
      resetSilenceTimer();
      const cov = coverage(S.finalBuf, S.chunks[S.cur] || '');
      if (cov >= 0.82) setTimeout(() => {
        if (S.phase === PHASE.LISTEN && S.running) offlineDoCompare();
      }, 300);
    }
  };

  r.onerror = (e) => {
    const ignorable = ['no-speech', 'aborted', 'interrupted'];
    if (ignorable.includes(e.error)) return;
    if (S.running && !S.paused) setTimeout(() => { try { r.start(); } catch (x) {} }, 600);
  };
  r.onend = () => {
    if (S.running && !S.paused) setTimeout(() => { try { r.start(); } catch (x) {} }, 200);
  };

  try { r.start(); } catch (e) {}
  S.rec = r;
}

function stopRec() {
  if (S.rec) { try { S.rec.abort(); } catch (e) {} S.rec = null; }
}

/* ── OFFLINE COMPARE ────────────────────────────────── */
function offlineDoCompare() {
  if (!S.running) return;
  clearTimeout(S.silTimer);
  clearTimeout(S.lisTimer);
  setPhase(PHASE.COMPARE);

  const spoken   = S.finalBuf.trim();
  const expected = S.chunks[S.cur];
  const result   = compareTexts(spoken, expected);

  S.segResults[S.cur] = { score: result.score, status: result.status };
  S.accHist.push(result.score);
  renderLiveChunkList();
  showCompareDetail(result);
  showChunkText(expected, spoken, result);
  setM('acc', result.matchPct + '%');

  logCoach(
    result.status === 'ok' ? 'ok' : result.status === 'warn' ? 'warn' : 'miss',
    result.status === 'ok' ? '✅' : '⚠️',
    `[Offline] Score: <strong>${result.matchPct}%</strong> · ${result.feedback}`
  );

  if (result.score >= getThreshold()) {
    setTimeout(() => offlineDoAdvance(), 700);
  } else {
    setTimeout(() => offlineDoCorrect(result), 700);
  }
}

function offlineDoCorrect(result) {
  if (!S.running) return;
  setPhase(PHASE.CORRECT);
  S.corrections++;
  setM('corr', S.corrections);

  const attempts = (S.segResults[S.cur]?.attempts || 0) + 1;
  if (S.segResults[S.cur]) S.segResults[S.cur].attempts = attempts;
  const chunk = S.chunks[S.cur];

  if (attempts >= 4) {
    speak('Moving on.', () => { if (S.running && !S.paused) offlineDoAdvance(); });
    return;
  }
  if (S.mode === 'silent') {
    speak(chunk, () => { if (S.running && !S.paused) setTimeout(() => offlineDoListen(), 450); });
  } else if (S.mode === 'hint') {
    const missed = result.missedWords.slice(0, 3);
    speak(missed.length ? 'Key words: ' + missed.join('… ') : 'Try again', () => {
      if (S.running && !S.paused) setTimeout(() => offlineDoListen(), 500);
    });
  } else {
    const prefix = ['Try again: ', 'Once more: ', 'Last chance: '][Math.min(attempts - 1, 2)];
    speak(prefix + chunk, () => { if (S.running && !S.paused) setTimeout(() => offlineDoListen(), 450); });
  }
}

function offlineDoAdvance() {
  if (!S.running) return;
  S.segsDone++;
  setM('done', S.segsDone);
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
  setTimeout(() => { if (S.running && !S.paused) offlineDoDeliver(); }, 900);
}

function offlineDoDeliver() {
  if (!S.running || S.paused || S.cur >= S.chunks.length) return;
  setPhase(PHASE.DELIVER);
  showChunkText(S.chunks[S.cur], null, null);
  renderLiveChunkList();
  logCoach('deliver', '🔊', `[Offline] Chunk ${S.cur + 1}: <strong>"${S.chunks[S.cur]}"</strong>`);
  speak(S.chunks[S.cur], () => {
    if (S.running && !S.paused) setTimeout(() => offlineDoListen(), 500);
  });
}

function offlineDoListen() {
  if (!S.running || S.paused) return;
  setPhase(PHASE.LISTEN);
  S.finalBuf   = '';
  S.interimBuf = '';
  const el = document.getElementById('live-tx');
  if (el) el.innerHTML = '<span style="color:var(--text-muted);font-style:italic">Listening (offline mode)…</span>';
  const words    = (S.chunks[S.cur] || '').split(/\s+/).length;
  const listenMs = Math.max(6000, words * 950);
  S.lisTimer = setTimeout(() => {
    if (S.running && S.phase === PHASE.LISTEN) offlineDoCompare();
  }, listenMs);
  resetSilenceTimer();
}

/* ── SILENCE TIMER ──────────────────────────────────── */
function resetSilenceTimer() {
  clearTimeout(S.silTimer);
  if (S.phase === PHASE.LISTEN && S.running) {
    S.silTimer = setTimeout(() => {
      if (S.running && S.phase === PHASE.LISTEN) offlineDoCompare();
    }, 2200);
  }
}

/* ── LIVE TX DISPLAY ────────────────────────────────── */
function updateLiveTx(final, interim) {
  const el = document.getElementById('live-tx');
  if (!el) return;
  const tail = (final || '').trim().split(/\s+/).slice(-40).join(' ');
  el.innerHTML =
    `<span style="color:var(--text-primary)">${tail}</span>` +
    (interim ? `<span style="color:var(--text-muted);font-style:italic"> ${interim}</span>` : '');
  el.scrollTop = el.scrollHeight;
}

/* ── WPM TRACKING ───────────────────────────────────── */
function trackWPM(wordCount) {
  const now = Date.now();
  if (S.lastWordTime) {
    const mins = (now - S.lastWordTime) / 60000;
    if (mins > 0) {
      const wpm = Math.round(wordCount / mins);
      if (wpm > 20 && wpm < 500) {
        S.wpmHist.push(wpm);
        S.wpmAll.push(wpm);
        if (S.wpmHist.length > 8) S.wpmHist.shift();
        setM('wpm', Math.round(S.wpmHist.reduce((a, b) => a + b, 0) / S.wpmHist.length));
      }
    }
  }
  S.lastWordTime  = now;
  S.totalWords   += wordCount;
}

/* ── WEB AUDIO VISUALIZER ───────────────────────────── */
const WAVE_COUNT = 32;

function buildWaveform() {
  const wrap = document.getElementById('waveform-wrap');
  if (!wrap) return;
  wrap.innerHTML   = '';
  S.waveformBars   = [];
  for (let i = 0; i < WAVE_COUNT; i++) {
    const bar = document.createElement('div');
    bar.className = 'wav-bar';
    bar.style.animationDelay    = `${(i % 8) * 0.12}s`;
    bar.style.animationDuration = `${1.8 + (i % 4) * 0.3}s`;
    wrap.appendChild(bar);
    S.waveformBars.push(bar);
  }
}

function animateWaveformForPhase(ph) {
  const COLORS = {
    [PHASE.DELIVER]: 'var(--primary)',
    [PHASE.LISTEN]:  'var(--secondary)',
    [PHASE.COMPARE]: 'var(--accent)',
    [PHASE.CORRECT]: 'var(--danger)',
  };
  const color  = COLORS[ph] || 'var(--surface-4)';
  const active = ph !== PHASE.IDLE;
  const mode   = ph === PHASE.LISTEN ? 'listening' : ph === PHASE.DELIVER ? 'delivering' : '';
  S.waveformBars.forEach(b => {
    b.style.background = active ? color : 'var(--surface-4)';
    b.style.boxShadow  = active ? `0 0 5px ${color}50` : 'none';
    b.className        = 'wav-bar' + (mode ? ` ${mode}` : '');
  });
}

function resetWaveform() {
  S.waveformBars.forEach(b => {
    b.style.background = 'var(--surface-4)';
    b.style.boxShadow  = 'none';
    b.style.height     = '4px';
    b.className        = 'wav-bar';
  });
}
