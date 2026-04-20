"""
XARIT — Flying vehicle for precision agriculture
Serveur web Flask — réseau local WiFi
Accès depuis n'importe quel appareil sur le même réseau :
  http://<IP_DU_PI>:5000
"""

from flask import Flask, Response, jsonify
import numpy as np
from datetime import datetime
import threading

app = Flask(__name__)

# ─────────────────────────────────────────────
# ÉTAT GLOBAL DE L'APPLICATION
# ─────────────────────────────────────────────

etat = {
    "derniere_capture": None,
    "gps": {"lat": "14.7167° N", "lon": "17.4677° W"},
    "en_cours": False,
}

# ─────────────────────────────────────────────
# CAPTURE + CALCUL INDICES
# ─────────────────────────────────────────────

def capturer_et_calculer():
    """
    Sur Raspberry Pi : utilise picamera2.
    Sur Windows/Mac  : génère des valeurs simulées.
    """
    etat["en_cours"] = True
    try:
        try:
            from picamera2 import Picamera2
            import time
            cam = Picamera2()
            config = cam.create_still_configuration(
                main={"size": (1640, 1232), "format": "RGB888"},
                controls={"AwbEnable": False, "AeEnable": True}
            )
            cam.configure(config)
            cam.start()
            time.sleep(2)
            image = cam.capture_array()
            cam.stop()

            R = image[:, :, 0].astype(np.float32)
            G = image[:, :, 1].astype(np.float32)
            B = image[:, :, 2].astype(np.float32)
            eps = 1e-6
            NIR, ROUGE, VERT = R, B, G

        except Exception:
            # Mode simulation (Windows / test sans Pi)
            NIR   = np.random.uniform(100, 200, (100, 100)).astype(np.float32)
            ROUGE = np.random.uniform(50,  150, (100, 100)).astype(np.float32)
            VERT  = np.random.uniform(80,  160, (100, 100)).astype(np.float32)
            eps   = 1e-6

        NDVI  = float(np.clip((NIR - ROUGE) / (NIR + ROUGE + eps), -1, 1).mean())
        GNDVI = float(np.clip((NIR - VERT)  / (NIR + VERT  + eps), -1, 1).mean())
        VARI  = float(np.clip((VERT - ROUGE) / (VERT + ROUGE - VERT + eps), -1, 1).mean())

        etat["derniere_capture"] = {
            "NDVI":      round(NDVI,  3),
            "GNDVI":     round(GNDVI, 3),
            "VARI":      round(VARI,  3),
            "timestamp": datetime.now().strftime("%d/%m/%Y at %H:%M"),
        }  # type: ignore[dict-item]

    except Exception as e:
        etat["derniere_capture"] = {"erreur": str(e)}
    finally:
        etat["en_cours"] = False


def generer_diagnostic(stats, gps):
    """Génère le texte de diagnostic en langage naturel."""
    ndvi = stats["NDVI"]
    vari = stats["VARI"]
    lat  = gps["lat"]
    lon  = gps["lon"]

    if ndvi > 0.5:
        etat_veg = "in <strong>good health</strong> — dense vegetation"
    elif ndvi > 0.2:
        etat_veg = "in <strong>average condition</strong> — moderate vegetation"
    else:
        etat_veg = "in <strong>critical condition</strong> — very sparse vegetation"

   
    else:
        etat_eau = "moisture is <strong>good</strong>"
        eau_action = ("ok", "Good moisture — no irrigation needed.")

    texte = f"Plants in zone <strong>{lat} / {lon}</strong> are {etat_veg} (NDVI {ndvi:.2f}). However, {etat_eau} (NDWI {ndwi:.2f})."

    actions = []
    if ndvi > 0.5:
        actions.append(("ok", "Healthy vegetation — no action needed."))
    elif ndvi > 0.2:
        actions.append(("warn", "Moderate vegetation — monitor closely."))
    else:
        actions.append(("alert", "Critical vegetation — urgent action required."))

    actions.append(eau_action)

    if vari < 0:
        actions.append(("alert", "High stress detected — check for disease or pests."))
    elif vari < 0.2:
        actions.append(("warn", "Light stress — monitor on next pass."))
    else:
        actions.append(("ok", "No visible stress — plants are healthy."))

    fiabilite = int(70 + ndvi * 20)
    return texte, actions, fiabilite


# ─────────────────────────────────────────────
# ROUTES FLASK
# ─────────────────────────────────────────────

@app.route("/")
def index():
    return Response(HTML_TEMPLATE, mimetype="text/html")

@app.route("/api/capturer", methods=["POST"])
def api_capturer():
    if etat["en_cours"]:
        return jsonify({"status": "en_cours"})
    t = threading.Thread(target=capturer_et_calculer)
    t.start()
    return jsonify({"status": "lance"})

@app.route("/api/stats")
def api_stats():
    stats = etat["derniere_capture"]
    if stats is None:
        return jsonify({"status": "vide", "en_cours": etat["en_cours"]})
    if isinstance(stats, dict) and "erreur" in stats:
        return jsonify({"status": "vide", "en_cours": etat["en_cours"]})

    texte, actions, fiabilite = generer_diagnostic(stats, etat["gps"])
    return jsonify({
        "status": "ok",
        "en_cours": etat["en_cours"],
        "stats": stats,
        "gps": etat["gps"],
        "diagnostic": {"texte": texte, "actions": actions, "fiabilite": fiabilite},
    })

# ─────────────────────────────────────────────
# TEMPLATE HTML
# ─────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XARIT — Precision Agriculture</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: sans-serif; background: #F5F0E8; color: #3A3228; }

  .topbar { background: #2D5016; padding: 0 24px; height: 64px; display: flex; align-items: center; justify-content: space-between; }
  .logo { display: flex; align-items: center; gap: 12px; }
  .logo-title { color: #F5F0E8; font-size: 22px; font-weight: 500; letter-spacing: 2px; }
  .logo-sub { color: #9FE1CB; font-size: 10px; margin-top: 2px; }
  .pill { font-size: 11px; padding: 4px 12px; border-radius: 20px; }
  .pill-green { background: #3B6D11; color: #C0DD97; border: 0.5px solid #639922; }
  .pill-blue  { background: #1D3A6B; color: #B5D4F4; border: 0.5px solid #378ADD; }
  .pills { display: flex; gap: 10px; align-items: center; }

  .navbar { background: #3B6D11; display: flex; padding: 0 24px; gap: 2px; }
  .nav-btn { color: #C0DD97; font-size: 13px; padding: 10px 18px; border: none; background: transparent; cursor: pointer; border-radius: 6px 6px 0 0; }
  .nav-btn.active { background: #F5F0E8; color: #2D5016; font-weight: 500; }

  .main { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 140px); }

  .sidebar { background: #EDE8DC; border-right: 0.5px solid #C8C0A8; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
  .sidebar-title { font-size: 11px; color: #7A7260; letter-spacing: 1px; text-transform: uppercase; }

  .metric-card { background: #F5F0E8; border-radius: 8px; border: 0.5px solid #C8C0A8; padding: 10px 12px; }
  .metric-label { font-size: 11px; color: #7A7260; margin-bottom: 2px; }
  .metric-value { font-size: 20px; font-weight: 500; }
  .bar-bg { background: #C8C0A8; height: 4px; border-radius: 3px; margin-top: 6px; }
  .bar { height: 4px; border-radius: 3px; transition: width 0.5s; }

  .btn-capture { background: #2D5016; color: #F5F0E8; border: none; border-radius: 8px; padding: 12px; font-size: 14px; font-weight: 500; cursor: pointer; width: 100%; margin-top: 8px; }
  .btn-capture:hover { background: #3B6D11; }
  .btn-capture:disabled { opacity: 0.6; cursor: not-allowed; }
  .btn-export { background: transparent; color: #3B6D11; border: 0.5px solid #3B6D11; border-radius: 8px; padding: 10px; font-size: 13px; cursor: pointer; width: 100%; }
  .btn-export:hover { background: #EAF3DE; }

  .content { padding: 16px; display: flex; flex-direction: column; gap: 12px; }

  .map-box { background: #D8E8C0; border-radius: 10px; border: 0.5px solid #8BB060; min-height: 200px; display: flex; align-items: center; justify-content: center; color: #2D5016; font-size: 13px; flex: 1; }

  .badges { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .badge { background: #EDE8DC; border-radius: 8px; border: 0.5px solid #C8C0A8; padding: 10px; text-align: center; }
  .badge-name { font-size: 11px; color: #7A7260; }
  .badge-val { font-size: 17px; font-weight: 500; margin: 4px 0 3px; }
  .badge-status { font-size: 10px; padding: 2px 8px; border-radius: 10px; display: inline-block; }

  .diag-panel { background: #F5F0E8; border-radius: 10px; border: 0.5px solid #C8C0A8; overflow: hidden; }
  .diag-header { background: #2D5016; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; }
  .diag-header-left { display: flex; align-items: center; gap: 8px; }
  .diag-dot { width: 8px; height: 8px; background: #97C459; border-radius: 50%; }
  .diag-title { color: #F5F0E8; font-size: 13px; font-weight: 500; }
  .diag-zone { color: #9FE1CB; font-size: 11px; }
  .diag-body { padding: 14px; }
  .diag-text { font-size: 13px; color: #3A3228; line-height: 1.7; margin-bottom: 12px; }
  .diag-actions { display: flex; flex-direction: column; gap: 6px; }
  .action { display: flex; align-items: flex-start; gap: 10px; padding: 8px 10px; border-radius: 7px; font-size: 12px; line-height: 1.5; }
  .action.ok    { background: #EAF3DE; color: #27500A; border: 0.5px solid #C0DD97; }
  .action.warn  { background: #FAEEDA; color: #633806; border: 0.5px solid #FAC775; }
  .action.alert { background: #FCEBEB; color: #501313; border: 0.5px solid #F7C1C1; }
  .diag-footer { border-top: 0.5px solid #C8C0A8; padding: 8px 14px; display: flex; justify-content: space-between; align-items: center; }
  .diag-ts { font-size: 10px; color: #7A7260; }
  .diag-fiab { font-size: 10px; color: #3B6D11; background: #EAF3DE; padding: 2px 8px; border-radius: 10px; }

  .statusbar { background: #2D5016; padding: 6px 24px; display: flex; justify-content: space-between; }
  .statusbar span { color: #9FE1CB; font-size: 11px; }

  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #9FE1CB; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 6px; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="topbar">
  <div class="logo">
    <svg width="38" height="38" viewBox="0 0 38 38">
      <circle cx="19" cy="19" r="18" fill="#3B6D11" stroke="#97C459" stroke-width="1"/>
      <path d="M19 30 C19 30 11 22 11 15 C11 10.6 14.6 7 19 7 C23.4 7 27 10.6 27 15 C27 22 19 30 19 30Z" fill="#97C459"/>
      <path d="M19 15 L19 28" stroke="#2D5016" stroke-width="1.5" stroke-linecap="round"/>
      <path d="M19 19 L15 16" stroke="#2D5016" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M19 17 L23 14" stroke="#2D5016" stroke-width="1.2" stroke-linecap="round"/>
      <path d="M12 10 L8 8 M26 10 L30 8" stroke="#C0DD97" stroke-width="1" stroke-linecap="round"/>
    </svg>
    <div>
      <div class="logo-title">XARIT</div>
      <div class="logo-sub">Flying vehicle for precision agriculture</div>
    </div>
  </div>
  <div class="pills">
    <span class="pill pill-blue" id="gps-pill">GPS · 14.7167° N · 17.4677° W</span>
    <span class="pill pill-green">● Caméra active</span>
  </div>
</div>

<div class="navbar">
  <button class="nav-btn active">Analysis</button>
  <button class="nav-btn">GPS Map</button>
  <button class="nav-btn">History</button>
  <button class="nav-btn">Export</button>
</div>

<div class="main">
  <div class="sidebar">
    <div class="sidebar-title">Spectral indices</div>
    <div class="metric-card">
      <div class="metric-label">NDVI — Vegetation</div>
      <div class="metric-value" id="val-ndvi" style="color:#3B6D11">—</div>
      <div class="bar-bg"><div class="bar" id="bar-ndvi" style="width:0%;background:#639922"></div></div>
    </div>
    <div class="metric-card">
      <div class="metric-label">VARI — Stress</div>
      <div class="metric-value" id="val-vari" style="color:#854F0B">—</div>
      <div class="bar-bg"><div class="bar" id="bar-vari" style="width:0%;background:#EF9F27"></div></div>
    </div>
    <div class="metric-card">
      <div class="metric-label">GNDVI — Chlorophyll</div>
      <div class="metric-value" id="val-gndvi" style="color:#3B6D11">—</div>
      <div class="bar-bg"><div class="bar" id="bar-gndvi" style="width:0%;background:#639922"></div></div>
    </div>
    <button class="btn-capture" id="btn-cap" onclick="capturer()">Capture</button>
    <button class="btn-export" onclick="exporter()">Export report</button>
  </div>

  <div class="content">
    <div class="map-box">GPS Map — Analyzed zone<br>14.72°N · 17.47°W</div>

    <div class="badges">
      <div class="badge">
        <div class="badge-name">NDVI</div>
        <div class="badge-val" id="b-ndvi">—</div>
        <div class="badge-status" id="bs-ndvi" style="background:#EAF3DE;color:#27500A">—</div>
      </div>
      <div class="badge">
        <div class="badge-name">GNDVI</div>
        <div class="badge-val" id="b-gndvi">—</div>
        <div class="badge-status" id="bs-gndvi" style="background:#EAF3DE;color:#27500A">—</div>
      </div>
      <div class="badge">
        <div class="badge-name">VARI</div>
        <div class="badge-val" id="b-vari">—</div>
        <div class="badge-status" id="bs-vari" style="background:#EAF3DE;color:#27500A">—</div>
      </div>
    </div>

    <div class="diag-panel">
      <div class="diag-header">
        <div class="diag-header-left">
          <div class="diag-dot"></div>
          <div class="diag-title">XARIT Diagnostic</div>
        </div>
        <div class="diag-zone" id="diag-zone">Waiting...</div>
      </div>
      <div class="diag-body">
        <div class="diag-text" id="diag-text">Run a capture to get the zone diagnostic.</div>
        <div class="diag-actions" id="diag-actions"></div>
      </div>
      <div class="diag-footer">
        <span class="diag-ts" id="diag-ts">—</span>
        <span class="diag-fiab" id="diag-fiab"></span>
      </div>
    </div>
  </div>
</div>

<div class="statusbar">
  <span id="status-ts">Waiting for capture</span>
  <span>Raspberry Pi · NoIR IMX219</span>
  <span>XARIT v1.0</span>
</div>

<script>
let polling = null;

function pct(v) { return Math.round(((v + 1) / 2) * 100) + '%'; }

function badgeConfig(v, ok, warn) {
  if (v > ok)   return ['Healthy',   '#27500A', '#EAF3DE'];
  if (v > warn) return ['Moderate', '#633806', '#FAEEDA'];
  return ['Low', '#501313', '#FCEBEB'];
}

function majInterface(data) {
  const s = data.stats;
  document.getElementById('val-ndvi').textContent  = s.NDVI.toFixed(2);
  document.getElementById('val-vari').textContent  = s.VARI.toFixed(2);
  document.getElementById('val-gndvi').textContent = s.GNDVI.toFixed(2);
  document.getElementById('bar-ndvi').style.width  = pct(s.NDVI);
  document.getElementById('bar-vari').style.width  = pct(s.VARI);
  document.getElementById('bar-gndvi').style.width = pct(s.GNDVI);

  const badges = [
    ['ndvi',  s.NDVI,  0.5, 0.2],
    ['gndvi', s.GNDVI, 0.4, 0.2],
    ['vari',  s.VARI,  0.2, 0.0],
  ];
  badges.forEach(([nom, val, ok, warn]) => {
    const [txt, fg, bg] = badgeConfig(val, ok, warn);
    document.getElementById('b-' + nom).textContent = val.toFixed(2);
    const bs = document.getElementById('bs-' + nom);
    bs.textContent = txt;
    bs.style.color = fg;
    bs.style.background = bg;
  });

  const d = data.diagnostic;
  document.getElementById('diag-zone').textContent = `Zone · ${data.gps.lat} · ${data.gps.lon}`;
  document.getElementById('diag-text').innerHTML = d.texte;

  const actionsEl = document.getElementById('diag-actions');
  actionsEl.innerHTML = '';
  const icones = { ok: '✓', warn: '!', alert: '!!' };
  d.actions.forEach(([niveau, texte]) => {
    actionsEl.innerHTML += `<div class="action ${niveau}"><span style="font-weight:500;min-width:16px">${icones[niveau]}</span><span>${texte}</span></div>`;
  });

  document.getElementById('diag-ts').textContent   = `Analyzed on ${s.timestamp}`;
  document.getElementById('diag-fiab').textContent  = `Reliability : ${d.fiabilite}%`;
  document.getElementById('status-ts').textContent  = `Last capture : ${s.timestamp}`;
}

async function pollStats() {
  try {
    const r = await fetch('/api/stats');
    const data = await r.json();
    if (data.status === 'ok') {
      majInterface(data);
      if (!data.en_cours) {
        clearInterval(polling);
        polling = null;
        const btn = document.getElementById('btn-cap');
        btn.disabled = false;
        btn.textContent = 'Capture';
      }
    }
  } catch(e) {}
}

async function capturer() {
  const btn = document.getElementById('btn-cap');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>Capturing...';
  await fetch('/api/capturer', { method: 'POST' });
  if (!polling) polling = setInterval(pollStats, 1500);
}

function exporter() {
  const s = document.getElementById('val-ndvi').textContent;
  if (s === '—') { alert('Run a capture first.'); return; }
  const ndvi  = document.getElementById('val-ndvi').textContent;
  const ndwi  = document.getElementById('val-ndwi').textContent;
  const vari  = document.getElementById('val-vari').textContent;
  const gndvi = document.getElementById('val-gndvi').textContent;
  const ts    = document.getElementById('diag-ts').textContent;
  const txt   = `XARIT — Rapport d'analyse\n${ts}\n\nNDVI  : ${ndvi}\nGNDVI : ${gndvi}\nNDWI  : ${ndwi}\nVARI  : ${vari}\n`;
  const blob  = new Blob([txt], { type: 'text/plain' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'xarit_rapport.txt';
  a.click();
}
</script>
</body>
</html>
"""

# ─────────────────────────────────────────────
# LANCEMENT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("  XARIT — Local web server")
    print("  Open in your browser:")
    print("  http://localhost:5000")
    print("  or from another device:")
    print("  http://<IP_DU_PI>:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False)
