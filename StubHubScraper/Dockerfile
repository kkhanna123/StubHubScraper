FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY . .

CMD ["python", "run_forever.py"]
