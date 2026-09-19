#!/usr/bin/env python3
"""Test 4 : Serveur TCP silencieux (« trou noir ») pour validation réelle du timeout réseau.

Ce serveur accepte les connexions TCP, lit la requête HTTP entrante, mais ne renvoie
jamais de réponse. Il maintient les sockets ouverts dans une liste active pendant 60 secondes
avant de les fermer pour éviter l'épuisement des descripteurs de fichiers hôtes.

Usage :
    python backend/scripts/test4_blackhole.py --port 8002
"""

import argparse
import socket
import sys
import time


def run_blackhole(port: int = 8002, host: str = "0.0.0.0"):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(10)
    s.settimeout(0.5)

    print(f"============================================================")
    print(f"[TROU NOIR ACTIF] Écoute sur {host}:{port}")
    print(f"Accepte les connexions et garde un silence total (pas d'ACK HTTP).")
    print(f"Appuyez sur Ctrl+C pour arrêter le serveur.")
    print(f"============================================================")

    open_connections = []

    try:
        while True:
            try:
                conn, addr = s.accept()
                conn.settimeout(0.1)
                t_connect = time.time()
                print(f"[{time.strftime('%H:%M:%S')}] Connexion acceptée depuis {addr[0]}:{addr[1]}. Lecture requête...")
                try:
                    data = conn.recv(4096)
                    print(f"[{time.strftime('%H:%M:%S')}] {len(data)} octets reçus. Maintien du silence TCP...")
                except (socket.timeout, OSError):
                    pass
                open_connections.append((conn, t_connect, addr))
            except socket.timeout:
                pass

            # Nettoyage des connexions expirées (> 60s)
            now = time.time()
            still_open = []
            for conn, t_conn, addr in open_connections:
                if now - t_conn >= 60.0:
                    try:
                        conn.close()
                    except OSError:
                        pass
                    print(f"[{time.strftime('%H:%M:%S')}] Connexion {addr} fermée après 60s de silence.")
                else:
                    still_open.append((conn, t_conn, addr))
            open_connections = still_open

    except KeyboardInterrupt:
        print("\n[INFO] Arrêt demandé par l'utilisateur.")
    finally:
        print(f"[INFO] Fermeture de {len(open_connections)} connexions ouvertes...")
        for conn, _, _ in open_connections:
            try:
                conn.close()
            except OSError:
                pass
        s.close()
        print("[OK] Serveur trou noir arrêté.")


def main():
    parser = argparse.ArgumentParser(description="Serveur trou noir TCP pour tester les timeouts matériels.")
    parser.add_argument("--port", type=int, default=8002, help="Port d'écoute (défaut: 8002)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Adresse d'écoute (défaut: 0.0.0.0)")
    args = parser.parse_args()
    run_blackhole(args.port, args.host)


if __name__ == "__main__":
    main()
