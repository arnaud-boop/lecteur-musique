"""Réglages du lecteur.

Les réglages sont dans local/lecteur.json (hors de Git). Plus tard, ils
viendront du dépôt privé lecteur-musique-data.
"""
import json
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LOCAL = RACINE / "local"
CACHE = LOCAL / "cache"
FICHIER = LOCAL / "lecteur.json"

DEFAUT = {
    "nom_appareil": "Test Soloist",   # nom de Soloist dans la liste des appareils Spotify
    "soloist_ws": "127.0.0.1:9090",   # adresse de l'API WebSocket de Soloist
    "volume": 30,                     # volume fixé par les parents (0 à 100)
    "playlists": [],                  # adresses spotify:playlist:... autorisées, dans l'ordre
}


def charger():
    LOCAL.mkdir(exist_ok=True)
    if not FICHIER.exists():
        FICHIER.write_text(json.dumps(DEFAUT, indent=2, ensure_ascii=False) + "\n")
    cfg = dict(DEFAUT)
    cfg.update(json.loads(FICHIER.read_text()))
    return cfg
