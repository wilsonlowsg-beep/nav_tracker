
from flask import Flask, request, jsonify, Response
from datetime import datetime

app = Flask(__name__)

@app.route("/")
def home():
    return "NAV TRACKER TEST OK"

@app.route("/health")
def health():
    return jsonify({"ok": true, "ts": datetime.utcnow().isoformat()}), 200




# import math
# import os
# import sqlite3
# from pathlib import Path  

# print("Render PORT =", os.environ.get("PORT"), flush=True)

# app = Flask(__name__)

# @app.get("/")
# def root():
#     return "OK", 200

# DB_PATH = os.environ.get("DB_PATH", "nav_tracker.sqlite")

# def get_conn():
#     # Ensure folder exists (important for /var/data on Render disk)
#     Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     return conn

# def ensure_column(con, table, col, coltype):
#     cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
#     if col not in cols:
#         con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")

# def init_db():
#     with get_conn() as con:
#         con.execute("""
#         CREATE TABLE IF NOT EXISTS events (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             ts TEXT NOT NULL,
#             user TEXT NOT NULL,
#             event TEXT NOT NULL,
#             lat REAL,
#             lng REAL,
#             acc REAL
#         )
#         """)
#         con.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)")
#         con.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON events(user)")
#         con.commit()

#   # ---- auto add new columns safely ----
#         ensure_column(con, "events", "ua", "TEXT")
#         ensure_column(con, "events", "ip", "TEXT")
#         ensure_column(con, "events", "source", "TEXT")
#         con.commit()      

# # ✅ IMPORTANT: create tables immediately at startup
# init_db()


# # =============================
# # Config
# # =============================
# TOKEN = os.environ.get("TOKEN", "OPS2026")  # keep your default
# DB_PATH = os.environ.get("DB_PATH", "")    # set in Render -> Environment
# MAX_TRAIL_POINTS = 200                     # in-memory cap per user
# DEFAULT_LIMIT = 300                        # API default return

# # =============================
# # In-memory (still useful for fast map refresh)
# # =============================
# # latest_pos[user] = {"lat":..., "lng":..., "ts":..., "acc":...}
# latest_pos = {}
# # recent_trails[user] = [ {"lat":..., "lng":..., "ts":..., "acc":...}, ... ]
# recent_trails = {}
# # recent_events = list of {"ts","user","event","lat","lng","acc"}
# recent_events = []

# def utc_ts():
#     return datetime.utcnow().isoformat() + "Z"

# def clamp_float(x, lo, hi):
#     return max(lo, min(hi, x))

# def haversine_m(lat1, lon1, lat2, lon2):
#     R = 6371000.0
#     p1 = math.radians(lat1)
#     p2 = math.radians(lat2)
#     dlat = math.radians(lat2 - lat1)
#     dlon = math.radians(lon2 - lon1)
#     a = math.sin(dlat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dlon/2)**2
#     c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
#     return R * c

# # =============================
# # SQLite helpers (Step 2C)
# # =============================
# def db_enabled():
#     return bool(DB_PATH)

# def db_conn():
#     # check_same_thread=False is safe here for simple demo
#     return sqlite3.connect(DB_PATH, check_same_thread=False)

# def init_db():
#     if not db_enabled():
#         return
#     # ensure directory exists (Render Disk mount path should exist, but safe anyway)
#     os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
#     with db_conn() as con:
#         cur = con.cursor()
#         cur.execute("""
#             CREATE TABLE IF NOT EXISTS pings (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 ts TEXT NOT NULL,
#                 user TEXT NOT NULL,
#                 lat REAL NOT NULL,
#                 lng REAL NOT NULL,
#                 acc REAL
#             )
#         """)
#         cur.execute("""
#             CREATE INDEX IF NOT EXISTS idx_pings_user_ts ON pings(user, ts)
#         """)
#         cur.execute("""
#             CREATE TABLE IF NOT EXISTS events (
#                 id INTEGER PRIMARY KEY AUTOINCREMENT,
#                 ts TEXT NOT NULL,
#                 user TEXT NOT NULL,
#                 event TEXT NOT NULL,
#                 lat REAL,
#                 lng REAL,
#                 acc REAL
#             )
#         """)
#         cur.execute("""
#             CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)
#         """)
#         con.commit()

#         con.commit()
#         #Initialize DB immediately (Flask 3 compatible)
#         init_db()

# def db_insert_ping(ts, user, lat, lng, acc):
#     if not db_enabled():
#         return
#     with db_conn() as con:
#         con.execute(
#             "INSERT INTO pings(ts,user,lat,lng,acc) VALUES (?,?,?,?,?)",
#             (ts, user, lat, lng, acc)
#         )
#         con.commit()

# def db_insert_event(ts, user, event, lat=None, lng=None, acc=None):
#     if not db_enabled():
#         return
#     with db_conn() as con:
#         con.execute(
#             "INSERT INTO events(ts,user,event,lat,lng,acc) VALUES (?,?,?,?,?,?)",
#             (ts, user, event, lat, lng, acc)
#         )
#         con.commit()

# # =============================
# # API: ingest position
# # =============================
# @app.post("/ping")
# def ping():
#     data = request.get_json(force=True, silent=True) or {}

#     if data.get("token") != TOKEN:
#         return jsonify({"ok": False, "error": "unauthorized"}), 401

#     user = (data.get("user") or "unknown").strip()
#     lat = data.get("lat", None)
#     lng = data.get("lng", None)
#     acc = data.get("acc", None)

#     if lat is None or lng is None:
#         return jsonify({"ok": False, "error": "Missing lat/lng"}), 400

#     try:
#         lat = float(lat)
#         lng = float(lng)
#         acc = float(acc) if acc is not None else None
#     except Exception:
#         return jsonify({"ok": False, "error": "lat/lng/acc must be numbers"}), 400

#     lat = clamp_float(lat, -90, 90)
#     lng = clamp_float(lng, -180, 180)

#     now = utc_ts()

#     prev = latest_pos.get(user)
#     latest_pos[user] = {"lat": lat, "lng": lng, "ts": now, "acc": acc}

#     # trail list
#     if user not in recent_trails:
#         recent_trails[user] = []

#     # ignore tiny jitter
#     if prev:
#         d = haversine_m(prev["lat"], prev["lng"], lat, lng)
#         if d < 2:
#             return jsonify({"ok": True, "user": user, "ignored": True})

#     point = {"lat": lat, "lng": lng, "ts": now, "acc": acc}
#     recent_trails[user].append(point)
#     if len(recent_trails[user]) > MAX_TRAIL_POINTS:
#         recent_trails[user] = recent_trails[user][-MAX_TRAIL_POINTS:]

#     # record event (memory)
#     recent_events.append({"ts": now, "user": user, "event": "ping", "lat": lat, "lng": lng, "acc": acc})
#     if len(recent_events) > 500:
#         del recent_events[:-500]

#     # record to DB (history)
#     db_insert_ping(now, user, lat, lng, acc)
#     db_insert_event(now, user, "ping", lat, lng, acc)

#     return jsonify({"ok": True, "user": user, "lat": lat, "lng": lng, "ts": now})

# # =============================
# # API: data for map UI
# # =============================
# @app.get("/positions", strict_slashes=False)
# def api_positions():
#     # return dict keyed by user (your JS expects this)
#     return jsonify(latest_pos)

# @app.get("/trails", strict_slashes=False)
# def api_trails():
#     """
#     /trails?user=wilson&limit=1000
#     If DB enabled: returns persisted history (latest first)
#     Else: returns in-memory recent trails
#     """
#     user = (request.args.get("user") or "").strip()
#     limit = request.args.get("limit", str(DEFAULT_LIMIT))
#     try:
#         limit = max(1, min(int(limit), 5000))
#     except Exception:
#         limit = DEFAULT_LIMIT

#     if db_enabled():
#         q = "SELECT ts,user,lat,lng,acc FROM pings "
#         args = []
#         if user:
#             q += "WHERE user=? "
#             args.append(user)
#         q += "ORDER BY id DESC LIMIT ?"
#         args.append(limit)

#         with db_conn() as con:
#             rows = con.execute(q, args).fetchall()

#         # return newest first
#         out = [{"ts": r[0], "user": r[1], "lat": r[2], "lng": r[3], "acc": r[4]} for r in rows]
#         return jsonify(out)

#     # fallback: in-memory
#     if user:
#         return jsonify(recent_trails.get(user, []))
#     return jsonify(recent_trails)

# @app.get("/events", strict_slashes=False)
# def api_events():
#     """
#     /events?limit=200
#     If DB enabled: returns persisted events (latest first)
#     Else: in-memory recent events
#     """
#     limit = request.args.get("limit", "200")
#     try:
#         limit = max(1, min(int(limit), 2000))
#     except Exception:
#         limit = 200

#     if db_enabled():
#         with db_conn() as con:
#             rows = con.execute(
#                 "SELECT ts,user,event,lat,lng,acc FROM events ORDER BY ts DESC LIMIT ?",
#                 (limit,)
#             ).fetchall()
#         out = [{"ts": r[0], "user": r[1], "event": r[2], "lat": r[3], "lng": r[4], "acc": r[5]} for r in rows]
#         return jsonify(out)

#     return jsonify(list(reversed(recent_events))[:limit])

# from datetime import datetime, timezone

# def _ago(ts_str: str) -> str:
#     # ts_str like "2026-02-22T07:19:09.572993Z"
#     try:
#         dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
#         now = datetime.now(timezone.utc)
#         secs = int((now - dt).total_seconds())
#         if secs < 60:
#             return f"{secs}s ago"
#         if secs < 3600:
#             return f"{secs//60}m ago"
#         return f"{secs//3600}h ago"
#     except Exception:
#         return ts_str

# def _acc_label(acc: float) -> str:
#     # you can tune thresholds
#     if acc <= 10:
#         return "✅ GOOD"
#     if acc <= 30:
#         return "🟡 OK"
#     return "🔴 POOR"

# @app.get("/events_view")
# def events_view():
#     limit = int(request.args.get("limit", "30"))
#     with get_conn() as con:
#         rows = con.execute(
#             "SELECT ts, user, event, lat, lng, acc FROM events ORDER BY ts DESC LIMIT ?",
#             (limit,),
#         ).fetchall()

#     html_rows = []
#     for r in rows:
#         ts, user, event, lat, lng, acc = r
#         gmaps = f"https://maps.google.com/?q={lat},{lng}"
#         html_rows.append(f"""
#         <tr>
#           <td>{ts}<br><small>{_ago(ts)}</small></td>
#           <td>{user}</td>
#           <td>{event}</td>
#           <td>{lat:.6f}, {lng:.6f}<br><a href="{gmaps}" target="_blank">Open map</a></td>
#           <td>{acc:.1f} m<br>{_acc_label(acc)}</td>
#         </tr>
#         """)

#     return f"""
#     <html>
#     <head>
#       <meta name="viewport" content="width=device-width, initial-scale=1" />
#       <title>Events</title>
#       <style>
#         body {{ font-family: Arial, sans-serif; padding: 12px; }}
#         table {{ border-collapse: collapse; width: 100%; }}
#         th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
#         th {{ background: #f2f2f2; }}
#         small {{ color: #666; }}
#       </style>
#     </head>
#     <body>
#       <h2>Events (latest {limit})</h2>
#       <p>
#         API: <a href="/events?limit={limit}">/events?limit={limit}</a>
#       </p>
#       <table>
#         <tr>
#           <th>Time</th><th>User</th><th>Event</th><th>Location</th><th>Accuracy</th>
#         </tr>
#         {''.join(html_rows) if html_rows else '<tr><td colspan="5">No events yet</td></tr>'}
#       </table>
#     </body>
#     </html>
#     """

# @app.get("/health")
# def health():
#     return Response("ok", mimetype="text/plain")

# # =============================
# # UI: Map (mobile-friendly + Events button toggle)
# # =============================

# @app.get("/map")
# def map_view():
#     html = r"""
# <!doctype html>
# <html>
# <head>
#   <meta charset="utf-8"/>
#   <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
#   <title>Nav Tracker Map</title>
#   <link rel="stylesheet" href="https://unpkg.com/leaflet/dist/leaflet.css"/>
#   <style>
#     html, body { height: 100%; margin: 0; padding: 0; }
#     body { height: 100vh; height: 100dvh; font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif; }
#     .wrap { display:flex; flex-direction:row; height:100%; width:100%; }
#     #map { flex:1 1 auto; min-width:0; }
#     .side {
#       width: 340px;
#       max-width: 40vw;
#       padding: 12px;
#       border-left: 1px solid #eee;
#       overflow: auto;
#       background: #fff;
#     }
#     .title { font-size: 22px; font-weight: 700; margin: 0 0 6px; }
#     .sub { color: #666; margin: 0 0 10px; font-size: 14px; }
#     .card { border: 1px solid #eee; border-radius: 10px; padding: 10px; margin: 8px 0; }
#     .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: 12px; }
#     .userline { display:flex; justify-content:space-between; gap:8px; }
#     .badge { font-size: 12px; padding: 3px 8px; border-radius: 999px; background: #f2f2f2; }

#     /* Mobile: full map; Events opens as overlay */
#     .toggle {
#       display:none;
#       position:fixed;
#       top:12px;
#       right:12px;
#       z-index:9999;
#       font-size:16px;
#       padding:10px 12px;
#       border-radius:12px;
#       border:1px solid #ddd;
#       background:#fff;
#     }
#     @media (max-width: 900px) {
#       .wrap { flex-direction: column; }
#       #map { height: 100vh; height: 100dvh; }
#       .toggle { display:block; }
#       .side {
#         display:none;
#         position:fixed;
#         top:0; left:0; right:0; bottom:0;
#         width:auto; max-width:none;
#         border-left:none;
#         z-index:9998;
#         background:#fff;
#       }
#       .side.show { display:block; }
#     }
#   </style>
# </head>
# <body>
#   <button class="toggle" id="toggleBtn">Events</button>

#   <div class="wrap">
#     <div id="map"></div>
#     <div class="side" id="sidePanel">
#       <h1 class="title">Events</h1>
#       <p class="sub">Auto-refresh every 3s</p>
#       <div id="users"></div>
#       <div id="eventlist"></div>
#     </div>
#   </div>

# <script src="https://unpkg.com/leaflet/dist/leaflet.js"></script>
# <script>
#   const map = L.map('map', { zoomControl: true }).setView([1.3521, 103.8198], 11);
#   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap' }).addTo(map);

#   // Mobile toggle
#   const side = document.getElementById("sidePanel");
#   const btn = document.getElementById("toggleBtn");
#   btn.addEventListener("click", () => {
#     side.classList.toggle("show");
#     setTimeout(() => map.invalidateSize(), 150);
#   });

#   const markers = {};
#   const polylines = {};
#   const colors = ["#d62728","#1f77b4","#2ca02c","#ff7f0e","#9467bd","#8c564b","#e377c2","#7f7f7f"];
#   function colorForUser(user) {
#     let h = 0;
#     for (let i=0; i<user.length; i++) h = (h*31 + user.charCodeAt(i)) >>> 0;
#     return colors[h % colors.length];
#   }
#   function ensureUser(user) {
#     if (!markers[user]) markers[user] = L.marker([1.3521, 103.8198]).addTo(map).bindPopup(user);
#     if (!polylines[user]) polylines[user] = L.polyline([], { color: colorForUser(user), weight: 4, opacity: 0.8 }).addTo(map);
#   }

#   function renderUsersPanel(posData) {
#     const usersDiv = document.getElementById("users");
#     const users = Object.keys(posData).sort();
#     if (users.length === 0) {
#       usersDiv.innerHTML = `<div class="card">No devices yet.</div>`;
#       return;
#     }
#     usersDiv.innerHTML = users.map(u => {
#       const p = posData[u];
#       return `
#         <div class="card">
#           <div class="userline">
#             <div><b>${u}</b> <span class="badge" style="border:1px solid #eee;">${p.ts || ""}</span></div>
#             <div class="badge" style="background:${colorForUser(u)}20; border:1px solid ${colorForUser(u)}55;">trail</div>
#           </div>
#           <div class="mono">lat ${Number(p.lat).toFixed(6)}, lng ${Number(p.lng).toFixed(6)}</div>
#         </div>
#       `;
#     }).join("");
#   }

#   async function refresh() {
#     try {
#       const [posRes, trailsRes, eventsRes] = await Promise.all([
#         fetch("/positions"),
#         fetch("/trails"),
#         fetch("/events?limit=30")
#       ]);
#       const posData = await posRes.json();
#       const trailData = await trailsRes.json();
#       const eventsData = await eventsRes.json();

#       // Update markers & trails
#       const users = Object.keys(posData);
#       for (const user of users) {
#         ensureUser(user);
#         const p = posData[user];
#         markers[user].setLatLng([p.lat, p.lng]);

#         // in-memory trails dict OR DB trails list
#         let t = [];
#         if (Array.isArray(trailData)) {
#           // DB mode: filter by user
#           t = trailData.filter(x => x.user === user).reverse();
#         } else {
#           t = trailData[user] || [];
#         }
#         const latlngs = t.map(x => [x.lat, x.lng]);
#         polylines[user].setLatLngs(latlngs);
#       }

#       renderUsersPanel(posData);

#       // Events list
#       const list = document.getElementById("eventlist");
#       list.innerHTML = (eventsData || []).map(e => `
#         <div class="card">
#           <div><b>${e.user}</b> — ${e.event}</div>
#           <div class="mono">${e.ts}</div>
#           ${(e.lat != null) ? `<div class="mono">lat ${Number(e.lat).toFixed(6)}, lng ${Number(e.lng).toFixed(6)}</div>` : ""}
#         </div>
#       `).join("");

#       setTimeout(() => map.invalidateSize(), 80);
#     } catch (err) {
#       console.log("refresh error:", err);
#     }
#   }

#   refresh();
#   setInterval(refresh, 3000);
# </script>
# </body>
# </html>
# """
#     return Response(html, mimetype="text/html")

# # =============================
# # UI: Phone GPS Sender
# # =============================
# @app.get("/phone")
# def phone_sender():
#     user = (request.args.get("user") or "phone").strip()
#     token = (request.args.get("token") or "").strip()

#     html = f"""
# <!doctype html>
# <html>
# <head>
#   <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"/>
#   <meta charset="utf-8"/>
#   <title>Phone GPS Sender</title>
#   <style>
#     body {{
#       font-family: -apple-system, system-ui, Segoe UI, Roboto, Arial, sans-serif;
#       padding: 18px; line-height: 1.35;
#     }}
#     h1 {{ margin: 0 0 8px; font-size: 22px; }}
#     .mono {{ font-family: ui-monospace, Menlo, Consolas, monospace; }}
#     button {{
#       font-size: 18px; padding: 12px 14px; border-radius: 12px;
#       border: 1px solid #ddd; background: #fff;
#     }}
#     .row {{ margin: 12px 0; }}
#     .hint {{ color:#666; font-size: 14px; }}
#   </style>
# </head>
# <body>
#   <h1>Phone GPS Sender</h1>
#   <div class="row"><b>User:</b> <span class="mono">{user}</span></div>
#   <div class="row"><b>Token:</b> <span class="mono">{token}</span></div>

#   <div class="row">
#     <button onclick="start()">Start Sending</button>
#     <button onclick="stop()">Stop</button>
#   </div>

#   <div class="row hint">
#     Keep this tab open. iOS may pause GPS if the screen locks or Safari goes background.
#   </div>

#   <div class="row mono" id="status">Not started</div>

# <script>
#   const USER = {user!r};
#   const TOKEN = {token!r};
#   let watchId = null;
#   let sending = false;

#   async function send(lat, lng, acc) {{
#     try {{
#       const payload = {{ user: USER, lat: lat, lng: lng, acc: acc, token: TOKEN }};
#       const r = await fetch("/ping", {{
#         method: "POST",
#         headers: {{ "Content-Type": "application/json" }},
#         body: JSON.stringify(payload)
#       }});
#       return await r.json();
#     }} catch (e) {{
#       return {{ ok:false, error: String(e) }};
#     }}
#   }}

#   function start() {{
#     if (!navigator.geolocation) {{
#       document.getElementById("status").innerText = "Geolocation not supported";
#       return;
#     }}
#     if (watchId !== null) return;

#     sending = true;
#     document.getElementById("status").innerText = "Requesting location permission...";

#     watchId = navigator.geolocation.watchPosition(
#       async (pos) => {{
#         if (!sending) return;
#         const lat = pos.coords.latitude;
#         const lng = pos.coords.longitude;
#         const acc = pos.coords.accuracy;
#         await send(lat, lng, acc);
#         document.getElementById("status").innerText =
#           "Sending: " + lat.toFixed(6) + ", " + lng.toFixed(6) + " (±" + Math.round(acc) + "m)";
#       }},
#       (err) => {{
#         document.getElementById("status").innerText = "Error: " + err.message;
#       }},
#       {{ enableHighAccuracy: true, maximumAge: 1000, timeout: 10000 }}
#     );
#   }}

#   function stop() {{
#     sending = false;
#     if (watchId !== null) {{
#       navigator.geolocation.clearWatch(watchId);
#       watchId = null;
#     }}
#     document.getElementById("status").innerText = "Stopped";
#   }}
# </script>
# </body>
# </html>
# """
#     return Response(html, mimetype="text/html")