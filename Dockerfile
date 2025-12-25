# Use an official Ubuntu runtime as a parent image
FROM eclipse-temurin:21-jre-alpine

# Set the working directory in the container to /app
WORKDIR /app

# Get UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install python libs
COPY pyproject.toml .python-version uv.lock /app/
RUN uv sync