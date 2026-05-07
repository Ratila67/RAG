import time
import streamlit as st

from rag.rag import RAG, SYSTEM_PROMPT


def _inject_css() -> None:
    st.markdown(
        """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

html, body, [class*="css"] { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }

/* Page spacing */
.block-container { padding-top: 2.0rem; padding-bottom: 2.0rem; max-width: 980px; }

/* Hide Streamlit chrome bits (keep it subtle, not hostile) */
header { visibility: hidden; height: 0; }
footer { visibility: hidden; height: 0; }

/* Title */
.rag-title {
  display:flex; align-items:center; justify-content:space-between;
  margin: 0 0 1rem 0;
}
.rag-title h1 { font-size: 1.35rem; margin: 0; letter-spacing: -0.02em; }
.rag-badge {
  font-size: 0.75rem; padding: 0.25rem 0.5rem; border-radius: 999px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(255,255,255,0.06);
}

/* Chat bubbles polish */
div[data-testid="stChatMessage"] { border-radius: 16px; }
div[data-testid="stChatMessage"] > div { gap: 0.75rem; }

/* Inputs */
div[data-testid="stChatInput"] textarea {
  border-radius: 14px !important;
  border: 1px solid rgba(255,255,255,0.14) !important;
  background: rgba(255,255,255,0.04) !important;
}

/* Expanders */
details {
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 14px;
  padding: 0.35rem 0.75rem;
  background: rgba(255,255,255,0.03);
}

/* Small muted text */
.muted { opacity: 0.72; font-size: 0.9rem; }

</style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def _get_rag() -> RAG:
    return RAG()


def _init_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Pose ta question sur le Code du travail. Je réponds uniquement à partir des extraits retrouvés et je cite les articles.",
            }
        ]
    if "last_sources" not in st.session_state:
        st.session_state.last_sources = []


def main() -> None:
    st.set_page_config(
        page_title="RAG — Code du travail",
        page_icon="⚖️",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    _inject_css()
    _init_state()

    # Sidebar (minimal controls)
    with st.sidebar:
        st.markdown("### Réglages")
        show_sources = st.toggle("Afficher les sources", value=True)
        top_k = st.slider("top_k (extraits)", min_value=1, max_value=12, value=5, step=1)
        st.markdown("---")
        if st.button("Nouvelle conversation", use_container_width=True):
            st.session_state.messages = st.session_state.messages[:1]
            st.session_state.last_sources = []
            st.rerun()
        st.caption("Les réponses sont générées à partir de l’index local FAISS.")

    st.markdown(
        """
<div class="rag-title">
  <h1>RAG — Code du travail</h1>
  <span class="rag-badge">minimal • sources • FAISS</span>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="muted">Réponse fondée sur des extraits indexés (articles cités).</div>', unsafe_allow_html=True)

    # Render history
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Quelle est ta question ?")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    rag = _get_rag()
    with st.chat_message("assistant"):
        with st.spinner("Recherche des extraits et génération…"):
            t0 = time.time()
            hits = rag.retrieve(prompt, top_k=top_k)
            # On réutilise la même logique que rag.ask, mais en injectant top_k de la sidebar.
            context = rag._build_context(hits)  # noqa: SLF001 (pragmatique pour dashboard)
            completion = rag.groq.chat.completions.create(
                model=rag.settings.groq_model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Question: {prompt}\n\nExtraits:\n{context}\n\nRéponse:",
                    },
                ],
                temperature=0.2,
            )
            answer = completion.choices[0].message.content
            dt_ms = int((time.time() - t0) * 1000)

        st.markdown(answer)
        st.caption(f"⏱️ {dt_ms} ms • top_k={top_k} • vecteurs={rag.store.index.ntotal}")

        st.session_state.last_sources = [
            {"article_id": h["article_id"], "num": h.get("num"), "distance": h["distance"], "text": h["text"]}
            for h in hits
        ]

        if show_sources:
            with st.expander("Sources (extraits retrouvés)", expanded=False):
                for s in st.session_state.last_sources:
                    label = f"art. {s['num']}" if s.get("num") else s["article_id"]
                    st.markdown(f"**{label}** — dist={s['distance']:.3f}")
                    st.write(s["text"])
                    st.markdown("---")

    st.session_state.messages.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()

