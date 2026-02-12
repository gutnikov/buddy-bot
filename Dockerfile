FROM python:3.12-slim

WORKDIR /app

# System dependencies + Node.js 20 (for Claude Code CLI and mcp-remote)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI and mcp-remote globally
RUN npm install -g @anthropic-ai/claude-code mcp-remote

# Python dependencies
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# MCP config
COPY config/mcp-config.json ./config/

# Create data directory
RUN mkdir -p /data

CMD ["python", "-m", "buddy_bot.main"]
