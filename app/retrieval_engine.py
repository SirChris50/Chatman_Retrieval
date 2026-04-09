"""
retrieval_engine.py
-------------------
Combines fuzzy (rapidfuzz) and semantic (sentence-transformers + ChromaDB)
matching to answer questions from the local SQLite QA database.

Score blending
--------------
  combined = SEMANTIC_WEIGHT * semantic_score + FUZZY_WEIGHT * fuzzy_score

  SEMANTIC_WEIGHT = 0.70
  FUZZY_WEIGHT    = 0.30

  Both scores are normalised to [0, 1] before blending.
  If the combined score is below CONFIDENCE_THRESHOLD the engine returns
  a polite no-match message rather than a low-quality guess.
"""

import os

# Must be set before torch/OpenMP DLLs are loaded to prevent the Intel OpenMP
# deadlock that occurs when Python is spawned as a subprocess on Windows.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import sqlite3
import chromadb

from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH          = os.path.join(os.path.dirname(__file__), "..", "data", "retrieval.db")
CHROMA_PATH      = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_store")
COLLECTION_NAME  = "qa_questions"
MODEL_NAME       = "all-MiniLM-L6-v2"

SEMANTIC_WEIGHT  = 0.70
FUZZY_WEIGHT     = 0.30
CONFIDENCE_THRESHOLD = 0.55   # combined score below this → no-match response

NO_MATCH_MESSAGE = (
    "I don't have a confident answer for that. "
    "Try rephrasing or ask something else."
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_qa_from_db():
    """Return all rows as a list of (id, question, answer) tuples."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, question, answer FROM qa_pairs").fetchall()
    conn.close()
    return rows


def _chroma_id(row_id: int) -> str:
    return f"qa_{row_id}"


# ---------------------------------------------------------------------------
# RetrievalEngine
# ---------------------------------------------------------------------------

class RetrievalEngine:
    """
    Lazy-initialised retrieval engine.

    Call `engine.query(text)` — the model and ChromaDB collection are loaded
    on the first call so import time stays fast.
    """

    def __init__(self):
        self._model      = None
        self._collection = None

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init(self):
        """Load model and ChromaDB, sync any new rows from SQLite."""
        if self._model is not None:
            return  # already initialised

        self._model = SentenceTransformer(MODEL_NAME)

        chroma_client    = chromadb.PersistentClient(path=CHROMA_PATH)
        self._collection = chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        self._sync_embeddings()

    def _sync_embeddings(self):
        """
        Add any rows from SQLite that are not yet in ChromaDB.
        Safe to call multiple times — skips existing IDs.
        """
        rows = _load_qa_from_db()
        if not rows:
            return

        existing_ids = set(
            self._collection.get(ids=[_chroma_id(r[0]) for r in rows])["ids"]
        )

        new_rows = [r for r in rows if _chroma_id(r[0]) not in existing_ids]
        if not new_rows:
            return

        questions   = [r[1] for r in new_rows]
        embeddings  = self._model.encode(questions).tolist()
        chroma_ids  = [_chroma_id(r[0]) for r in new_rows]
        metadatas   = [{"db_id": r[0], "question": r[1], "answer": r[2]} for r in new_rows]

        self._collection.add(
            ids=chroma_ids,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _semantic_score(self, query: str, n_results: int = 5):
        """
        Returns top-n results from ChromaDB as a list of
        {"question", "answer", "semantic_score"} dicts.

        ChromaDB cosine distance is in [0, 2]; we convert to similarity in [0, 1].
        """
        results = self._collection.query(
            query_embeddings=self._model.encode([query]).tolist(),
            n_results=min(n_results, self._collection.count()),
            include=["metadatas", "distances"],
        )

        hits = []
        for meta, dist in zip(results["metadatas"][0], results["distances"][0]):
            # cosine distance → similarity
            score = max(0.0, 1.0 - dist / 2.0)
            hits.append({
                "question":       meta["question"],
                "answer":         meta["answer"],
                "semantic_score": score,
            })
        return hits

    @staticmethod
    def _fuzzy_score(query: str, candidate: str) -> float:
        """
        Blend of token_sort_ratio and partial_ratio, normalised to [0, 1].
        token_sort_ratio handles word-order differences; partial_ratio handles
        substring / length mismatches.
        """
        token_sort  = fuzz.token_sort_ratio(query, candidate) / 100.0
        partial     = fuzz.partial_ratio(query, candidate)    / 100.0
        return 0.6 * token_sort + 0.4 * partial

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, text: str) -> dict:
        """
        Find the best matching answer for *text*.

        Returns a dict:
            {
                "answer":          str,
                "matched_question": str | None,
                "combined_score":  float,
                "semantic_score":  float,
                "fuzzy_score":     float,
                "matched":         bool,
            }
        """
        self._init()

        text = text.strip()
        if not text:
            return {
                "answer":           NO_MATCH_MESSAGE,
                "matched_question": None,
                "combined_score":   0.0,
                "semantic_score":   0.0,
                "fuzzy_score":      0.0,
                "matched":          False,
            }

        # Step 1 — semantic candidates
        candidates = self._semantic_score(text, n_results=5)

        # Step 2 — attach fuzzy scores and compute combined score
        for c in candidates:
            c["fuzzy_score"]    = self._fuzzy_score(text, c["question"])
            c["combined_score"] = (
                SEMANTIC_WEIGHT * c["semantic_score"]
                + FUZZY_WEIGHT  * c["fuzzy_score"]
            )

        # Step 3 — pick the best
        best = max(candidates, key=lambda c: c["combined_score"])

        if best["combined_score"] < CONFIDENCE_THRESHOLD:
            return {
                "answer":           NO_MATCH_MESSAGE,
                "matched_question": None,
                "combined_score":   round(best["combined_score"], 4),
                "semantic_score":   round(best["semantic_score"], 4),
                "fuzzy_score":      round(best["fuzzy_score"], 4),
                "matched":          False,
            }

        return {
            "answer":           best["answer"],
            "matched_question": best["question"],
            "combined_score":   round(best["combined_score"], 4),
            "semantic_score":   round(best["semantic_score"], 4),
            "fuzzy_score":      round(best["fuzzy_score"], 4),
            "matched":          True,
        }

    def reload(self):
        """Force a re-sync of embeddings (call after adding rows to SQLite)."""
        self._init()
        self._sync_embeddings()


# Module-level singleton — import and use directly
engine = RetrievalEngine()
