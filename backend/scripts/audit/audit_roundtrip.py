"""Read-only audit: firmware encoder (m5stack/b4_protocol.py) vs backend decoder.

Run from backend/ with the backend venv. Writes nothing to the repo.
"""
import importlib.util
import math
import random
import struct
import sys
from pathlib import Path

import numpy as np

BACKEND = Path.cwd()
REPO = BACKEND.parent
sys.path.insert(0, str(BACKEND))

spec = importlib.util.spec_from_file_location("fw_b4_protocol", REPO / "m5stack" / "b4_protocol.py")
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

from app.core import binary_protocol as proto  # noqa: E402
from app.services import binary_telemetry as bt  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))


# 1. Formats and sizes -------------------------------------------------------
check("v2 format string identical", fw.PACKET_FORMAT == proto.PACKET_FORMAT, fw.PACKET_FORMAT)
check("v3 format string identical", fw.UNTIMED_FORMAT == proto.UNTIMED_FORMAT, fw.UNTIMED_FORMAT)
check("v2 calcsize == 45", struct.calcsize(fw.PACKET_FORMAT) == proto.PACKET_SIZE == 45)
check("v3 calcsize == 58", struct.calcsize(fw.UNTIMED_FORMAT) == proto.UNTIMED_SIZE == 58)
check("GPS sentinel identical", fw.GPS_ABSENT == proto.GPS_ABSENT == -2147483648)
check("both formats little-endian '<'", fw.PACKET_FORMAT[0] == fw.UNTIMED_FORMAT[0] == "<")


def make_window(samples):
    w = fw.Window()
    for s in samples:
        w.add(s)
    return w


def reference(samples):
    a = np.asarray(samples, dtype=np.float64)
    ref = {}
    for i, axis in enumerate("xyz"):
        v = a[:, i]
        ref[f"accel_{axis}_mean"] = v.mean()
        ref[f"accel_{axis}_std"] = v.std(ddof=0)
        ref[f"accel_{axis}_min"] = v.min()
        ref[f"accel_{axis}_max"] = v.max()
    mag = np.abs(np.sqrt((a ** 2).sum(axis=1)) - 1.0)
    ref["activity"] = mag.mean()
    ref["activity_std"] = mag.std(ddof=0)
    return ref


# 2. Random round-trips (v2, GPS present/absent) -----------------------------
rng = random.Random(20261003)
max_err = 0.0
worst = None
n_cases = 3000
order_ok = True
for case in range(n_cases):
    kind = case % 4
    if kind == 0:   # resting: gravity on one axis + small noise
        g_axis = rng.randrange(3)
        samples = [tuple((1.0 if i == g_axis else 0.0) + rng.gauss(0, 0.02) for i in range(3)) for _ in range(150)]
    elif kind == 1:  # active, wide spread
        samples = [tuple(rng.uniform(-3.9, 3.9) for _ in range(3)) for _ in range(150)]
    elif kind == 2:  # negative-only axes
        samples = [tuple(rng.uniform(-4.0, -0.001) for _ in range(3)) for _ in range(150)]
    else:            # tilted gravity
        th = rng.uniform(0, math.pi)
        samples = [(math.sin(th) + rng.gauss(0, .1), rng.gauss(0, .1), math.cos(th) + rng.gauss(0, .1)) for _ in range(150)]
    samples = [tuple(max(-4.0, min(4.0, v)) for v in s) for s in samples]
    gps = None if case % 2 else (rng.uniform(-90, 90), rng.uniform(-180, 180), rng.randint(1, 50))
    raw = make_window(samples).encode(rng.randint(1, 65535), rng.randint(1577836800, 4294967295), gps, rng.randint(0, 100))
    dec = bt.decode_binary_payload(raw)
    ref = reference(samples)
    keys = list(proto.FEATURE_NAMES)
    order_ok &= [k for k in dec if k.startswith("accel_")] == keys
    for k, v in ref.items():
        err = abs(dec[k] - v)
        if err > max_err:
            max_err, worst = err, (case, k, dec[k], v)
    if gps is None:
        ok = dec["latitude"] is None and dec["longitude"] is None and dec["satellites"] == 0
    else:
        ok = abs(dec["latitude"] - gps[0]) <= 5e-7 and abs(dec["longitude"] - gps[1]) <= 5e-7 and dec["satellites"] == gps[2]
    if not ok:
        check(f"GPS round-trip case {case}", False, f"{gps} -> {dec['latitude']},{dec['longitude']},{dec['satellites']}")
    if (dec["sample_rate"], dec["window_samples"]) != (10, 150):
        check(f"profile case {case}", False, str((dec["sample_rate"], dec["window_samples"])))

check(f"{n_cases} random v2 round-trips: max |decoded - numpy(ddof=0)| <= 0.5 mg",
      max_err <= 0.0005 + 1e-9, f"max_err={max_err:.6g} worst={worst}")
check("decoded feature order == FEATURE_NAMES == x(mean,std,min,max), y(...), z(...)", order_ok)

# 3. Endianness spot check ----------------------------------------------------
w = make_window([(0.001, -0.002, 1.0)] * 150)
raw = w.encode(0x1234, 0x6A000000, None, 77)
check("transport_id bytes little-endian (34 12)", raw[1:3] == b"\x34\x12", raw[1:3].hex())
check("timestamp bytes little-endian", raw[3:7] == (0x6A000000).to_bytes(4, "little"), raw[3:7].hex())
check("GPS absent bytes = 00 00 00 80 x2, sats 0",
      raw[7:15] == b"\x00\x00\x00\x80" * 2 and raw[15] == 0, raw[7:16].hex())
x_mean = struct.unpack_from("<h", raw, 17)[0]
check("accel_x_mean int16 at offset 17 == round(0.001*1000) == 1", x_mean == 1, str(x_mean))
y_mean = struct.unpack_from("<h", raw, 17 + 8)[0]
check("accel_y_mean int16 at offset 25 == -2 (signed)", y_mean == -2, str(y_mean))

# 4. Extremes / int16 scale ---------------------------------------------------
for label, samples in {
    "all +4.0g": [(4.0, 4.0, 4.0)] * 150,
    "all -4.0g": [(-4.0, -4.0, -4.0)] * 150,
    "alternating +-4g (std=4)": [((4.0, -4.0, 4.0) if i % 2 else (-4.0, 4.0, -4.0)) for i in range(150)],
}.items():
    try:
        dec = bt.decode_binary_payload(make_window(samples).encode(1, 1789257600, None, 50))
        ref = reference(samples)
        err = max(abs(dec[k] - ref[k]) for k in ref)
        check(f"extreme {label} decodes, max_err={err:.2g}", err <= 0.0005 + 1e-9)
    except Exception as exc:  # noqa: BLE001
        check(f"extreme {label} decodes", False, repr(exc))
try:
    fw.Window().add((4.0001, 0, 0))
    check("firmware rejects |a| > 4.0 g", False)
except ValueError:
    check("firmware rejects |a| > 4.0 g", True)

# 5. GPS sentinel edge cases (hand-crafted packets) ---------------------------
base = list(struct.unpack(proto.PACKET_FORMAT, make_window([(0, 0, 1.0)] * 150).encode(1, 1789257600, None, 50)))
def crafted(lat, lon, sats):
    v = list(base)
    v[3], v[4], v[5] = lat, lon, sats
    return struct.pack(proto.PACKET_FORMAT, *v)
S = proto.GPS_ABSENT
for label, args, expect_ok in [
    ("sentinel/sentinel/sats=0 -> absent", (S, S, 0), True),
    ("sentinel/sentinel/sats=5 -> reject", (S, S, 5), False),
    ("valid lat/lon, sats=0 -> reject", (34_690_100, 135_195_500, 0), False),
    ("lat sentinel only -> reject", (S, 135_195_500, 5), False),
    ("lon sentinel only, sats=0 -> reject", (34_690_100, S, 0), False),
    ("0,0 with sats=4 -> accepted as real position (Null Island)", (0, 0, 4), True),
]:
    try:
        d = bt.decode_binary_payload(crafted(*args))
        check(f"sentinel: {label}", expect_ok, f"lat={d['latitude']} lon={d['longitude']} sats={d['satellites']}")
    except bt.BinaryMeasurementError as exc:
        check(f"sentinel: {label}", not expect_ok, str(exc))

# 6. v3 round-trip and version routing ----------------------------------------
samples = [(0.1, -0.2, 0.98)] * 150
w = make_window(samples)
raw3 = w.encode_untimed(42, 2**63 - 1, 4294967295, 15000, 2, None, 30)
check("v3 packet length 58", len(raw3) == 58, str(len(raw3)))
check("v3 header routes to version 3", bt.read_binary_header(raw3)[0] == 3)
d3 = bt.decode_untimed_payload(raw3)
check("v3 fields round-trip (session, sequence, elapsed, reason)",
      (d3["session_id"], d3["sequence"], d3["window_end_elapsed_ms"], d3["time_uncertainty_reason"])
      == (2**63 - 1, 4294967295, 15000, "holdover_expired"), str({k: d3[k] for k in ("session_id", "sequence", "window_end_elapsed_ms", "time_uncertainty_reason")}))
check("v3 GPS absent decodes to None", d3["latitude"] is None and d3["longitude"] is None)
ref = reference(samples)
check("v3 features match numpy", max(abs(d3[k] - ref[k]) for k in ref) <= 0.0005 + 1e-9)
raw3g = w.encode_untimed(42, 7, 1, 20000, 1, (5.35, -4.02, 7), 30)
d3g = bt.decode_untimed_payload(raw3g)
check("v3 GPS present round-trip", abs(d3g["latitude"] - 5.35) < 1e-6 and abs(d3g["longitude"] + 4.02) < 1e-6 and d3g["satellites"] == 7)
try:
    bt.decode_binary_payload(raw3)
    check("v3 rejected by dated decoder", False)
except bt.BinaryProtocolError as exc:
    check("v3 rejected by dated decoder", True, str(exc))
try:
    bt.decode_untimed_payload(make_window(samples).encode(1, 1789257600, None, 50))
    check("v2 rejected by untimed decoder", False)
except bt.BinaryProtocolError as exc:
    check("v2 rejected by untimed decoder", True, str(exc))
try:
    bt.read_binary_header(raw3[:45])
    check("v3 header with 45 B rejected", False)
except bt.BinaryProtocolError as exc:
    check("v3 header with 45 B rejected", True, str(exc))

# 7. Profiles: v1 (10,50) decodes, ingestion rejects with 422 ------------------
v1 = bytearray(make_window(samples).encode(1, 1789257600, None, 50)); v1[0] = 1
try:
    bt.decode_binary_payload(bytes(v1))
    check("v1 with GPS sentinel", False, "accepted")
except bt.BinaryMeasurementError as exc:
    check("v1 with GPS sentinel rejected (absent GPS is v2/v3 only)", True, str(exc))
v1 = bytearray(make_window(samples).encode(1, 1789257600, (5.35, -4.02, 7), 50)); v1[0] = 1
dv1 = bt.decode_binary_payload(bytes(v1))
check("v1 packet decodes to profile (10, 50)", (dv1["sample_rate"], dv1["window_samples"]) == (10, 50))
from fastapi import HTTPException  # noqa: E402
from app.schemas.telemetry import BinaryTelemetryCreate  # noqa: E402
from app.services.telemetry_ingestion import ingest_telemetry  # noqa: E402
for label, profile in [("5 s (10,50)", (10, 50)), ("missing (None,None)", (None, None))]:
    fields = {**dv1, "sample_rate": profile[0], "window_samples": profile[1]}
    try:
        data = BinaryTelemetryCreate(device_id="AUDIT", **fields)
        try:
            ingest_telemetry(data, db=None, idempotent=True, protocol_version=1)  # check precedes any DB access
            check(f"ingestion rejects {label}", False)
        except HTTPException as exc:
            check(f"ingestion rejects {label} with {exc.status_code}", exc.status_code == 422, exc.detail)
    except Exception as exc:  # pydantic ValidationError -> FastAPI 422
        check(f"schema rejects {label} (ValidationError -> 422)", type(exc).__name__ == "ValidationError", type(exc).__name__)
from app.api.v1.predict import PredictRequest  # noqa: E402
base_req = {k: dv1[k] for k in proto.FEATURE_NAMES}
for sr, ws in [(10, 50), (10, 150)]:
    try:
        PredictRequest(**base_req, sample_rate=sr, window_samples=ws)
        check(f"/predict schema accepts ({sr},{ws})", ws == 150)
    except Exception as exc:
        check(f"/predict schema rejects ({sr},{ws}) -> 422", ws != 150, type(exc).__name__)

# Report -----------------------------------------------------------------------
width = max(len(n) for n, _, _ in results)
fails = 0
for name, ok, detail in results:
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
print(f"\n{len(results) - fails}/{len(results)} checks passed")
