FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY solver/ solver/
COPY api/ api/
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-8000}/health')"
ENV PORT=8000
EXPOSE ${PORT}
CMD uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1
