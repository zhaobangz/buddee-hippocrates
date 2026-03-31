# Use Python 3.12 for maximum performance in clinical workflows
FROM python:3.12-slim

# System setup for Medical-grade OCR (OpenCV/EasyOCR), RAG, and Audio
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    portaudio19-dev \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Enable low-level optimizations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install clinical dependencies independently for cache efficiency
COPY requirements.txt ./
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Copy source code and audit/memory persistence
COPY . .

# Expose Clinical Backend (8000) and Web Terminal (3000)
EXPOSE 8000 3000

# Start both services using a simplified launcher
CMD ["bash", "run-web.sh"]
