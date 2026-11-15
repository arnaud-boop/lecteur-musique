"""Simulateur dans le navigateur : l'écran 240 x 240 et les 4 boutons.

Page locale sur http://127.0.0.1:8090. Les boutons se cliquent à la souris
ou avec les touches A, B, X et Y du clavier (maintenir pour un appui long).
"""
import io
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

PAGE = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Simulateur du lecteur</title>
<style>
  :root { --fond: #0d1020; --boitier: #2a2f45; --bord: #3a4060; --texte: #e8eaf4; --gris: #9aa2c0; --accent: #ffc740; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; background: var(--fond); color: var(--texte);
         font: 15px/1.4 -apple-system, system-ui, sans-serif; display: flex; flex-direction: column;
         align-items: center; justify-content: center; gap: 18px; padding: 16px; }
  .boitier { display: grid; grid-template-columns: auto auto auto; gap: 14px; align-items: stretch;
             background: var(--boitier); border: 2px solid var(--bord); border-radius: 28px; padding: 18px; }
  .colonne { display: flex; flex-direction: column; justify-content: space-between; padding: 16px 0; }
  .ecran { width: min(480px, calc(100vw - 190px)); aspect-ratio: 1; border-radius: 10px; overflow: hidden;
           background: #000; box-shadow: inset 0 0 0 2px #000; }
  .ecran img { width: 100%; height: 100%; display: block; }
  button { width: 52px; height: 52px; border-radius: 50%; border: 2px solid var(--bord); background: #1b1f33;
           color: var(--texte); font-size: 18px; font-weight: 700; cursor: pointer; touch-action: none;
           user-select: none; -webkit-user-select: none; }
  button.appuye { background: var(--accent); color: #111; border-color: var(--accent); }
  .aide { color: var(--gris); max-width: 620px; text-align: center; }
  .aide b { color: var(--texte); }
  .etat { color: var(--gris); font-size: 13px; min-height: 18px; }
</style>
</head>
<body>
  <div class="boitier">
    <div class="colonne"><button data-nom="A">A</button><button data-nom="B">B</button></div>
    <div class="ecran"><img id="ecran" alt="Écran du lecteur" src="/ecran.png"></div>
    <div class="colonne"><button data-nom="X">X</button><button data-nom="Y">Y</button></div>
  </div>
  <div class="etat" id="etat"></div>
  <p class="aide">Clique sur les boutons ou utilise les touches <b>A</b>, <b>B</b>, <b>X</b> et <b>Y</b> du clavier.
  Maintiens un bouton pour un appui long : <b>A</b> ou <b>B</b> 1 s sur l'écran de lecture (j'aime, je n'aime pas),
  <b>Y</b> 3 s pour éteindre, puis <b>Y</b> 2 s pour rallumer, <b>X</b> et <b>Y</b> ensemble 5 s pour la configuration.</p>
<script>
  const img = document.getElementById('ecran');
  const etat = document.getElementById('etat');
  const enfonces = new Set();
  const boutons = {};
  document.querySelectorAll('button[data-nom]').forEach(b => boutons[b.dataset.nom] = b);

  const flux = new EventSource('/flux');
  flux.onmessage = e => {
    const [version, allume] = e.data.split(' ');
    img.src = '/ecran.png?v=' + version;
    etat.textContent = allume === '1' ? '' : 'Écran éteint : appuie sur un bouton pour le rallumer.';
  };
  flux.onerror = () => { etat.textContent = 'Connexion au lecteur perdue. Il redémarre peut-être.'; };

  function envoyer(nom, appuye) {
    if (appuye ? enfonces.has(nom) : !enfonces.has(nom)) return;
    if (appuye) enfonces.add(nom); else enfonces.delete(nom);
    boutons[nom].classList.toggle('appuye', appuye);
    fetch('/bouton', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                       body: JSON.stringify({ nom, appuye }) });
  }
  const touches = { a: 'A', b: 'B', x: 'X', y: 'Y' };
  addEventListener('keydown', e => {
    const nom = touches[e.key.toLowerCase()];
    if (!nom || e.metaKey || e.ctrlKey) return;
    e.preventDefault();
    if (!e.repeat) envoyer(nom, true);
  });
  addEventListener('keyup', e => { const nom = touches[e.key.toLowerCase()]; if (nom) envoyer(nom, false); });
  addEventListener('blur', () => [...enfonces].forEach(nom => envoyer(nom, false)));
  Object.entries(boutons).forEach(([nom, b]) => {
    b.addEventListener('pointerdown', e => { b.setPointerCapture(e.pointerId); envoyer(nom, true); });
    b.addEventListener('pointerup', () => envoyer(nom, false));
    b.addEventListener('pointercancel', () => envoyer(nom, false));
    b.addEventListener('contextmenu', e => e.preventDefault());
  });
</script>
</body>
</html>
"""

NOIR = Image.new("RGB", (240, 240), (0, 0, 0))


class Simulateur:
    def __init__(self, port=8090):
        self.port = port
        self.lecteur = None
        self.png = self._encoder(NOIR)
        self.allume = True
        self.version = 0
        self.condition = threading.Condition()

    @staticmethod
    def _encoder(image):
        tampon = io.BytesIO()
        image.save(tampon, "PNG")
        return tampon.getvalue()

    def afficher(self, image, allume):
        png = self._encoder(image if allume else NOIR)
        with self.condition:
            if png == self.png and allume == self.allume:
                return
            self.png = png
            self.allume = allume
            self.version += 1
            self.condition.notify_all()

    def servir(self):
        simulateur = self

        class Requete(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _envoyer(self, code, type_contenu, corps):
                self.send_response(code)
                self.send_header("Content-Type", type_contenu)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def do_GET(self):
                chemin = self.path.split("?", 1)[0]
                if chemin == "/":
                    self._envoyer(200, "text/html; charset=utf-8", PAGE.encode())
                elif chemin == "/ecran.png":
                    self._envoyer(200, "image/png", simulateur.png)
                elif chemin == "/flux":
                    self._flux()
                elif chemin == "/etat" and simulateur.lecteur:
                    corps = json.dumps(simulateur.lecteur.resume(), ensure_ascii=False).encode()
                    self._envoyer(200, "application/json; charset=utf-8", corps)
                else:
                    self._envoyer(404, "text/plain", b"introuvable")

            def _flux(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                vue = -1
                try:
                    while True:
                        with simulateur.condition:
                            simulateur.condition.wait_for(lambda: simulateur.version != vue, timeout=15)
                            version, allume = simulateur.version, simulateur.allume
                        if version == vue:
                            self.wfile.write(b": rien de neuf\n\n")
                        else:
                            vue = version
                            self.wfile.write(f"data: {version} {1 if allume else 0}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            def do_POST(self):
                if self.path != "/bouton":
                    self._envoyer(404, "text/plain", b"introuvable")
                    return
                try:
                    taille = int(self.headers.get("Content-Length", "0"))
                    donnees = json.loads(self.rfile.read(taille) or b"{}")
                    nom = donnees.get("nom")
                    if nom in ("A", "B", "X", "Y") and simulateur.lecteur:
                        simulateur.lecteur.evenement_bouton(nom, bool(donnees.get("appuye")))
                    self._envoyer(204, "text/plain", b"")
                except (ValueError, OSError):
                    self._envoyer(400, "text/plain", b"requete invalide")

        serveur = ThreadingHTTPServer(("127.0.0.1", self.port), Requete)
        serveur.daemon_threads = True
        serveur.serve_forever()
