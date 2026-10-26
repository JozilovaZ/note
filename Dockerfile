FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DB_PATH=/app/data/bot.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# bot root huquqisiz ishlaydi; baza /app/data papkasida (volume) saqlanadi
RUN useradd --create-home bot && mkdir -p /app/data && chown bot /app/data
USER bot

CMD ["python", "main.py"]
