# RasoSpeak — Your Secondary Brain & AI Partner
# Base: AMD ROCm 6.2 + Python 3.11
# Runs on AMD Instinct MI300X via AMD Developer Cloud

FROM rocm/dev-ubuntu-22.04:latest

# Install Python 3.11 and pip + system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    ffmpeg \
    libsndfile1 \
    redis-server \
    curl \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && rm -rf /var/lib/apt/lists/*

LABEL maintainer="RasoSpeak Team"
LABEL description="RasoSpeak v2 — Agentic AI Speech Coach on AMD MI300X"

# ── WORKDIR ────────────────────────────────────────────
WORKDIR /app

# ── INSTALL PYTHON DEPENDENCIES ──────────────────────
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir torch torchvision torchaudio

# ── INSTALL PYTHON DEPS ────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── COPY APPLICATION ───────────────────────────────────
COPY *.py .
COPY *.js .
COPY *.html .
COPY *.css .

# ── ENVIRONMENT ────────────────────────────────────────
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV AMD_DEVICE=cuda
ENV ROCM_PATH=/opt/rocm

# AMD GPU visibility (set via docker run --device)
ENV HIP_VISIBLE_DEVICES=0

# ── PORTS ──────────────────────────────────────────────
# 8000: FastAPI (RasoSpeak backend)
# 8001: vLLM server
EXPOSE 8000 8001

# ── STARTUP SCRIPT ─────────────────────────────────────
CMD ["python", "main.py"]
