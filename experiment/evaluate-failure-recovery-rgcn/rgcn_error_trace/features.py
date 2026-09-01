from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, List, Optional

import numpy as np


class TextEncoder:
    """Sentence-BERT encoder with a deterministic hashing fallback for smoke tests."""

    def __init__(self, model_name: str, cache_dir: Path, allow_hashing_fallback: bool = True) -> None:
        self.model_name = model_name
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.allow_hashing_fallback = allow_hashing_fallback
        self.backend = "sbert"
        self.model = None

        if model_name.startswith("hashing"):
            self.backend = "hashing"
            self.dimension = self._parse_hashing_dim(model_name)
            return

        try:
            from sentence_transformers import SentenceTransformer

            self.model = SentenceTransformer(model_name)
            self.dimension = int(self.model.get_sentence_embedding_dimension())
        except Exception:
            if not allow_hashing_fallback:
                raise
            self.backend = "hashing"
            self.dimension = 384

    def encode(self, texts: Iterable[str]) -> np.ndarray:
        text_list = list(texts)
        if not text_list:
            return np.zeros((0, self.dimension), dtype=np.float32)

        vectors: List[np.ndarray] = []
        missing_texts: List[str] = []
        missing_positions: List[int] = []
        for index, text in enumerate(text_list):
            cached = self._load_cache(text)
            if cached is None:
                vectors.append(np.zeros(self.dimension, dtype=np.float32))
                missing_texts.append(text)
                missing_positions.append(index)
            else:
                vectors.append(cached)

        if missing_texts:
            if self.backend == "sbert":
                encoded = self.model.encode(missing_texts, normalize_embeddings=True, show_progress_bar=False)
                encoded = np.asarray(encoded, dtype=np.float32)
            else:
                encoded = np.stack([self._hash_text(text) for text in missing_texts]).astype(np.float32)

            for text, position, vector in zip(missing_texts, missing_positions, encoded):
                self._save_cache(text, vector)
                vectors[position] = vector

        return np.stack(vectors).astype(np.float32)

    def _parse_hashing_dim(self, model_name: str) -> int:
        if ":" not in model_name:
            return 384
        try:
            return int(model_name.split(":", 1)[1])
        except ValueError:
            return 384

    def _cache_path(self, text: str) -> Path:
        payload = json.dumps({"model": self.model_name, "backend": self.backend, "text": text}, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.npy"

    def _load_cache(self, text: str) -> Optional[np.ndarray]:
        path = self._cache_path(text)
        if not path.exists():
            return None
        vector = np.load(path)
        if vector.shape != (self.dimension,):
            return None
        return vector.astype(np.float32)

    def _save_cache(self, text: str, vector: np.ndarray) -> None:
        np.save(self._cache_path(text), vector.astype(np.float32))

    def _hash_text(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dimension, dtype=np.float32)
        normalized = text.strip()
        tokens = normalized.split()
        if not tokens:
            tokens = [normalized[i : i + 2] for i in range(max(0, len(normalized) - 1))]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, byteorder="little", signed=False)
            index = value % self.dimension
            sign = 1.0 if (value >> 8) % 2 == 0 else -1.0
            vector[index] += sign

        norm = np.linalg.norm(vector)
        if norm > 0:
            vector /= norm
        return vector
