FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libimage-exiftool-perl ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt
COPY mediasort/ mediasort/
COPY mediaserve/ mediaserve/
ENV LIBRARY_DIR=/data/library CATALOG_DB=/data/catalog.db \
    INCOMING_DIR=/data/incoming DEVICES_DB=/data/devices.db
EXPOSE 8787
CMD ["uvicorn", "mediaserve.app:app", "--host", "0.0.0.0", "--port", "8787"]
