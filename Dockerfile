# Image de base Python
FROM python:3.11-slim

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers requirements et code
COPY requirements.txt .
COPY . .

# Installer les dépendances
RUN pip install --no-cache-dir -r requirements.txt

# Définir la commande pour démarrer le bot
CMD ["python", "bot.py"]
