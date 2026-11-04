"""Drift-triggered recalibration (opt-in). Without it, once the shift monitor or the drift ladder refuses a batch,
every later batch is refused until someone sends a fresh labeled window to /calibrate. This does that automatically.

    rec = Recalibrator(client, "chip-a", alpha=0.01, window_shots=4000, pool="recent", alphas=[0.01])
    for batch in stream:                       # time order
        if rec.needs_labels:                   # run known-state shots (e.g. prepare |1>, so the true flip is known)
            rec.add_labeled(dets, flips)       # these shots are spent on calibration and are never kept
        else:
            r = rec.decode(dets)               # normal use; r["accept"] marks the shots to keep

The cost is labels. After a refusal the next `window_shots` shots must have known logical outcomes, which in a lab means
dedicated known-state test runs. Those shots are used only to refit; certificates apply to later batches only.
pool="recent": refit on the windows sent since the refusal (the stale pool is dropped, pool_from in /calibrate).
pool="cumulative": append the window to everything sent before.
If the requested alpha is still not certified after `max_windows` windows, it stops asking for labels (gave_up) and
later batches are refused until the profile certifies again.

Warning: in my held-out evaluation (docs/RECALIBRATION.md) this broke one cap on real IBM data (0.511% kept error at
alpha=0.005), lost net kept shots on a chip whose drift came and went, and wasted labels at alpha=0.002. Use it for
lasting drift at a loose enough alpha, and check the results.
"""
import numpy as np
from .client import QcalError


class Recalibrator:
    def __init__(self, client, device_id, alpha, window_shots=4000, pool="recent", max_windows=5, prefix="recal", **cal_opts):
        assert pool in ("recent", "cumulative")
        self.c, self.dev, self.alpha, self.W, self.pool, self.max_windows, self.prefix = (
            client, device_id, alpha, int(window_shots), pool, int(max_windows), prefix)
        self.cal_opts = cal_opts
        self.needs_labels = False
        self.certified = self._ok(client.profiles(device_id)["latest"])
        self._buf = []; self._from = None; self._ep_windows = 0
        self.recalibrations = 0; self.episodes = 0; self.gave_up = 0; self.labeled_shots = 0; self.events = []

    def _ok(self, prof):
        c = (prof or {}).get("certificates", {}).get(str(self.alpha))
        return bool(prof and prof.get("status") == "ok" and c and c.get("certified"))

    def decode(self, dets):
        """Decode one batch. A refusal under a working profile starts a recalibration episode."""
        n = len(dets)
        if not self.certified:
            return {"accept": [False] * n, "refused": True, "correction": None, "reason": "no certified profile"}
        try:
            r = self.c.decode(self.dev, dets, self.alpha)
        except QcalError as e:
            if e.status != 409: raise
            return {"accept": [False] * n, "refused": True, "correction": None, "reason": e.detail}
        if r["refused"] and not self.needs_labels:
            self.needs_labels = True; self._from = None; self._ep_windows = 0; self.episodes += 1
            self.events.append({"event": "refused", "reason": r["certificate"]["reason"]})
        return r

    def add_labeled(self, dets, flips):
        """dets: 0/1 array (shots x detectors). Collect known-outcome shots; once `window_shots` are in, send them to /calibrate. Returns the profile or None."""
        self._buf.append((np.asarray(dets), np.asarray(flips).reshape(-1)))
        self.labeled_shots += len(flips)
        if sum(len(b[1]) for b in self._buf) < self.W:
            return None
        d = np.concatenate([b[0] for b in self._buf]); y = np.concatenate([b[1] for b in self._buf]); self._buf = []
        wid = f"{self.prefix}{self.recalibrations}"
        pf = (self._from or wid) if self.pool == "recent" else None
        prof = self.c.calibrate(self.dev, wid, d, y, pool_from=pf, **self.cal_opts)
        self._from = pf; self.recalibrations += 1; self._ep_windows += 1
        self.certified = self._ok(prof)
        if self.certified or self._ep_windows >= self.max_windows:
            self.needs_labels = False
            if not self.certified: self.gave_up += 1
        self.events.append({"event": "recalibrated", "window": wid, "pool_from": pf, "pool_size": prof.get("pool_size"),
                            "certified": self.certified})
        return prof

    def summary(self):
        return {"recalibrations": self.recalibrations, "episodes": self.episodes, "gave_up": self.gave_up,
                "labeled_shots": self.labeled_shots, "pool": self.pool, "window_shots": self.W}
