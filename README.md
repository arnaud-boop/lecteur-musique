# lecteur-musique

Lecteur de musique et d'histoires sur Raspberry Pi.

Ce dépôt est public. Il ne contient aucune donnée personnelle, aucune clé et
aucun jeton. Les réglages et l'état du lecteur sont dans un dépôt privé séparé.

## Lancer le simulateur sur le Mac

1. Lancer Soloist dans Terminal (voir les notes du projet).
2. Dans le dossier du dépôt : `python3 -m lecteur`
3. Ouvrir http://127.0.0.1:8090 dans le navigateur.

Les boutons se cliquent à la souris, ou avec les touches A, B, X et Y du clavier.

## Les boutons

A en haut à gauche, B en bas à gauche, X en haut à droite, Y en bas à droite.

| Bouton | Partout | Écran Lecture |
|---|---|---|
| A | Monter | Titre précédent. Maintenu 1 s : j'aime |
| B | Descendre | Titre suivant. Maintenu 1 s : je n'aime pas |
| X | Ouvrir, choisir | Pause ou lecture |
| Y | Retour | Retour à la liste des titres |

- Y maintenu 3 s : veille. En veille, Y maintenu 2 s : rallumage.
- X et Y maintenus 5 s : mode configuration.

## Protections

- Seules les playlists de `local/lecteur.json` peuvent jouer. Tout autre contenu
  (par exemple lancé par erreur depuis le téléphone d'un parent) est arrêté, et
  le lecteur revient à la musique de l'enfant.
- Le volume reste celui choisi par les parents.
- Lecture dans l'ordre, en boucle sur la playlist.

## Contenu

- `lecteur/app.py` : écrans, boutons et protections.
- `lecteur/rendu.py` : dessin des écrans (240 x 240 pixels).
- `lecteur/simulateur.py` : écran et boutons dans le navigateur.
- `lecteur/soloist.py` : connexion à l'API WebSocket de Soloist.
- `lecteur/bibliotheque.py` : playlists, titres et images (API Web de Spotify).
- `lecteur/spotify_web.py` : connexion à l'API Web de Spotify (méthode PKCE,
  sans secret). Première connexion : `python3 lecteur/spotify_web.py`
- `outils/essai_3a.py` : essais de l'étape 3a.

## Fichiers locaux (jamais dans Git)

Le dossier `local/` est ignoré par Git. Il contient :

- `config.json` : `{"spotify_client_id": "..."}`
- `spotify_token.json` : le jeton Spotify
- `lecteur.json` : nom de Soloist, volume, playlists autorisées
- `journal.jsonl` : les « j'aime » et « je n'aime pas »
- `cache/` : playlists et images gardées pour aller plus vite
