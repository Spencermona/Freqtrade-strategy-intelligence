FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MPLCONFIGDIR=/app/.mpl-cache
ENV PYTHON_EXECUTABLE=python

WORKDIR /app

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY README.md .
COPY scripts ./scripts
COPY config ./config

RUN mkdir -p /app/results /app/Strategies /app/short_timeframe_strategies /app/strategies_too_large /app/strategies_error /app/.mpl-cache

EXPOSE 7860

CMD ["python", "scripts/config_server.py"]
