FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости напрямую, чтобы ничего не ломалось
RUN pip install --no-cache-dir aiogram==3.13.1 Flask==3.0.3 werkzeug==3.0.3

COPY . .

CMD ["python", "bot.py"]
