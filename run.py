"""
run.py — PyInstaller entry point for Chatman Retrieval.

Resolves portable base paths, starts Flask on port 5000, then opens
the default browser automatically after a short delay.
"""
import sys
import os

# ---------------------------------------------------------------------------
# Resolve base directories before any app imports touch the filesystem.
#   frozen : running as a PyInstaller .exe
#   _MEIPASS : temp dir where the bundle was extracted (bundled .py, DLLs, …)
#   sys.executable dir : permanent location next to the .exe (data/, model_cache/)
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    _EXE_DIR    = os.path.dirname(sys.executable)   # dist/ChatmanRetrieval/
    _BUNDLE_DIR = sys._MEIPASS                       # dist/ChatmanRetrieval/_internal/
else:
    _EXE_DIR    = os.path.dirname(os.path.abspath(__file__))
    _BUNDLE_DIR = _EXE_DIR

# Expose to the rest of the app so retrieval_engine / app.py see consistent
# values even if they compute their own frozen check.
os.environ["CHATMAN_EXE_DIR"]    = _EXE_DIR
os.environ["CHATMAN_BUNDLE_DIR"] = _BUNDLE_DIR

# Ensure the bundle dir (where app/ lives) is on the import path.
if _BUNDLE_DIR not in sys.path:
    sys.path.insert(0, _BUNDLE_DIR)

# ---------------------------------------------------------------------------
import threading
import webbrowser
import time

PORT = 5000


def _open_browser():
    """Give Flask a few seconds to bind, then open the default browser."""
    time.sleep(4)
    webbrowser.open(f"http://localhost:{PORT}")


if __name__ == "__main__":
    try:
        # Validate that required data files exist before starting Flask.
        _db = os.path.join(_EXE_DIR, "data", "retrieval.db")
        if not os.path.exists(_db):
            print(
                f"\n[ERROR] Database not found: {_db}\n"
                "Make sure the 'data' folder is in the same directory as this exe.\n",
                flush=True,
            )
            input("Press Enter to exit.")
            sys.exit(1)

        print(f"\n{'='*55}", flush=True)
        print("  Chatman Retrieval  —  starting up …", flush=True)
        print(f"  http://localhost:{PORT}", flush=True)
        print(f"  Data  : {os.path.join(_EXE_DIR, 'data')}", flush=True)
        print(f"  Model : {os.path.join(_EXE_DIR, 'model_cache')}", flush=True)
        print(f"{'='*55}\n", flush=True)
        print("  Your browser will open automatically in a few seconds.", flush=True)
        print("  Close this window to shut the app down.\n", flush=True)

        threading.Thread(target=_open_browser, daemon=True).start()

        from app.app import app
        app.run(debug=False, port=PORT, use_reloader=False, threaded=True)

    except Exception:
        import traceback
        print("\n" + "=" * 55, flush=True)
        print("  CRASH — unhandled exception:", flush=True)
        print("=" * 55, flush=True)
        traceback.print_exc()
        print("\n" + "=" * 55, flush=True)
        input("\nPress Enter to close this window.")
        sys.exit(1)
