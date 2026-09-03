# Deploy target: Railway (or any host that builds a Dockerfile and passes $PORT).
# Root directory for this service in a monorepo host should be services/inference,
# so the COPY paths below are relative to that directory, not the repo root.

FROM python:3.11-slim

# libgl1/libglib2.0-0: opencv-python-headless and mediapipe still dlopen these
# even in "headless" mode. Without them the import fails at container start,
# not at build time, which is a much worse place to find out.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only PyTorch build first, matching .github/workflows/ci.yml -- the
# default PyPI wheel pulls in a multi-GB CUDA toolkit this service never
# uses, and this service is CPU-only by design (see README.md's Runtime notes).
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY . .
RUN pip install --no-cache-dir -e .

# Pretrained weights (spatial classifier, AASIST checkpoint, MediaPipe/YuNet
# models) download on first use into VERIFRAME_MODEL_CACHE_DIR, not at build
# time -- the first request after a cold start or redeploy is slow (~340MB+
# of downloads) unless that directory is backed by a persistent volume.
EXPOSE 8000
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
