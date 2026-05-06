# RAG — Code du travail (Légifrance)

TP "Build a RAG" — **option 3** : un assistant conversationnel qui répond à des questions sur le **Code du travail français** en s'appuyant sur les articles officiels récupérés via l'**API Légifrance** (PISTE / DILA).

## Architecture

```
RAG/
├── .env                      # GROQ_API_KEY, client_id, client_secret, PISTE_ENV
├── requirements.txt
├── data/index/               # créé par l'ingestion
│   ├── faiss.index           # index vectoriel FAISS
│   └── meta.json             # métadonnées (modèle d'embedding, hashes, chunks…)
└── rag/
    ├── config.py             # chargement .env + Settings
    ├── legifrance.py         # client Légifrance (OAuth + search + getArticle)
    ├── chunking.py           # nettoyage HTML + découpage en chunks
    ├── embedder.py           # SentenceTransformer encapsulé
    ├── vectorstore.py        # FAISS persistant + meta.json
    ├── ingest.py             # pipeline d'ingestion (idempotent)
    ├── rag.py                # classe RAG (init unique des clients)
    └── chat.py               # boucle CLI du chatbot
```

### Pipeline RAG

1. **Ingestion** (`rag.ingest`) — parcourt les `LEGIARTI` du Code du travail via `/search` paginé, télécharge chaque article via `/consult/getArticle`, nettoie le HTML, découpe en chunks, calcule les embeddings, enregistre dans FAISS + `meta.json`.
2. **Recherche** — la question utilisateur est encodée par le même modèle, FAISS retourne les `top_k` chunks les plus proches (L2).
3. **Génération** — les chunks sont injectés comme contexte dans un prompt système, Groq (Llama 3.1) génère la réponse en citant les articles.

### Choix de conception

- **Idempotence** : chaque article est identifié par son `LEGIARTI` + un hash SHA-256 de son texte nettoyé. Relancer `rag.ingest` ne ré-indexe **rien** si le contenu n'a pas changé. Sauvegardes incrémentales toutes les 50 entrées (reprise possible après crash).
- **Embedding model dans les métadonnées** : `meta.json` contient le nom du modèle d'embedding utilisé. Au chargement, l'index refuse de s'ouvrir si le modèle demandé ne correspond pas — pas de mélange silencieux d'espaces vectoriels.
- **Aucun re-fetch des credentials par requête** : à l'init du chatbot, on construit *une seule fois* le client Groq et le `LegifranceClient` (qui obtient son token OAuth2 immédiatement). Le token est mis en cache, surveillé via `expires_in`, et rafraîchi automatiquement seulement sur expiration ou HTTP 401.

## Prérequis

- **Python 3.12** (le `str | None` du code requiert ≥ 3.10).
- Compte **PISTE** (`piste.gouv.fr`) avec une application autorisée à l'API **Légifrance** → `client_id` + `client_secret`.
- Clé API **Groq** (`console.groq.com`).

## Installation

```bash
# 1. Cloner le repo et entrer dans le dossier
cd RAG

# 2. Créer le venv (Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Installer les dépendances
pip install --upgrade pip
pip install -r requirements.txt
```

## Configuration `.env`

À la racine de `RAG/` :

```dotenv
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxx
client_id=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
client_secret=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PISTE_ENV=prod

# Optionnel — valeurs par défaut affichées
GROQ_MODEL=llama-3.1-8b-instant
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2
INDEX_DIR=data/index
CHUNK_SIZE=800
CHUNK_OVERLAP=100
TOP_K=5
```

## Utilisation

### 1. Ingestion

Test rapide sur 20 articles :

```bash
python -m rag.ingest --limit 20
```

Ingestion complète (long, ~10 000 articles) :

```bash
python -m rag.ingest
```

Sortie attendue :
```
... articles candidats
Ingestion: 100%|████████| 20/20 [00:42<00:00, ...]
Ajoutés: 20 | Skip (déjà indexés): 0 | Vides: 0
```

### 2. Chatbot

```bash
python -m rag.chat
```

Exemple de session :
```
Initialisation du RAG (chargement index, token Légifrance, client Groq)...
Prêt — modèle d'embedding: paraphrase-multilingual-mpnet-base-v2 | vecteurs: 47 | LLM: llama-3.1-8b-instant
Tape ta question (Ctrl-C pour quitter).

> Quelle est la durée légale du travail ?

La durée légale du travail effectif est fixée à 35 heures par semaine (art. L3121-27)...

Sources:
  - art. L3121-27 (dist=0.412)
  - art. L3121-28 (dist=0.518)
```


## Dépannage

- **`ModuleNotFoundError: No module named 'rag'`** — lancer la commande depuis `RAG/` (le parent de `rag/`), pas depuis l'intérieur du package.
- **`attempted relative import with no known parent package`** — un `rag.py` à la racine masque le package `rag/`. Vérifier qu'il n'y a qu'un dossier `rag/`.
- **`Index existant utilise '...' ≠ modèle demandé '...'`** — soit aligner `EMBEDDING_MODEL` sur le `meta.json`, soit supprimer `data/index/` et ré-ingérer.
- **HTTP 401 répétés** — vérifier `PISTE_ENV` (`prod` vs `sandbox`) et que l'application PISTE est autorisée à l'API Légifrance.

## Stack

- **LLM** : Groq (`llama-3.1-8b-instant`)
- **Embeddings** : `sentence-transformers` — `paraphrase-multilingual-mpnet-base-v2` (768 dim, multilingue, adapté au français)
- **Vector store** : FAISS (`IndexFlatL2`) persisté sur disque
- **Source** : API Légifrance via PISTE — `LEGITEXT000006072050` (Code du travail)
