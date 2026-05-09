# RasoSpeak v2 — Dockerfile
# Base: AMD ROCm 6.1 + Python 3.11
# Runs on AMD Instinct MI300X via AMD Developer Cloud

FROM rocm/pytorch:rocm6.1_ubuntu22.04_py3.11_pytorch_2.1.2

LABEL maintainer="RasoSpeak Team"
LABEL description="RasoSpeak v2 — Agentic AI Speech Coach on AMD MI300X"

# ── SYSTEM DEPS ────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    redis-server \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── WORKDIR ────────────────────────────────────────────
WORKDIR /app

# ── INSTALL vLLM WITH ROCm BACKEND ────────────────────
RUN pip install --no-cache-dir \
    vllm \
    --extra-index-url https://download.pytorch.org/whl/rocm6.1

# ── INSTALL PYTHON DEPS ────────────────────────────────
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── COPY APPLICATION ───────────────────────────────────
COPY backend/ ./backend/
COPY index.html .
COPY css/ ./css/
COPY js/ ./js/

# ── ENVIRONMENT ────────────────────────────────────────
ENV PYTHONPATH=/app/backend
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
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
