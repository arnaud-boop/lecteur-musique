"""Playlists, titres et images, lus avec l'API Web de Spotify.

Tout est gardé dans local/cache/ : si Internet manque, le lecteur affiche
la dernière version connue.
"""
import hashlib
import json
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

from . import config
from .spotify_web import api

ATTENTE_APRES_ECHEC = 30  # secondes avant de réessayer une image


def _id(uri):
    return uri.rsplit(":", 1)[-1]


def _image_adaptee(images, largeur_min):
    """Choisit la plus petite image d'au moins `largeur_min` pixels."""
    images = sorted((i for i in images or [] if i.get("url")), key=lambda i: i.get("width") or 0)
    for i in images:
        if (i.get("width") or 0) >= largeur_min:
            return i["url"]
    return images[-1]["url"] if images else None


class Bibliotheque:
    def __init__(self, sur_change):
        self.sur_change = sur_change  # appelé quand une image vient d'arriver
        self.dossier = config.CACHE
        (self.dossier / "playlists").mkdir(parents=True, exist_ok=True)
        (self.dossier / "images").mkdir(parents=True, exist_ok=True)
        self._images = {}
        self._en_cours = set()
        self._echecs = {}
        self._verrou = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="image")
        self._appareil = None

    # Playlists

    def charger_playlist(self, uri):
        pid = _id(uri)
        fichier = self.dossier / "playlists" / f"{pid}.json"
        try:
            code, meta = api("GET", f"/playlists/{pid}", params={"fields": "name,images"})
            if code != 200:
                raise RuntimeError(f"playlist : réponse {code}")
            titres = []
            chemin, params = f"/playlists/{pid}/items", {"limit": 50}
            while chemin:
                code, page = api("GET", chemin, params=params)
                if code != 200:
                    raise RuntimeError(f"titres : réponse {code}")
                for x in page.get("items", []):
                    t = x.get("item") or x.get("track") or {}
                    if not t.get("uri"):
                        continue
                    images = (t.get("album") or {}).get("images") or t.get("images") or []
                    # Un fichier local ajouté à une playlist peut avoir un artiste sans nom.
                    artistes = ", ".join(n for n in (a.get("name") for a in t.get("artists") or []) if n)
                    # Épisode de podcast (histoires) : l'« album » est le nom de l'émission.
                    emission = (t.get("show") or {}).get("name") or (t.get("album") or {}).get("name") or ""
                    titres.append({
                        "uri": t["uri"],
                        "nom": t.get("name") or "?",
                        "artistes": artistes or emission,
                        "image": _image_adaptee(images, 300),
                        "vignette": _image_adaptee(images, 60),
                        "duree_ms": t.get("duration_ms") or 0,
                        "jouable": t.get("is_playable", True) is not False,
                    })
                chemin, params = page.get("next"), None
            playlist = {
                "uri": uri,
                "nom": meta.get("name") or "?",
                "image": _image_adaptee(meta.get("images"), 300),
                "titres": titres,
            }
            fichier.write_text(json.dumps(playlist, ensure_ascii=False))
            return playlist
        except Exception:
            if fichier.exists():
                return json.loads(fichier.read_text())
            raise

    # Images (téléchargées en arrière-plan)

    def image(self, url, taille):
        """Renvoie l'image redimensionnée, ou None si elle n'est pas encore prête."""
        if not url:
            return None
        cle = (url, taille)
        with self._verrou:
            if cle in self._images:
                return self._images[cle]
            if cle in self._en_cours or time.time() - self._echecs.get(url, 0) < ATTENTE_APRES_ECHEC:
                return None
            self._en_cours.add(cle)
        self._pool.submit(self._preparer, url, taille)
        return None

    def _preparer(self, url, taille):
        cle = (url, taille)
        try:
            fichier = self.dossier / "images" / (hashlib.sha1(url.encode()).hexdigest() + ".jpg")
            if not fichier.exists():
                req = urllib.request.Request(url, headers={"User-Agent": "lecteur-musique"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    fichier.write_bytes(r.read())
            img = Image.open(fichier).convert("RGB").resize((taille, taille), Image.LANCZOS)
            with self._verrou:
                self._images[cle] = img
            self.sur_change()
        except Exception:
            with self._verrou:
                self._echecs[url] = time.time()
        finally:
            with self._verrou:
                self._en_cours.discard(cle)

    # Lecture à un titre précis, avec l'API Web

    def demarrer(self, nom_appareil, contexte, titre_uri=None):
        """Démarre `contexte` sur Soloist, au titre `titre_uri`. Renvoie True si accepté."""
        appareil = self._trouver_appareil(nom_appareil)
        if not appareil:
            return False
        corps = {"context_uri": contexte}
        if titre_uri:
            corps["offset"] = {"uri": titre_uri}
        code, _ = api("PUT", "/me/player/play", params={"device_id": appareil}, corps=corps)
        if code == 404:
            self._appareil = None  # l'identifiant a changé : on le recherchera
        return code in (200, 202, 204)

    def _trouver_appareil(self, nom):
        if self._appareil:
            return self._appareil
        code, d = api("GET", "/me/player/devices")
        if code == 200:
            for a in d.get("devices", []):
                if a.get("name") == nom:
                    self._appareil = a.get("id")
        return self._appareil
