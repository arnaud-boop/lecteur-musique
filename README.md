# lecteur-musique

Lecteur de musique et d'histoires sur Raspberry Pi.

Ce dépôt est public. Il ne contient aucune donnée personnelle, aucune clé et
aucun jeton. Les réglages et l'état du lecteur sont dans un dépôt privé séparé.

## Contenu

- `outils/spotify_web.py` : connexion à l'API Web de Spotify (méthode PKCE,
  sans secret) et appels à l'API.
- `outils/essai_3a.py` : essais de l'étape 3a (liste des titres d'une playlist,
  démarrage d'une playlist à un titre précis sur Soloist).

## Fichiers locaux (jamais dans Git)

Le dossier `local/` est ignoré par Git. Il contient :

- `config.json` : `{"spotify_client_id": "..."}`
- `spotify_token.json` : le jeton Spotify, créé par
  `python3 outils/spotify_web.py`
