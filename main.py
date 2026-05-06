from groq import Groq
from sentence_transformers import SentenceTransformer
import faiss
import numpy as np

from dotenv import load_dotenv
import os

load_dotenv()

groq_api_key = os.getenv("GROQ_API_KEY")
# Test Groq
client = Groq(api_key=groq_api_key)
response = client.chat.completions.create(
model="llama-3.1-8b-instant",
messages=[{"role": "user", "content": "Dis bonjour en une phrase."}]
)
print("■ Groq OK :", response.choices[0].message.content)

# Test Embeddings
model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")
vector = model.encode("Test d'embedding")
print(f"■ Embedding OK — dimension : {len(vector)}")

# Test FAISS
index = faiss.IndexFlatL2(768)
index.add(np.array([vector], dtype=np.float32))
print(f"■ FAISS OK — {index.ntotal} vecteur(s) indexé(s)")