"""Étape 3a : essais de l'API Web avec Soloist.

1. Lire la liste des titres de la playlist de test.
2. Trouver Soloist dans la liste des appareils Spotify.
3. Démarrer la playlist à un titre précis sur Soloist, puis vérifier avec soloist ctl.

Usage : python3 outils/essai_3a.py
"""
import json
import subprocess
import time
from pathlib import Path

from spotify_web import api

PLAYLIST = "1H4H68b72jTyB5rdByrARt"
NOM_APPAREIL = "Test Soloist"
SOLOIST = [str(Path.home() / "soloist-test" / "soloist"), "ctl", "--ws", "127.0.0.1:9090"]


def ctl(*args):
    return subprocess.run(SOLOIST + list(args), capture_output=True, text=True, timeout=10).stdout


def etat_soloist():
    d = json.loads(ctl("now", "--json"))
    item = d.get("item") or {}
    nom = ((item.get("decorations") or {}).get("identity") or {}).get("name")
    return {
        "statut": d.get("status"),
        "contexte": (d.get("context") or {}).get("uri"),
        "titre": nom,
        "volume": d.get("volume"),
    }


def titres():
    code, d = api("GET", f"/playlists/{PLAYLIST}/items", params={"limit": 50})
    print(f"1. Liste des titres : réponse {code}")
    if code != 200:
        print("   ", str(d)[:300])
        return []
    liste = []
    for x in d.get("items", []):
        t = x.get("item") or x.get("track") or {}
        artistes = ", ".join(a.get("name", "") for a in t.get("artists", []))
        images = (t.get("album") or {}).get("images") or []
        liste.append((t.get("uri"), t.get("name")))
        print(f"   {len(liste)}. {t.get('name')} - {artistes} "
              f"({len(images)} images, {t.get('duration_ms', 0) // 1000} s)")
    print(f"   Total annoncé par Spotify : {d.get('total')}")
    return liste


def appareil():
    code, d = api("GET", "/me/player/devices")
    print(f"2. Appareils : réponse {code}")
    if code != 200:
        print("   ", str(d)[:300])
        return None
    trouve = None
    for a in d.get("devices", []):
        print(f"   - {a.get('name')} ({a.get('type')}), actif : {a.get('is_active')}")
        if a.get("name") == NOM_APPAREIL:
            trouve = a.get("id")
    return trouve


def demarrer_a(device_id, uri_titre, rang):
    print(f"3. Démarrer la playlist au titre n°{rang} sur Soloist")
    print("   Avant :", etat_soloist())
    code, d = api("PUT", "/me/player/play", params={"device_id": device_id}, corps={
        "context_uri": f"spotify:playlist:{PLAYLIST}",
        "offset": {"uri": uri_titre},
        "position_ms": 0,
    })
    print(f"   Réponse {code}", "" if code in (200, 202, 204) else str(d)[:300])
    time.sleep(3)
    print("   Après :", etat_soloist())


if __name__ == "__main__":
    liste = titres()
    device_id = appareil()
    if liste and device_id:
        # Choisir un titre différent de celui en cours, pour que l'essai prouve quelque chose.
        en_cours = etat_soloist()["titre"]
        rang = next((i + 1 for i, (_, nom) in enumerate(liste) if i > 0 and nom != en_cours), 1)
        demarrer_a(device_id, liste[rang - 1][0], rang)
        ctl("pause")
        print("   (mis en pause)")
    elif not device_id:
        print("Soloist n'apparaît pas dans les appareils : essai 3 non fait.")
