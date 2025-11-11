# Build a reproducible runner that you can use locally and in ECS
FROM mcr.microsoft.com/playwright/python:v1.47.2-jammy

WORKDIR /app
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps

COPY app /app/app
COPY .env.example /app/.env.example

# By default we just show help
CMD ["python", "-m", "app.main", "--help"]
