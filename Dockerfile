# Voxel AI — configurable AI voice agent platform.
# Serves the FastAPI app (`app` in app.main) behind uvicorn on port 8000.

# 3.12 matches PYTHON_VERSION in render.yaml, so the container and the hosted
# deploy run the same interpreter.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# No apt packages needed: requirements.txt is trimmed to what the Vercel
# function bundle allows, which means asyncpg (manylinux wheels, no libpq) and
# no psycopg2 — so there is nothing here that needs a compiler or pg headers.

# requirements-server.txt, not requirements.txt: the latter is scoped to the
# serverless bundle and deliberately excludes uvicorn, which a long-lived
# container obviously needs.
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY . .

RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Uses the stdlib rather than curl so the image needs no apt layer at all.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
