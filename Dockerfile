FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 QCAL_STORE=/data
WORKDIR /app
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml README.md ./
COPY qcal ./qcal
RUN pip install --no-cache-dir . && useradd -m qcal && mkdir -p /data && chown qcal /data
USER qcal
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["qcal", "serve", "--host", "0.0.0.0", "--port", "8000", "--store", "/data"]
