# Lightweight, rootless init image; no third-party Python deps (stdlib only) => nothing to pin.
FROM python:3.12.11-slim-bookworm
RUN groupadd -g 10001 app && useradd -u 10001 -g 10001 -m -s /usr/sbin/nologin app
COPY docker/downloader/download_model.py /app/download_model.py
USER 10001:10001
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python", "/app/download_model.py"]
