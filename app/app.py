"""Flask app — local QA retrieval interface."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print(f"[DEBUG] HF_HOME = {os.environ.get('HF_HOME')!r}", flush=True)

from flask import Flask, request, jsonify, render_template
try:
    from retrieval_engine import engine          # python app/app.py
except ImportError:
    from app.retrieval_engine import engine      # python -m app.app

app = Flask(__name__, template_folder="../templates", static_folder="../static")


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


if __name__ == "__main__":
    app.run(debug=True, port=5000)
