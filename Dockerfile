# Use an official Python runtime as a parent image.
FROM python:3.11-slim

# Prevent Python from writing pyc files to disk & enable unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory inside the container.
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Create directory for SQLite database and set permissions
RUN mkdir -p /app/data && \
    chmod 777 /app/data

# Run migrations
# RUN python manage.py migrate --noinput

# Run as non-root user
RUN useradd -m myuser
USER myuser

EXPOSE 8000

# Command to run the application
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]