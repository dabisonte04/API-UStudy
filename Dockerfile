FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything else
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Ejecutar migración al iniciar
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]