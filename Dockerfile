FROM mcr.microsoft.com/playwright/python:v1.42.0

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Run the bot
CMD ["python", "BotSentimental.py"] 