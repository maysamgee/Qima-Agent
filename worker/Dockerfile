FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend /app/backend
COPY worker /app/worker
RUN pip install --no-cache-dir /app/backend && useradd --uid 10001 --create-home appuser && chown -R appuser:appuser /app
USER appuser
CMD ["python", "-m", "worker.app.main"]
