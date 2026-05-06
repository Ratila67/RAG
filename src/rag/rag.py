from groq import Groq
from .config import Settings, load_settings
from .embedder import Embedder
from .vectorstore import VectorStore
from .legifrance import LegifranceClient

SYSTEM_PROMPT = (
    "Tu es un assistant juridique spécialisé en droit du travail français. "
    "Réponds STRICTEMENT en t'appuyant sur les extraits du Code du travail fournis. "
    "Cite les numéros d'articles entre parenthèses (ex: (art. L1234-5)). "
    "Si l'information n'est pas dans les extraits, dis-le clairement."
)

class RAG:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        # Clés/tokens chargés UNE FOIS ici :
        self.groq = Groq(api_key=self.settings.groq_api_key)
        self.legifrance = LegifranceClient(self.settings)  # token OAuth obtenu maintenant
        self.embedder = Embedder(self.settings.embedding_model)
        self.store = VectorStore.load_or_create(
            self.settings.index_dir, self.settings.embedding_model, self.embedder.dim
        )
        if self.store.index.ntotal == 0:
            raise RuntimeError("Index vide — lance d'abord `python -m rag.ingest`.")

    def retrieve(self, question: str, top_k: int | None = None) -> list[dict]:
        k = top_k or self.settings.top_k
        qv = self.embedder.encode([question])
        return self.store.search(qv, k)

    def _build_context(self, hits: list[dict]) -> str:
        blocks = []
        for h in hits:
            label = f"Article {h['num']}" if h.get("num") else h["article_id"]
            blocks.append(f"[{label}]\n{h['text']}")
        return "\n\n---\n\n".join(blocks)

    def ask(self, question: str) -> dict:
        hits = self.retrieve(question)
        context = self._build_context(hits)
        completion = self.groq.chat.completions.create(
            model=self.settings.groq_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",
                 "content": f"Question: {question}\n\nExtraits:\n{context}\n\nRéponse:"},
            ],
            temperature=0.2,
        )
        return {
            "answer": completion.choices[0].message.content,
            "sources": [{"article_id": h["article_id"], "num": h.get("num"),
                          "distance": h["distance"]} for h in hits],
        }