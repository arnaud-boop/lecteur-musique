"""Accès à l'API Web de Spotify pour le lecteur.

Connexion avec la méthode PKCE : pas de « client secret ».
Le Client ID est lu dans local/config.json, et le jeton est gardé dans
local/spotify_token.json. Le dossier local/ n'est jamais envoyé sur GitHub.

Première connexion (ouvre le navigateur) :
    python3 outils/spotify_web.py
"""
import base64
import hashlib
import http.server
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LOCAL = RACINE / "local"
CONFIG = LOCAL / "config.json"
JETON = LOCAL / "spotify_token.json"

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = " ".join([
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
])
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API = "https://api.spotify.com/v1"


def client_id():
    return json.loads(CONFIG.read_text())["spotify_client_id"]


def _ecrire_jeton(data):
    LOCAL.mkdir(exist_ok=True)
    data["expires_at"] = time.time() + data.get("expires_in", 3600) - 60
    tmp = JETON.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.chmod(tmp, 0o600)
    tmp.replace(JETON)


def _post_token(params):
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode(params).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def connexion(delai_s=300):
    """Ouvre la page de connexion Spotify et attend la réponse sur 127.0.0.1:8888."""
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    etat = secrets.token_urlsafe(16)
    resultat = {}

    class Reponse(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            adresse = urllib.parse.urlparse(self.path)
            if adresse.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            q = urllib.parse.parse_qs(adresse.query)
            if q.get("state", [""])[0] != etat:
                resultat["erreur"] = "réponse inattendue (state)"
            elif "error" in q:
                resultat["erreur"] = q["error"][0]
            else:
                resultat["code"] = q.get("code", [""])[0]
            ok = "code" in resultat
            message = ("Connexion réussie. Tu peux fermer cet onglet." if ok
                       else "Échec de la connexion : " + resultat.get("erreur", "?"))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"<p style='font:20px sans-serif'>{message}</p>".encode())

        def log_message(self, *args):
            pass

    serveur = http.server.HTTPServer(("127.0.0.1", 8888), Reponse)
    serveur.timeout = 1
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id(),
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "scope": SCOPES,
        "state": etat,
    })
    print("Ouverture de la page de connexion Spotify dans le navigateur.", flush=True)
    webbrowser.open(url)
    fin = time.time() + delai_s
    while not resultat and time.time() < fin:
        serveur.handle_request()
    serveur.server_close()
    if "code" not in resultat:
        raise SystemExit("Connexion non terminée : " + resultat.get("erreur", "délai dépassé"))
    data = _post_token({
        "grant_type": "authorization_code",
        "code": resultat["code"],
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id(),
        "code_verifier": verifier,
    })
    _ecrire_jeton(data)
    print("Connexion réussie. Jeton enregistré dans local/ (hors de Git).")


def jeton():
    """Renvoie un jeton d'accès valide, renouvelé automatiquement si besoin."""
    if not JETON.exists():
        raise SystemExit("Pas de jeton : lance d'abord python3 outils/spotify_web.py")
    data = json.loads(JETON.read_text())
    if time.time() >= data.get("expires_at", 0):
        neuf = _post_token({
            "grant_type": "refresh_token",
            "refresh_token": data["refresh_token"],
            "client_id": client_id(),
        })
        neuf.setdefault("refresh_token", data["refresh_token"])
        _ecrire_jeton(neuf)
        data = json.loads(JETON.read_text())
    return data["access_token"]


def api(methode, chemin, corps=None, params=None):
    """Appelle l'API Web. Renvoie (code HTTP, réponse JSON ou texte)."""
    url = chemin if chemin.startswith("http") else API + chemin
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(url, data=data, method=methode, headers={
        "Authorization": "Bearer " + jeton(),
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            texte = r.read()
            return r.status, (json.loads(texte) if texte else None)
    except urllib.error.HTTPError as e:
        texte = e.read()
        try:
            return e.code, json.loads(texte)
        except ValueError:
            return e.code, texte.decode(errors="replace")[:300]


if __name__ == "__main__":
    connexion()
