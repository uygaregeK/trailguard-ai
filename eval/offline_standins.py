"""Deterministic stand-ins for the local models, used only with TRAILGUARD_OFFLINE=1
to test the evaluation code without downloading anything. Never used for results."""

import hashlib
import re

import numpy as np

WORD = re.compile(r"[a-z0-9çğıöşü]+")


class FakeSentenceModel:
    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True):
        rows = []
        for t in texts:
            v = np.zeros(256)
            low = t.lower()
            for f in WORD.findall(low) + [low[i:i + 3] for i in range(max(0, len(low) - 2))]:
                v[int(hashlib.md5(f.encode()).hexdigest(), 16) % 256] += 1.0
            rows.append(v / (np.linalg.norm(v) or 1.0))
        return np.array(rows)


class FakeCrossEncoder:
    def predict(self, pairs):
        return [float(len(set(WORD.findall(q.lower())) & set(WORD.findall(t.lower())))) for q, t in pairs]
