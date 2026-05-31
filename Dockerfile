FROM python:3.12-slim

WORKDIR /app

# Install dependencies directly (no editable install needed)
RUN pip install --no-cache-dir fastapi>=0.115.0 "uvicorn[standard]>=0.34.0"

# Copy simulation package
COPY simulation/ simulation/

EXPOSE 8000

CMD ["uvicorn", "simulation.app:app", "--host", "0.0.0.0", "--port", "8000"]
