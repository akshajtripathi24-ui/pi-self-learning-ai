"""A tiny GPT: the same kind of AI as ChatGPT, just about a million times smaller.

It reads a line of text one "token" (letter or digit) at a time and guesses the next one.
Inside: token and position "embeddings", then a few transformer blocks (attention + a small neural
network), then a guess for every possible next token. It learns with backpropagation and the Adam optimizer.

Everything is written out by hand with numpy (no PyTorch), so you can see every step.
"""
import json
import math

import numpy as np


class TinyGPT:
    def __init__(self, vocab, context, dim=64, heads=4, layers=2, seed=0):
        self.V, self.T, self.d, self.H, self.L = vocab, context, dim, heads, layers
        rng = np.random.RandomState(seed)
        n = lambda *s: (rng.randn(*s) * 0.02).astype(np.float32)
        z = lambda *s: np.zeros(s, np.float32)
        o = lambda *s: np.ones(s, np.float32)
        p = {"tok": n(vocab, dim), "pos": n(context, dim), "gf": o(dim), "bf": z(dim), "Wout": n(dim, vocab), "bout": z(vocab)}
        for l in range(layers):
            p.update({"g1_%d" % l: o(dim), "b1_%d" % l: z(dim), "Wqkv_%d" % l: n(dim, 3 * dim), "bqkv_%d" % l: z(3 * dim),
                      "Wo_%d" % l: n(dim, dim) / math.sqrt(2 * layers), "bo_%d" % l: z(dim),
                      "g2_%d" % l: o(dim), "b2_%d" % l: z(dim), "W1_%d" % l: n(dim, 4 * dim), "c1_%d" % l: z(4 * dim),
                      "W2_%d" % l: n(4 * dim, dim) / math.sqrt(2 * layers), "c2_%d" % l: z(dim)})
        self.p = p
        self.m = {k: np.zeros_like(v) for k, v in p.items()}     # Adam's memory of past gradients
        self.v = {k: np.zeros_like(v) for k, v in p.items()}
        self.steps = 0

    def size(self):
        return int(sum(v.size for v in self.p.values()))

    # ------------------------------------------------------------ the forward pass: tokens in, guesses out
    @staticmethod
    def _ln(x, g, b):
        mu = x.mean(-1, keepdims=True)
        var = x.var(-1, keepdims=True)
        inv = 1.0 / np.sqrt(var + 1e-5)
        xh = (x - mu) * inv
        return xh * g + b, (xh, inv, g)

    def forward(self, idx, keep=False):
        """idx: (batch, time) token numbers. Returns logits: (batch, time, vocab) scores for the next token."""
        p, B, T = self.p, idx.shape[0], idx.shape[1]
        H, dh = self.H, self.d // self.H
        x = p["tok"][idx] + p["pos"][:T]
        cache = {"idx": idx, "layers": []}
        mask = np.triu(np.full((T, T), -1e9, np.float32), 1)       # a token can't look at the future
        for l in range(self.L):
            c = {"x_in": x}
            h, c["ln1"] = self._ln(x, p["g1_%d" % l], p["b1_%d" % l])
            qkv = h @ p["Wqkv_%d" % l] + p["bqkv_%d" % l]
            q, k, v = [a.reshape(B, T, H, dh).transpose(0, 2, 1, 3) for a in np.split(qkv, 3, axis=-1)]
            att = q @ k.transpose(0, 1, 3, 2) / math.sqrt(dh) + mask
            att = np.exp(att - att.max(-1, keepdims=True))
            A = att / att.sum(-1, keepdims=True)                      # attention: how much each token looks at the others
            y = (A @ v).transpose(0, 2, 1, 3).reshape(B, T, self.d)
            x = x + y @ p["Wo_%d" % l] + p["bo_%d" % l]
            c.update(h=h, q=q, k=k, v=v, A=A, y=y, x_mid=x)
            h2, c["ln2"] = self._ln(x, p["g2_%d" % l], p["b2_%d" % l])
            a1 = h2 @ p["W1_%d" % l] + p["c1_%d" % l]
            r = np.maximum(a1, 0)
            x = x + r @ p["W2_%d" % l] + p["c2_%d" % l]
            c.update(h2=h2, a1=a1, r=r)
            cache["layers"].append(c)
        hf, cache["lnf"] = self._ln(x, p["gf"], p["bf"])
        logits = hf @ p["Wout"] + p["bout"]
        cache["hf"] = hf
        if keep:
            self.cache = cache
            self.attn = [c["A"] for c in cache["layers"]]
        return logits

    # ------------------------------------------------------------ learning: backpropagation
    @staticmethod
    def _ln_back(dy, saved):
        xh, inv, g = saved
        dxh = dy * g
        dg = (dy * xh).reshape(-1, xh.shape[-1]).sum(0)
        db = dy.reshape(-1, xh.shape[-1]).sum(0)
        dx = inv * (dxh - dxh.mean(-1, keepdims=True) - xh * (dxh * xh).mean(-1, keepdims=True))
        return dx, dg, db

    def loss_and_grads(self, idx, targets, weights):
        """Cross-entropy loss: how surprised the model is by the right next tokens (only where weights > 0)."""
        logits = self.forward(idx, keep=True)
        c, p = self.cache, self.p
        B, T, V = logits.shape
        z = logits - logits.max(-1, keepdims=True)
        logp = z - np.log(np.exp(z).sum(-1, keepdims=True))      # log-probabilities (the stable way)
        probs = np.exp(logp)
        wsum = max(1e-9, float(weights.sum()))
        picked = logp[np.arange(B)[:, None], np.arange(T)[None, :], targets]
        loss = float(-(picked * weights).sum() / wsum)
        dlog = probs
        dlog[np.arange(B)[:, None], np.arange(T)[None, :], targets] -= 1
        dlog *= (weights / wsum)[..., None]
        g = {}
        g["Wout"] = c["hf"].reshape(-1, self.d).T @ dlog.reshape(-1, V)
        g["bout"] = dlog.reshape(-1, V).sum(0)
        dx, g["gf"], g["bf"] = self._ln_back(dlog @ p["Wout"].T, c["lnf"])
        H, dh = self.H, self.d // self.H
        for l in reversed(range(self.L)):
            k = c["layers"][l]
            # the small neural network (MLP)
            g["W2_%d" % l] = k["r"].reshape(-1, 4 * self.d).T @ dx.reshape(-1, self.d)
            g["c2_%d" % l] = dx.reshape(-1, self.d).sum(0)
            da1 = (dx @ p["W2_%d" % l].T) * (k["a1"] > 0)
            g["W1_%d" % l] = k["h2"].reshape(-1, self.d).T @ da1.reshape(-1, 4 * self.d)
            g["c1_%d" % l] = da1.reshape(-1, 4 * self.d).sum(0)
            dh2 = da1 @ p["W1_%d" % l].T
            d2, g["g2_%d" % l], g["b2_%d" % l] = self._ln_back(dh2, k["ln2"])
            dx = dx + d2
            # attention
            g["Wo_%d" % l] = k["y"].reshape(-1, self.d).T @ dx.reshape(-1, self.d)
            g["bo_%d" % l] = dx.reshape(-1, self.d).sum(0)
            dy = (dx @ p["Wo_%d" % l].T).reshape(B, T, H, dh).transpose(0, 2, 1, 3)
            A = k["A"]
            dA = dy @ k["v"].transpose(0, 1, 3, 2)
            dv = A.transpose(0, 1, 3, 2) @ dy
            datt = A * (dA - (dA * A).sum(-1, keepdims=True)) / math.sqrt(dh)
            dq = datt @ k["k"]
            dk = datt.transpose(0, 1, 3, 2) @ k["q"]
            dqkv = np.concatenate([a.transpose(0, 2, 1, 3).reshape(B, T, self.d) for a in (dq, dk, dv)], axis=-1)
            g["Wqkv_%d" % l] = k["h"].reshape(-1, self.d).T @ dqkv.reshape(-1, 3 * self.d)
            g["bqkv_%d" % l] = dqkv.reshape(-1, 3 * self.d).sum(0)
            dh1 = dqkv @ p["Wqkv_%d" % l].T
            d1, g["g1_%d" % l], g["b1_%d" % l] = self._ln_back(dh1, k["ln1"])
            dx = dx + d1
        g["tok"] = np.zeros_like(p["tok"])
        np.add.at(g["tok"], c["idx"], dx)
        g["pos"] = np.zeros_like(p["pos"])
        g["pos"][:T] = dx.sum(0)
        return loss, g

    def learn(self, idx, targets, weights, lr=1e-3, clip=1.0):
        """One step of learning with the Adam optimizer. Returns the loss before the step."""
        loss, g = self.loss_and_grads(idx, targets, weights)
        norm = math.sqrt(sum(float((v * v).sum()) for v in g.values()))
        scale = min(1.0, clip / (norm + 1e-9))                 # don't take giant steps
        self.steps += 1
        b1, b2 = 0.9, 0.99
        for name, grad in g.items():
            grad = grad * scale
            self.m[name] = b1 * self.m[name] + (1 - b1) * grad
            self.v[name] = b2 * self.v[name] + (1 - b2) * grad * grad
            mh = self.m[name] / (1 - b1 ** self.steps)
            vh = self.v[name] / (1 - b2 ** self.steps)
            self.p[name] -= (lr * mh / (np.sqrt(vh) + 1e-8)).astype(np.float32)
        return loss

    # ------------------------------------------------------------ writing: one token at a time
    def generate(self, idx, steps, temperature=0.0, rng=None, stop=None):
        """Adds `steps` tokens to every row of idx. temperature 0 = always the most likely token."""
        idx = np.array(idx)
        for _ in range(steps):
            logits = self.forward(idx[:, -self.T:])[:, -1, :]
            if temperature <= 0:
                nxt = logits.argmax(-1)
            else:
                z = logits / temperature
                pr = np.exp(z - z.max(-1, keepdims=True))
                pr /= pr.sum(-1, keepdims=True)
                r = (rng or np.random).rand(len(pr), 1)
                nxt = (pr.cumsum(-1) < r).sum(-1).clip(0, self.V - 1)
            idx = np.concatenate([idx, nxt[:, None]], axis=1)
            if stop is not None and (idx == stop).any(1).all():
                break
        return idx

    # ------------------------------------------------------------ saving and loading
    def save(self, path, extra=None):
        np.savez_compressed(path, **{"p_" + k: v for k, v in self.p.items()}, **{"m_" + k: v for k, v in self.m.items()},
                            **{"v_" + k: v for k, v in self.v.items()},
                            meta=np.array(json.dumps({"V": self.V, "T": self.T, "d": self.d, "H": self.H, "L": self.L,
                                                      "steps": self.steps, "extra": extra or {}})))

    @classmethod
    def load(cls, path):
        f = np.load(path)
        meta = json.loads(str(f["meta"]))
        m = cls(meta["V"], meta["T"], meta["d"], meta["H"], meta["L"])
        for k in m.p:
            m.p[k], m.m[k], m.v[k] = f["p_" + k], f["m_" + k], f["v_" + k]
        m.steps = meta["steps"]
        return m, meta["extra"]
