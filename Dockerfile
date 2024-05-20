# Use an official Ubuntu runtime as a parent image
FROM ubuntu:latest

# Install Python latest, pip and Git
RUN apt-get update && \
    apt-get install -y software-properties-common && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y python3 python3-venv python3-dev python3-pip git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container to /app
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Create a virtual environment and install packages
RUN python3 -m venv venv && \
    . venv/bin/activate && \
    python3 -m pip install --upgrade pip && \
    python3 -m pip install --no-cache-dir -r requirements.txt

# Keep the container running
CMD ["tail", "-f", "/dev/null"]