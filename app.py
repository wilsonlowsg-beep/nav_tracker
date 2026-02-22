import os
import sqlite3
from datetime import datetime, timezone, timedelta

from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# -----------------------------
# Config
# -----------------------------
TOKEN = os.environ.get("TOKEN", "OPS2026")
DB_PATH = os.environ.get("DB_PATH", "nav-tracker.sqlite")

# How long to keep data in DB (hours). Old points auto-deleted on every POST /event.
RETENTION_HOURS = int(os.environ.get("RETENTION_HOURS", "24"))

# Default "how recent" for map (seconds). Map uses /positions?since_sec=...
DEFAULT_SINCE_SEC = int(os.environ.get("DEFAULT_SINCE_SEC", "3600"))  # 1 hour


# -----------------------------
# DB helpers
# -----------------------------
def ensure_db_dir():
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)


def get_conn():
    ensure_db_dir()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts TEXT NOT NULL,
              user TEXT NOT NULL,
              event TEXT NOT NULL,
              lat REAL,
              lng REAL,
              acc REAL,
              ua TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user, id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")


init_db()


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ok_token(t: str) -> bool:
    return (t or "") == TOKEN


def clean_user(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return "anonymous"
    # keep alnum + a few safe chars; avoid weird URL chars
    safe = "".join(ch for ch in u if ch.isalnum() or ch in ("_", "-", ".", " "))
    safe = safe.strip()
    return safe[:60] if safe else "anonymous"


def cleanup_old_rows():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RETENTION_HOURS)
    cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
    with get_conn() as conn:
        conn.execute("DELETE FROM events WHERE ts < ?", (cutoff_iso,))


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def root():
    return (
        "<h3>nav_tracker</h3>"
        "<ul>"
        "<li><a href='/map'>/map</a> (viewer)</li>"
        "<li><a href='/phone'>/phone</a> (GPS sender)</li>"
        "<li><a href='/health'>/health</a></li>"
        "</ul>"
    )


@app.get("/health")
def health():
    # Also checks DB can open
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return jsonify({"ok": True, "ts": now_iso()})
    except Exception as e:
        return jsonify({"ok": False, "ts": now_iso(), "error": str(e)}), 500


@app.get("/map")
def map_page():
    # Map reads ?since_sec=... optional, and uses /positions?since_sec=...
    return render_template("map.html", default_since_sec=DEFAULT_SINCE_SEC)


@app.get("/phone")
def phone_page():
    # Phone sender reads ?user=NAME&token=OPS2026
    return render_template("phone.html", token_default=TOKEN)


@app.post("/event")
def ingest_event():
    """
    Expected JSON:
    {
      "user": "Ben",
      "token": "OPS2026",
      "event": "ping",
      "lat": 1.3,
      "lng": 103.9,
      "acc": 9
    }
    """
    data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    if not ok_token(token):
        return jsonify({"ok": False, "error": "bad_token"}), 401

    user = clean_user(data.get("user"))
    event = (data.get("event") or "ping").strip()[:40]
    lat = data.get("lat", None)
    lng = data.get("lng", None)
    acc = data.get("acc", None)
    ua = (request.headers.get("User-Agent") or "")[:200]

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO events (ts, user, event, lat, lng, acc, ua)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), user, event, lat, lng, acc, ua),
        )

    # auto cleanup so old traces "disappear"
    try:
        cleanup_old_rows()
    except Exception:
        pass

    return jsonify({"ok": True})


@app.get("/events")
def list_events():
    """
    Query params:
      limit=30
      user=Ben (optional)
    """
    try:
        limit = int(request.args.get("limit", "30"))
        limit = max(1, min(limit, 200))
    except Exception:
        limit = 30

    user = request.args.get("user", "").strip()

    with get_conn() as conn:
        if user:
            rows = conn.execute(
                """
                SELECT id, ts, user, event, lat, lng, acc
                FROM events
                WHERE user = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (clean_user(user), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, ts, user, event, lat, lng, acc
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    return jsonify([dict(r) for r in rows])


@app.get("/positions")
def latest_positions():
    """
    Latest known position per user.
    Optional:
      since_sec=600  -> only users seen in last N seconds
    """
    cutoff_iso = None
    since_sec = request.args.get("since_sec", "").strip()
    if since_sec:
        try:
            s = int(since_sec)
            s = max(5, min(s, 7 * 24 * 3600))  # up to 7 days
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=s)
            cutoff_iso = cutoff.isoformat().replace("+00:00", "Z")
        except Exception:
            cutoff_iso = None

    with get_conn() as conn:
        if cutoff_iso:
            rows = conn.execute(
                """
                SELECT e.user, e.ts, e.lat, e.lng, e.acc, e.event
                FROM events e
                JOIN (
                    SELECT user, MAX(id) AS max_id
                    FROM events
                    WHERE ts >= ?
                    GROUP BY user
                ) m
                ON e.user = m.user AND e.id = m.max_id
                ORDER BY e.user
                """,
                (cutoff_iso,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT e.user, e.ts, e.lat, e.lng, e.acc, e.event
                FROM events e
                JOIN (
                    SELECT user, MAX(id) AS max_id
                    FROM events
                    GROUP BY user
                ) m
                ON e.user = m.user AND e.id = m.max_id
                ORDER BY e.user
                """
            ).fetchall()

    return jsonify([dict(r) for r in rows])


# Render uses gunicorn; keep local dev option
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, debug=True)