FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/data/hf

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

COPY . .

RUN mkdir -p /data/raw /data/processed /data/hf

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
