FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Instalar ffmpeg para o pydub
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar apenas os arquivos necessários, excluindo arquivos de teste
COPY main.py .
COPY sales_builder_status_checker.py .
COPY evo_api_v2.py .
COPY README.md .
COPY CONTRIBUTING.md .
COPY cloudbuild.yaml .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"] 