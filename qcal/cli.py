import argparse
from .bench import run, table


def main(argv=None):
    ap = argparse.ArgumentParser(prog="qcal", description="Calibrated confidence for QEC decoders")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bench", help="simulate, decode, calibrate, certify a rejection threshold")
    b.add_argument("--distance", type=int, nargs="+", default=[5])
    b.add_argument("--p", type=float, nargs="+", default=[0.005])
    b.add_argument("--alpha", type=float, nargs="+", default=[0.001])
    b.add_argument("--delta", type=float, default=0.1)
    b.add_argument("--shots", type=int, default=400_000)
    b.add_argument("--epochs", type=int, default=20)
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--out", default="out")
    r_ = sub.add_parser("real", help="calibrate+certify on Google's public Sycamore surface-code data (Zenodo 6804040)")
    r_.add_argument("--root", default="data/google_qec3v5")
    r_.add_argument("--exp", nargs="*", default=None, help="experiment dir names (default: built-in d3/d5 set)")
    r_.add_argument("--alpha", type=float, nargs="+", default=[0.02, 0.05, 0.1])
    r_.add_argument("--windows", type=int, default=5)
    r_.add_argument("--epochs", type=int, default=30)
    r_.add_argument("--download", action="store_true", help="fetch the needed files (range requests, ~9 MB)")
    r_.add_argument("--out", default="out")
    sv = sub.add_parser("serve", help="run the qcal HTTP API locally (FastAPI + uvicorn)")
    sv.add_argument("--host", default="127.0.0.1"); sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--store", default="qcal_store", help="directory holding qcal.db (SQLite)")
    sv.add_argument("--workers", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "serve":
        import uvicorn
        from .api import create_app
        import os
        os.environ["QCAL_STORE"] = a.store
        if a.workers > 1:
            uvicorn.run("qcal.api:create_app", factory=True, host=a.host, port=a.port, workers=a.workers)
        else:
            uvicorn.run(create_app(a.store), host=a.host, port=a.port)
        return
    if a.cmd == "real":
        import os
        from .real import DEFAULT_EXPS, download, run_real, table as rtable
        exps = a.exp or DEFAULT_EXPS
        if a.download: download(exps, a.root)
        for e in exps:
            print(rtable(run_real(os.path.join(a.root, e), a.alpha, a.out, a.windows, a.epochs))); print()
        return
    for d in a.distance:
        for p in a.p:
            r = run(d, p, a.alpha, a.shots, a.delta, a.seed, a.epochs, a.out)
            print(table(r)); print()


if __name__ == "__main__":
    main()
