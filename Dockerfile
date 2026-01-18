# Use uv's ARM64 Python base image (required by AgentCore Runtime)
FROM --platform=linux/arm64 ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Copy uv files
COPY pyproject.toml uv.lock ./

# Install dependencies (including strands-agents and bedrock-agentcore)
RUN uv sync --frozen --no-cache

# Copy agent file
COPY agent.py ./

# Expose port
EXPOSE 8080

# Run application using BedrockAgentCoreApp
CMD ["uv", "run", "python", "agent.py"]
