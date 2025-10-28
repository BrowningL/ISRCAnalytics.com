FROM mcr.microsoft.com/playwright/python:v1.45.0-jammy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy all worker files
COPY . /app/

# Set environment variable for the main command
ENV PYTHONUNBUFFERED=1

# Default command - can be overridden
CMD ["python", "main.py"]
