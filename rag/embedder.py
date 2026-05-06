import numpy as np
from sentence_transformers import SentenceTransformer

class Embedder:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self._model = SentenceTransformer(model_name)
        self.dim = self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self._model.encode(texts, show_progress_bar=False, normalize_embeddings=False),
            dtype=np.float32,
        )