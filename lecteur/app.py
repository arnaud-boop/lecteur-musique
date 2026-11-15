"""Cœur du lecteur : écrans, boutons et protections.

Le même code tourne sur le Mac (simulateur) et sur le Pi. Seule la « sortie »
change : elle reçoit les images à afficher avec `afficher(image, allume)`.
Les boutons arrivent par `evenement_bouton(nom, appuye)`.

Boutons : A en haut à gauche, B en bas à gauche, X en haut à droite,
Y en bas à droite.
- Partout : A monte, B descend, X ouvre ou choisit, Y revient en arrière.
- Écran Lecture : A titre précédent (long : j'aime), B titre suivant
  (long : je n'aime pas), X pause ou lecture, Y retour à la liste.
- Y maintenu 3 s : veille. En veille, Y maintenu 2 s : rallumage.
- X et Y maintenus 5 s : mode configuration.
"""
import json
import queue
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import config, rendu
from .bibliotheque import Bibliotheque
from .soloist import Soloist

# Durées, en secondes
APPUI_LONG = 1.0          # j'aime / je n'aime pas
REPETITION_DEBUT = 0.6    # A ou B maintenu dans une liste : défilement
REPETITION_PAS = 0.25
LUNE_DEBUT = 0.8          # Y maintenu : la lune apparaît
LUNE_FIN = 3.0            # Y maintenu : veille
SOLEIL_DEBUT = 0.3        # en veille, Y maintenu : le soleil apparaît
REVEIL = 2.0              # en veille, Y maintenu : rallumage
CONFIGURATION = 5.0       # X et Y maintenus : mode configuration
ECRAN_LECTURE = 20.0      # écran éteint après 20 s de musique sans appui
ECRAN_MENU = 300.0        # écran éteint après 5 min sans appui
DUREE_COEUR = 1.8
DUREE_TRISTE = 1.5
RECHARGER_PLAYLISTS = 600.0
IMAGES_PAR_SECONDE = 8


class Lecteur:
    def __init__(self, sortie, cfg=None):
        self.cfg = cfg or config.charger()
        self.sortie = sortie
        self.q = queue.Queue()
        self.taches = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tache")
        self.biblio = Bibliotheque(lambda: self.q.put(("redessiner",)))
        self.journal = config.LOCAL / "journal.jsonl"
        self.avis = self._lire_avis()   # titre -> "aime" ou "naime_pas" (le dernier avis compte)

        # Écran et navigation
        self.ecran = "chargement"
        self.allume = True
        self.dernier_appui = time.monotonic()
        self.playlists = []
        self.sel_playlist = 0
        self.ouverte = 0
        self.sel_titre = 0
        self.superposition = None   # ("coeur", début), ("triste", début), ("lune", part), ("soleil", part)

        # Boutons
        self.appuis = {}            # bouton -> moment de l'appui
        self.consommes = set()      # boutons dont l'action longue a déjà eu lieu
        self.reveil_ecran = set()   # boutons dont l'appui a seulement rallumé l'écran
        self.repetitions = {}       # bouton -> nombre de pas de défilement

        # Soloist et protections
        self.soloist_ok = False
        self.etat = {}
        self.dernier_ok = None      # (playlist autorisée, titre) joués en dernier
        self.derniere_ecoute = -1e9 # dernier moment où sa musique jouait
        self.dernier_retour = 0.0
        self.silence_jusqua = 0.0   # pendant le contournement, on ne corrige pas le volume
        self.transition_jusqua = 0.0  # juste après un lancement, on ne juge pas la playlist
        self.prochain_chargement = 0.0

        self._sale = True
        self._derniere_image = 0.0
        self.soloist = Soloist(self.cfg["soloist_ws"], lambda ev: self.q.put(("soloist", ev)))

    # Entrées

    def demarrer(self):
        threading.Thread(target=self._boucle, name="lecteur", daemon=True).start()

    def evenement_bouton(self, nom, appuye):
        self.q.put(("bouton", nom, appuye, time.monotonic()))

    def resume(self):
        """Petit résumé de l'état, pour les essais automatiques du simulateur."""
        return {
            "ecran": self.ecran,
            "allume": self.allume,
            "playlists": [p["nom"] for p in self.playlists],
            "sel_playlist": self.sel_playlist,
            "ouverte": self.ouverte,
            "sel_titre": self.sel_titre,
        }

    # Boucle principale : tout l'état est modifié ici, dans un seul fil

    def _boucle(self):
        while True:
            try:
                ev = self.q.get(timeout=0.05)
            except queue.Empty:
                ev = None
            try:
                if ev:
                    self._traiter(ev)
                maintenant = time.monotonic()
                if maintenant >= self.prochain_chargement:
                    self.prochain_chargement = maintenant + RECHARGER_PLAYLISTS
                    self.taches.submit(self._charger_playlists)
                self._tick(maintenant)
                self._dessiner_si_besoin()
            except Exception:
                traceback.print_exc()

    def _traiter(self, ev):
        genre = ev[0]
        if genre == "bouton":
            self._bouton(ev[1], ev[2], ev[3])
        elif genre == "soloist":
            self._soloist(ev[1])
        elif genre == "playlists":
            self._playlists_chargees(ev[1])
        self._sale = True

    def _charger_playlists(self):
        resultat = []
        for uri in self.cfg["playlists"]:
            try:
                resultat.append(self.biblio.charger_playlist(uri))
            except Exception as e:
                print("Playlist non chargée :", uri, e, flush=True)
        self.q.put(("playlists", resultat))

    def _playlists_chargees(self, playlists):
        self.playlists = playlists
        n = len(playlists)
        self.sel_playlist = min(self.sel_playlist, max(0, n - 1))
        self.ouverte = min(self.ouverte, max(0, n - 1))
        if self.ecran == "titres" and n:
            self.sel_titre = min(self.sel_titre, max(0, len(playlists[self.ouverte]["titres"]) - 1))
        if self.ecran == "chargement":
            idx = self._index_playlist(self._contexte())
            if idx is not None:
                self.sel_playlist = idx
            self.ecran = "lecture" if idx is not None and self._en_lecture() else "playlists"

    # Soloist

    def _soloist(self, ev):
        t = ev.get("type")
        if t == "_connecte":
            self.soloist_ok = True
            return
        if t == "_deconnecte":
            self.soloist_ok = False
            return
        if t == "playback_state":
            for cle in ("status", "item", "context", "position", "volume", "is_active", "options"):
                if cle in ev:
                    self.etat[cle] = ev[cle]
        elif t == "track_changed":
            self.etat["item"] = ev.get("item")
        elif t == "playback_changed":
            self.etat["status"] = ev.get("status")
        elif t == "volume_changed":
            self.etat["volume"] = ev.get("volume")
        elif t == "device_changed":
            self.etat["is_active"] = ev.get("is_active")
        elif t == "context_changed":
            self.etat["context"] = ev.get("context")
        elif t == "options_changed":
            self.etat["options"] = ev.get("options")
        elif t == "position_sync":
            self.etat["position"] = ev.get("position")
        elif t == "error":
            print("Soloist :", ev.get("message"), flush=True)
            return
        else:
            return
        self._proteger()

    def _proteger(self):
        """Seulement les playlists autorisées, au volume choisi par les parents."""
        if not self.etat.get("is_active"):
            return
        maintenant = time.monotonic()
        if maintenant > self.silence_jusqua:
            volume = self.etat.get("volume")
            if volume is not None and volume != self.cfg["volume"]:
                self.soloist.commande("set_volume", volume=self.cfg["volume"])
        contexte = self._contexte()
        titre = self._item_uri()
        if contexte in self.cfg["playlists"]:
            # Le titre peut changer juste avant la playlist : on ne garde que les titres connus.
            if titre and self._titre_connu(contexte, titre):
                self.dernier_ok = (contexte, titre)
            if self.etat.get("status") == "playing":
                self.derniere_ecoute = maintenant
            options = self.etat.get("options") or {}
            if options.get("shuffle"):
                self.soloist.commande("set_shuffle", enabled=False)
            if options and options.get("repeat") != "context":
                self.soloist.commande("set_repeat_context", enabled=True)
        elif maintenant < self.transition_jusqua:
            # Le lecteur vient de lancer sa musique : Spotify change le titre puis la playlist,
            # et l'état est mélangé pendant un instant. On attend la fin du changement.
            pass
        elif (contexte or titre) and maintenant - self.dernier_retour > 3:
            self.dernier_retour = maintenant
            elle_ecoutait = maintenant - self.derniere_ecoute < 15
            print("Contenu non autorisé :", contexte or titre,
                  "-> retour à sa musique" if elle_ecoutait else "-> pause", flush=True)
            self.soloist.commande("pause")
            if self.dernier_ok and elle_ecoutait:
                self._jouer(*self.dernier_ok)

    def _titre_connu(self, contexte, titre):
        playlist = next((p for p in self.playlists if p["uri"] == contexte), None)
        return playlist is None or any(t["uri"] == titre for t in playlist["titres"])

    def _jouer(self, contexte, titre_uri=None):
        """Démarre une playlist à un titre précis : API Web d'abord, contournement sinon."""
        self.transition_jusqua = time.monotonic() + 4.0

        def tache():
            ok = False
            try:
                ok = self.biblio.demarrer(self.cfg["nom_appareil"], contexte, titre_uri)
            except Exception as e:
                print("API Web :", e, flush=True)
            if not ok:
                print("API Web indisponible : contournement par sauts de titres", flush=True)
                self._jouer_secours(contexte, titre_uri)
        self.taches.submit(tache)

    def _jouer_secours(self, contexte, titre_uri):
        """Sans l'API Web : démarrer en silence, sauter jusqu'au titre, remettre le son."""
        playlist = next((p for p in self.playlists if p["uri"] == contexte), None)
        rang = 0
        if playlist and titre_uri:
            rang = next((i for i, t in enumerate(playlist["titres"]) if t["uri"] == titre_uri), 0)
        self.transition_jusqua = time.monotonic() + 3.0 + 0.2 * rang
        if rang:
            self.silence_jusqua = time.monotonic() + 2.0 + 0.2 * rang
            self.soloist.commande("set_volume", volume=0)
        self.soloist.commande("play", uri=contexte)
        if rang:
            time.sleep(1.0)
            for _ in range(rang):
                self.soloist.commande("skip_next")
                time.sleep(0.15)
            self.soloist.commande("set_volume", volume=self.cfg["volume"])

    # Boutons

    def _bouton(self, nom, appuye, t):
        if appuye:
            if nom in self.appuis:
                return
            self.appuis[nom] = t
            self.dernier_appui = t
            if not self.allume and self.ecran != "veille":
                self.allume = True
                self.reveil_ecran.add(nom)
            return
        t0 = self.appuis.pop(nom, None)
        if t0 is None:
            return
        duree = t - t0
        deja = nom in self.consommes or nom in self.reveil_ecran or self.repetitions.get(nom)
        self.consommes.discard(nom)
        self.reveil_ecran.discard(nom)
        self.repetitions.pop(nom, None)
        if self.superposition and self.superposition[0] in ("lune", "soleil"):
            self.superposition = None   # relâché trop tôt : on annule
        if deja or self.ecran == "veille" or self.appuis:
            return
        if nom == "Y" and duree >= LUNE_DEBUT:
            return
        if nom in ("A", "B") and self.ecran == "lecture" and duree >= APPUI_LONG:
            return
        self._appui_court(nom)

    def _tick(self, t):
        if "X" in self.appuis and "Y" in self.appuis:
            debut = max(self.appuis["X"], self.appuis["Y"])
            if t - debut >= CONFIGURATION and "X" not in self.consommes:
                self.consommes.update(("X", "Y"))
                self.superposition = None
                self.ecran = "config"
                self._sale = True
            return
        for nom, t0 in list(self.appuis.items()):
            if nom in self.consommes:
                continue
            d = t - t0
            if self.ecran == "veille":
                if nom == "Y" and d >= REVEIL:
                    self.consommes.add("Y")
                    self._reveiller()
                elif nom == "Y" and d >= SOLEIL_DEBUT:
                    self.superposition = ("soleil", (d - SOLEIL_DEBUT) / (REVEIL - SOLEIL_DEBUT))
                    self._sale = True
                continue
            if nom == "Y" and d >= LUNE_DEBUT:
                if d >= LUNE_FIN:
                    self.consommes.add("Y")
                    self._mettre_en_veille()
                else:
                    self.superposition = ("lune", (d - LUNE_DEBUT) / (LUNE_FIN - LUNE_DEBUT))
                    self._sale = True
            elif nom in self.reveil_ecran:
                continue
            elif nom in ("A", "B") and self.ecran == "lecture" and d >= APPUI_LONG:
                self.consommes.add(nom)
                self._aime(nom == "A")
            elif nom in ("A", "B") and self.ecran in ("playlists", "titres") and d >= REPETITION_DEBUT:
                attendu = 1 + int((d - REPETITION_DEBUT) / REPETITION_PAS)
                while self.repetitions.get(nom, 0) < attendu:
                    self.repetitions[nom] = self.repetitions.get(nom, 0) + 1
                    self._appui_court(nom)
                    self._sale = True

        # Écran éteint après un moment sans appui
        if self.allume and self.ecran not in ("veille", "chargement") and not self.appuis:
            delai = ECRAN_LECTURE if self.ecran == "lecture" and self._en_lecture() else ECRAN_MENU
            if t - self.dernier_appui > delai:
                self.allume = False
                self._sale = True

        # Fin du cœur et du visage triste
        if self.superposition and self.superposition[0] in ("coeur", "triste"):
            duree = DUREE_COEUR if self.superposition[0] == "coeur" else DUREE_TRISTE
            if t - self.superposition[1] > duree:
                self.superposition = None
                self._sale = True

    def _appui_court(self, nom):
        e = self.ecran
        if e == "playlists":
            if nom == "A":
                self.sel_playlist = max(0, self.sel_playlist - 1)
            elif nom == "B":
                self.sel_playlist = min(max(0, len(self.playlists) - 1), self.sel_playlist + 1)
            elif nom == "X" and self.playlists:
                self._ouvrir(self.sel_playlist)
            elif nom == "Y" and self._contexte() in self.cfg["playlists"]:
                self.ecran = "lecture"
        elif e == "titres":
            titres = self.playlists[self.ouverte]["titres"] if self.playlists else []
            if nom == "A":
                self.sel_titre = max(0, self.sel_titre - 1)
            elif nom == "B":
                self.sel_titre = min(max(0, len(titres) - 1), self.sel_titre + 1)
            elif nom == "X" and titres:
                playlist = self.playlists[self.ouverte]
                self._jouer(playlist["uri"], titres[self.sel_titre]["uri"])
                self.ecran = "lecture"
            elif nom == "Y":
                self.sel_playlist = self.ouverte
                self.ecran = "playlists"
        elif e == "lecture":
            if nom == "A":
                self._commande_lecture("skip_prev")
            elif nom == "B":
                self._commande_lecture("skip_next")
            elif nom == "X":
                self._lecture_pause()
            elif nom == "Y":
                idx = self._index_playlist(self._contexte())
                if idx is not None:
                    self._ouvrir(idx)
                else:
                    self.ecran = "playlists"
        elif e == "config":
            if nom == "Y":
                self.ecran = "playlists"

    def _ouvrir(self, idx):
        self.ouverte = idx
        self.ecran = "titres"
        playlist = self.playlists[idx]
        self.sel_titre = 0
        if self._contexte() == playlist["uri"]:
            en_cours = self._item_uri()
            self.sel_titre = next(
                (i for i, t in enumerate(playlist["titres"]) if t["uri"] == en_cours), 0)

    def _commande_lecture(self, commande):
        if not self.etat.get("is_active"):
            self.soloist.commande("activate")
        self.soloist.commande(commande)

    def _lecture_pause(self):
        if not self.etat.get("is_active"):
            # Un autre appareil avait pris la main : on reprend au même endroit.
            self.soloist.commande("activate")
        elif self.etat.get("status") == "playing":
            self.soloist.commande("pause")
        else:
            self.soloist.commande("play")

    def _aime(self, positif):
        if self._contexte() not in self.cfg["playlists"]:
            return   # jamais d'avis sur une musique qui n'est pas la sienne
        item = self.etat.get("item") or {}
        nom = ((item.get("decorations") or {}).get("identity") or {}).get("name")
        entree = {
            "moment": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "avis": "aime" if positif else "naime_pas",
            "titre": item.get("uri"),
            "nom": nom,
            "playlist": self._contexte(),
        }
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(entree, ensure_ascii=False) + "\n")
        if item.get("uri"):
            self.avis[item["uri"]] = entree["avis"]
        self.superposition = ("coeur" if positif else "triste", time.monotonic())
        self._sale = True
        if not positif:
            def passer():
                time.sleep(1.2)
                self.soloist.commande("skip_next")
            self.taches.submit(passer)

    def _mettre_en_veille(self):
        self.superposition = None
        if self.etat.get("is_active") and self.etat.get("status") == "playing":
            self.soloist.commande("pause")
        self.ecran = "veille"
        self.allume = False
        self._sale = True

    def _reveiller(self):
        self.superposition = None
        self.allume = True
        self.dernier_appui = time.monotonic()
        self.ecran = "lecture" if self._contexte() in self.cfg["playlists"] else "playlists"
        self._sale = True

    # Petites aides

    def _lire_avis(self):
        avis = {}
        try:
            with open(self.journal, encoding="utf-8") as f:
                for ligne in f:
                    try:
                        entree = json.loads(ligne)
                    except ValueError:
                        continue
                    if entree.get("titre") and entree.get("avis") in ("aime", "naime_pas"):
                        avis[entree["titre"]] = entree["avis"]
        except FileNotFoundError:
            pass
        return avis

    def _contexte(self):
        return (self.etat.get("context") or {}).get("uri")

    def _item_uri(self):
        return (self.etat.get("item") or {}).get("uri")

    def _en_lecture(self):
        return bool(self.etat.get("is_active")) and self.etat.get("status") == "playing"

    def _index_playlist(self, uri):
        return next((i for i, p in enumerate(self.playlists) if p["uri"] == uri), None)

    # Dessin

    def _dessiner_si_besoin(self):
        t = time.monotonic()
        anime = self.allume and self.ecran in ("chargement", "playlists", "titres", "lecture")
        if not (self._sale or anime or self.superposition):
            return
        if t - self._derniere_image < 1.0 / IMAGES_PAR_SECONDE:
            return
        self._derniere_image = t
        self._sale = False
        image = rendu.dessiner(self._vue(), self.biblio.image, t)
        self.sortie.afficher(image, self.allume or bool(self.superposition))

    def _vue(self):
        item = self.etat.get("item") or {}
        deco = item.get("decorations") or {}
        couvertures = (deco.get("visual_identity") or {}).get("cover") or []
        image = next((c["url"] for c in couvertures if c.get("size") == "default"),
                     couvertures[0]["url"] if couvertures else None)
        artistes = ", ".join(
            (((c.get("entity") or {}).get("decorations") or {}).get("identity") or {}).get("name", "")
            for c in deco.get("creators") or [])
        duree = (deco.get("playback") or {}).get("duration_ms") or 0
        pos = self.etat.get("position") or {}
        position = pos.get("position_ms") or 0
        if pos.get("timestamp_ms") and pos.get("speed"):
            position += (time.time() * 1000 - pos["timestamp_ms"]) * pos["speed"]
        contexte = self._contexte()
        lecture = None
        # On ne montre que sa musique : jamais la pochette d'un contenu non autorisé.
        if item.get("uri") and contexte in self.cfg["playlists"]:
            lecture = {
                "nom": (deco.get("identity") or {}).get("name") or "?",
                "artistes": artistes,
                "image": image,
                "duree_ms": duree,
                "position_ms": max(0, min(position, duree or position)),
                "en_pause": self.etat.get("status") != "playing",
                "avis": self.avis.get(item["uri"]),
            }
        ouverte = self.playlists[self.ouverte] if self.playlists else None
        return {
            "ecran": self.ecran,
            "allume": self.allume,
            "soloist_ok": self.soloist_ok,
            "autre_appareil": self.soloist_ok and bool(self.etat) and not self.etat.get("is_active"),
            "playlists": self.playlists,
            "sel_playlist": self.sel_playlist,
            "playlist_en_cours": self._index_playlist(contexte),
            "peut_revenir": contexte in self.cfg["playlists"],
            "ouverte": ouverte,
            "ouverte_en_cours": bool(ouverte) and ouverte["uri"] == contexte,
            "sel_titre": self.sel_titre,
            "titre_en_cours": item.get("uri"),
            "en_lecture": self._en_lecture(),
            "avis": self.avis,
            "lecture": lecture,
            "superposition": self.superposition,
        }
