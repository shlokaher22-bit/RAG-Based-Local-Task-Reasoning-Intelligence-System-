
# Private Local RAG Chatbot

A chatbot that answers questions from your own documents, running entirely on your own hardware. The language model, the embeddings and the vector database are all local, so confidential information never leaves your machine or network.

Built as a single Jupyter notebook, with Docker for the infrastructure.

---

## Why this exists

Cloud AI tools are convenient, but sending confidential documents to a third-party server is not an option for many institutions, such as hospitals, universities, law firms, banks and government offices. This project shows that you can have document question-answering **without giving up control of your data**.

## Features

- **Fully local.** LLM, embeddings and vector database run on your hardware. No external API calls at query time.
- **Retrieval-Augmented Generation (RAG).** Answers are built only from the retrieved passages of your documents.
- **Cited answers.** Every answer lists the source file and page. If the answer is not in the documents, the bot says so instead of guessing.
- **Multi-institution isolation.** Each document is tagged with an institution, and every search is filtered by it, so one institution cannot retrieve another's content.
- **Privacy-preserving audit log.** Stores timestamps, user, SHA-256 hash of the query and source filenames. It never stores raw questions or answers.
- **Easy ingestion.** Drop files into a folder, or upload them from the browser inside the notebook.
- **Dockerised services.** One command starts the vector database and the LLM server. Ports are bound to `127.0.0.1` only and telemetry is disabled.
- **Supported formats:** `.pdf`, `.docx`, `.txt`, `.md`.

## Architecture

```
Documents --> Loader --> Chunker --> Embedder --> Qdrant
                                                    (payload: institution, source, page, access_level)
                                                       ^
Question --> Embedder --> Filtered similarity search --+
                                   |  top-k chunks (only the user's institution)
                                   v
                      Grounded prompt --> Local LLM (Ollama) --> Answer + citations
                                                    |
                                           Audit log (hashes only)
```

## Tech stack

| Layer | Tool | Where it runs |
|---|---|---|
| LLM | [Ollama](https://ollama.com) (default `llama3.2:3b`) | Docker container |
| Embeddings | `BAAI/bge-small-en-v1.5` via sentence-transformers | Local Python |
| Vector database | [Qdrant](https://qdrant.tech) | Docker container |
| Orchestration and UI | Jupyter notebook and ipywidgets | Local |

## Requirements

- Docker Desktop or Docker Engine with Docker Compose v2
- Python 3.10 or newer
- Jupyter (JupyterLab or Notebook)
- RAM: at least 8 GB for 3B models, 16 GB or more for 7-8B models
- Optional: an NVIDIA GPU with the NVIDIA Container Toolkit for faster responses
- Internet is needed **once**, to download container images, the LLM and the embedding model. After that the system can run fully offline.

## Project structure

```
.
├── private_local_rag.ipynb      # The whole project: setup, ingestion, retrieval, chat UI
├── docker-compose.yml           # Qdrant + Ollama (also written by the notebook)
├── documents/                   # Your files: documents/<institution>/<file>
│   └── <institution>/
├── data/                        # Created on first run: persistent DB and model storage
│   ├── qdrant/
│   └── ollama/
├── audit_log.jsonl              # Created on first query
├── private_rag_pitch_deck.pptx  # Optional: project pitch (editable)
├── private_rag_pitch_deck.pdf   # Optional: project pitch (PDF)
└── README.md
```

## Quick start

1. **Install Docker** and make sure it is running.
2. **Start Jupyter** in the project folder:
   ```bash
   jupyter lab
   ```
3. **Open `private_local_rag.ipynb`** and run the cells from top to bottom. The notebook will:
   - install the Python dependencies,
   - start Qdrant and Ollama with `docker compose up -d`,
   - download the LLM (first run only; a few GB),
   - load the embedding model,
   - create the vector collection,
   - index the sample documents,
   - launch the chat interface.
4. **Ask a question** in the chat box, choosing an institution from the dropdown.

You can also start the services yourself, outside the notebook:

```bash
docker compose up -d
docker compose ps
```

## Adding your own documents

**Option A: copy files into a folder**

Create one subfolder per institution inside `documents/` and put that institution's files in it:

```
documents/
├── city_hospital/
│   └── patient_policy.pdf
└── state_university/
    └── exam_rules.pdf
```

The folder name becomes the institution tag. Then run the ingestion cell, or click **Re-index docs** in the chat UI.

**Option B: upload from the browser**

Run the upload cell (section 10b). Type or pick an institution, choose your files, and click **Upload & index**. The files are saved to `documents/<institution>/` and indexed immediately.

**Removing the sample data**

Delete the sample folders (`city_hospital`, `state_university`), skip the sample-data cell, and reset the collection once:

```python
init_collection(recreate=True)
```

**Removing a single file from the index**

```python
qdrant.delete(COLLECTION, points_selector=models.FilterSelector(
    filter=models.Filter(must=[
        models.FieldCondition(key="source", match=models.MatchValue(value="old_file.pdf"))])))
```

If you edit a file and re-index it, the old version stays in the database until you delete it with the snippet above.

## Configuration

All settings are in the configuration cell near the top of the notebook.

| Setting | Default | What it does |
|---|---|---|
| `LLM_MODEL` | `llama3.2:3b` | Ollama model. Alternatives: `mistral:7b`, `llama3.1:8b`, `qwen2.5:7b`, `phi3:mini` |
| `EMBED_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model. For multilingual documents try `intfloat/multilingual-e5-base` |
| `CHUNK_WORDS` | `180` | Words per chunk |
| `CHUNK_OVERLAP` | `40` | Words shared between neighbouring chunks |
| `TOP_K` | `5` | Number of chunks retrieved per question |
| `MIN_SCORE` | `0.35` | Minimum similarity score; below it the bot answers "not found" |
| `TEMPERATURE` | `0.1` | Lower values give more consistent, factual answers |
| `QDRANT_API_KEY` | none | Set via environment variable if you enable the Qdrant API key |

If you change `EMBED_MODEL`, recreate the collection (`init_collection(recreate=True)`) and re-index, because vector sizes differ between models.

## Privacy and security design

- **No external calls at query time.** Everything runs locally. Hugging Face offline mode is enabled after the embedding model loads.
- **Localhost-only ports.** Qdrant (`6333`) and Ollama (`11434`) are bound to `127.0.0.1`, so they are not reachable from other machines.
- **Telemetry disabled** in Qdrant.
- **Tenant isolation.** `retrieve()` requires an institution and always applies it as a server-side filter.
- **Minimal logging.** The audit log holds hashes and filenames only.
- **Prompt hardening.** The system prompt restricts answers to the retrieved context and tells the model to ignore instructions found inside documents.

### Hardening checklist for production

- [ ] Run the host, or a Docker `internal: true` network, with **no outbound internet** after setup. Verify with `docker exec rag-ollama curl -m 3 https://example.com` (it should fail).
- [ ] Store `./data` and `./documents` on an encrypted volume (LUKS, BitLocker or FileVault).
- [ ] Enable the Qdrant API key and TLS if the database runs on a separate host.
- [ ] Derive the institution from authenticated identity (SSO or LDAP) through a small API service. **Never trust a client-supplied institution.** The dropdown in the notebook is for demonstration only.
- [ ] Consider separate Qdrant collections or deployments per institution for stricter isolation.
- [ ] Add local PII redaction before indexing (for example Microsoft Presidio).
- [ ] Pin and scan container images, and restrict who can add documents.
- [ ] Take regular encrypted snapshots with `qdrant.create_snapshot(COLLECTION)`.

## Troubleshooting

| Problem | Likely cause and fix |
|---|---|
| `docker compose` fails or services do not start | Docker is not running, or Compose v2 is missing. Start Docker and check `docker compose version`. |
| Port `6333` or `11434` already in use | Another instance is running. Stop it, or change the host port in `docker-compose.yml`. |
| Model download is very slow | Models are several GB. Try a smaller model such as `llama3.2:3b` or `phi3:mini`. |
| `Indexed 0 new chunks` | The PDF is probably a scan (images only). Run it through a local OCR tool such as `ocrmypdf` first. |
| Bot always says "couldn't find that" | Lower `MIN_SCORE` (for example `0.25`), raise `TOP_K`, and check that you picked the right institution. |
| Upload button does not appear | The ipywidgets extension may not be active (common in VS Code). Copy files into `documents/<institution>/` and click **Re-index docs**. |
| Slow answers | Use a smaller model, or enable GPU support in `docker-compose.yml`. |
| Embedding model fails to load offline | Run the embedding cell once with internet so it is cached, then go offline. |

## Known limitations

- **No OCR.** Scanned PDFs and images are not indexed.
- **Tables and complex layouts** may extract poorly from PDFs.
- **Smaller local models** are less capable than large cloud models. Retrieval keeps answers grounded, but for harder reasoning use a larger model if your hardware allows.
- **Re-indexing edited files** requires deleting the old version first.
- **The notebook's institution selector is not real authentication.**

## Roadmap ideas

- Local OCR for scanned documents
- A reranker (for example `BAAI/bge-reranker-base`) for better retrieval
- A FastAPI service with SSO authentication in front of the retriever
- Support for Excel, email and HTML sources
- Evaluation set with question and answer pairs to tune chunking and retrieval

## Cleanup

```bash
docker compose down        # stop containers, keep data
docker compose down -v     # stop containers and remove volumes
```

To wipe all indexed vectors, run `qdrant.delete_collection(COLLECTION)` in the notebook. Downloaded models and the database live in `./data`; delete that folder to remove them completely.

## License

Add your license here (for example MIT or Apache-2.0) before sharing or publishing the project.
