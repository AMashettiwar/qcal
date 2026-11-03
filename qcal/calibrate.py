"""Calibrated heads trained with proper scoring rules + post-hoc recalibration + metrics."""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.preprocessing import StandardScaler


def brier(p, y):
    return float(np.mean((p - y) ** 2))


def log_loss(p, y, eps=1e-12):
    p = np.clip(p, eps, 1 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def ece(p, y, bins=15, strategy="quantile"):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1)) if strategy == "quantile" else np.linspace(0, 1, bins + 1)
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    tot = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            tot += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(tot)


def reliability(p, y, bins=12):
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    idx = np.clip(np.searchsorted(edges, p, side="right") - 1, 0, bins - 1)
    xs, ys, ns = [], [], []
    for b in range(bins):
        m = idx == b
        if m.sum() > 0:
            xs.append(p[m].mean()); ys.append(y[m].mean()); ns.append(int(m.sum()))
    return np.array(xs), np.array(ys), np.array(ns)


class GapPlatt:
    """Baseline: P(err) = sigmoid(a*gap + b) -- the standard logistic gap calibration."""
    def fit(self, X, y):
        self.m = LogisticRegression(C=1e4, max_iter=2000).fit(X[:, :1], y); return self
    def predict(self, X):
        return self.m.predict_proba(X[:, :1])[:, 1]


class LogRegHead:
    """Multi-feature logistic head (log loss = strictly proper)."""
    def fit(self, X, y):
        self.s = StandardScaler().fit(X)
        self.m = LogisticRegression(C=1.0, max_iter=2000).fit(self.s.transform(X), y); return self
    def predict(self, X):
        return self.m.predict_proba(self.s.transform(X))[:, 1]


class MLPHead:
    """Small torch MLP trained on BCE (log loss) or Brier."""
    def __init__(self, loss="bce", epochs=30, hidden=32, seed=0):
        self.loss, self.epochs, self.hidden, self.seed = loss, epochs, hidden, seed
    def fit(self, X, y):
        import torch
        torch.manual_seed(self.seed)
        self.s = StandardScaler().fit(X)
        Xt = torch.tensor(self.s.transform(X), dtype=torch.float32)
        yt = torch.tensor(y, dtype=torch.float32)
        self.net = torch.nn.Sequential(torch.nn.Linear(X.shape[1], self.hidden), torch.nn.ReLU(),
                                       torch.nn.Linear(self.hidden, self.hidden), torch.nn.ReLU(),
                                       torch.nn.Linear(self.hidden, 1))
        opt = torch.optim.Adam(self.net.parameters(), lr=3e-3)
        n = len(yt)
        for _ in range(self.epochs):
            perm = torch.randperm(n)
            for i in range(0, n, 4096):
                b = perm[i:i + 4096]
                z = self.net(Xt[b]).squeeze(-1)
                if self.loss == "bce":
                    l = torch.nn.functional.binary_cross_entropy_with_logits(z, yt[b])
                else:
                    l = ((torch.sigmoid(z) - yt[b]) ** 2).mean()
                opt.zero_grad(); l.backward(); opt.step()
        return self
    def predict(self, X):
        import torch
        with torch.no_grad():
            z = self.net(torch.tensor(self.s.transform(X), dtype=torch.float32)).squeeze(-1)
        return torch.sigmoid(z).numpy().astype(float)


class Isotonic:
    """Post-hoc recalibration of any score on a held-out split."""
    def fit(self, p, y):
        self.m = IsotonicRegression(out_of_bounds="clip", y_min=0, y_max=1).fit(p, y); return self
    def predict(self, p):
        return self.m.predict(p)
