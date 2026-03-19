FROM python:3.11-slim

WORKDIR /app

# Stratégie de cache : dépendances d'abord, code source ensuite
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# AMÉLIORATION 5 : gunicorn remplace le serveur de développement Flask
# --workers 2  : 2 processus worker (adapté à un conteneur léger)
# --timeout 60 : coupe les requêtes qui dépassent 60 secondes
# --access-logfile - : logs d'accès sur stdout (visible dans docker logs)
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "2", "--timeout", "60", "--access-logfile", "-", "app:app"]
