from .rag import RAG

def main() -> None:
    print("Initialisation du RAG (chargement index, token Légifrance, client Groq)...")
    rag = RAG()  # tout est chargé ICI, une seule fois
    print(f"Prêt ! modèle d'embedding: {rag.embedder.model_name} | "
          f"vecteurs: {rag.store.index.ntotal} | LLM: {rag.settings.groq_model}")
    print("Tape ta question (Ctrl-C pour quitter).\n")
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not q:
            continue
        out = rag.ask(q)
        print("\n" + out["answer"] + "\n")
        print("Sources:")
        for s in out["sources"]:
            label = f"art. {s['num']}" if s["num"] else s["article_id"]
            print(f"  - {label} (dist={s['distance']:.3f})")
        print()

if __name__ == "__main__":
    main()