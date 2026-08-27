FROM eclipse-temurin:21-jre-alpine

WORKDIR /app

# Get UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install python libs
RUN adduser -D -u 1000 mcuser && \
    chown mcuser:mcuser /app
USER mcuser
COPY pyproject.toml uv.lock /app/
RUN uv sync
COPY src/start.py # Copy src code after installed libs are cached

ENV PYTHONUNBUFFERED=1
# https://github.com/astral-sh/uv/issues/12650
CMD ["uv", "run", "--no-cache", "--no-sync", "start.py"] 