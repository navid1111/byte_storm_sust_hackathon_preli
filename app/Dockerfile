FROM python:3.12-slim

# Local build context for this Dockerfile is the `app/` directory.
WORKDIR /app

# Install runtime dependencies first so this layer is cached unless
# requirements.txt actually changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source.
COPY . .

# `app/main.py` does `from api.routes import router`, so when the build
# context is `app/` the import path resolves directly and we run `main:app`.
#
# Bind to 0.0.0.0 so the container is reachable from outside.
# PORT defaults to 8000 but is overridable via the hosting platform's
# standard `PORT` env var (Render / Railway / Fly / Heroku / Poridhi).
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]