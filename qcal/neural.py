"""Neural decoder baseline on raw detection events + qcal confidence from its logit.

NNDecoder: MLP (dets -> logit of observable flip), trained with BCE on stim samples.
Confidence inputs fed to qcal:
  * nn_self   : P(NN decoder wrong) = isotonic(-|logit|)        (confidence of the NN's own decision)
  * hybrid    : logreg+isotonic on [gap, w_best, z_rel] for the MATCHING decision, where
                z_rel = logit * (1 - 2*pred_matching) (> 0 means the NN disagrees with matching).
"""
import numpy as np
import torch

torch.set_num_threads(4)


class NNDecoder:
    def __init__(self, hidden=(512, 256), epochs=6, lr=3e-3, batch=8192, seed=0):
        self.hidden, self.epochs, self.lr, self.batch, self.seed = hidden, epochs, lr, batch, seed
        self.net = None

    def _build(self, n_in):
        torch.manual_seed(self.seed)
        L, prev = [], n_in
        for h in self.hidden:
            L += [torch.nn.Linear(prev, h), torch.nn.ReLU()]; prev = h
        self.net = torch.nn.Sequential(*L, torch.nn.Linear(prev, 1))

    def fit(self, dets, obs, epochs=None, lr=None):
        if self.net is None:
            self._build(dets.shape[1])
        opt = torch.optim.Adam(self.net.parameters(), lr=lr or self.lr)
        E = epochs or self.epochs
        sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=lr or self.lr, total_steps=E * ((len(obs) + self.batch - 1) // self.batch))
        D = torch.from_numpy(np.ascontiguousarray(dets, dtype=np.uint8)); Y = torch.from_numpy(obs.astype(np.float32))
        g = torch.Generator().manual_seed(self.seed)
        self.net.train()
        for _ in range(E):
            perm = torch.randperm(len(Y), generator=g)
            for i in range(0, len(Y), self.batch):
                b = perm[i:i + self.batch]
                z = self.net(D[b].float()).squeeze(-1)
                loss = torch.nn.functional.binary_cross_entropy_with_logits(z, Y[b])
                opt.zero_grad(); loss.backward(); opt.step(); sched.step()
        return self

    def logit(self, dets):
        self.net.eval(); out = []
        with torch.no_grad():
            for i in range(0, len(dets), 65536):
                out.append(self.net(torch.from_numpy(np.ascontiguousarray(dets[i:i + 65536], dtype=np.uint8)).float()).squeeze(-1).numpy())
        return np.concatenate(out).astype(float)
