"""
m5stack/tests/bench_sensor_range.py
=====================================
Test au banc (B.2) — comparer les 3 plages d'accelerometre du MPU6886 :
+/-2g / +/-4g / +/-8g, pour decider laquelle graver dans le firmware final.

Volontairement isole : PAS de WiFi, PAS de HTTP, PAS de fenetrage/features.
Juste la lecture brute du capteur, pour ne pas meler ce test a d'autres
sources d'erreur potentielles.

Confirme au REPL avant d'ecrire ce script :
  - imu.acceleration() est une METHODE (pas une @property) sur cette carte
  - imu._accel_so == 16384  ->  plage active par defaut = +/-2g (jamais changee
    jusqu'ici dans simulation1.py, qui instancie MPU6886(i2c) sans argument)
  - imu._accel_sf == 9.80665  ->  acceleration() renvoie des m/s^2
  - Registres confirmes : 0x00 = +/-2g, 0x08 = +/-4g, 0x10 = +/-8g
  - imu._accel_fs(valeur) reconfigure la plage sur l'instance deja creee,
    pas besoin de reinstancier MPU6886 a chaque fois

Protocole (pour chacune des 3 plages) :
  1. Phase REPOS (3s) : poser le capteur immobile, a plat -> mesure le bruit
     de fond (plus la plage est large, plus le bruit au repos est eleve,
     car la sensibilite mg/LSB diminue avec la plage)
  2. Phase MOUVEMENT (5s) : bouger/secouer le capteur a la main de facon
     representative d'un mouvement de tete bovin (coup de tete, secousse
     rapide) -> verifie si les valeurs saturent (plafonnent a la limite
     de la plage, signe que la plage est trop etroite)

Usage :
  Copier ce fichier sur le M5Stack (Thonny : File > Save as > MicroPython
  device), puis l'executer depuis le REPL :
    >>> exec(open('bench_sensor_range.py').read())
  ou directement comme script principal si copie en tant que main.py temporaire.
"""
from machine import I2C
from mpu6886 import MPU6886
import utime

i2c = I2C(0, scl=22, sda=21, freq=400000)
imu = MPU6886(i2c)

GRAVITY = 9.80665  # confirme via imu._accel_sf sur cette carte (m/s^2 -> g)

# (nom affiche, valeur registre ACCEL_CONFIG, limite theorique en g)
RANGES = [
    ("+/-2g", 0x00, 2.0),
    ("+/-4g", 0x08, 4.0),
    ("+/-8g", 0x10, 8.0),
]

SAMPLE_RATE_HZ = 10
REST_SECONDS = 3
MOVE_SECONDS = 5
SATURATION_MARGIN = 0.98  # >= 98% de la limite theorique = considere sature


def read_g():
    try:
        ax, ay, az = imu.acceleration()
        return ax / GRAVITY, ay / GRAVITY, az / GRAVITY
    except OSError as e:
        print("     (lecture I2C ratee, echantillon ignore : {})".format(e))
        return None


def countdown(label, seconds=2):
    print("  {} dans...".format(label), end=" ")
    for i in range(seconds, 0, -1):
        print(i, end=" ")
        utime.sleep(1)
    print("GO !")


def run_phase(seconds):
    n = int(seconds * SAMPLE_RATE_HZ)
    samples = []
    for _ in range(n):
        sample = read_g()
        if sample is not None:
            samples.append(sample)
        utime.sleep(1.0 / SAMPLE_RATE_HZ)
    if len(samples) == 0:
        print("     /!\\ Aucun echantillon valide sur cette phase (toutes les lectures ont echoue).")
    return samples


def summarize(samples, max_g):
    if len(samples) == 0:
        print("     (pas de donnees a resumer)")
        return False
    xs = [s[0] for s in samples]
    ys = [s[1] for s in samples]
    zs = [s[2] for s in samples]
    any_saturation = False
    for axis_name, vals in [("X", xs), ("Y", ys), ("Z", zs)]:
        vmin = min(vals)
        vmax = max(vals)
        vmean = sum(vals) / len(vals)
        saturated = abs(vmin) >= max_g * SATURATION_MARGIN or abs(vmax) >= max_g * SATURATION_MARGIN
        any_saturation = any_saturation or saturated
        flag = "  <-- SATURATION" if saturated else ""
        print("     {}: min={:.3f}g max={:.3f}g mean={:.3f}g{}".format(
            axis_name, vmin, vmax, vmean, flag))
    return any_saturation


print("=" * 60)
print("BENCH TEST -- Plage accelerometre MPU6886 (B.2)")
print("=" * 60)

results = []

for label, reg_value, max_g in RANGES:
    print("\n### Plage {} (registre 0x{:02X}) ###".format(label, reg_value))
    imu._accel_so = imu._accel_fs(reg_value)  # <-- fix : capturer ET réassigner le diviseur
    utime.sleep(0.1)  # laisser le registre se stabiliser

    countdown("Phase REPOS -- pose le capteur A PLAT sur une surface stable et LACHE-le", 3)
    rest_samples = run_phase(REST_SECONDS)
    print("   Repos ({}s) :".format(REST_SECONDS))
    summarize(rest_samples, max_g)

    # Garde-fou : le Z moyen au repos doit rester ~1g peu importe la plage
    # (c'est juste la gravité -- si ça varie avec la plage, c'est un bug de
    # conversion, pas un vrai changement physique). Alerte si > 15% d'écart.
    if len(rest_samples) > 0:
        z_rest_mean = sum(s[2] for s in rest_samples) / len(rest_samples)
        if abs(z_rest_mean - 1.0) > 0.15:
            print("   /!\\ ALERTE : Z moyen au repos = {:.3f}g, attendu ~1.0g.".format(z_rest_mean))
            print("       Probable bug de conversion (diviseur de sensibilite pas a jour).")
            print("       Verifier imu._accel_so avant de faire confiance aux resultats.")

    countdown("Phase MOUVEMENT -- secoue/bouge le capteur comme un coup de tete", 2)
    move_samples = run_phase(MOVE_SECONDS)
    print("   Mouvement ({}s) :".format(MOVE_SECONDS))
    saturated = summarize(move_samples, max_g)

    results.append((label, saturated))

print("\n" + "=" * 60)
print("RESUME")
print("=" * 60)
for label, saturated in results:
    status = "SATURE pendant le mouvement" if saturated else "pas de saturation observee"
    print("  {} : {}".format(label, status))
print("\nCritere de decision :")
print("- Choisir la plage la plus FINE (2g < 4g < 8g) qui n'a PAS sature.")
print("- Une plage plus fine = moins de bruit au repos = meilleure sensibilite")
print("  pour distinguer les comportements peu actifs (grazing/resting).")
print("- Si +/-2g ne sature jamais meme pendant le mouvement le plus vif que")
print("  tu as pu simuler a la main, elle reste candidate -- mais rappelle-toi")
print("  qu'un vrai coup de tete ou une course de vache peut depasser ce que")
print("  la main reproduit ; garder une marge de securite est raisonnable.")
print("=" * 60)
