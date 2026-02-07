# Используем легкий образ Python
FROM python:3.11-slim

# Рабочая директория
WORKDIR /app

# Копируем зависимости и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

ENV PYTHONUNBUFFERED=1

# Запускаем бота
CMD ["python", "main.py"]
