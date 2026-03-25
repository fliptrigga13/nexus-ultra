FROM python:3.11-slim

WORKDIR /app

# Install Node.js for server.cjs
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt* ./
RUN pip install --no-cache-dir requests redis praw python-dotenv faiss-cpu numpy 2>/dev/null || true

# Node dependencies
COPY package*.json ./
RUN npm install --omit=dev 2>/dev/null || true

# Copy application
COPY . .

# Default command (overridden by docker-compose)
CMD ["python", "-X", "utf8", "-u", "nexus_swarm_loop.py"]
