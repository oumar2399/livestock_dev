"""Test 4 : Script de banc pour le M5Stack (Paliers 4.0 à 4.5).

À exécuter dans Thonny REPL sur le M5Stack.
Compatible MicroPython standard (aucun f-string).

Exemple d'utilisation dans Thonny :
    import test_fault_tolerance as bench
    bench.test_runtime_nominal()       # Palier 4.0
    bench.test_unreachable_server()    # Palier 4.1
    bench.test_blackhole_server()      # Palier 4.1b
    bench.test_wifi_reconnect()        # Palier 4.2
    bench.test_ack_lost()              # Palier 4.3
    bench.test_ram_stability(20)       # Palier 4.4
"""

import time
import b4_runtime

try:
    import test4_config as config
except ImportError:
    print("[ERREUR] test4_config.py introuvable ! Copiez test4_config.example.py sous test4_config.py.")
    config = None


_bench_clock_base_s = 1726600000


class BenchClock:
    """Horloge synthétique produisant des timestamps croissants pour le banc de test."""
    def __init__(self, start_unix_s=None):
        global _bench_clock_base_s
        if start_unix_s is None:
            start_unix_s = _bench_clock_base_s
            _bench_clock_base_s += 1000
        self.base_ms = start_unix_s * 1000
        self.start_tick = time.ticks_ms()

    def utc_ms(self, tick=None):
        if tick is None:
            tick = time.ticks_ms()
        elapsed = time.ticks_diff(tick, self.start_tick)
        if elapsed < 0:
            elapsed = 0
        return self.base_ms + elapsed


def _check_config():
    if config is None:
        raise RuntimeError("test4_config.py manquant")
    if not getattr(config, "B4_ISOLATED_BENCH", False):
        raise RuntimeError("B4_ISOLATED_BENCH doit etre positionne a True dans test4_config.py")


def test_runtime_nominal():
    """Palier 4.0 : Smoke test nominal de b4_runtime.run()."""
    _check_config()
    print("\n=== PALIER 4.0 : Smoke Test Runtime (1 cycle) ===")
    clock = BenchClock()
    counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock)
    print("Resultat Palier 4.0 :", counters)
    if counters.get("sent") == 1:
        print("[PASS] Palier 4.0 reussi : 1 paquet transmis avec succes.")
    else:
        print("[FAIL] Palier 4.0 echoue : paquet non envoye.")
    return counters


def test_unreachable_server():
    """Palier 4.1 : Serveur inaccessible (IP non routable)."""
    _check_config()
    print("\n=== PALIER 4.1 : Serveur Inaccessible (3 retries attendus) ===")
    clock = BenchClock()
    orig_url = config.API_BASE_URL
    try:
        config.API_BASE_URL = "http://192.0.2.1:8000"
        t0 = time.ticks_ms()
        counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock)
        duration_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
        print("Duree totale : %.1fs | Compteurs : %s" % (duration_s, counters))
        if counters.get("send_dropped") == 1 and counters.get("sent") == 0:
            print("[PASS] Palier 4.1 reussi : drop borne apres epuisement des retries.")
        else:
            print("[FAIL] Palier 4.1 echoue.")
    finally:
        config.API_BASE_URL = orig_url


def test_blackhole_server(blackhole_url=None):
    """Palier 4.1b : Serveur silencieux trou noir (mesure precise du timeout)."""
    _check_config()
    target_url = blackhole_url or config.API_BASE_URL.replace(":8000", ":8002")
    print("\n=== PALIER 4.1b : Serveur Trou Noir (%s) ===" % target_url)
    print("Verifiez que python test4_blackhole.py tourne sur le PC port 8002 !")
    clock = BenchClock()
    orig_url = config.API_BASE_URL
    try:
        config.API_BASE_URL = target_url
        t0 = time.ticks_ms()
        counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock)
        duration_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
        print("Duree totale : %.1fs | Compteurs : %s" % (duration_s, counters))
        if counters.get("send_dropped") == 1 and duration_s >= 25.0:
            print("[PASS] Palier 4.1b reussi : timeout respecte (~%.1fs attendu pour 3x10s)." % duration_s)
        else:
            print("[ATTENTION] Palier 4.1b : duree=%.1fs (attendu >=25s). Verifier le timeout." % duration_s)
    finally:
        config.API_BASE_URL = orig_url


def test_wifi_reconnect(prepare_delay_s=5):
    """Palier 4.2 : Coupure Wi-Fi synchronisee et reconnexion au 2e cycle."""
    _check_config()
    print("\n=== PALIER 4.2 : Coupure Wi-Fi & Reconnexion (2 cycles) ===")
    print("Consigne : A l'affichage de ATTENTE_COUPE_WIFI (%ds), coupez le Wi-Fi." % prepare_delay_s)
    print("Rallumez-le pendant la collecte du cycle 2.")
    clock = BenchClock()
    orig_delay = getattr(config, "BENCH_PREPARE_DELAY_S", 0)
    try:
        config.BENCH_PREPARE_DELAY_S = prepare_delay_s
        counters = b4_runtime.run(config, max_cycles=2, bench_clock=clock)
        print("Resultat Palier 4.2 :", counters)
        if counters.get("send_dropped") == 1 and counters.get("sent") == 1:
            print("[PASS] Palier 4.2 reussi : 1 drop (sans Wi-Fi) puis 1 envoi reussi (apres reconnexion).")
        else:
            print("[FAIL] Palier 4.2 : Resultat inattendu.")
    finally:
        config.BENCH_PREPARE_DELAY_S = orig_delay


def test_ack_lost(proxy_url=None):
    """Palier 4.3 : Injection de perte d'ACK via le proxy port 8001."""
    _check_config()
    target_url = proxy_url or config.API_BASE_URL.replace(":8000", ":8001")
    print("\n=== PALIER 4.3 : ACK Perdu / Idempotence (%s) ===" % target_url)
    print("Verifiez que python test4_fault_proxy.py --drop-first-ack tourne sur le PC port 8001 !")
    clock = BenchClock()
    orig_url = config.API_BASE_URL
    try:
        config.API_BASE_URL = target_url
        counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock)
        print("Resultat Palier 4.3 :", counters)
        if counters.get("sent") == 1:
            print("[PASS] Palier 4.3 : Envoi valide cote M5Stack apres retry.")
            print("Executez maintenant 'python backend/scripts/test4_verify_sql.py' sur le PC pour confirmer l'idempotence BDD.")
    finally:
        config.API_BASE_URL = orig_url


def test_ram_stability(cycles=20):
    """Palier 4.4 : Test de stabilite RAM sur N cycles (serveur inaccessible)."""
    _check_config()
    print("\n=== PALIER 4.4 : Stabilite RAM sur %d cycles ===" % cycles)
    clock = BenchClock()
    orig_url = config.API_BASE_URL
    try:
        config.API_BASE_URL = "http://192.0.2.1:8000"
        counters = b4_runtime.run(config, max_cycles=cycles, bench_clock=clock)
        print("Fin des %d cycles. Compteurs : %s" % (cycles, counters))
        print("Consultez les logs Thonny 'COLLECTE_DEBUT cycle X mem_free Y' pour calculer la regression memoire.")
    finally:
        config.API_BASE_URL = orig_url


def test_recovery_cycle():
    """Palier 4.5 : Reprise nominale apres reboot materiel."""
    _check_config()
    print("\n=== PALIER 4.5 : Smoke Test Post-Reboot (1 cycle) ===")
    return test_runtime_nominal()
