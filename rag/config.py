from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    groq_model: str
    client_id: str
    client_secret: str
    piste_env: str
    embedding_model: str
    index_dir: Path
    code_legitext: str
    code_name: str
    chunk_size: int
    chunk_overlap: int
    top_k: int

def load_settings() -> Settings:
    groq_api_key = os.getenv("GROQ_API_KEY")
    client_id = os.getenv("client_id") or os.getenv("CLIENT_ID")
    client_secret = os.getenv("client_secret") or os.getenv("CLIENT_SECRET")
    if not groq_api_key:
        raise RuntimeError("GROQ_API_KEY manquante dans .env")
    if not client_id or not client_secret:
        raise RuntimeError("client_id / client_secret manquants dans .env")
    return Settings(
        groq_api_key=groq_api_key,
        groq_model=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
        client_id=client_id,
        client_secret=client_secret,
        piste_env=(os.getenv("PISTE_ENV") or "prod").lower(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "paraphrase-multilingual-mpnet-base-v2"),
        index_dir=Path(os.getenv("INDEX_DIR", "data/index")),
        code_legitext="LEGITEXT000006072050",
        code_name="Code du travail",
        chunk_size=int(os.getenv("CHUNK_SIZE", "800")),
        chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "100")),
        top_k=int(os.getenv("TOP_K", "5")),
    )