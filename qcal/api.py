"""qcal hosted API: calibrated confidence + certified accept/reject for a QEC decoder.

Run:  qcal serve --store qcal_store --port 8000
Storage: one SQLite file <store>/qcal.db (WAL mode, safe for concurrent requests; back up by copying it).
  devices(device_id, info json) | windows(device_id, window_id, seq, npz blob) | profiles(device_id, window_id, seq, json)
Security / ops (env vars):
  QCAL_API_KEY        if set, every endpoint except /health requires header X-API-Key (constant-time compare)
  QCAL_RATE_PER_MIN   per-client request budget per minute (default 120)
  QCAL_MAX_BODY_MB    max request body size (default 200)
  QCAL_SHIFT_P        KS p-value below which /decode flags a distribution shift and refuses (default 0.001)
  QCAL_LOCAL_P        per-detector check: refuse a batch when any single detector fires more often than in calibration,
                      Bonferroni-corrected p-value below this (default 0 = off; 0.001 is the setting tested in
                      docs/VALIDATION.md section 2c). Off by default because on real Willow data it halves the accept rate.
Calibration = cumulative pool of all windows so far -> random split 50% head fit / 25% isotonic /
25% Learn-then-Test, certified at alpha_eff = margin * alpha (default margin 0.8, delta 0.1).
"""
import hashlib, hmac, io, json, logging, os, re, sqlite3, threading, time, uuid
from collections import defaultdict, deque
from typing import Literal
import numpy as np
import stim
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from scipy.stats import ks_2samp, binom
from pydantic import BaseModel, Field, field_validator, model_validator
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from .real import DemSoftMatcher
from .conformal import ltt_threshold

MAX_SHOTS = 200_000
MIN_POOL = 2_000
DEFAULT_ALPHAS = [0.001, 0.003, 0.01, 0.03, 0.05, 0.1]
_ID = r"^[A-Za-z0-9_.-]{1,64}$"


# ---------------- schemas ----------------
class SimSpec(BaseModel):
    distance: int = Field(ge=3, le=15)
    p: float = Field(gt=0, lt=0.05)
    rounds: int | None = Field(default=None, ge=1, le=100)


class CalibrateRequest(BaseModel):
    device_id: str = Field(pattern=_ID)
    window_id: str = Field(pattern=_ID)
    syndromes: list[str] = Field(description="one '0'/'1' string per shot, one char per detector")
    logical_flips: list[int] = Field(description="true observable flip (0/1) per shot")
    dem: str | None = Field(default=None, description="stim detector error model text (first call only)")
    circuit: str | None = Field(default=None, description="stim circuit text; DEM derived from it")
    simulated: SimSpec | None = Field(default=None, description="use stim's rotated_memory_z circuit")
    head: Literal["gap", "hybrid"] = "hybrid"
    alphas: list[float] = Field(default_factory=lambda: list(DEFAULT_ALPHAS))
    delta: float = Field(default=0.1, gt=0, lt=0.5)
    margin: float = Field(default=0.8, gt=0, le=1)
    seed: int = 0

    @field_validator("alphas")
    @classmethod
    def _alphas(cls, v):
        if not v or any(not (0 < a < 0.5) for a in v):
            raise ValueError("alphas must be a non-empty list of values in (0, 0.5)")
        return sorted(set(v))

    @model_validator(mode="after")
    def _shapes(self):
        if len(self.syndromes) != len(self.logical_flips):
            raise ValueError(f"syndromes ({len(self.syndromes)}) and logical_flips ({len(self.logical_flips)}) differ in length")
        if not 1 <= len(self.syndromes) <= MAX_SHOTS:
            raise ValueError(f"need 1..{MAX_SHOTS} shots per request")
        if any(f not in (0, 1) for f in self.logical_flips):
            raise ValueError("logical_flips must be 0/1")
        if sum(x is not None for x in (self.dem, self.circuit, self.simulated)) > 1:
            raise ValueError("give at most one of dem, circuit, simulated")
        return self


class DecodeRequest(BaseModel):
    device_id: str = Field(pattern=_ID)
    syndromes: list[str]
    alpha: float = Field(gt=0, lt=0.5)

    @field_validator("syndromes")
    @classmethod
    def _n(cls, v):
        if not 1 <= len(v) <= MAX_SHOTS:
            raise ValueError(f"need 1..{MAX_SHOTS} shots per request")
        return v


# ---------------- helpers ----------------
def _parse(synd, n_det):
    bad = next((i for i, s in enumerate(synd) if len(s) != n_det or re.search(r"[^01]", s)), None)
    if bad is not None:
        raise HTTPException(422, f"syndrome {bad} must be a string of exactly {n_det} '0'/'1' characters (got length {len(synd[bad])})")
    return (np.frombuffer("".join(synd).encode(), dtype=np.uint8) - 48).reshape(len(synd), n_det)


def _features(m, dets):
    pred, w, gap = m.decode(dets)
    return pred, np.column_stack([gap, w, dets.sum(1).astype(float)])


def _min_cal(alpha, delta):
    """Smallest accepted set that could ever pass the binomial test (zero errors)."""
    return int(np.ceil(np.log(delta) / np.log1p(-alpha)))


def _npz(**kw):
    b = io.BytesIO(); np.savez_compressed(b, **kw); return b.getvalue()


class Store:
    """Single-file SQLite store. One connection per thread; WAL lets readers run during writes."""

    def __init__(self, root):
        self.root = root; os.makedirs(root, exist_ok=True)
        self.path = os.path.join(root, "qcal.db"); self._m = {}; self._tl = threading.local()
        self.write_lock = threading.Lock()
        c = self.db
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
          CREATE TABLE IF NOT EXISTS devices(device_id TEXT PRIMARY KEY, info TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS windows(device_id TEXT, window_id TEXT, seq INTEGER, data BLOB,
                                             PRIMARY KEY(device_id, window_id));
          CREATE TABLE IF NOT EXISTS profiles(device_id TEXT, window_id TEXT, seq INTEGER, prof TEXT,
                                              PRIMARY KEY(device_id, window_id));""")
        c.commit()

    @property
    def db(self):
        c = getattr(self._tl, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
            c.execute("PRAGMA busy_timeout=30000"); self._tl.c = c
        return c

    def devices(self):
        return [r[0] for r in self.db.execute("SELECT device_id FROM devices ORDER BY device_id")]

    def device(self, d, required=True):
        r = self.db.execute("SELECT info FROM devices WHERE device_id=?", (d,)).fetchone()
        if r is None:
            if not required: return None
            raise HTTPException(404, f"unknown device '{d}': call /calibrate with dem, circuit or simulated first")
        return json.loads(r[0])

    def put_device(self, d, info):
        self.db.execute("INSERT OR REPLACE INTO devices VALUES(?,?)", (d, json.dumps(info)))

    def n_windows(self, d):
        return self.db.execute("SELECT COUNT(*) FROM windows WHERE device_id=?", (d,)).fetchone()[0]

    def has_window(self, d, w):
        return self.db.execute("SELECT 1 FROM windows WHERE device_id=? AND window_id=?", (d, w)).fetchone() is not None

    def put_window(self, d, w, F, y, dc):
        self.db.execute("INSERT INTO windows VALUES(?,?,?,?)", (d, w, time.time_ns(), _npz(F=F, y=y, dc=dc)))

    def windows(self, d):
        out = []
        for w, blob in self.db.execute("SELECT window_id, data FROM windows WHERE device_id=? ORDER BY seq", (d,)):
            z = np.load(io.BytesIO(blob)); out.append((w, z["F"], z["y"], z["dc"] if "dc" in z else None))
        return out

    def put_profile(self, d, w, prof):
        self.db.execute("INSERT OR REPLACE INTO profiles VALUES(?,?,?,?)", (d, w, time.time_ns(), json.dumps(prof)))

    def history(self, d):
        return [json.loads(r[0]) for r in self.db.execute("SELECT prof FROM profiles WHERE device_id=? ORDER BY seq", (d,))]

    def matcher(self, d):
        info = self.device(d)
        key = (d, info["dem_sha"])
        if key not in self._m:
            self._m[key] = DemSoftMatcher(stim.DetectorErrorModel(info["dem"]))
        return self._m[key], info

    def profile(self, d):
        r = self.db.execute("SELECT prof FROM profiles WHERE device_id=? ORDER BY seq DESC LIMIT 1", (d,)).fetchone()
        if r is None:
            raise HTTPException(404, f"device '{d}' has no calibration profile yet")
        return json.loads(r[0])


DRIFT_LADDER = [round(1 + 0.01 * i, 2) for i in range(1, 51)]  # syndrome-weight ratios 1.01 .. 1.50


def _drift_exp(dem):
    """LER ~ p^((d+1)/2) below threshold; d = weight of the DEM's shortest graphlike logical error."""
    try:
        return (len(dem.shortest_graphlike_error()) + 1) / 2
    except Exception:
        return None


def _fit_profile(F, y, head, alphas, delta, margin, seed, drift_exp=None, det_counts=None, n_shots=None):
    n = len(y)
    idx = np.random.default_rng(seed).permutation(n)
    a, b = n // 2, (3 * n) // 4
    tr, rc, ca = idx[:a], idx[a:b], idx[b:]
    cols = [0] if head == "gap" else [0, 1, 2]
    mu, sd = F[tr][:, cols].mean(0), F[tr][:, cols].std(0) + 1e-9
    Z = lambda X: (X[:, cols] - mu) / sd
    lr = LogisticRegression(C=1e4 if head == "gap" else 1.0, max_iter=2000).fit(Z(F[tr]), y[tr])
    raw = lambda X: lr.predict_proba(Z(X))[:, 1]
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(raw(F[rc]), y[rc])
    gmax = float(F[:, 0].max())
    score = lambda X: iso.predict(raw(X)) - 1e-9 * X[:, 0] / (1 + gmax)
    s_rc, s_ca = score(F[rc]), score(F[ca])
    grid = np.unique(np.quantile(s_rc, np.linspace(0, 1, 2000)))
    certs = {}
    for al in alphas:
        ae = margin * al; need = _min_cal(ae, delta)
        t = ltt_threshold(s_ca, y[ca], ae, delta, grid=grid)
        if t is None:
            why = (f"calibration split has {len(ca)} shots; certifying alpha_eff={ae:.3g} at delta={delta} needs "
                   f"at least {need} accepted shots with zero errors (in practice ~5x that)"
                   if len(ca) < 5 * need else
                   "no threshold passed the Learn-then-Test binomial test (decoder too unreliable at this alpha)")
            certs[str(al)] = {"certified": False, "reason": why, "alpha_eff": ae}
        else:
            acc = s_ca <= t
            certs[str(al)] = {"certified": True, "threshold": float(t), "alpha_eff": ae,
                              "cal_accept_rate": float(acc.mean()), "cal_accepted": int(acc.sum()),
                              "cal_accepted_errors": int(y[ca][acc].sum())}
            if drift_exp:
                # label-free drift correction: if a decode batch's mean syndrome weight is r x the calibration
                # mean, certify at alpha_eff / r^drift_exp instead. Thresholds precomputed for a ladder of r.
                lad = []
                for rr in DRIFT_LADDER:
                    aer = ae / rr ** drift_exp; nd = _min_cal(aer, delta)
                    pf = max(1, min(5, int(0.4 * len(ca) / nd)))  # label-independent start, kept feasible for this cal size
                    tr_ = ltt_threshold(s_ca, y[ca], aer, delta, grid=grid, power_factor=pf)
                    if tr_ is None: break
                    lad.append([rr, float(tr_)])
                certs[str(al)]["drift_ladder"] = lad
    ref = np.sort(s_ca)[np.linspace(0, len(s_ca) - 1, min(2000, len(s_ca))).astype(int)]
    return {"ref_scores": ref.tolist(), "sw_mean": float(F[:, 2].mean()), "drift_exp": drift_exp,
            "det_counts": None if det_counts is None else np.asarray(det_counts).astype(int).tolist(), "det_shots": n_shots, "head": head, "cols": cols, "mu": mu.tolist(), "sd": sd.tolist(),
            "coef": lr.coef_[0].tolist(), "intercept": float(lr.intercept_[0]),
            "iso_x": iso.X_thresholds_.tolist(), "iso_y": iso.y_thresholds_.tolist(), "gmax": gmax,
            "delta": delta, "margin": margin, "pool_size": int(n), "cal_size": int(len(ca)),
            "pool_ler": float(y.mean()), "certificates": certs}


def _predict(prof, F):
    X = (F[:, prof["cols"]] - np.array(prof["mu"])) / np.array(prof["sd"])
    raw = 1 / (1 + np.exp(-(X @ np.array(prof["coef"]) + prof["intercept"])))
    p = np.interp(raw, prof["iso_x"], prof["iso_y"])
    return p, p - 1e-9 * F[:, 0] / (1 + prof["gmax"])


def _drift_threshold(prof, cert, sw):
    """Return (threshold or None, info) after the syndrome-weight drift correction."""
    if not cert["certified"]:
        return None, {"applied": False}
    if prof.get("sw_mean") is None or "drift_ladder" not in cert:
        return cert["threshold"], {"applied": False, "reason": "profile has no drift ladder (recalibrate)"}
    rr = float(np.mean(sw) / prof["sw_mean"])
    info = {"applied": True, "sw_ratio": rr, "drift_exp": prof["drift_exp"]}
    if rr <= 1.0:
        return cert["threshold"], info
    for r_, t in cert["drift_ladder"]:
        if r_ >= rr:
            return t, {**info, "ladder_ratio": r_}
    return None, {**info, "refused": f"syndrome weight is {rr:.3f}x calibration; no certified threshold that far out. Recalibrate."}


def _local_shift(prof, counts, n, level):
    """Per-detector check for drift in one place (a bad qubit or a bad round), which barely moves the mean
    syndrome weight. For each detector, conditional on its total count in calibration + batch, the batch's share is
    Binomial(total, n / (n + n_cal)) if nothing changed; one-sided test for 'fires more often now', Bonferroni over detectors."""
    if not level or prof.get("det_counts") is None or n < 200:
        return {"checked": False, "detected": False}
    kc = np.asarray(prof["det_counts"]); kb = np.asarray(counts); tot = kc + kb
    pv = binom.sf(kb - 1, tot, n / (n + prof["det_shots"]))
    j = int(np.argmin(pv)); padj = float(min(1.0, pv[j] * len(pv)))
    return {"checked": True, "p_adjusted": padj, "threshold": level, "detected": padj < level, "detector": j,
            "rate_ratio": float((kb[j] / n) / max(kc[j] / prof["det_shots"], 1e-12))}


# ---------------- app ----------------
log = logging.getLogger("qcal")


def _setup_logging():
    if not log.handlers:
        h = logging.StreamHandler(); h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h); log.setLevel(logging.INFO); log.propagate = False


def create_app(store_dir=None, api_key=None, rate_per_min=None, max_body_mb=None, shift_p=None, local_p=None):
    _setup_logging()
    S = Store(store_dir or os.environ.get("QCAL_STORE", "qcal_store"))
    KEY = api_key if api_key is not None else os.environ.get("QCAL_API_KEY", "")
    RATE = int(rate_per_min or os.environ.get("QCAL_RATE_PER_MIN", 120))
    MAXB = float(max_body_mb or os.environ.get("QCAL_MAX_BODY_MB", 200)) * 1e6
    SHIFT_P = float(shift_p if shift_p is not None else os.environ.get("QCAL_SHIFT_P", 1e-3))
    LOCAL_P = float(local_p if local_p is not None else os.environ.get("QCAL_LOCAL_P", 0))
    stats = {"started": time.time(), "requests": defaultdict(int), "status": defaultdict(int), "shots_decoded": 0,
             "shots_accepted": 0, "shift_refusals": 0, "auth_failures": 0, "rate_limited": 0, "latency_ms_sum": defaultdict(float)}
    hits = defaultdict(deque); hl = threading.Lock()
    app = FastAPI(title="qcal", version="0.4.0",
                  description="Calibrated P(logical error) and certified accept/reject for PyMatching decoding.")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        rid = uuid.uuid4().hex[:12]; t0 = time.time(); path = request.url.path
        def done(resp, **extra):
            ms = (time.time() - t0) * 1000
            stats["requests"][path] += 1; stats["status"][str(resp.status_code)] += 1; stats["latency_ms_sum"][path] += ms
            log.info(json.dumps({"ts": round(t0, 3), "rid": rid, "method": request.method, "path": path,
                                 "status": resp.status_code, "ms": round(ms, 1), **extra}))
            resp.headers["X-Request-ID"] = rid; return resp
        if KEY and path not in ("/health", "/docs", "/openapi.json"):
            got = request.headers.get("x-api-key", "")
            if not hmac.compare_digest(got.encode(), KEY.encode()):
                stats["auth_failures"] += 1
                return done(JSONResponse({"detail": "missing or invalid X-API-Key"}, status_code=401))
        cl = request.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > MAXB:
            return done(JSONResponse({"detail": f"request body {int(cl)/1e6:.1f} MB exceeds limit {MAXB/1e6:.0f} MB"}, status_code=413))
        who = hashlib.sha256((request.headers.get("x-api-key") or (request.client.host if request.client else "?")).encode()).hexdigest()[:12]
        now = time.time()
        with hl:
            q = hits[who]
            while q and now - q[0] > 60: q.popleft()
            if len(q) >= RATE:
                stats["rate_limited"] += 1
                return done(JSONResponse({"detail": f"rate limit {RATE}/min exceeded"}, status_code=429, headers={"Retry-After": "60"}))
            q.append(now)
        return done(await call_next(request), client=who)

    @app.get("/health")
    def health():
        return {"status": "ok", "version": app.version, "auth": bool(KEY), "devices": S.devices()}

    @app.get("/metrics")
    def metrics():
        return {"uptime_s": round(time.time() - stats["started"], 1), "requests": dict(stats["requests"]),
                "status_codes": dict(stats["status"]), "shots_decoded": stats["shots_decoded"],
                "shots_accepted": stats["shots_accepted"], "shift_refusals": stats["shift_refusals"],
                "auth_failures": stats["auth_failures"], "rate_limited": stats["rate_limited"],
                "mean_latency_ms": {k: round(v / stats["requests"][k], 1) for k, v in stats["latency_ms_sum"].items() if stats["requests"][k]},
                "devices": len(S.devices())}

    @app.post("/calibrate")
    def calibrate(r: CalibrateRequest):
        with S.write_lock:
            return _calibrate(r)

    def _calibrate(r):
        if r.dem or r.circuit or r.simulated:
            try:
                if r.dem: dem = stim.DetectorErrorModel(r.dem); src = "dem"
                elif r.circuit: dem = stim.Circuit(r.circuit).detector_error_model(decompose_errors=True); src = "circuit"
                else:
                    from .data import make_circuit
                    dem = make_circuit(r.simulated.distance, r.simulated.p, r.simulated.rounds).detector_error_model(decompose_errors=True)
                    src = f"simulated:{r.simulated.model_dump()}"
            except Exception as e:
                raise HTTPException(422, f"could not build a detector error model: {e}")
            if dem.num_observables != 1:
                raise HTTPException(422, f"DEM must have exactly 1 logical observable (has {dem.num_observables})")
            txt = str(dem); old = S.device(r.device_id, required=False)
            if old and old["dem"] != txt and S.n_windows(r.device_id):
                raise HTTPException(409, "device already has calibration windows under a different DEM; use a new device_id")
            S.put_device(r.device_id, {"device_id": r.device_id, "source": src, "num_detectors": dem.num_detectors, "dem": txt,
                                       "dem_sha": hashlib.sha256(txt.encode()).hexdigest()[:16], "created": time.time()})
            S.db.commit()
        m, info = S.matcher(r.device_id)
        dets = _parse(r.syndromes, info["num_detectors"])
        if S.has_window(r.device_id, r.window_id):
            raise HTTPException(409, f"window '{r.window_id}' already stored for device '{r.device_id}'")
        pred, F = _features(m, dets)
        y = (pred != np.array(r.logical_flips, dtype=np.uint8)).astype(np.int64)
        S.put_window(r.device_id, r.window_id, F, y, dets.sum(0).astype(np.int64))
        wins = S.windows(r.device_id)
        F_all, y_all = np.concatenate([w[1] for w in wins]), np.concatenate([w[2] for w in wins])
        dc_all = None if any(w[3] is None for w in wins) else np.sum([w[3] for w in wins], axis=0)
        base = {"device_id": r.device_id, "window_id": r.window_id, "windows_used": [w[0] for w in wins],
                "batch_size": len(y), "batch_ler": float(y.mean())}
        if len(y_all) < MIN_POOL or y_all.sum() < 10:
            prof = {**base, "status": "not_certified", "pool_size": int(len(y_all)),
                    "reason": f"cumulative calibration pool has {len(y_all)} shots and {int(y_all.sum())} decoder errors; "
                              f"need at least {MIN_POOL} shots and 10 errors to fit a calibrated head and certify. "
                              f"Send more calibration windows."}
        else:
            prof = {**base, "status": "ok", **_fit_profile(F_all, y_all, r.head, r.alphas, r.delta, r.margin, r.seed,
                                                               drift_exp=_drift_exp(stim.DetectorErrorModel(info["dem"])),
                                                               det_counts=dc_all, n_shots=int(len(y_all)))}
        prof["fitted_at"] = time.time()
        S.put_profile(r.device_id, r.window_id, prof); S.db.commit()
        return _public(prof)

    @app.post("/decode")
    def decode(r: DecodeRequest):
        m, info = S.matcher(r.device_id); prof = S.profile(r.device_id)
        if prof["status"] != "ok":
            raise HTTPException(409, f"device not certified: {prof['reason']}")
        cert = prof["certificates"].get(str(r.alpha)) or prof["certificates"].get(repr(float(r.alpha)))
        if cert is None:
            raise HTTPException(422, f"alpha={r.alpha} not in calibrated alphas {list(prof['certificates'])}; recalibrate with it")
        dets = _parse(r.syndromes, info["num_detectors"])
        pred, F = _features(m, dets)
        p, s = _predict(prof, F)
        # shift monitor: compare this batch's score distribution with the calibration split (needs >= 200 shots)
        shift = {"checked": False}
        if len(s) >= 200 and prof.get("ref_scores"):
            ksp = float(ks_2samp(s, np.array(prof["ref_scores"])).pvalue)
            shift = {"checked": True, "ks_p": ksp, "threshold": SHIFT_P, "detected": ksp < SHIFT_P,
                     "batch_mean_p": float(p.mean())}
        local = _local_shift(prof, dets.sum(0), len(dets), LOCAL_P)
        refused = shift.get("detected", False) or local["detected"]
        thr, drift = _drift_threshold(prof, cert, F[:, 2])
        refused = refused or ("refused" in drift)
        accept = (s <= thr) if (thr is not None and not refused) else np.zeros(len(p), bool)
        stats["shots_decoded"] += len(p); stats["shots_accepted"] += int(accept.sum()); stats["shift_refusals"] += int(refused)
        if "refused" in drift:
            guarantee = "none: " + drift["refused"]
        elif local["detected"]:
            guarantee = (f"none: detector {local['detector']} fires {local['rate_ratio']:.2f}x as often as in calibration "
                         f"(corrected p={local['p_adjusted']:.2g} < {LOCAL_P}), a sign that one part of the device changed; "
                         "everything rejected. Send a fresh labeled window to /calibrate.")
        elif refused:
            guarantee = ("none: this batch's syndrome statistics differ from the calibration data (KS p="
                         f"{shift['ks_p']:.2g} < {SHIFT_P}); everything rejected. Send a fresh labeled window to /calibrate.")
        elif cert["certified"]:
            guarantee = (f"With probability >= {1 - prof['delta']:.2f} over the calibration data, P(logical error | accepted) "
                         f"<= {cert['alpha_eff']:.3g} (<= alpha={r.alpha}) for shots exchangeable with calibration shots.")
        else:
            guarantee = "none: everything rejected"
        return {"device_id": r.device_id, "n_shots": len(p),
                "correction": pred.astype(int).tolist(),
                "p_logical_error": np.round(p, 6).tolist(), "accept": accept.tolist(),
                "accept_rate": float(accept.mean()), "shift": shift, "local_shift": local, "drift_correction": drift,
                "certificate": {"alpha": r.alpha, "alpha_eff": cert["alpha_eff"], "delta": prof["delta"],
                                "certified": cert["certified"] and not refused, "threshold": thr,
                                "reason": (drift.get("refused") or ("drift in one detector" if local["detected"] else None)
                                           or ("distribution shift detected" if refused else cert.get("reason"))),
                                "calibration_size": prof["cal_size"],
                                "pool_size": prof["pool_size"], "windows_used": prof["windows_used"], "head": prof["head"],
                                "guarantee": guarantee}}

    @app.get("/profiles/{device_id}")
    def profiles(device_id: str):
        S.device(device_id)
        hist = [_public(h) for h in S.history(device_id)]
        return {"device_id": device_id, "latest": hist[-1] if hist else None, "history": hist}

    return app


def _public(p):
    return {k: v for k, v in p.items() if k not in ("iso_x", "iso_y", "mu", "sd", "coef", "intercept", "cols", "gmax", "ref_scores", "det_counts")}
