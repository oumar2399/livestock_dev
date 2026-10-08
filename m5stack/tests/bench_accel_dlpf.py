"""
m5stack/tests/bench_accel_dlpf.py
=================================
Bench check of the accelerometer low-pass filter (ACCEL_CONFIG2 0x1D, A_DLPF_CFG).
Not firmware: run it alone from Thonny, then reboot into main.py.

Protocol: lay the M5 flat and still on a table, then run
    >>> exec(open('bench_accel_dlpf.py').read())
It records one 15 s window (150 samples at 10 Hz, +/-4g) with A_DLPF_CFG=0
(the chip reset value, no firmware filter) and one with A_DLPF_CFG=6 (firmware
setting), and prints the per-axis std in mg for both.

Expected order of magnitude at rest (noise density 100 ug/sqrt(Hz), datasheet):
  std = 100 ug * sqrt(noise bandwidth)
  A_DLPF_CFG=0: noise BW 235 Hz [to verify] -> about 1.5 mg (about 12 LSB)
  A_DLPF_CFG=6: noise BW 7.8 Hz             -> about 0.3 mg (about 2 LSB)
So "after" should be several times lower than "before" (about 5x in theory).
1 LSB = 0.12 mg at +/-4g. Table vibrations raise both values.
"""
from machine import I2C
from mpu6886 import MPU6886
import utime


def apply_accel_dlpf(i2c, cfg):
    # Same register logic as b4_runtime.apply_accel_dlpf, copied so this check does
    # not have to load the whole runtime into the M5's limited RAM.
    old = i2c.readfrom_mem(0x68, 0x1D, 1)[0]
    value = (old & 0xF0) | cfg
    i2c.writeto_mem(0x68, 0x1D, bytes([value]))
    if i2c.readfrom_mem(0x68, 0x1D, 1)[0] != value:
        raise ValueError("MPU6886 accel DLPF not applied")
    return old, value


i2c = I2C(0, scl=22, sda=21, freq=400000)
imu = MPU6886(i2c)
imu._accel_so = imu._accel_fs(0x08) or imu._accel_so
if imu._accel_so != 8192:
    raise ValueError("MPU6886 driver did not apply the 4g scale")
GRAVITY = imu._accel_sf


def window_std_mg(samples=150, period_ms=100):
    n, s, q = 0, [0.0] * 3, [0.0] * 3
    deadline = utime.ticks_ms()
    for _ in range(samples):
        deadline = utime.ticks_add(deadline, period_ms)
        for axis, value in enumerate(imu.acceleration()):
            g = value / GRAVITY
            s[axis] += g
            q[axis] += g * g
        n += 1
        utime.sleep_ms(max(0, utime.ticks_diff(deadline, utime.ticks_ms())))
    return [1000 * max(0.0, q[a] / n - (s[a] / n) ** 2) ** 0.5 for a in range(3)]


results = {}
for cfg in (0, 6):
    old, new = apply_accel_dlpf(i2c, cfg)
    utime.sleep_ms(200)  # let the filter settle
    print("ACCEL_CONFIG2 0x%02x -> 0x%02x (A_DLPF_CFG=%d), recording 15 s..." % (old, new, cfg))
    results[cfg] = window_std_mg()
    print("  std mg  x=%.3f  y=%.3f  z=%.3f" % tuple(results[cfg]))

ratios = [results[6][a] / results[0][a] if results[0][a] else 0 for a in range(3)]
print("after/before  x=%.2f  y=%.2f  z=%.2f  (expected about 0.2)" % tuple(ratios))
print("Filter active" if max(ratios) < 0.5 else "CHECK: no clear noise reduction")
