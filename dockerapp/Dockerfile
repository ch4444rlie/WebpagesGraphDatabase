FROM python:3.9-slim

WORKDIR /app

# Install system dependencies for pyarrow
RUN apt-get update && apt-get install -y \
    curl \
    libffi-dev \
    python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/0.4.27/install.sh | sh && \
    mv /root/.cargo/bin/uv /usr/local/bin/uv

# Copy and install dependencies
COPY requirements.txt .
RUN uv pip install --no-cache-dir --system -r requirements.txt

# Copy app files
COPY app/main.py .
COPY app/db/ ./db/
COPY app/templates/ ./templates/

EXPOSE 5000

CMD ["python", "main.py"]