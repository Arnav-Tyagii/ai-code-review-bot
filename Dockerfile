FROM python:3.12.10-slim

WORKDIR /app

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create and switch to non-root user
RUN useradd -m botuser && chown -R botuser /app
USER botuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "webhook.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
