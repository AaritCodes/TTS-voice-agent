# Use official Python lightweight image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Install system dependencies (ffmpeg is often required for audio processing fallback)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the AudioSocket port
EXPOSE 9090

# Run the Asterisk Server Python script
CMD ["python", "asterisk_server.py"]
