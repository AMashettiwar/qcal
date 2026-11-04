"""Minimal Python client for the qcal API.

    from qcal.client import QcalClient
    c = QcalClient("http://127.0.0.1:8000", api_key="...")   # or env QCAL_API_KEY
    c.calibrate("chip-a", "w0", dets, flips, dem=open("model.dem").read())
    r = c.decode("chip-a", dets, alpha=0.01)
Automatic recalibration after drift: qcal.recal.Recalibrator.
`dets` may be a 0/1 numpy array (shots x detectors) or a list of '0'/'1' strings.
"""
import os
import numpy as np


def _to01(dets):
    if isinstance(dets, list) and (not dets or isinstance(dets[0], str)):
        return dets
    a = np.asarray(dets, dtype=np.uint8)
    return ["".join(map(str, row)) for row in a.tolist()] if a.size else []


class QcalError(RuntimeError):
    def __init__(self, status, detail):
        super().__init__(f"HTTP {status}: {detail}"); self.status, self.detail = status, detail


class QcalClient:
    def __init__(self, url="http://127.0.0.1:8000", api_key=None, timeout=600, http=None):
        import httpx
        key = api_key if api_key is not None else os.environ.get("QCAL_API_KEY")
        self.h = http or httpx.Client(base_url=url, timeout=timeout)
        if key: self.h.headers["X-API-Key"] = key

    def _req(self, method, path, **kw):
        r = self.h.request(method, path, **kw)
        if r.status_code >= 400:
            try: d = r.json().get("detail")
            except Exception: d = r.text
            raise QcalError(r.status_code, d)
        return r.json()

    def health(self): return self._req("GET", "/health")
    def metrics(self): return self._req("GET", "/metrics")
    def profiles(self, device_id): return self._req("GET", f"/profiles/{device_id}")

    def calibrate(self, device_id, window_id, dets, logical_flips, dem=None, circuit=None, simulated=None, pool_from=None, **opts):
        body = {"device_id": device_id, "window_id": window_id, "syndromes": _to01(dets),
                "logical_flips": [int(x) for x in np.asarray(logical_flips).reshape(-1)], **opts}
        if pool_from is not None: body["pool_from"] = pool_from
        for k, v in (("dem", dem), ("circuit", circuit), ("simulated", simulated)):
            if v is not None: body[k] = str(v) if k != "simulated" else v
        return self._req("POST", "/calibrate", json=body)

    def decode(self, device_id, dets, alpha):
        return self._req("POST", "/decode", json={"device_id": device_id, "syndromes": _to01(dets), "alpha": alpha})
