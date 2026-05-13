/**
 * RasoSpeak Voice Overlay - Persistent Audio Conversation Mode
 * ============================================================
 * Provides voice-first operating system control with "Hey Raso" wake word.
 * Shows persistent overlay across all pages with live transcripts,
 * cognitive state, and system control.
 */

const RasoVoice = {
  // State
  isListening: false,
  isSpeaking: false,
  isActive: false,
  wakeWordDetected: false,
  conversationMode: false,
  currentTranscript: '',
  finalTranscript: '',
  audioLevel: 0,
  recognition: null,
  synth: window.speechSynthesis,
  wakeWords: ['hey raso', 'raso', 'hey jarvis', 'jarvis'],
  lastWakeTime: 0,
  cooldownMs: 2000,

  // DOM Elements
  overlay: null,
  statusIndicator: null,
  transcriptDisplay: null,

  init() {
    this.createOverlay();
    this.setupSpeechRecognition();
    this.setupWakeWordDetection();
    console.log('RasoVoice: Voice overlay initialized');
  },

  createOverlay() {
    // Create persistent voice overlay
    const overlay = document.createElement('div');
    overlay.id = 'raso-voice-overlay';
    overlay.className = 'fixed bottom-6 right-6 z-[9999] transition-all duration-300';
    overlay.innerHTML = `
      <!-- Minimized State -->
      <div id="raso-voice-minimized" class="flex items-center gap-3 px-4 py-3 rounded-full shadow-2xl cursor-pointer"
           style="background: linear-gradient(135deg, #1B4332 0%, #2D6A4F 100%); color: white;"
           onclick="RasoVoice.toggleFullOverlay()">
        <div class="relative">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
          </svg>
          <span id="raso-voice-indicator" class="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-gray-400 transition-colors duration-300"></span>
        </div>
        <span class="text-sm font-medium">Hey Raso</span>
        <span id="raso-voice-state" class="text-xs opacity-70">Idle</span>
      </div>

      <!-- Expanded Voice Panel -->
      <div id="raso-voice-panel" class="hidden w-96 shadow-2xl rounded-2xl overflow-hidden"
           style="background: #FFFEFA; border: 1px solid #E7E3DB;">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3" style="background: #1B4332; color: white;">
          <div class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-white/20 flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
              </svg>
            </div>
            <span class="font-semibold">Raso Voice Mode</span>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="RasoVoice.toggleMute()" id="raso-mute-btn" class="p-1.5 rounded-lg hover:bg-white/20" title="Mute">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"/>
              </svg>
            </button>
            <button onclick="RasoVoice.minimize()" class="p-1.5 rounded-lg hover:bg-white/20" title="Minimize">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Voice State -->
        <div class="px-4 py-2 flex items-center justify-between" style="background: #F6F3EE;">
          <div class="flex items-center gap-2">
            <span id="raso-voice-status-dot" class="w-2 h-2 rounded-full bg-gray-400"></span>
            <span id="raso-voice-status-text" class="text-xs font-medium" style="color: #78716C;">Idle</span>
          </div>
          <div class="flex items-center gap-1">
            <span class="text-xs" style="color: #78716C;">Listening</span>
            <div id="raso-audio-level" class="w-16 h-1.5 rounded-full bg-gray-200 overflow-hidden">
              <div id="raso-audio-level-bar" class="h-full rounded-full transition-all duration-100" style="width: 0%; background: #1B4332;"></div>
            </div>
          </div>
        </div>

        <!-- Transcript Area -->
        <div class="p-4 space-y-3" style="min-height: 200px; max-height: 300px; overflow-y: auto;">
          <!-- User Transcript -->
          <div id="raso-user-transcript" class="hidden">
            <div class="flex items-start gap-2">
              <div class="w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center" style="background: #1B4332; color: white;">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                </svg>
              </div>
              <div class="flex-1">
                <div class="text-xs font-medium" style="color: #78716C;">You</div>
                <div id="raso-user-text" class="text-sm mt-0.5" style="color: #1C1917;">...</div>
                <div id="raso-user-interim" class="text-sm mt-0.5 italic" style="color: #78716C;"></div>
              </div>
            </div>
          </div>

          <!-- AI Response -->
          <div id="raso-ai-response" class="hidden">
            <div class="flex items-start gap-2">
              <div class="w-6 h-6 rounded-full flex-shrink-0 flex items-center justify-center" style="background: #52796F; color: white;">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/>
                </svg>
              </div>
              <div class="flex-1">
                <div class="text-xs font-medium" style="color: #78716C;">Raso</div>
                <div id="raso-ai-text" class="text-sm mt-0.5" style="color: #1C1917;">...</div>
                <!-- Cognitive State -->
                <div id="raso-cognitive-state" class="mt-2 hidden">
                  <div class="flex items-center gap-1 text-xs" style="color: #52796F;">
                    <span class="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
                    <span id="raso-active-layer">Thinking</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Empty State -->
          <div id="raso-empty-state" class="text-center py-8">
            <div class="w-12 h-12 mx-auto rounded-full flex items-center justify-center mb-3" style="background: #F6F3EE;">
              <svg class="w-6 h-6" style="color: #78716C;" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"/>
              </svg>
            </div>
            <p class="text-sm" style="color: #78716C;">Say "Hey Raso" to start</p>
            <p class="text-xs mt-1" style="color: #78716C;">or click the microphone to begin</p>
          </div>
        </div>

        <!-- Controls -->
        <div class="px-4 py-3 flex items-center justify-between" style="background: #F6F3EE; border-top: 1px solid #E7E3DB;">
          <button onclick="RasoVoice.stopListening()" class="px-3 py-1.5 rounded-lg text-xs font-medium" style="background: #FEF2F2; color: #B91C1C;">
            Stop
          </button>
          <button onclick="RasoVoice.toggleConversationMode()" id="raso-convo-mode-btn" class="px-3 py-1.5 rounded-lg text-xs font-medium" style="background: #1B4332; color: white;">
            Continuous
          </button>
          <button onclick="RasoVoice.startListening()" id="raso-push-talk" class="px-3 py-1.5 rounded-lg text-xs font-medium" style="background: #52796F; color: white;">
            Push to Talk
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    this.overlay = overlay;
  },

  setupSpeechRecognition() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      console.warn('RasoVoice: Speech recognition not supported');
      return;
    }

    this.recognition = new SR();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.lang = 'en-US';
    this.recognition.maxAlternatives = 3;

    this.recognition.onstart = () => {
      console.log('RasoVoice: Recognition started');
      this.setState('listening');
    };

    this.recognition.onresult = (event) => {
      let interim = '';
      let final = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          final += transcript + ' ';
        } else {
          interim += transcript;
        }
      }

      this.currentTranscript = final + interim;
      this.updateTranscript(final, interim);

      // Check for wake word in final
      if (final.trim()) {
        this.checkWakeWord(final.trim());
      }
    };

    this.recognition.onerror = (event) => {
      console.error('RasoVoice: Recognition error', event.error);
      if (event.error !== 'no-speech') {
        this.setState('error');
      }
    };

    this.recognition.onend = () => {
      console.log('RasoVoice: Recognition ended');
      if (this.conversationMode && this.isListening) {
        // Restart in continuous mode
        setTimeout(() => this.startListening(), 100);
      } else {
        this.setState('idle');
      }
    };
  },

  setupWakeWordDetection() {
    // Wake word detection happens in checkWakeWord via text
    console.log('RasoVoice: Wake word detection ready');
  },

  checkWakeWord(text) {
    const now = Date.now();
    if (now - this.lastWakeTime < this.cooldownMs) return;

    const textLower = text.toLowerCase().trim();
    for (const wakeWord of this.wakeWords) {
      if (textLower === wakeWord || textLower.startsWith(wakeWord + ' ') || textLower.includes(' ' + wakeWord + ' ')) {
        console.log('RasoVoice: Wake word detected!', wakeWord);
        this.lastWakeTime = now;
        this.activate();
        return;
      }
    }
  },

  activate() {
    this.isActive = true;
    this.wakeWordDetected = true;
    this.conversationMode = true;

    // Show expanded panel
    document.getElementById('raso-voice-minimized').classList.add('hidden');
    document.getElementById('raso-voice-panel').classList.remove('hidden');
    document.getElementById('raso-empty-state').classList.add('hidden');
    document.getElementById('raso-user-transcript').classList.remove('hidden');

    // Speak confirmation
    this.speak('I\'m listening. How can I help you?');

    // Start continuous listening
    this.startListening();
  },

  startListening() {
    if (!this.recognition) {
      console.error('RasoVoice: Recognition not initialized');
      return;
    }

    try {
      this.recognition.start();
      this.isListening = true;
    } catch (e) {
      console.error('RasoVoice: Failed to start recognition', e);
    }
  },

  stopListening() {
    if (this.recognition) {
      this.recognition.stop();
    }
    this.isListening = false;
    this.setState('idle');
  },

  updateTranscript(final, interim) {
    // Update user transcript display
    if (final) {
      this.finalTranscript = final;
      document.getElementById('raso-user-text').textContent = final;
      document.getElementById('raso-user-interim').textContent = '';
    }
    if (interim) {
      document.getElementById('raso-user-interim').textContent = interim;
    }
  },

  showAIResponse(text, cognitiveState = null) {
    document.getElementById('raso-ai-response').classList.remove('hidden');
    document.getElementById('raso-ai-text').textContent = text;

    if (cognitiveState) {
      document.getElementById('raso-cognitive-state').classList.remove('hidden');
      document.getElementById('raso-active-layer').textContent = cognitiveState;
    }
  },

  setState(state) {
    const statusDot = document.getElementById('raso-voice-status-dot');
    const statusText = document.getElementById('raso-voice-status-text');
    const indicator = document.getElementById('raso-voice-indicator');
    const stateText = document.getElementById('raso-voice-state');

    const states = {
      idle: { color: '#78716C', text: 'Idle', indicator: '#78716C' },
      listening: { color: '#22C55E', text: 'Listening...', indicator: '#22C55E' },
      processing: { color: '#EAB308', text: 'Processing...', indicator: '#EAB308' },
      speaking: { color: '#3B82F6', text: 'Speaking', indicator: '#3B82F6' },
      error: { color: '#EF4444', text: 'Error', indicator: '#EF4444' }
    };

    const s = states[state] || states.idle;
    statusDot.style.background = s.color;
    statusText.textContent = s.text;
    if (indicator) indicator.style.background = s.indicator;
    if (stateText) stateText.textContent = s.text;
  },

  toggleFullOverlay() {
    const minimized = document.getElementById('raso-voice-minimized');
    const panel = document.getElementById('raso-voice-panel');

    if (panel.classList.contains('hidden')) {
      // Expand
      minimized.classList.add('hidden');
      panel.classList.remove('hidden');
    } else {
      // Minimize
      panel.classList.add('hidden');
      minimized.classList.remove('hidden');
    }
  },

  minimize() {
    document.getElementById('raso-voice-panel').classList.add('hidden');
    document.getElementById('raso-voice-minimized').classList.remove('hidden');
  },

  toggleMute() {
    if (this.synth.speaking) {
      this.synth.pause();
      document.getElementById('raso-mute-btn').innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2"/></svg>';
    } else {
      this.synth.resume();
      document.getElementById('raso-mute-btn').innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z"/></svg>';
    }
  },

  toggleConversationMode() {
    this.conversationMode = !this.conversationMode;
    const btn = document.getElementById('raso-convo-mode-btn');
    btn.textContent = this.conversationMode ? 'Continuous' : 'Single';
    btn.style.background = this.conversationMode ? '#1B4332' : '#52796F';
  },

  speak(text, callback) {
    if (!text) return;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 0.9;
    utterance.pitch = 0.96;
    utterance.volume = 0.92;

    utterance.onstart = () => {
      this.setState('speaking');
    };

    utterance.onend = () => {
      this.setState(this.isListening ? 'listening' : 'idle');
      if (callback) callback();
    };

    this.synth.speak(utterance);
  },

  // Process voice command through 7-layer cognitive pipeline
  async processCommand(text) {
    this.setState('processing');
    this.showAIResponse('Processing your request...', 'Perception');

    try {
      // Use unified cognitive pipeline
      const resp = await fetch('/api/v1/process', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, user_id: 'default' })
      });

      if (resp.ok) {
        const data = await resp.json();
        // Show cognitive layer processing state
        const layer = data.cognitive_layers?.[0] || 'execution';
        this.showAIResponse(data.response || 'I\'m thinking...', layer.charAt(0).toUpperCase() + layer.slice(1));

        // Speak the response
        this.speak(data.response);
      }
    } catch (e) {
      console.error('RasoVoice: Command processing failed', e);
      this.showAIResponse('I\'m having trouble processing that request.', 'Error');
    }
  }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  RasoVoice.init();
});