import hashlib, re
from dataclasses import dataclass
from bs4 import BeautifulSoup

@dataclass
class Chunk:
    article_id: str
    article_num: str | None
    chunk_idx: int
    text: str

def clean_html(raw: str) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def split_text(text: str, size: int, overlap: int) -> list[str]:
    if len(text) <= size:
        return [text] if text else []
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return chunks

def article_to_chunks(article: dict, size: int, overlap: int) -> list[Chunk]:
    cleaned = clean_html(article.get("texte", ""))
    if not cleaned:
        return []
    parts = split_text(cleaned, size, overlap)
    return [Chunk(article["id"], article.get("num"), i, p) for i, p in enumerate(parts)]