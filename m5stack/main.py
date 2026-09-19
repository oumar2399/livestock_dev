"""Firmware de Production Autonome pour Collier Bovin M5Stack (M5GO ESP32).

Affiliation : Kobe Institute of Computing (KIC), Graduate School of Information Technology.
Projet      : Livestock Monitoring System (Pastoral Cattle Monitoring - Cote d'Ivoire).
Auteur      : Antigravity AI & Pastoral Research Team.
Licence     : Proprietaire / Recherche Academique.

Ce script s'execute automatiquement au demarrage du M5Stack (sur batterie ou USB).
Il orchestre :
  1. L'initialisation de l'ecran LCD (interface visuelle terrain KIC).
  2. La verification du chien de garde materiel (Watchdog WDT).
  3. L'execution continue de la boucle B.4 (15s IMU Welford 10Hz, GPS temps reel).
  4. La protection contre la perte de donnees sous canopee via l'archive v3 flash.
  5. Le superviseur de resilience (gestion du 401 basse consommation, reboot sur panne).
"""

import gc
import sys
import time

# Permettre l'import des modules que ce soit a la racine ou dans /tests
for path in (".", "tests", "/flash", "/flash/tests"):
    if path not in sys.path:
        sys.path.append(path)

try:
    from m5stack import lcd, power
    HAS_HARDWARE_UI = True
except ImportError:
    lcd = None
    power = None
    HAS_HARDWARE_UI = False

try:
    import machine
    HAS_MACHINE = True
except ImportError:
    machine = None
    HAS_MACHINE = False

# Import de la configuration de production
try:
    import device_config as config
except ImportError:
    try:
        from tests import device_config as config
    except ImportError:
        config = None

# Import du runtime B.4
try:
    import b4_runtime
except ImportError:
    try:
        from tests import b4_runtime
    except ImportError:
        b4_runtime = None


# --- PALETTE COULEURS LCD (Theme sombre pastoral KIC) ---
COLOR_BG = 0x10141D       # Fond bleu ardoise profond
COLOR_HEADER_BG = 0x1E293B# Bandeau en-tete
COLOR_WHITE = 0xFFFFFF    # Texte principal
COLOR_GRAY = 0x94A3B8     # Texte secondaire
COLOR_CYAN = 0x06B6D4     # Accent KIC / Primaire
COLOR_GREEN = 0x10B981    # Succes / Batterie OK
COLOR_YELLOW = 0xF59E0B   # Avertissement / Recherche GPS
COLOR_RED = 0xEF4444      # Alerte critique / Erreur 401


class DisplayManager:
    """Gestionnaire d'affichage LCD ultra-resilient compatible UIFlow/MicroPython."""

    def __init__(self):
        self.enabled = HAS_HARDWARE_UI and lcd is not None
        if not self.enabled:
            return
        try:
            try:
                lcd.clear()
            except Exception:
                pass
            self._draw_header()
        except Exception as e:
            print("[WARN LCD init]:", e)

    def _draw_header(self):
        if not self.enabled:
            return
        try:
            lcd.setTextColor(COLOR_CYAN)
            lcd.setCursor(10, 10)
            lcd.print("[KIC] LIVESTOCK MONITOR")
            self.update_battery(self.get_battery_level())
        except Exception:
            pass

    def get_battery_level(self):
        if HAS_HARDWARE_UI and power is not None:
            try:
                lvl = power.getBatteryLevel()
                if 0 <= lvl <= 100:
                    return int(lvl)
            except Exception:
                pass
        return 85

    def update_battery(self, level):
        if not self.enabled:
            return
        try:
            if isinstance(level, int) and level > 0:
                col = COLOR_GREEN if level > 50 else (COLOR_YELLOW if level > 20 else COLOR_RED)
                lcd.setTextColor(col)
                lcd.setCursor(220, 10)
                lcd.print("BAT " + str(level) + "% ")
            else:
                lcd.setTextColor(COLOR_GREEN)
                lcd.setCursor(220, 10)
                lcd.print("USB PWR ")
        except Exception:
            pass

    def show_startup(self, dev_id, transport_id):
        if not self.enabled:
            return
        try:
            lcd.setTextColor(COLOR_WHITE)
            lcd.setCursor(10, 32)
            lcd.print("Dev: " + str(dev_id) + " | TID: " + str(transport_id) + "     ")
            lcd.setTextColor(COLOR_GRAY)
            lcd.setCursor(10, 52)
            lcd.print("FW: v2.0 (B.4+v3) | GPS: Active   ")
        except Exception:
            pass

    def update_status(self, main_text, color=COLOR_WHITE, sub_text=""):
        if not self.enabled:
            return
        try:
            lcd.setTextColor(color)
            lcd.setCursor(10, 80)
            lcd.print(str(main_text) + "                    ")
            if sub_text:
                lcd.setTextColor(COLOR_GRAY)
                lcd.setCursor(10, 105)
                lcd.print(str(sub_text) + "                    ")
        except Exception:
            pass

    def update_counters(self, counters, cycle_num, mem_free):
        if not self.enabled:
            return
        try:
            sent = counters.get("sent", 0)
            dropped = counters.get("send_dropped", 0)
            no_gps = counters.get("no_gps", 0)
            no_clock = counters.get("no_clock", 0)
            lcd.setTextColor(COLOR_WHITE)
            lcd.setCursor(10, 135)
            lcd.print("Sent:%d Drop:%d Arch:%d   " % (sent, dropped, no_clock))

            lcd.setTextColor(COLOR_GRAY)
            lcd.setCursor(10, 160)
            lcd.print("NoFix:%d | Cycle:#%d       " % (no_gps, cycle_num))

            lcd.setTextColor(COLOR_CYAN)
            lcd.setCursor(10, 185)
            mem_kb = mem_free // 1024 if mem_free else 0
            lcd.print("RAM:%d KB | WDT:OK        " % mem_kb)
        except Exception:
            pass

    def show_401_alert(self, minutes_left):
        if not self.enabled:
            return
        try:
            lcd.clear()
            lcd.setTextColor(COLOR_RED)
            lcd.setCursor(10, 20)
            lcd.print("ACCES 401 : SECRET REVOQUE")
            lcd.setTextColor(COLOR_WHITE)
            lcd.setCursor(10, 60)
            lcd.print("Secret refuse par le serveur.")
            lcd.setTextColor(COLOR_YELLOW)
            lcd.setCursor(10, 90)
            lcd.print("Mode veille basse conso.")
            lcd.setTextColor(COLOR_CYAN)
            lcd.setCursor(10, 135)
            lcd.print("Reprise dans: %d min" % minutes_left)
            lcd.setTextColor(COLOR_GRAY)
            lcd.setCursor(10, 200)
            lcd.print("Kobe Institute of Computing")
        except Exception:
            pass

    def show_fatal_error(self, message):
        if not self.enabled:
            return
        try:
            lcd.clear()
            lcd.setTextColor(COLOR_RED)
            lcd.setCursor(10, 20)
            lcd.print("ERREUR MATERIELLE")
            lcd.setTextColor(COLOR_WHITE)
            lcd.setCursor(10, 60)
            lcd.print(str(message)[:26])
            lcd.setCursor(10, 85)
            lcd.print(str(message)[26:52])
            lcd.setTextColor(COLOR_YELLOW)
            lcd.setCursor(10, 130)
            lcd.print("Redemarrage dans 10s...")
        except Exception:
            pass


display = DisplayManager()


def init_watchdog():
    """Initialise le chien de garde materiel (WDT) avec timeout de 60s."""
    if not HAS_MACHINE:
        return None
    try:
        wdt = machine.WDT(timeout=60000)
        print("[INIT] Chien de garde (WDT) arme a 60000 ms.")
        return wdt
    except Exception as e:
        print("[WARN] Watchdog WDT non disponible :", e)
        return None


def main():
    """Superviseur principal de production."""
    print("=======================================================")
    print("  KOBE INSTITUTE OF COMPUTING - LIVESTOCK MONITORING  ")
    print("  Firmware de Production M5Stack v2.0 (B.4 + Archive)  ")
    print("=======================================================")

    if config is None:
        err = "ERREUR : device_config.py introuvable !"
        print("[CRITICAL]", err)
        display.show_fatal_error(err)
        while True:
            time.sleep(1)

    if b4_runtime is None:
        err = "ERREUR : b4_runtime.py introuvable !"
        print("[CRITICAL]", err)
        display.show_fatal_error(err)
        while True:
            time.sleep(1)

    dev_id = getattr(config, "DEVICE_ID", "M5-COLLAR")
    transport_id = getattr(config, "TRANSPORT_ID", 101)
    display.show_startup(dev_id, transport_id)

    # Forcer les parametres de production vitaux
    config.PRODUCTION_MODE = True
    config.B4_ISOLATED_BENCH = False
    config.UNTIMED_ARCHIVE_ENABLED = getattr(config, "UNTIMED_ARCHIVE_ENABLED", True)

    wdt = init_watchdog()
    cycle_counter = 0

    def on_status_event(event, data):
        """Callback recevant les notifications d'etat de b4_runtime."""
        nonlocal cycle_counter
        if wdt:
            try:
                wdt.feed()
            except Exception:
                pass

        bat = display.get_battery_level()
        display.update_battery(bat)

        if event == "collecting":
            cycle_counter = data.get("cycle", cycle_counter + 1)
            display.update_status(
                "COLLECTE IMU (10 Hz)...",
                COLOR_CYAN,
                "Cycle #" + str(cycle_counter) + " | 150 echantillons"
            )
        elif event == "collected":
            display.update_status("TRAITEMENT WELFORD...", COLOR_WHITE, "Calcul variance & moyennes")
        elif event == "transmitting":
            attempt = data.get("attempt", 1)
            retry_count = data.get("retry_count", 3)
            ver = data.get("version", 2)
            display.update_status(
                "ENVOI SERVEUR (v" + str(ver) + ")...",
                COLOR_YELLOW,
                "Tentative " + str(attempt) + "/" + str(retry_count) + " via Wi-Fi"
            )
        elif event == "no_clock":
            counters = data.get("counters", {})
            archived = data.get("archived", False)
            msg = "ARCHIVE v3 FLASH" if archived else "NO CLOCK (Rejet)"
            display.update_status(
                msg,
                COLOR_YELLOW,
                "Canopee / Pas d'heure fiable"
            )
            display.update_counters(counters, cycle_counter, gc.mem_free() if hasattr(gc, "mem_free") else 0)
        elif event == "cycle_done":
            counters = data.get("counters", {})
            success = data.get("success", False)
            status_txt = "CYCLE VALIDE : ENVOYE" if success else "ENVOI ECHOUE (DROP)"
            status_col = COLOR_GREEN if success else COLOR_RED
            display.update_status(status_txt, status_col, "Prochain cycle dans 1s")
            display.update_counters(counters, cycle_counter, gc.mem_free() if hasattr(gc, "mem_free") else 0)

    # Boucle de supervision infinie et resiliente
    while True:
        try:
            if wdt:
                wdt.feed()
            display.update_status("PRET : DEMARRAGE CYCLE", COLOR_GREEN)
            b4_runtime.run(config, max_cycles=None, on_status=on_status_event)

        except KeyboardInterrupt:
            # Permettre a l'utilisateur d'interrompre proprement avec Ctrl+C dans Thonny
            print("\n[INFO] Arret demande par l'utilisateur (Thonny REPL).")
            display.update_status("PAUSED - THONNY REPL", COLOR_CYAN, "Prompt actif")
            break

        except RuntimeError as e:
            err_msg = str(e)
            if "Device access denied" in err_msg or "401" in err_msg:
                # HTTP 401 : Cle refusee ou revoquee
                print("\n[CRITICAL 401] Acces refuse par le serveur. Mise en veille 30 min...")
                # Veille de 30 minutes sans decharger la batterie sur l'animal
                for remaining in range(30, 0, -1):
                    display.show_401_alert(remaining)
                    for _ in range(60):
                        if wdt:
                            try:
                                wdt.feed()
                            except Exception:
                                pass
                        time.sleep(1)
                # Apres 30 minutes, on recree l'ecran et on retente
                display._draw_header()
            else:
                print("\n[SUPERVISOR] Erreur Runtime :", e)
                try:
                    sys.print_exception(e)
                except Exception:
                    pass
                display.show_fatal_error(err_msg)
                for _ in range(15):
                    if wdt:
                        try:
                            wdt.feed()
                        except Exception:
                            pass
                    time.sleep(1)
                print("[SUPERVISOR] Redemarrage materiel...")
                if HAS_MACHINE:
                    try:
                        machine.reset()
                    except Exception:
                        pass

        except Exception as e:
            print("\n[SUPERVISOR] Exception inattendue :", e)
            try:
                sys.print_exception(e)
            except Exception:
                pass
            display.show_fatal_error(str(e))
            for _ in range(15):
                if wdt:
                    try:
                        wdt.feed()
                    except Exception:
                        pass
                time.sleep(1)
            print("[SUPERVISOR] Redemarrage materiel...")
            if HAS_MACHINE:
                try:
                    machine.reset()
                except Exception:
                    pass


# Lancement direct (que ce soit via boot MicroPython ou import main dans Thonny)
main()
