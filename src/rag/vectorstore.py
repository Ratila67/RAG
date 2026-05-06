import json, time
from pathlib import Path
import faiss
import numpy as np
from .chunking import Chunk

META_FILENAME = "meta.json"
INDEX_FILENAME = "faiss.index"

class VectorStore:
    def __init__(self, index_dir: Path, embedding_model: str, dim: int):
        self.index_dir = Path(index_dir)
        self.embedding_model = embedding_model
        self.dim = dim
        self.index: faiss.Index | None = None
        # meta : nom du modèle, dim, date, articles déjà indexés (pour idempotence), chunks
        self.meta: dict = {
            "embedding_model": embedding_model,
            "dim": dim,
            "created_at": None,
            "updated_at": None,
            "articles": {},   # legiarti_id -> {"hash": ..., "n_chunks": ..., "first_vec": int}
            "chunks": [],     # liste alignée à l'index : {"article_id","num","chunk_idx","text"}
        }

    @classmethod
    def load_or_create(cls, index_dir: Path, embedding_model: str, dim: int) -> "VectorStore":
        store = cls(index_dir, embedding_model, dim)
        meta_path = store.index_dir / META_FILENAME
        index_path = store.index_dir / INDEX_FILENAME
        if meta_path.exists() and index_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("embedding_model") != embedding_model:
                raise RuntimeError(
                    f"Index existant utilise '{meta.get('embedding_model')}' "
                    f"≠ modèle demandé '{embedding_model}'. Supprime {index_dir} ou change EMBEDDING_MODEL."
                )
            if meta.get("dim") != dim:
                raise RuntimeError(f"Dimension index ({meta.get('dim')}) ≠ modèle ({dim}).")
            store.meta = meta
            store.index = faiss.read_index(str(index_path))
        else:
            store.index_dir.mkdir(parents=True, exist_ok=True)
            store.index = faiss.IndexFlatL2(dim)
            store.meta["created_at"] = time.time()
        return store

    def has_article(self, article_id: str, content_hash: str) -> bool:
        entry = self.meta["articles"].get(article_id)
        return bool(entry and entry["hash"] == content_hash)

    def add_article(self, article_id: str, content_hash: str, chunks: list[Chunk], vectors: np.ndarray) -> None:
        if vectors.dtype != np.float32:
            vectors = vectors.astype(np.float32)
        first_vec = self.index.ntotal
        self.index.add(vectors)
        self.meta["articles"][article_id] = {
            "hash": content_hash, "n_chunks": len(chunks), "first_vec": first_vec,
        }
        for c in chunks:
            self.meta["chunks"].append({
                "article_id": c.article_id, "num": c.article_num,
                "chunk_idx": c.chunk_idx, "text": c.text,
            })

    def search(self, query_vec: np.ndarray, top_k: int) -> list[dict]:
        if query_vec.dtype != np.float32:
            query_vec = query_vec.astype(np.float32)
        if query_vec.ndim == 1:
            query_vec = query_vec[None, :]
        D, I = self.index.search(query_vec, top_k)
        out = []
        for dist, idx in zip(D[0], I[0]):
            if 0 <= idx < len(self.meta["chunks"]):
                row = dict(self.meta["chunks"][idx])
                row["distance"] = float(dist)
                out.append(row)
        return out

    def save(self) -> None:
        self.meta["updated_at"] = time.time()
        faiss.write_index(self.index, str(self.index_dir / INDEX_FILENAME))
        (self.index_dir / META_FILENAME).write_text(
            json.dumps(self.meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )