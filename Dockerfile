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

# Copy directories
COPY agents/ ./agents/
COPY config/ ./config/
COPY models/ ./models/

# ── ENV VARIABLES ─────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV HOST=0.0.0.0

# ── EXPOSE PORT (HF Spaces uses 7860) ───────────────────
EXPOSE 7860

# ── STARTUP ─────────────────────────────────────────────
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]