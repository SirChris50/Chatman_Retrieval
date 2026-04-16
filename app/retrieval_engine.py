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
import sys

# Must be set before torch/OpenMP DLLs are loaded to prevent the Intel OpenMP
# deadlock that occurs when Python is spawned as a subprocess on Windows.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("KMP_INIT_AT_FORK", "FALSE")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import datetime
import math
import random
import re
import sqlite3
import chromadb

from rapidfuzz import fuzz
from sentence_transformers import SentenceTransformer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# When frozen by PyInstaller, data lives next to the .exe; otherwise project root.
if getattr(sys, 'frozen', False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

DB_PATH          = os.path.join(_BASE_DIR, "data", "retrieval.db")
CHROMA_PATH      = os.path.join(_BASE_DIR, "data", "chroma_store")
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
# Math detection
# ---------------------------------------------------------------------------

def _fmt(n: float) -> str:
    """Integer notation when whole, otherwise trimmed decimal."""
    if n == int(n):
        return str(int(n))
    return str(round(n, 10)).rstrip("0").rstrip(".")


def _math_result(answer: str) -> dict:
    return {
        "answer":           answer,
        "matched_question": None,
        "combined_score":   1.0,
        "semantic_score":   1.0,
        "fuzzy_score":      1.0,
        "matched":          True,
    }


# --- Compiled regexes -------------------------------------------------------

# Basic arithmetic: "12 + 45", "6 times 7", "what is 100 divided by 4"
_MATH_RE = re.compile(
    r"""(?:what\s+is\s+|calculate\s+|compute\s+|solve\s+)?
        (-?\d+(?:\.\d+)?)\s*
        (plus|added\s+to|minus|subtract(?:ed)?|times|multiplied\s+by|divided\s+by|over|[+\-*/x×÷])\s*
        (-?\d+(?:\.\d+)?)\s*\??$""",
    re.IGNORECASE | re.VERBOSE,
)

# Square root: "square root of 64", "sqrt 64", "what is the square root of 9"
_SQRT_RE = re.compile(
    r"^(?:what\s+is\s+(?:the\s+)?|calculate\s+)?(?:square\s+root|sqrt)\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*\??$",
    re.IGNORECASE,
)

# Squared / cubed: "7 squared", "3 cubed", "what is 5 squared"
_POW_RE = re.compile(
    r"^(?:what\s+is\s+(?:the\s+)?)?(\d+(?:\.\d+)?)\s+(?:(squared|cubed)|\^([23]))\s*\??$",
    re.IGNORECASE,
)

# Percentage of: "what is 15% of 200", "15 percent of 200"
_PCT_OF_RE = re.compile(
    r"^(?:what\s+is\s+(?:the\s+)?)?(\d+(?:\.\d+)?)\s*(?:%|percent(?:age)?)\s+of\s+(\d+(?:\.\d+)?)\s*\??$",
    re.IGNORECASE,
)

# Tip: "20% tip on 47", "20 percent tip on 47 dollars"
_TIP_RE = re.compile(
    r"^(?:what\s+is\s+(?:a\s+)?)?(\d+(?:\.\d+)?)\s*(?:%|percent)\s+tip\s+on\s+(\d+(?:\.\d+)?)(?:\s+dollars?)?\s*\??$",
    re.IGNORECASE,
)

# Age: "how old is someone born in 1976", "if someone was born in 1990 how old are they"
_AGE_RE = re.compile(
    r"(?:how\s+old\s+(?:is|are|would)\s+(?:someone|a\s+person)\s+born\s+in"
    r"|age\s+of\s+(?:someone|a\s+person)\s+born\s+in"
    r"|if\s+(?:someone|a\s+person)\s+(?:was|were)\s+born\s+in)\s+(\d{4})\s*\??$",
    re.IGNORECASE,
)

# Unit conversion: "5 miles to km", "100 fahrenheit to celsius", "convert 70 lbs to kg"
_UNIT_RE = re.compile(
    r"""^(?:convert\s+)?
        (-?\d+(?:\.\d+)?)\s*
        (miles?|mi|kilometers?|kilometres?|km|
         fahrenheit|celsius|°f|°c|
         pounds?|lbs?|kilograms?|kgs?|
         inch(?:es)?|centimeters?|centimetres?|cm)
        \s+(?:to|in|into|as)\s+
        (miles?|mi|kilometers?|kilometres?|km|
         fahrenheit|celsius|°f|°c|
         pounds?|lbs?|kilograms?|kgs?|
         inch(?:es)?|centimeters?|centimetres?|cm)
        \s*\??$""",
    re.IGNORECASE | re.VERBOSE,
)

# Unit conversion using bare f/c: "37 f to c", "212 f to celsius"
_TEMP_BARE_RE = re.compile(
    r"^(?:convert\s+)?(-?\d+(?:\.\d+)?)\s+(f|c)\s+(?:to|in)\s+(f|c)\s*\??$",
    re.IGNORECASE,
)


def _normalize_unit(s: str) -> str:
    s = s.lower().strip()
    if s in ("mile", "miles", "mi"):                                       return "miles"
    if s in ("km", "kilometer", "kilometers", "kilometre", "kilometres"):  return "km"
    if s in ("fahrenheit", "°f", "f"):                                     return "f"
    if s in ("celsius", "°c", "c"):                                        return "c"
    if s in ("pound", "pounds", "lb", "lbs"):                              return "lbs"
    if s in ("kilogram", "kilograms", "kg", "kgs"):                        return "kg"
    if s in ("inch", "inches", "in"):                                      return "in"
    if s in ("centimeter", "centimeters", "centimetre", "centimetres", "cm"): return "cm"
    return s


_UNIT_CONVERSIONS = {
    ("miles", "km"):  lambda v: f"{_fmt(v * 1.60934)} km",
    ("km", "miles"):  lambda v: f"{_fmt(v / 1.60934)} miles",
    ("f",   "c"):     lambda v: f"{_fmt((v - 32) * 5 / 9)}°C",
    ("c",   "f"):     lambda v: f"{_fmt(v * 9 / 5 + 32)}°F",
    ("lbs", "kg"):    lambda v: f"{_fmt(v * 0.453592)} kg",
    ("kg",  "lbs"):   lambda v: f"{_fmt(v / 0.453592)} lbs",
    ("in",  "cm"):    lambda v: f"{_fmt(v * 2.54)} cm",
    ("cm",  "in"):    lambda v: f"{_fmt(v / 2.54)} inches",
}


def _try_math(text: str):
    """
    Check text against all math/calculation patterns.
    Returns a result dict if matched, otherwise None.
    Runs before any database lookup so no model inference is needed.
    """
    t = text.strip()

    # 1. Square root
    m = _SQRT_RE.match(t)
    if m:
        n = float(m.group(1))
        if n < 0:
            return _math_result("Square root of a negative number is undefined in real numbers.")
        return _math_result(_fmt(math.sqrt(n)))

    # 2. Squared / cubed
    m = _POW_RE.match(t)
    if m:
        base = float(m.group(1))
        word = (m.group(2) or "").lower()
        exp_ch = m.group(3) or ""
        exp = 3 if (word == "cubed" or exp_ch == "3") else 2
        return _math_result(_fmt(base ** exp))

    # 3. Percentage of
    m = _PCT_OF_RE.match(t)
    if m:
        pct, total = float(m.group(1)), float(m.group(2))
        return _math_result(_fmt(pct / 100 * total))

    # 4. Tip calculator
    m = _TIP_RE.match(t)
    if m:
        pct, bill = float(m.group(1)), float(m.group(2))
        tip   = pct / 100 * bill
        total = bill + tip
        return _math_result(f"Tip: ${_fmt(round(tip, 2))} — Total: ${_fmt(round(total, 2))}")

    # 5. Age calculator
    m = _AGE_RE.search(t)
    if m:
        birth_year = int(m.group(1))
        age = datetime.date.today().year - birth_year
        return _math_result(f"{age} years old (born {birth_year})")

    # 6. Unit conversion (bare f/c checked first to avoid ambiguity)
    m = _TEMP_BARE_RE.match(t)
    if m:
        val       = float(m.group(1))
        from_unit = _normalize_unit(m.group(2))
        to_unit   = _normalize_unit(m.group(3))
        conv      = _UNIT_CONVERSIONS.get((from_unit, to_unit))
        if conv:
            return _math_result(conv(val))

    m = _UNIT_RE.match(t)
    if m:
        val       = float(m.group(1))
        from_unit = _normalize_unit(m.group(2))
        to_unit   = _normalize_unit(m.group(3))
        conv      = _UNIT_CONVERSIONS.get((from_unit, to_unit))
        if conv:
            return _math_result(conv(val))
        return _math_result(f"Sorry, I can't convert {m.group(2)} to {m.group(3)}.")

    # 7. Basic arithmetic
    normalised = re.sub(r"added\s+to",              "plus",      t,          flags=re.IGNORECASE)
    normalised = re.sub(r"subtracted\s+by|subtracted", "minus",  normalised, flags=re.IGNORECASE)
    normalised = re.sub(r"multiplied\s+by",          "times",    normalised, flags=re.IGNORECASE)
    normalised = re.sub(r"divided\s+by",             "dividedby",normalised, flags=re.IGNORECASE)

    m = _MATH_RE.search(normalised)
    if not m:
        return None

    left_s, op_s, right_s = m.group(1), m.group(2).strip().lower(), m.group(3)
    left, right = float(left_s), float(right_s)

    op_map = {
        "plus": "+", "+": "+",
        "minus": "-", "-": "-",
        "times": "*", "*": "*", "x": "*", "×": "*",
        "dividedby": "/", "over": "/", "/": "/", "÷": "/",
    }
    op = op_map.get(op_s.replace(" ", ""))
    if op is None:
        return None

    if op == "/" and right == 0:
        return _math_result("That's a division by zero — undefined.")

    if op == "+":   result = left + right
    elif op == "-": result = left - right
    elif op == "*": result = left * right
    else:           result = left / right

    return _math_result(_fmt(result))


# ---------------------------------------------------------------------------
# Date / time / random detection
# ---------------------------------------------------------------------------

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# "what day of the week is July 4 2026" / "what day is March 15 2025"
_DAY_OF_WEEK_RE = re.compile(
    r"(?:what\s+day(?:\s+of\s+the\s+week)?\s+is\s+)"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?"
    r"(?:\s*[,]?\s*(\d{4}))?"
    r"\s*\??$",
    re.IGNORECASE,
)

# "how many days until Christmas" / "how many days until July 4" / "how many days until July 4 2027"
_DAYS_UNTIL_RE = re.compile(
    r"how\s+many\s+days\s+(?:until|till|to|before)\s+"
    r"(christmas|new\s+year(?:'s)?(?:\s+day)?|thanksgiving|halloween|valentine(?:'s)?(?:\s+day)?|"
    r"(january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
    r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*[,]?\s*(\d{4}))?)"
    r"\s*\??$",
    re.IGNORECASE,
)

# "what is today's date" / "what day is it" / "what is the date today"
_TODAY_RE = re.compile(
    r"(?:what(?:'s|\s+is)\s+(?:today(?:'s)?\s+)?(?:the\s+)?date"
    r"|what\s+day\s+is\s+(?:it|today)"
    r"|today(?:'s)?\s+date)",
    re.IGNORECASE,
)

# "what time is it" / "current time"
_TIME_RE = re.compile(
    r"(?:what(?:'s|\s+is)\s+the\s+(?:current\s+)?time"
    r"|what\s+time\s+is\s+it"
    r"|current\s+time)",
    re.IGNORECASE,
)

# "pick a random number between 1 and 100" / "random number from 5 to 50"
_RANDOM_RE = re.compile(
    r"(?:pick\s+a?\s*|give\s+me\s+a?\s*|generate\s+a?\s*|random\s+number\s+)"
    r"random\s+number\s+(?:between|from)\s+(-?\d+)\s+(?:and|to)\s+(-?\d+)"
    r"|(?:random\s+number\s+(?:between|from)\s+(-?\d+)\s+(?:and|to)\s+(-?\d+))",
    re.IGNORECASE,
)

# "flip a coin" / "coin flip" / "heads or tails"
_COIN_RE = re.compile(
    r"(?:flip\s+a?\s+coin|coin\s+flip|heads\s+or\s+tails|toss\s+a?\s+coin)\s*\??$",
    re.IGNORECASE,
)


def _next_occurrence(month: int, day: int) -> datetime.date:
    """Return the next calendar occurrence of (month, day) from today."""
    today = datetime.date.today()
    candidate = datetime.date(today.year, month, day)
    if candidate <= today:
        candidate = datetime.date(today.year + 1, month, day)
    return candidate


_NAMED_DATES = {
    "christmas":         lambda y: datetime.date(y, 12, 25),
    "halloween":         lambda y: datetime.date(y, 10, 31),
    "valentine":         lambda y: datetime.date(y,  2, 14),
    "valentines":        lambda y: datetime.date(y,  2, 14),
    "new year":          lambda y: datetime.date(y,  1,  1),
    "new years":         lambda y: datetime.date(y,  1,  1),
    "new years day":     lambda y: datetime.date(y,  1,  1),
    "thanksgiving":      None,   # computed separately (4th Thursday of November)
}


def _thanksgiving(year: int) -> datetime.date:
    """Return US Thanksgiving (4th Thursday of November) for the given year."""
    nov1   = datetime.date(year, 11, 1)
    offset = (3 - nov1.weekday()) % 7   # days until first Thursday
    return nov1 + datetime.timedelta(days=offset + 21)


def _try_datetime(text: str):
    """
    Detect date/time/random queries and return a result dict, or None.
    Runs completely offline using Python's stdlib.
    """
    t = text.strip()

    # Today's date
    if _TODAY_RE.search(t):
        today = datetime.date.today()
        day_name = _WEEKDAYS[today.weekday()]
        return _math_result(f"{day_name}, {today.strftime('%B %d, %Y')}")

    # Current time
    if _TIME_RE.search(t):
        now = datetime.datetime.now()
        return _math_result(now.strftime("%I:%M %p").lstrip("0"))

    # Day of week for a specific date
    m = _DAY_OF_WEEK_RE.search(t)
    if m:
        month_name, day_s, year_s = m.group(1), m.group(2), m.group(3)
        month = _MONTHS[month_name.lower()]
        day   = int(day_s)
        year  = int(year_s) if year_s else datetime.date.today().year
        try:
            d = datetime.date(year, month, day)
            return _math_result(f"{_WEEKDAYS[d.weekday()]}, {d.strftime('%B %d, %Y')}")
        except ValueError:
            return _math_result(f"That date ({month_name} {day}, {year}) doesn't exist.")

    # Days until a named holiday or specific date
    m = _DAYS_UNTIL_RE.search(t)
    if m:
        full_target = m.group(1).strip().lower()
        month_name  = m.group(2)
        day_s       = m.group(3)
        year_s      = m.group(4)
        today       = datetime.date.today()

        if month_name:
            # Specific date given
            month = _MONTHS[month_name.lower()]
            day   = int(day_s)
            year  = int(year_s) if year_s else None
            try:
                if year:
                    target = datetime.date(year, month, day)
                else:
                    target = _next_occurrence(month, day)
            except ValueError:
                return _math_result("That date doesn't exist.")
        else:
            # Named holiday
            key = re.sub(r"[''']s?\s*(day)?$", "", full_target).strip()
            key = re.sub(r"\s+", " ", key)
            if key == "thanksgiving":
                target = _thanksgiving(today.year)
                if target <= today:
                    target = _thanksgiving(today.year + 1)
            elif key in _NAMED_DATES:
                fn = _NAMED_DATES[key]
                target = fn(today.year)
                if target <= today:
                    target = fn(today.year + 1)
            else:
                return None

        delta = (target - today).days
        if delta < 0:
            return _math_result(f"That date was {abs(delta)} days ago ({target.strftime('%B %d, %Y')}).")
        if delta == 0:
            return _math_result(f"That's today! ({target.strftime('%B %d, %Y')})")
        day_name = _WEEKDAYS[target.weekday()]
        return _math_result(f"{delta} days ({day_name}, {target.strftime('%B %d, %Y')})")

    # Random number
    m = _RANDOM_RE.search(t)
    if m:
        lo = int(m.group(1) or m.group(3))
        hi = int(m.group(2) or m.group(4))
        if lo > hi:
            lo, hi = hi, lo
        return _math_result(str(random.randint(lo, hi)))

    # Coin flip
    if _COIN_RE.search(t):
        return _math_result(random.choice(["Heads", "Tails"]))

    return None


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

        self._model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=os.path.join(_BASE_DIR, "model_cache", "huggingface", "hub"),
        )

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

        # Step 0 — built-in calculators (no DB lookup needed)
        math_result = _try_math(text)
        if math_result is not None:
            return math_result

        dt_result = _try_datetime(text)
        if dt_result is not None:
            return dt_result

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
