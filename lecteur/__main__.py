"""Lancer le lecteur avec le simulateur : python3 -m lecteur"""
import argparse

from .app import Lecteur
from .simulateur import Simulateur


def main():
    parser = argparse.ArgumentParser(description="Lecteur de musique (simulateur dans le navigateur)")
    parser.add_argument("--port", type=int, default=8090, help="port de la page du simulateur")
    args = parser.parse_args()
    simulateur = Simulateur(args.port)
    lecteur = Lecteur(simulateur)
    simulateur.lecteur = lecteur
    lecteur.demarrer()
    print(f"Simulateur : http://127.0.0.1:{args.port}", flush=True)
    simulateur.servir()


if __name__ == "__main__":
    main()
