# Use an official Ubuntu runtime as a parent image
FROM ubuntu:latest

# Install Python latest, pip and Git
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3 python3-dev python3-pip git default-jre firefox && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install packages
RUN python3 -m pip install --no-cache-dir -r requirements.txt --break-system-packages

# Keep the container running
CMD ["python3", "start.py"]