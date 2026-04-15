FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8050

ENV PYTHONUNBUFFERED=1
ENV USE_AZURE=true

CMD ["gunicorn", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "120", \
     "--access-logfile", "-", "--error-logfile", "-", "app:server"]
