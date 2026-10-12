# Сервис проверки чертежей для ERP (HTTP API, порт 8765)
#   docker build -t drawing-checker .
#   docker run -d -p 8765:8765 -e CHECKING_API_TOKEN=секрет drawing-checker
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY checking ./checking
COPY web ./web
COPY app.py config.json ./
ENV CHECKING_HOST=0.0.0.0 CHECKING_PORT=8765 PYTHONUTF8=1
EXPOSE 8765
CMD ["python", "app.py", "--no-browser"]
