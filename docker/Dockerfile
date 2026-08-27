FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./server/
COPY server_sse.py .

ENV PYTHONUNBUFFERED=1
ENV MCP_PORT=8765

EXPOSE 8765

CMD ["python", "server_sse.py"]
