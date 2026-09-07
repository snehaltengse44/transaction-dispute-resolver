FROM python:3.11-slim

# Tesseract binary — this is why we need Docker, not Render's native runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Tesseract is on PATH inside the container at this default location —
# set TESSERACT_CMD accordingly in Render's environment variables
ENV TESSERACT_CMD=/usr/bin/tesseract

EXPOSE 8501

CMD ["streamlit", "run", "frontend/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]