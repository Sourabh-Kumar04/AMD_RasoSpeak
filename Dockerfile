# RasoSpeak — HuggingFace Space Docker
# Full-stack: FastAPI backend + Custom HTML/CSS UI

FROM python:3.11-slim

# ── SYSTEM DEPENDS ───────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── COPY FILES ────────────────────────────────────────────
COPY requirements.txt .

# Install dependencies first (layer caching)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY main.py .
COPY app.py .
COPY index.html .
COPY styles.css .
COPY app.js .
COPY state.js .
COPY ui.js .
COPY speech.js .
COPY nlp.js .

# Copy agent files (at root level in Space)
COPY analytics_agent.py ./agents/analytics_agent.py
COPY base_agent.py ./agents/base_agent.py
COPY coaching_agent.py ./agents/coaching_agent.py
COPY document_agent.py ./agents/document_agent.py
COPY notification_agent.py ./agents/notification_agent.py
COPY partner_agent.py ./agents/partner_agent.py
COPY qa_agent.py ./agents/qa_agent.py
COPY recording_agent.py ./agents/recording_agent.py
COPY scoring_agent.py ./agents/scoring_agent.py
COPY search_agent.py ./agents/search_agent.py
COPY segmentation_agent.py ./agents/segmentation_agent.py
COPY session_memory_agent.py ./agents/session_memory_agent.py
COPY shared_memory_agent.py ./agents/shared_memory_agent.py
COPY transcription_agent.py ./agents/transcription_agent.py
COPY wake_word_agent.py ./agents/wake_word_agent.py

# Copy config files
COPY prompts.py ./config/prompts.py
COPY settings.py ./config/settings.py

# Copy model files
COPY schemas.py ./models/schemas.py

# ── ENV VARIABLES ─────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0

# ── EXPOSE PORT (HF Spaces uses 7860) ───────────────────
EXPOSE 7860

# ── STARTUP ─────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]