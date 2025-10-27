# Bot planning
Bot discord pour récupérer le planning du CNAM et l'envoyer sur discord sous forme d'image

Pour le lancer pour vous :
  - faites un bot sur le dev portal de discord (discord.dev)
  - faites un ".env" dans le dossier du projet et faites 2 variables : DISCORD_TOKEN pour le token du bot et EDT_PATH pour l'url du Google Sheets (avec /export?format=csv à la fin)
  - créer le docker avec la commande ci-dessous
    CREER L'IMAGE
    docker build -t bot-planning .
  - lancer le avec la commande bash ou powershell
    BASH
    ```bash
    docker run -d --name bot-planning \
      --env-file .\.env \\
      --restart always \
      bot-planning:latest
    ```

    POWERSHELL
    ```pws
    docker run -d --name bot-planning `
      --env-file .\.env `
      --restart always `
      bot-planning:latest
    ```
