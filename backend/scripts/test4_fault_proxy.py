#!/usr/bin/env python3
"""Test 4 : Proxy TCP d'injection de pannes (drop du premier ACK HTTP).

Ce proxy intercepte les paquets envoyés par le M5Stack, les transmet au backend cible,
mais supprime délibérément la réponse (l'ACK HTTP) lors de la première requête pour
simuler une perte réseau post-ingestion. Lors du retry qui suit, le proxy laisse passer
la réponse HTTP 200 OK.

Usage :
    python backend/scripts/test4_fault_proxy.py --drop-first-ack --listen-port 8001 --target-port 8000
"""

import argparse
import socket
import sys
import threading
import time


def handle_client(client_sock, client_addr, target_host, target_port, state):
    with state["lock"]:
        now = time.time()
        # Réinitialisation automatique du cycle si inactivité > 15 secondes (nouveau test après collecte IMU)
        if state.get("last_request_time") and (now - state["last_request_time"] > 15.0):
            print(f"\n[Proxy] Réinitialisation du cycle de drop (inactivité de {now - state['last_request_time']:.1f}s)")
            state["request_count"] = 0
        state["last_request_time"] = now
        request_idx = state["request_count"]
        state["request_count"] += 1

    drop_this = state["drop_first_ack"] and (request_idx == 0)
    print(f"\n[{time.strftime('%H:%M:%S')}] [Proxy] Connexion reçue #{request_idx + 1} de {client_addr}")

    try:
        # Lire la requête du client
        client_sock.settimeout(10.0)
        request_data = b""
        while True:
            chunk = client_sock.recv(4096)
            if not chunk:
                break
            request_data += chunk
            # Si en-têtes terminés et content-length lu
            if b"\r\n\r\n" in request_data:
                headers_part, body_part = request_data.split(b"\r\n\r\n", 1)
                content_len = 0
                for line in headers_part.split(b"\r\n"):
                    if line.lower().startswith(b"content-length:"):
                        try:
                            content_len = int(line.split(b":", 1)[1].strip())
                        except ValueError:
                            pass
                if len(body_part) >= content_len:
                    break

        print(f"[{time.strftime('%H:%M:%S')}] [Proxy] {len(request_data)} octets reçus du client. Acheminement vers {target_host}:{target_port}...")

        # Transférer au backend réel
        target_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_sock.settimeout(12.0)
        target_sock.connect((target_host, target_port))
        target_sock.sendall(request_data)

        # Lire la réponse du backend
        backend_response = b""
        while True:
            try:
                resp_chunk = target_sock.recv(4096)
                if not resp_chunk:
                    break
                backend_response += resp_chunk
                if b"\r\n\r\n" in backend_response:
                    headers_part, body_part = backend_response.split(b"\r\n\r\n", 1)
                    content_len = None
                    for line in headers_part.split(b"\r\n"):
                        if line.lower().startswith(b"content-length:"):
                            try:
                                content_len = int(line.split(b":", 1)[1].strip())
                            except ValueError:
                                pass
                    if content_len is not None and len(body_part) >= content_len:
                        break
            except socket.timeout:
                break
        target_sock.close()

        # Extraire le statut HTTP
        first_line = backend_response.split(b"\r\n")[0].decode("ascii", "ignore") if backend_response else "VIDE"
        print(f"[{time.strftime('%H:%M:%S')}] [Proxy] Backend a répondu : '{first_line}'")

        if drop_this:
            print(f"[{time.strftime('%H:%M:%S')}] [INJECTION PANNE] DROP de l'ACK HTTP ! Fermeture brutale du socket client.")
            client_sock.close()
        else:
            print(f"[{time.strftime('%H:%M:%S')}] [PASS-THROUGH] Renvoi de la réponse au client ({len(backend_response)} octets)...")
            client_sock.sendall(backend_response)
            client_sock.close()
            print(f"[{time.strftime('%H:%M:%S')}] [Proxy] Réponse transmise avec succès.")

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] [ERREUR Proxy] {e}")
        try:
            client_sock.close()
        except OSError:
            pass


def run_proxy(listen_port: int, target_host: str, target_port: int, drop_first_ack: bool):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", listen_port))
    s.listen(5)

    state = {
        "drop_first_ack": drop_first_ack,
        "request_count": 0,
        "last_request_time": None,
        "lock": threading.Lock()
    }

    print(f"============================================================")
    print(f"[PROXY FAULT-INJECTION] Écoute sur port {listen_port} -> Cible {target_host}:{target_port}")
    if drop_first_ack:
        print(f"Mode actif : Le 1er ACK HTTP sera supprimé (drop), les suivants seront transmis.")
    print(f"============================================================")

    try:
        while True:
            client_sock, client_addr = s.accept()
            t = threading.Thread(
                target=handle_client,
                args=(client_sock, client_addr, target_host, target_port, state),
                daemon=True
            )
            t.start()
    except KeyboardInterrupt:
        print("\n[INFO] Arrêt du proxy.")
    finally:
        s.close()


def main():
    parser = argparse.ArgumentParser(description="Proxy TCP d'injection de pannes (drop ACK)")
    parser.add_argument("--listen-port", type=int, default=8001, help="Port d'écoute du proxy (défaut: 8001)")
    parser.add_argument("--target-host", type=str, default="127.0.0.1", help="Hôte backend (défaut: 127.0.0.1)")
    parser.add_argument("--target-port", type=int, default=8000, help="Port backend réel (défaut: 8000)")
    parser.add_argument("--drop-first-ack", action="store_true", help="Supprimer le 1er ACK HTTP et laisser passer les suivants")
    args = parser.parse_args()

    run_proxy(args.listen_port, args.target_host, args.target_port, args.drop_first_ack)


if __name__ == "__main__":
    main()
