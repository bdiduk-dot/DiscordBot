# Используем Python 3.12 slim образ (3.13 имеет проблемы совместимости с aiohttp)
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем requirements.txt
COPY requirements.txt .

# Устанавливаем build tools для компиляции C-расширений
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем зависимости (только pre-built wheels для aiohttp)
RUN pip install --no-cache-dir --only-binary aiohttp -r requirements.txt

# Копируем весь код
COPY . .

# Запуск бота
CMD ["python", "casino_bot.py"]
