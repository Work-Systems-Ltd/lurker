FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY serve.py .

EXPOSE 8080

CMD ["uvicorn", "serve:app", "--host", "0.0.0.0", "--port", "8080"]
