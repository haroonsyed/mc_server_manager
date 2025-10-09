# Use an official Ubuntu runtime as a parent image
FROM eclipse-temurin:21-jre-alpine

# Set the working directory in the container to /app
WORKDIR /app

# Install python3
RUN apk add --no-cache python3 py3-pip

# Install python libs
COPY requirements.txt /app/
RUN pip install --no-cache-dir --break-system-packages -r requirements.txt