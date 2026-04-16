"""Flask app — local QA retrieval interface."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print(f"[DEBUG] HF_HOME = {os.environ.get('HF_HOME')!r}", flush=True)

import csv
import sqlite3

from flask import Flask, request, jsonify, render_template, redirect, url_for, flash
try:
    from retrieval_engine import engine          # python app/app.py
except ImportError:
    from app.retrieval_engine import engine      # python -m app.app

if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle — bundled files live in sys._MEIPASS
    _tmpl_dir   = os.path.join(sys._MEIPASS, "templates")
    _static_dir = os.path.join(sys._MEIPASS, "static")
else:
    _tmpl_dir   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "templates")
    _static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "static")

app = Flask(__name__, template_folder=_tmpl_dir, static_folder=_static_dir)
app.secret_key = "chatman-retrieval-admin"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, 'frozen', False):
    _DATA_DIR = os.path.join(os.path.dirname(sys.executable), "data")
else:
    _DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
DB_PATH      = os.path.join(_DATA_DIR, "retrieval.db")
CSV_PATH     = os.path.join(_DATA_DIR, "import.csv")
CSV_DONE     = os.path.join(_DATA_DIR, "import_done.csv")


# ---------------------------------------------------------------------------
# CSV import — runs once at startup
# ---------------------------------------------------------------------------

def _import_csv_if_present():
    if not os.path.exists(CSV_PATH):
        return
    conn = sqlite3.connect(DB_PATH)
    existing = {row[0].lower() for row in conn.execute("SELECT question FROM qa_pairs").fetchall()}
    imported = 0
    try:
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(CSV_PATH, newline="", encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    rows = list(reader)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Could not decode CSV with utf-8 or latin-1")
        for row in rows:
            q = (row.get("question") or "").strip()
            a = (row.get("answer") or "").strip()
            if q and a and q.lower() not in existing:
                conn.execute("INSERT INTO qa_pairs (question, answer) VALUES (?, ?)", (q, a))
                existing.add(q.lower())
                imported += 1
        conn.commit()
    finally:
        conn.close()
    os.rename(CSV_PATH, CSV_DONE)
    print(f"[CSV import] Imported {imported} new row(s) — renamed to import_done.csv", flush=True)


_import_csv_if_present()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/query", methods=["POST"])
def query():
    data = request.get_json(force=True, silent=True) or {}
    user_query = (data.get("query") or "").strip()
    if not user_query:
        return jsonify({"error": "query field is required"}), 400
    result = engine.query(user_query)
    return jsonify(result)


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        q = (request.form.get("question") or "").strip()
        a = (request.form.get("answer") or "").strip()
        if q and a:
            conn = sqlite3.connect(DB_PATH)
            conn.execute("INSERT INTO qa_pairs (question, answer) VALUES (?, ?)", (q, a))
            conn.commit()
            conn.close()
            engine.reload()
            flash("QA pair added.", "success")
        else:
            flash("Both question and answer are required.", "error")
        return redirect(url_for("admin"))

    conn = sqlite3.connect(DB_PATH)
    pairs = conn.execute("SELECT id, question, answer FROM qa_pairs ORDER BY id").fetchall()
    conn.close()
    return render_template("admin.html", pairs=pairs)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
