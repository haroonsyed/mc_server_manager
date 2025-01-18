# Use an official Ubuntu runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container to /app
WORKDIR /app

# Cache only the requirements.txt for installation
COPY requirements.txt /app/

# Install python libs, git, jre
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    default-jre \
    && python3 -m pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*