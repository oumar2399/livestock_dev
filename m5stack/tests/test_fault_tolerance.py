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

import sys
import time

if "/flash/tests" not in sys.path:  # bench configs and helpers live in /flash/tests
    sys.path.append("/flash/tests")

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


class TransportAudit:
    """Bounded summary only; independent of the LCD/watchdog status callback."""
    def __init__(self, timeout_s, attempts, tolerance_ms=500):
        if not 0 <= tolerance_ms <= 2000 or tolerance_ms >= timeout_s * 1000:
            raise ValueError("Fixer une tolerance positive inferieure au budget avant le banc")
        self.budget = int(timeout_s * 1000)
        self.expected = attempts
        self.tolerance = tolerance_ms
        self.count = 0
        self.http_count = 0
        self.silent = 0
        self.address_ms = 0
        self.started = None
        self.elapsed_ms = 0
        self.violation = None
        self.pending = False
        self.incomplete = False
        self.connection_failures = 0

    def observe(self, event, data):
        if event == "http":
            self.http_count += 1
            if self.pending:
                self.violation = "Observations HTTP dupliquees"
            self.pending = data
            self.address_ms += data["address_ms"]
            if data["http_ms"] > self.budget + self.tolerance:
                self.violation = "Plafond TCP/HTTP depasse"
            if (data["connected"] and data["request_complete"] and
                    data["phase"] == "response" and data["status"] is None and
                    data["received_bytes"] == 0 and data["error"] is not None and
                    self.budget - self.tolerance <= data["http_ms"] <= self.budget + self.tolerance):
                self.silent += 1
            print("TEST4_HTTP", data)
        elif event == "attempt":
            self.count += 1
            now = time.ticks_ms()
            if self.started is None:
                self.started = time.ticks_add(now, -data["elapsed_ms"])
            self.elapsed_ms = time.ticks_diff(now, self.started)
            if data["number"] != self.count or data["version"] != 2:
                self.violation = "Sequence de tentatives inattendue"
            if data["wifi_ms"] > self.budget + self.tolerance:
                self.violation = "Plafond Wi-Fi depasse"
            if data.get("error") in ("ValueError", "AttributeError", "TypeError"):
                self.violation = "Erreur locale, pas un echec reseau qualifie"
            if not self.pending:
                self.incomplete = True
            elif (data.get("phase") != "http" or data.get("error") != "OSError" or
                  data.get("status") is not None):
                self.incomplete = True
            elif (self.pending["phase"] == "connect" and not self.pending["connected"] and
                  self.pending["error"] == "OSError"):
                self.connection_failures += 1
            self.pending = False
            print("TEST4_ATTEMPT", data)

    def verdict(self, counters, blackhole=False, server_connections=None):
        backoff = sum(min(2 ** n, 30) * 1000 for n in range(self.expected - 1))
        limit = self.expected * (2 * self.budget + self.tolerance) + backoff
        if self.violation:
            return "FAIL", self.violation
        if (counters.get("sent") != 0 or counters.get("send_dropped") != 1 or
                counters.get("imu_invalid", 0) or counters.get("no_clock", 0)):
            return "FAIL", "Drop non attribuable au transport attendu"
        if self.count != self.expected or self.pending or self.incomplete:
            return "INCONCLUSIF", "Journal incomplet ou nombre de tentatives incorrect"
        if self.elapsed_ms - self.address_ms > limit:
            return "FAIL", "Budget transport hors preparation adresse depasse"
        if blackhole:
            if self.http_count != self.expected or self.silent != self.expected:
                return "FAIL", "Silence TCP et durees non prouves pour chaque tentative"
            if server_connections is None:
                return "INCONCLUSIF", "Confirmer les connexions acceptees dans le journal du serveur"
            if server_connections != self.expected:
                return "FAIL", "Nombre de connexions serveur incorrect"
        elif self.connection_failures != self.expected:
            return "INCONCLUSIF", "Echec de connexion TCP non prouve (Wi-Fi, adresse ou autre phase)"
        return "PASS", "Phases bornees observees ; preparation adresse mesuree sans garantie de borne"


def _audit():
    return TransportAudit(config.HTTP_TIMEOUT_S, config.MAX_SEND_ATTEMPTS,
                          getattr(config, "TEST4_TIMING_TOLERANCE_MS", 500))


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
    audit = _audit()
    try:
        config.API_BASE_URL = "http://192.0.2.1:8000"
        t0 = time.ticks_ms()
        counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock, on_transport=audit.observe)
        duration_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
        print("Duree totale : %.1fs | Compteurs : %s" % (duration_s, counters))
        verdict = audit.verdict(counters)
        print("[%s] Palier 4.1 : %s" % verdict)
        return {"counters": counters, "audit": audit, "verdict": verdict}
    finally:
        config.API_BASE_URL = orig_url


def test_blackhole_server(blackhole_url=None, server_connections=None):
    """Palier 4.1b : Serveur silencieux trou noir (mesure precise du timeout)."""
    _check_config()
    target_url = blackhole_url or config.API_BASE_URL.replace(":8000", ":8002")
    print("\n=== PALIER 4.1b : Serveur Trou Noir (%s) ===" % target_url)
    print("Verifiez que python test4_blackhole.py tourne sur le PC port 8002 !")
    clock = BenchClock()
    orig_url = config.API_BASE_URL
    audit = _audit()
    try:
        config.API_BASE_URL = target_url
        t0 = time.ticks_ms()
        counters = b4_runtime.run(config, max_cycles=1, bench_clock=clock, on_transport=audit.observe)
        duration_s = time.ticks_diff(time.ticks_ms(), t0) / 1000
        print("Duree totale : %.1fs | Compteurs : %s" % (duration_s, counters))
        verdict = audit.verdict(counters, blackhole=True, server_connections=server_connections)
        print("[%s] Palier 4.1b : %s" % verdict)
        print("Preparation adresse totale (non bornee):", audit.address_ms, "ms")
        print("Conservez ce resultat ; confirmez les connexions du serveur avant un PASS final.")
        return {"counters": counters, "audit": audit, "verdict": verdict}
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
