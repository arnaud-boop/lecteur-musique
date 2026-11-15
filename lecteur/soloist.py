"""Client WebSocket pour l'API locale de Soloist.

Bibliothèque standard seulement. La connexion est permanente et se rétablit
toute seule. Chaque message reçu est passé à `sur_evenement(dict)`, en plus
de deux messages internes : {"type": "_connecte"} et {"type": "_deconnecte"}.
"""
import base64
import json
import os
import socket
import struct
import threading
import time


class Soloist:
    def __init__(self, adresse, sur_evenement):
        hote, port = adresse.rsplit(":", 1)
        self.hote = hote
        self.port = int(port)
        self.sur_evenement = sur_evenement
        self.connecte = False
        self._sock = None
        self._verrou = threading.Lock()
        threading.Thread(target=self._boucle, name="soloist", daemon=True).start()

    def commande(self, nom, **champs):
        """Envoie une commande. Renvoie False si Soloist n'est pas joignable."""
        message = json.dumps({"type": "command", "command": nom, **champs}).encode()
        with self._verrou:
            if self._sock is None:
                return False
            try:
                self._envoyer(0x1, message)
                return True
            except OSError:
                return False

    # Connexion et lecture des messages

    def _boucle(self):
        while True:
            try:
                sock = socket.create_connection((self.hote, self.port), timeout=5)
                fichier = self._poignee_de_main(sock)
                sock.settimeout(None)
                with self._verrou:
                    self._sock = sock
                self.connecte = True
                self.sur_evenement({"type": "_connecte"})
                while True:
                    op, donnees = self._lire_message(fichier)
                    if op == 0x1:
                        try:
                            self.sur_evenement(json.loads(donnees))
                        except ValueError:
                            pass
                    elif op == 0x9:  # ping : on répond pong
                        with self._verrou:
                            self._envoyer(0xA, donnees)
                    elif op == 0x8:  # fermeture
                        break
            except (OSError, ConnectionError, ValueError):
                pass
            with self._verrou:
                if self._sock is not None:
                    try:
                        self._sock.close()
                    except OSError:
                        pass
                self._sock = None
            if self.connecte:
                self.connecte = False
                self.sur_evenement({"type": "_deconnecte"})
            time.sleep(2)

    def _poignee_de_main(self, sock):
        cle = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((
            f"GET / HTTP/1.1\r\nHost: {self.hote}:{self.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {cle}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        fichier = sock.makefile("rb")
        if b" 101 " not in fichier.readline():
            raise ConnectionError("Soloist a refusé la connexion WebSocket")
        while fichier.readline() not in (b"\r\n", b""):
            pass
        return fichier

    def _envoyer(self, op, donnees):
        entete = bytearray([0x80 | op])
        n = len(donnees)
        if n < 126:
            entete.append(0x80 | n)
        elif n < 65536:
            entete.append(0x80 | 126)
            entete += struct.pack(">H", n)
        else:
            entete.append(0x80 | 127)
            entete += struct.pack(">Q", n)
        masque = os.urandom(4)
        entete += masque
        corps = bytes(b ^ masque[i % 4] for i, b in enumerate(donnees))
        self._sock.sendall(bytes(entete) + corps)

    @staticmethod
    def _lire_exact(fichier, n):
        donnees = fichier.read(n)
        if donnees is None or len(donnees) < n:
            raise ConnectionError("connexion fermée")
        return donnees

    def _lire_message(self, fichier):
        morceaux = []
        op_message = None
        while True:
            b1, b2 = self._lire_exact(fichier, 2)
            fin = b1 & 0x80
            op = b1 & 0x0F
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._lire_exact(fichier, 2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._lire_exact(fichier, 8))[0]
            masque = self._lire_exact(fichier, 4) if b2 & 0x80 else None
            donnees = self._lire_exact(fichier, n) if n else b""
            if masque:
                donnees = bytes(b ^ masque[i % 4] for i, b in enumerate(donnees))
            if op >= 0x8:
                return op, donnees
            if op != 0x0:
                op_message = op
            morceaux.append(donnees)
            if fin:
                return op_message, b"".join(morceaux)
