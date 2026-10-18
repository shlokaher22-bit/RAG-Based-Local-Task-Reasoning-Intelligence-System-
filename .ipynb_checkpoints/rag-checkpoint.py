"""
Minimal local RAG: load files from ./docs -> chunk -> embed -> store in Chroma -> ask Claude.

Setup:
    pip install anthropic chromadb sentence-transformers pypdf
    set ANTHROPIC_API_KEY=your-key        (Windows cmd)
    $env:ANTHROPIC_API_KEY="your-key"     (PowerShell)

Usage (run from the folder that contains rag.py and the docs/ folder):
    python rag.py index              # build / refresh the vector DB
    python rag.py ask "your question"
"""
import os
import sys
from pathlib import Path

DOCS_DIR = Path("docs")
DB_DIR = "./vector_db"
COLLECTION = "private_kb"
EMBED_MODEL = "all-MiniLM-L6-v2"
CLAUDE_MODEL = "claude-sonnet-4-6"


# ---------- 1. LOAD ----------
def load_docs(folder=DOCS_DIR):
    """Return a list of {"source": filename, "text": full text}."""
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"Folder not found: {folder.resolve()}")

    docs = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text = "\n".join((p.extract_text() or "") for p in reader.pages)
        else:
            continue  # skip unsupported file types
        if text.strip():
            docs.append({"source": path.name, "text": text})
        else:
            print(f"Skipped (no extractable text): {path.name}")
    print(f"Loaded {len(docs)} document(s) from {folder.resolve()}")
    return docs


# ---------- 2. CHUNK ----------
def chunk(text, size=800, overlap=100):
    """Split text into ~size-character chunks, preferring paragraph breaks."""
    text = text.replace("\r\n", "\n").strip()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for p in paragraphs:
        # Hard-split any single paragraph longer than size
        while len(p) > size:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(p[:size])
            p = p[size - overlap:]
        if len(current) + len(p) + 2 <= size:
            current = f"{current}\n\n{p}" if current else p
        else:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            current = f"{tail}\n\n{p}" if tail else p
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


# ---------- 3. INDEX ----------
def build_index():
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    docs = load_docs()
    ids, texts, metas = [], [], []
    for d in docs:
        for i, c in enumerate(chunk(d["text"])):
            ids.append(f'{d["source"]}-{i}')
            texts.append(c)
            metas.append({"source": d["source"]})

    if not texts:
        raise ValueError("No chunks produced. Check the docs/ folder and file types.")

    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(COLLECTION)
    collection.upsert(
        ids=ids,
        documents=texts,
        metadatas=metas,
        embeddings=embedder.encode(texts).tolist(),
    )
    print(f"Indexed {len(texts)} chunks from {len(docs)} document(s).")


# ---------- 4. ASK ----------
def ask(question, k=5):
    import anthropic
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer

    embedder = SentenceTransformer(EMBED_MODEL)
    client = chromadb.PersistentClient(path=DB_DIR, settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(COLLECTION)

    res = collection.query(query_embeddings=embedder.encode([question]).tolist(), n_results=k)
    hits = res["documents"][0]
    sources = [m["source"] for m in res["metadatas"][0]]
    context = "\n\n---\n\n".join(f"[{s}]\n{h}" for s, h in zip(sources, hits))

    resp = anthropic.Anthropic().messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        system=("Answer only from the provided context. Cite the source file in brackets. "
                "If the answer is not in the context, say you don't know."),
        messages=[{"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"}],
    )
    return resp.content[0].text


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "index":
        build_index()
    elif len(sys.argv) >= 3 and sys.argv[1] == "ask":
        print(ask(" ".join(sys.argv[2:])))
    else:
        print(__doc__)
