FROM python:3.11-slim

# HF_HOME deliberately lives outside /data. /data is a mounted volume in
# docker-compose (`ragdata:/data`), and a pre-existing non-empty volume shadows
# whatever the image ships at that path — which would silently hide the
# cross-encoder weights baked in below.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# System deps for lxml / sentence-transformers wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU-only PyTorch first. torch is pulled transitively by
# sentence-transformers; the default Linux wheel now declares CUDA 13 deps
# (nvidia-cudnn/nccl/cublas/…), which add ~3-5GB of GPU libraries that are dead
# weight on this CPU deployment. Pinning the CPU index keeps the image lean; the
# subsequent `-r requirements.txt` resolves against the already-satisfied torch.
RUN pip install --upgrade pip \
    && pip install --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

# Bake the cross-encoder weights into the image. Without this, the first /ask
# after every cold start pulls ~1.1GB from HuggingFace onto an ephemeral disk —
# and reranker.py catches a download failure and falls back to lexical scoring
# *silently*, so a failed pull looks like a healthy boot while the headline
# reranking feature is quietly off. Kept above `COPY . .` so application code
# changes don't invalidate this layer. ARG mirrors settings.reranker_model.
ARG RERANKER_MODEL=BAAI/bge-reranker-base
RUN mkdir -p /opt/hf \
    && python -c "from sentence_transformers import CrossEncoder; CrossEncoder('${RERANKER_MODEL}', device='cpu')"

# Baking the weights is necessary but not sufficient: huggingface_hub still
# contacts the Hub to revalidate a cached model before loading it, so a Hub
# outage or rate-limit at cold start would raise — and reranker.py catches that
# and degrades to lexical scoring silently. Pinning offline mode forces the
# baked cache to be authoritative and removes the network from the boot path.
# Set *after* the download above, which needs the network.
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY . .

RUN mkdir -p /data/raw /data/processed

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
