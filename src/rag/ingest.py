import argparse
from tqdm import tqdm
from .config import load_settings
from .legifrance import LegifranceClient
from .embedder import Embedder
from .vectorstore import VectorStore
from .chunking import article_to_chunks, hash_text, clean_html

def run(limit: int | None = None) -> None:
    settings = load_settings()
    client = LegifranceClient(settings)
    client.ping()
    embedder = Embedder(settings.embedding_model)
    store = VectorStore.load_or_create(
        settings.index_dir, settings.embedding_model, embedder.dim
    )

    ids = list(client.iter_code_article_ids())
    if limit:
        ids = ids[:limit]
    print(f"{len(ids)} articles candidats")

    n_added = n_skipped = n_empty = 0
    for aid in tqdm(ids, desc="Ingestion"):
        article = client.get_article(aid)
        cleaned = clean_html(article.get("texte", ""))
        if not cleaned:
            n_empty += 1; continue
        h = hash_text(cleaned)
        if store.has_article(aid, h):
            n_skipped += 1; continue
        chunks = article_to_chunks(article, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            n_empty += 1; continue
        vectors = embedder.encode([c.text for c in chunks])
        store.add_article(aid, h, chunks, vectors)
        n_added += 1
        # sauvegarde incrémentale tous les 50 articles → reprise après crash
        if n_added % 50 == 0:
            store.save()
    store.save()
    print(f"Ajoutés: {n_added} | Skip (déjà indexés): {n_skipped} | Vides: {n_empty}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=None, help="N articles max (debug)")
    args = p.parse_args()
    run(limit=args.limit)