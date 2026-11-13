FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The real Ibagy form is a JavaScript widget, so real submissions need Chromium. It is opt-in
# (it adds ~400 MB to the image and ~300 MB of RAM while a submission runs), keeping small hosts light:
#   docker compose build --build-arg INSTALL_BROWSER=true backend
ARG INSTALL_BROWSER=false
RUN if [ "$INSTALL_BROWSER" = "true" ]; then       playwright install --with-deps chromium-headless-shell && rm -rf /var/lib/apt/lists/*;     fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
