FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=300 \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple \
        "torch>=2.5.0" "torchaudio>=2.5.0" \
 && pip install --no-cache-dir --default-timeout=300 -r requirements.txt

COPY . .

RUN python3 -m compileall -q /app \
    && python3 -m compileall -q /usr/local/lib/python3.11/site-packages/ \
    2>/dev/null; exit 0

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
