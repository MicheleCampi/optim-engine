FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY solver/ solver/
COPY routing/ routing/
COPY packing/ packing/
COPY api/ api/
ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
