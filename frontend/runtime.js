/**
 * RasoSpeak OS — Unified Frontend Runtime
 * Shared global state across all pages
 * Replaces page-level isolation with unified cognitive state
 */

// ── UNIFIED RUNTIME STATE ─────────────────────────────
const UnifiedRuntime = {
  // Connection state
  ws: null,
  wsVoice: null,
  connected: false,

  // User identity
  userId: 'default',
  sessionId: null,

  // Provider state (synced with backend)
  currentProvider: 'google',
  currentModel: 'gemini-2.0-flash-exp',

  // Memory state
  memoryConnected: false,
  memoryStats: { total: 0, episodic: 0, semantic: 0 },

  // Voice state
  voiceActive: false,
  voiceMode: 'command',  // command, streaming, interactive

  // Cognitive state
  cognitionEnabled: true,
  contextWindow: [],

  // Latency tracking
  metrics: {
    llmLatency: 0,
    memoryLatency: 0,
    voiceLatency: 0,
    totalLatency: 0,
  },

  // Event handlers
  _handlers: {},

  // ── INITIALIZATION ─────────────────────────────────

  async initialize(config = {}) {
    this.userId = config.userId || 'default';
    this.sessionId = config.sessionId || this._generateSessionId();

    // Connect to main WebSocket
    await this._connect();

    // Connect to voice WebSocket
    await this._connectVoice();

    console.log('✅ Unified Runtime initialized');
    return this;
  },

  _generateSessionId() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  },

  // ── WEBSOCKET CONNECTIONS ───────────────────────────

  async _connect() {
    return new Promise((resolve, reject) => {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = location.hostname === 'localhost' ? 'localhost:8000' : location.host;
      this.ws = new WebSocket(`${protocol}//${host}/ws?user_id=${this.userId}`);

      this.ws.onopen = () => {
        this.connected = true;
        console.log('✅ WebSocket connected');
        resolve();
      };

      this.ws.onmessage = (event) => {
        this._handleMessage(JSON.parse(event.data));
      };

      this.ws.onclose = () => {
        this.connected = false;
        console.log('⚠️ WebSocket disconnected - reconnecting...');
        setTimeout(() => this._connect(), 3000);
      };

      this.ws.onerror = (err) => {
        console.error('WebSocket error:', err);
        reject(err);
      };
    });
  },

  async _connectVoice() {
    return new Promise((resolve, reject) => {
      const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = location.hostname === 'localhost' ? 'localhost:8000' : location.host;
      this.wsVoice = new WebSocket(`${protocol}//${host}/ws/voice?user_id=${this.userId}`);

      this.wsVoice.onopen = () => {
        console.log('✅ Voice WebSocket connected');
        resolve();
      };

      this.wsVoice.onmessage = (event) => {
        this._handleVoiceMessage(JSON.parse(event.data));
      };

      this.wsVoice.onerror = reject;
    });
  },

  // ── MESSAGE HANDLING ─────────────────────────────────

  _handleMessage(msg) {
    const { type } = msg;

    switch (type) {
      case 'connected':
        this.currentProvider = msg.provider?.provider_id || 'google';
        this.currentModel = msg.provider?.model || 'gemini-2.0-flash-exp';
        this._emit('providerChanged', msg.provider);
        break;

      case 'provider_state':
        this.currentProvider = msg.data?.provider_id || this.currentProvider;
        this._emit('providerChanged', msg.data);
        break;

      case 'pong':
        this._emit('ping', { time: Date.now() });
        break;

      default:
        this._emit(type, msg);
    }
  },

  _handleVoiceMessage(msg) {
    const { type } = msg;

    switch (type) {
      case 'ready':
        this._emit('voiceReady', msg);
        break;

      case 'voice_response':
        this._emit('voiceResponse', {
          transcript: msg.transcript,
          response: msg.response,
          audio: msg.audio,  // base64 TTS
          latency: Date.now() - (this._lastVoiceTime || Date.now()),
        });
        this._lastVoiceTime = null;
        break;

      case 'transcript':
        this._emit('transcript', msg);
        break;

      case 'error':
        this._emit('voiceError', msg);
        break;
    }
  },

  // ── PUBLIC API ───────────────────────────────────────

  // Text input → cognitive pipeline
  async ask(question) {
    if (!this.connected) throw new Error('Not connected');

    const startTime = Date.now();

    try {
      const response = await fetch('/raso/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question }),
      });

      const result = await response.json();

      this.metrics.llmLatency = Date.now() - startTime;
      this.metrics.totalLatency = this.metrics.llmLatency;

      // Add to context window
      this.contextWindow.push({ role: 'user', content: question });
      this.contextWindow.push({ role: 'assistant', content: result.answer });

      // Keep context window manageable
      if (this.contextWindow.length > 20) {
        this.contextWindow = this.contextWindow.slice(-20);
      }

      return result;
    } catch (err) {
      console.error('Ask failed:', err);
      throw err;
    }
  },

  // Voice input → cognitive pipeline (same pipeline as text)
  async askVoice(audioBlob) {
    if (!this.wsVoice || this.wsVoice.readyState !== WebSocket.OPEN) {
      throw new Error('Voice not connected');
    }

    this._lastVoiceTime = Date.now();

    // Convert blob to base64
    const reader = new FileReader();
    const audioBase64 = await new Promise((resolve) => {
      reader.onload = () => resolve(reader.result.split(',')[1]);
      reader.readAsDataURL(audioBlob);
    });

    // Send to voice pipeline - uses SAME cognitive pipeline as text
    this.wsVoice.send(JSON.stringify({
      type: 'audio',
      audio: audioBase64,
    }));

    // Wait for response
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Voice timeout')), 30000);

      this._handlers.voiceResponse = (msg) => {
        clearTimeout(timeout);
        resolve(msg);
        delete this._handlers.voiceResponse;
      };

      this._handlers.voiceError = (msg) => {
        clearTimeout(timeout);
        reject(new Error(msg.message));
        delete this._handlers.voiceError;
      };
    });
  },

  // Switch provider at runtime
  async switchProvider(providerType, model = null) {
    if (!this.ws) throw new Error('Not connected');

    this.ws.send(JSON.stringify({
      type: 'switch_provider',
      provider_type: providerType,
      model: model,
    }));

    // Wait for confirmation
    return new Promise((resolve) => {
      this._handlers.providerChanged = (state) => {
        if (state.provider_type === providerType) {
          this.currentProvider = providerType;
          this.currentModel = model || state.model;
          resolve(state);
          delete this._handlers.providerChanged;
        }
      };
    });
  },

  // Get memory stats
  async getMemoryStats() {
    try {
      const response = await fetch('/brain/stats');
      const stats = await response.json();
      this.memoryStats = stats;
      return stats;
    } catch (err) {
      console.error('Failed to get memory stats:', err);
      return null;
    }
  },

  // Get health status
  async getHealth() {
    try {
      const response = await fetch('/health');
      return await response.json();
    } catch (err) {
      console.error('Health check failed:', err);
      return null;
    }
  },

  // ── EVENT SYSTEM ─────────────────────────────────────

  on(event, handler) {
    this._handlers[event] = handler;
  },

  off(event) {
    delete this._handlers[event];
  },

  _emit(event, data) {
    if (this._handlers[event]) {
      this._handlers[event](data);
    }
  },

  // ── CLEANUP ─────────────────────────────────────────

  disconnect() {
    if (this.ws) this.ws.close();
    if (this.wsVoice) this.wsVoice.close();
    this.connected = false;
    this.voiceActive = false;
  },
};

// ── EXPORT ────────────────────────────────────────────
window.UnifiedRuntime = UnifiedRuntime;

// Auto-initialize on load if configured
if (document.currentScript.getAttribute('auto-init') !== 'false') {
  document.addEventListener('DOMContentLoaded', () => {
    UnifiedRuntime.initialize().catch(console.error);
  });
}