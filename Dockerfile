# Use an official Ubuntu runtime as a parent image
FROM eclipse-temurin:25-jre-alpine

# Set the working directory in the container to /app
WORKDIR /app

# Install python3
RUN apk add --no-cache python3 py3-pip

# Cache only the requirements.txt for installation
COPY requirements.txt /app/

# Install python libs, git, jre
RUN python3 -m venv .venv
RUN source .venv/bin/activate && pip install --no-cache-dir -r requirements.txt