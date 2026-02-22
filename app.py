from flask import Flask, request, jsonify, Response
from datetime import datetime
import math
import os
import sqlite3

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "/var/data/nav_tracker.sqlite")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user TEXT NOT NULL,
        lat REAL NOT NULL,
        lng REAL NOT NULL,
        acc REAL
    )
    """)
    conn.commit()
    conn.close()

init_db()


TOKEN = "OPS2026"

# In-memory state (resets if service restarts)
POSITIONS = {}  # user -> {"lat":..., "lng":..., "ts":...}
TRAILS = {}     # user -> [ {"lat":..., "lng":..., "ts":...}, ... ]
EVENTS = []     # newest appended last
MAX_TRAIL_POINTS = 500
MAX_EVENTS = 800


def utc_ts():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def clamp_float(x, lo, hi):
    return max(lo, min(hi, x))


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def add_event(user, event, **info):
    EVENTS.append({"ts": utc_ts(), "user": user, "event": event, **info})
    if len(EVENTS) > MAX_EVENTS:
        del EVENTS[:-MAX_EVENTS]


# -----------------------------
# Health (Render checks this)
# -----------------------------
@app.get("/health")
def health():
    return Response("ok", mimetype="text/plain")


# -----------------------------
# API: ingest position
# -----------------------------
@app.post("/ping")
def ping():
    data = request.get_json(force=True, silent=True) or {}

    if data.get("token") != TOKEN:
        return jsonify({"ok": False, "error": "unauthorized"}), 401

    user = (data.get("user") or "unknown").strip()
    lat = data.get("lat")
    lng = data.get("lng")

    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Missing lat/lng"}), 400

    try:
        lat = float(lat)
        lng = float(lng)
    except Exception:
        return jsonify({"ok": False, "error": "lat/lng must be numbers"}), 400

    lat = clamp_float(lat, -90, 90)
    lng = clamp_float(lng, -180, 180)

    now = utc_ts()
    prev = POSITIONS.get(user)
    POSITIONS[user] = {"lat": lat, "lng": lng, "ts": now}

    TRAILS.setdefault(user, [])

    # ignore tiny jitter (<2m)
    if prev:
        d = haversine_m(prev["lat"], prev["lng"], lat, lng)
        if d < 2:
            return jsonify({"ok": True, "user": user, "ignored": True})

    TRAILS[user].append({"lat": lat, "lng": lng, "ts": now})
    if len(TRAILS[user]) > MAX_TRAIL_POINTS:
        TRAILS[user] = TRAILS[user][-MAX_TRAIL_POINTS:]

    add_event(user, "ping", lat=lat, lng=lng)

# Save to DB (permanent history)
    conn = db()
    conn.execute(
        "INSERT INTO pings (ts, user, lat, lng, acc) VALUES (?, ?, ?, ?, ?)",
        (now, user, lat, lng, data.get("acc"))
    )
    conn.commit()
    conn.close()    
    return jsonify({"ok": True, "user": user, "lat": lat, "lng": lng, "ts": now})

# -----------------------------
# API: data for map UI
# -----------------------------
@app.get("/positions")
def get_positions():
    # return dict keyed by user (easier for the JS)
    return jsonify(POSITIONS)


@app.get("/trails")
def get_trails():
    return jsonify(TRAILS)


@app.get("/events")
def get_events():
    # newest first
    return jsonify(list(reversed(EVENTS)))


# -----------------------------
# UI: Map (mobile-friendly with Events button)
# -----------------------------
@app.get("/")
@app.get("/map")
def map_view():
    html = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <title>Nav Tracker Map</title>

  <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>

  <style>
    html, body { height: 100%; margin: 0; padding: 0; }
    body { height: 100vh; height: 100dvh; font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif; }

    .wrap { display:flex; flex-direction:row; height:100%; width:100%; }
    #map { flex: 1 1 auto; min-width:0; }

    .side {
      width: 340px;
      max-width: 42vw;
      padding: 12px;
      border-left: 1px solid #eee;
      overflow: auto;
      background: #fff;
    }

    .title { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
    .sub { color: #666; margin: 0 0 10px; font-size: 14px; }
    .card { border: 1px solid #eee; border-radius: 10px; padding: 10px; margin: 8px 0; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 12px; }
    .userline { display:flex; justify-content:space-between; gap:8px; align-items:center; }
    .badge { font-size: 12px; padding: 3px 8px; border-radius: 999px; background: #f2f2f2; }

    /* Toggle button (mobile only) */
    .toggle{
      display:none;
      position:fixed;
      top:12px;
      right:12px;
      z-index:9999;
      font-size:16px;
      padding:10px 12px;
      border-radius:12px;
      border:1px solid #ddd;
      background:#fff;
    }

    /* Mobile: map full screen; events panel is hidden until toggled */
    @media (max-width: 900px) {
      .toggle { display:block; }
      .wrap { flex-direction: column; }
      #map { height: 100vh; height: 100dvh; }
      .side {
        display:none;
        position:fixed;
        left:0; right:0; bottom:0;
        height: 55vh; height:55dvh;
        width: auto;
        max-width:none;
        border-left:none;
        border-top:1px solid #eee;
        z-index:9998;
        box-shadow: 0 -10px 30px rgba(0,0,0,0.12);
      }
      .side.show { display:block; }
    }
  </style>
</head>

<body>
  <button id="toggleEvents" class="toggle">Events</button>

  <div class="wrap">
    <div id="map"></div>

    <div class="side" id="sidePanel">
      <h1 class="title">Events</h1>
      <p class="sub">Auto-refresh every 3s</p>
      <div id="users"></div>
      <div id="eventlist"></div>
    </div>
  </div>

<script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
<script>
  const map = L.map('map', { zoomControl: true }).setView([1.3521, 103.8198], 11);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap'
  }).addTo(map);

  // mobile events toggle
  const btn = document.getElementById("toggleEvents");
  const side = document.getElementById("sidePanel");
  btn.addEventListener("click", () => {
    side.classList.toggle("show");
    btn.textContent = side.classList.contains("show") ? "Map" : "Events";
    setTimeout(() => map.invalidateSize(), 150);
  });

  const markers = {};
  const polylines = {};
  const colors = ["#d62728","#1f77b4","#2ca02c","#ff7f0e","#9467bd","#8c564b","#e377c2","#7f7f7f"];
  function colorForUser(user) {
    let h = 0;
    for (let i=0; i<user.length; i++) h = (h*31 + user.charCodeAt(i)) >>> 0;
    return colors[h % colors.length];
  }

  function ensureUserOnMap(user) {
    if (!markers[user]) {
      markers[user] = L.marker([1.3521, 103.8198]).addTo(map).bindPopup(user);
    }
    if (!polylines[user]) {
      polylines[user] = L.polyline([], { color: colorForUser(user), weight: 4, opacity: 0.8 }).addTo(map);
    }
  }

  function renderUsersPanel(posDict) {
    const usersDiv = document.getElementById("users");
    const users = Object.keys(posDict || {}).sort();
    if (users.length === 0) {
      usersDiv.innerHTML = `<div class="card">No devices yet.</div>`;
      return;
    }
    usersDiv.innerHTML = users.map(u => {
      const p = posDict[u];
      return `
        <div class="card">
          <div class="userline">
            <div><b>${u}</b> <span class="badge">${p.ts || ""}</span></div>
            <div class="badge" style="background:${colorForUser(u)}20; border:1px solid ${colorForUser(u)}55;">trail</div>
          </div>
          <div class="mono">lat ${Number(p.lat).toFixed(6)}, lng ${Number(p.lng).toFixed(6)}</div>
        </div>
      `;
    }).join("");
  }

  async function refresh() {
    try {
      const [posRes, trailsRes, eventsRes] = await Promise.all([
        fetch("/positions"),
        fetch("/trails"),
        fetch("/events")
      ]);

      const posDict = await posRes.json();
      const trailDict = await trailsRes.json();
      const eventsData = await eventsRes.json();

      const users = Object.keys(posDict || {});
      for (const user of users) {
        ensureUserOnMap(user);
        const p = posDict[user];
        markers[user].setLatLng([p.lat, p.lng]);

        const t = trailDict[user] || [];
        polylines[user].setLatLngs(t.map(x => [x.lat, x.lng]));
      }

      renderUsersPanel(posDict);

      const list = document.getElementById("eventlist");
      const top = (eventsData || []).slice(0, 40);
      list.innerHTML = top.map(e => `
        <div class="card">
          <div><b>${e.user}</b> — ${e.event}</div>
          <div class="mono">${e.ts}</div>
          ${("lat" in e) ? `<div class="mono">lat ${Number(e.lat).toFixed(6)}, lng ${Number(e.lng).toFixed(6)}</div>` : ""}
        </div>
      `).join("");

      setTimeout(() => map.invalidateSize(), 80);
    } catch (err) {
      console.log("refresh error:", err);
    }
  }

  refresh();
  setInterval(refresh, 3000);
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")


# -----------------------------
# UI: Phone GPS Sender
# -----------------------------
@app.get("/phone")
def phone_sender():
    user = (request.args.get("user") or "phone").strip()
    token = (request.args.get("token") or "").strip()

    html = f"""
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
  <meta charset="utf-8"/>
  <title>Phone GPS Sender</title>
  <style>
    body {{
      font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif;
      padding: 18px;
      line-height: 1.35;
    }}
    h1 {{ margin: 0 0 8px; font-size: 22px; }}
    .mono {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
    button {{
      font-size: 18px;
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid #ddd;
      background: #fff;
      margin-right: 10px;
    }}
    .row {{ margin: 12px 0; }}
    .hint {{ color:#666; font-size: 14px; }}
  </style>
</head>
<body>
  <h1>Phone GPS Sender</h1>
  <div class="row"><b>User:</b> <span class="mono">{user}</span></div>

  <div class="row">
    <button onclick="start()">Start Sending</button>
    <button onclick="stop()">Stop</button>
  </div>

  <div class="row hint">
    Keep this tab open. iOS may pause GPS if the screen locks or Safari goes background.
  </div>

  <div class="row mono" id="status">Not started</div>

<script>
  const USER = {user!r};
  const TOKEN = {token!r};

  let watchId = null;
  let sending = false;

  async function send(lat, lng, acc) {{
    try {{
      const payload = {{ user: USER, lat, lng, acc, token: TOKEN }};
      const r = await fetch("/ping", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(payload)
      }});
      return await r.json();
    }} catch (e) {{
      return {{ ok:false, error: String(e) }};
    }}
  }}

  function start() {{
    if (!navigator.geolocation) {{
      document.getElementById("status").innerText = "Geolocation not supported";
      return;
    }}
    if (watchId !== null) return;

    sending = true;
    document.getElementById("status").innerText = "Requesting location permission...";

    watchId = navigator.geolocation.watchPosition(
      async (pos) => {{
        if (!sending) return;
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        const acc = pos.coords.accuracy;

        await send(lat, lng, acc);
        document.getElementById("status").innerText =
          "Sending: " + lat.toFixed(6) + ", " + lng.toFixed(6) + " (±" + Math.round(acc) + "m)";
      }},
      (err) => {{
        document.getElementById("status").innerText = "Error: " + err.message;
      }},
      {{
        enableHighAccuracy: true,
        maximumAge: 1000,
        timeout: 10000
      }}
    );
  }}

  function stop() {{
    sending = false;
    if (watchId !== null) {{
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }}
    document.getElementById("status").innerText = "Stopped";
  }}
</script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")