FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8190
CMD ["gunicorn", "-b", "0.0.0.0:8190", "-w", "1", "--threads", "16", "-t", "180", "app:app"]
