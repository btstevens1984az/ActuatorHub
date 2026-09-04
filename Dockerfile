FROM node:22-alpine AS frontend-build
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY backend /app/backend
COPY --from=frontend-build /ui/dist /app/frontend/dist
ENV PYTHONPATH=/app/backend
ENV MQTT_HOST=mosquitto
ENV MQTT_PORT=1883
EXPOSE 8788
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8788"]
