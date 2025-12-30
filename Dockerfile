# Use an official Ubuntu runtime as a parent image
FROM eclipse-temurin:21-jre-alpine

# Set the working directory in the container to /app
WORKDIR /app

# Get UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/


# Install python libs
RUN adduser -D -u 1000 mcuser && \
    chown mcuser:mcuser /app
USER mcuser
COPY pyproject.toml src/start.py uv.lock /app/
RUN uv sync
CMD ["uv", "run", "start.py"]