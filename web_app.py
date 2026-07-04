"""FastAPI LAN dashboard for the AC.

Owns the auto-cycle and shows usage/cost analytics. Shares the app/ logic and
the SQLite DB with the Telegram bot. LAN-only (no auth) — bind on the home
network, never expose to the internet.
"""
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app import analytics, config, db
from app.ac import ACController
from app.commands import set_ac, toggle_flip
from app.cycle import CycleManager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logging.getLogger("aioswitcher").setLevel(logging.WARNING)
logger = logging.getLogger("ac-web")

ac = ACController()
cycle = CycleManager(ac)
_last_result = {"ts": None, "action": None, "ok": None, "err": None}


@asynccontextmanager
async def lifespan(app):
    config.validate_device()
    db.init_db()
    if cycle.resume():
        logger.info("Resumed persisted auto-cycle")
    yield
    cycle.stop(clear_file=False)  # leave persistence so it resumes next boot


app = FastAPI(lifespan=lifespan, title="AC Dashboard")


def _current_state():
    """Last successful ON/OFF intent = the commanded state."""
    for e in reversed(db.get_events()):
        if e["success"]:
            return e["action"]
    return None


def _status_payload():
    return {
        "state": _current_state(),
        "flipped": db.get_flip(),
        "device_ip": ac.ip,
        "cycle": cycle.status(),
        "last_result": _last_result,
    }


@app.get("/api/status")
async def api_status():
    return _status_payload()


async def _command(intent_on, label):
    ok, err = await set_ac(ac, intent_on, source="web")
    _last_result.update(ts=time.time(), action=label, ok=ok, err=err)
    return {"ok": ok, "err": err, **_status_payload()}


@app.post("/api/on")
async def api_on():
    return await _command(True, "ON")


@app.post("/api/off")
async def api_off():
    return await _command(False, "OFF")


@app.post("/api/flip")
async def api_flip():
    flipped = toggle_flip(source="web")
    return {"flipped": flipped, **_status_payload()}


@app.post("/api/cycle/start")
async def api_cycle_start(req: Request):
    body = await req.json()
    try:
        on = int(body.get("on", 0))
        off = int(body.get("off", 0))
    except (TypeError, ValueError):
        return JSONResponse({"error": "on and off must be integers"}, status_code=400)
    if on <= 0 or off <= 0:
        return JSONResponse({"error": "on and off must be positive minutes"}, status_code=400)
    cycle.start(on, off)
    return {"ok": True, **_status_payload()}


@app.post("/api/cycle/stop")
async def api_cycle_stop():
    cycle.stop()
    return {"ok": True, **_status_payload()}


@app.get("/api/analytics")
async def api_analytics():
    return analytics.compute()


@app.get("/api/settings")
async def api_get_settings():
    return {
        "cost_per_min": db.get_setting("cost_per_min", "0"),
        "currency": db.get_setting("currency", "₪"),
    }


@app.post("/api/settings")
async def api_set_settings(req: Request):
    body = await req.json()
    if "cost_per_min" in body:
        try:
            float(body["cost_per_min"])
        except (TypeError, ValueError):
            return JSONResponse({"error": "cost_per_min must be a number"}, status_code=400)
        db.set_setting("cost_per_min", body["cost_per_min"])
    if "currency" in body:
        db.set_setting("currency", str(body["currency"]))
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
async def index():
    return INDEX_HTML


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AC Dashboard</title>
<style>
  :root{
    --bg:#f4f5f7; --card:#fff; --text:#1a1d21; --muted:#6b7280; --border:#e5e7eb;
    --on:#16a34a; --off:#dc2626; --accent:#2563eb; --bar:#60a5fa;
  }
  @media (prefers-color-scheme: dark){
    :root{ --bg:#0f1115; --card:#1a1d23; --text:#e7e9ee; --muted:#9aa1ac;
           --border:#2a2e37; --bar:#3b82f6; }
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;
       background:var(--bg);color:var(--text);padding:16px;max-width:760px;margin:0 auto}
  h1{font-size:1.4rem;margin:.2rem 0 1rem}
  h2{font-size:1rem;margin:0 0 .75rem;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
  .card{background:var(--card);border:1px solid var(--border);border-radius:14px;padding:18px;margin-bottom:16px}
  .row{display:flex;gap:12px;flex-wrap:wrap}
  .row>*{flex:1}
  button{font-size:1rem;font-weight:600;padding:16px;border:none;border-radius:12px;cursor:pointer;color:#fff}
  button:active{transform:translateY(1px)}
  .btn-on{background:var(--on)} .btn-off{background:var(--off)}
  .btn-alt{background:var(--accent)} .btn-ghost{background:transparent;color:var(--text);border:1px solid var(--border)}
  .state{display:flex;align-items:center;gap:12px;margin-bottom:8px}
  .dot{width:14px;height:14px;border-radius:50%;background:var(--muted)}
  .dot.on{background:var(--on)} .dot.off{background:var(--off)}
  .state b{font-size:1.5rem}
  .meta{color:var(--muted);font-size:.85rem;line-height:1.5}
  .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;text-align:center}
  .stat .n{font-size:1.5rem;font-weight:700}
  .stat .l{color:var(--muted);font-size:.8rem}
  .chart{display:flex;align-items:flex-end;gap:3px;height:120px;margin-top:8px}
  .chart .col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;gap:4px}
  .chart .bar{width:100%;background:var(--bar);border-radius:3px 3px 0 0;min-height:2px}
  .chart .cl{font-size:.6rem;color:var(--muted)}
  input{padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--text);width:100%}
  label{font-size:.85rem;color:var(--muted);display:block;margin-bottom:4px}
  .banner{padding:10px 14px;border-radius:10px;margin-bottom:12px;font-size:.9rem;display:none}
  .banner.ok{display:block;background:rgba(22,163,74,.15);color:var(--on)}
  .banner.err{display:block;background:rgba(220,38,38,.15);color:var(--off)}
  .cyc{display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap}
  .cyc>div{flex:1;min-width:90px}
  small{color:var(--muted)}
</style>
</head>
<body>
<h1>🌡️ AC Dashboard</h1>
<div id="banner" class="banner"></div>

<div class="card">
  <div class="state">
    <span id="dot" class="dot"></span>
    <div><b id="stateText">…</b><div class="meta" id="cycleText"></div></div>
  </div>
  <div class="meta" id="metaText"></div>
</div>

<div class="card">
  <h2>Control</h2>
  <div class="row">
    <button class="btn-on" onclick="cmd('on')">🟢 Turn ON</button>
    <button class="btn-off" onclick="cmd('off')">🔴 Turn OFF</button>
  </div>
  <div class="row" style="margin-top:12px">
    <button class="btn-ghost" onclick="cmd('flip')">🔄 Flip <small id="flipState"></small></button>
  </div>
</div>

<div class="card">
  <h2>Auto Cycle</h2>
  <div id="cycleActive" style="display:none">
    <p>Running: 🟢 <b id="caOn"></b>m ON / 🔴 <b id="caOff"></b>m OFF</p>
    <button class="btn-off" onclick="cycleStop()">🛑 Stop Cycle</button>
  </div>
  <div id="cycleIdle">
    <div class="cyc">
      <div><label>ON minutes</label><input id="onMin" type="number" min="1" value="15"></div>
      <div><label>OFF minutes</label><input id="offMin" type="number" min="1" value="15"></div>
      <div style="flex:0 0 auto"><button class="btn-alt" onclick="cycleStart()">Start</button></div>
    </div>
  </div>
</div>

<div class="card">
  <h2>Usage</h2>
  <div class="stats">
    <div class="stat"><div class="n" id="uToday">–</div><div class="l">min today</div></div>
    <div class="stat"><div class="n" id="uWeek">–</div><div class="l">min this week</div></div>
    <div class="stat"><div class="n" id="uMonth">–</div><div class="l">min this month</div></div>
  </div>
  <div class="meta" style="margin-top:10px" id="usageMeta"></div>
  <div class="chart" id="chart"></div>
  <div class="meta" style="text-align:center;margin-top:6px">last 14 days (min/day)</div>
</div>

<div class="card">
  <h2>Cost</h2>
  <div class="stats">
    <div class="stat"><div class="n" id="cToday">–</div><div class="l">today</div></div>
    <div class="stat"><div class="n" id="cWeek">–</div><div class="l">week</div></div>
    <div class="stat"><div class="n" id="cMonth">–</div><div class="l">month</div></div>
  </div>
  <div class="cyc" style="margin-top:12px">
    <div><label>Cost per ON-minute</label><input id="costPerMin" type="number" step="0.001" min="0"></div>
    <div><label>Currency</label><input id="currency" maxlength="4"></div>
    <div style="flex:0 0 auto;display:flex;align-items:flex-end"><button class="btn-alt" onclick="saveSettings()">Save</button></div>
  </div>
  <small id="rateNote"></small>
</div>

<script>
const $ = id => document.getElementById(id);
let CUR = "₪";

function banner(msg, ok){
  const b = $('banner');
  b.textContent = msg;
  b.className = 'banner ' + (ok ? 'ok' : 'err');
  setTimeout(()=>{ b.className='banner'; }, 4000);
}

async function api(path, method='GET', body){
  const opt = {method, headers:{'Content-Type':'application/json'}};
  if(body) opt.body = JSON.stringify(body);
  const r = await fetch(path, opt);
  return r.json();
}

function renderStatus(s){
  const st = s.state;
  $('dot').className = 'dot ' + (st==='ON'?'on':st==='OFF'?'off':'');
  $('stateText').textContent = st==='ON'?'AC is ON':st==='OFF'?'AC is OFF':'Unknown';
  $('flipState').textContent = s.flipped ? '(flipped)' : '';
  const meta = [];
  meta.push('Device IP: ' + (s.device_ip || 'not discovered yet'));
  if(s.last_result && s.last_result.action){
    const lr = s.last_result;
    meta.push('Last command: ' + lr.action + ' — ' + (lr.ok?'✅ sent':'❌ '+(lr.err||'failed')));
  }
  $('metaText').innerHTML = meta.join('<br>');

  const c = s.cycle || {running:false};
  if(c.running){
    $('cycleActive').style.display='block'; $('cycleIdle').style.display='none';
    $('caOn').textContent=c.on_min; $('caOff').textContent=c.off_min;
    const m = Math.floor(c.seconds_left/60), sec = c.seconds_left%60;
    $('cycleText').textContent = 'Cycle: '+c.phase.toUpperCase()+' phase, '+m+'m '+sec+'s left';
  } else {
    $('cycleActive').style.display='none'; $('cycleIdle').style.display='block';
    $('cycleText').textContent = '';
  }
}

async function refresh(){ renderStatus(await api('/api/status')); }

async function cmd(kind){
  banner('Sending '+kind.toUpperCase()+'…', true);
  const r = await api('/api/'+kind, 'POST');
  if(kind==='flip'){ banner('Flip is now '+(r.flipped?'ON':'OFF'), true); }
  else { r.ok ? banner(kind.toUpperCase()+' sent ✅', true) : banner(kind.toUpperCase()+' failed: '+(r.err||''), false); }
  renderStatus(r);
}

async function cycleStart(){
  const on = +$('onMin').value, off = +$('offMin').value;
  const r = await api('/api/cycle/start','POST',{on, off});
  if(r.error){ banner(r.error, false); return; }
  banner('Cycle started', true); renderStatus(r);
}
async function cycleStop(){ const r = await api('/api/cycle/stop','POST'); banner('Cycle stopped', true); renderStatus(r); }

async function loadAnalytics(){
  const a = await api('/api/analytics');
  CUR = a.currency || '₪';
  $('uToday').textContent = a.today_min;
  $('uWeek').textContent = a.week_min;
  $('uMonth').textContent = a.month_min;
  $('usageMeta').textContent = 'On-periods today: '+a.on_periods_today+' · avg on-duration: '+a.avg_period_min+' min';
  $('cToday').textContent = CUR+' '+a.cost_today;
  $('cWeek').textContent = CUR+' '+a.cost_week;
  $('cMonth').textContent = CUR+' '+a.cost_month;
  if($('costPerMin').value==='') $('costPerMin').value = a.cost_per_min;
  if($('currency').value==='') $('currency').value = a.currency;
  $('rateNote').textContent = a.cost_per_min>0 ? ('Rate: '+CUR+' '+a.cost_per_min+' / ON-minute')
      : 'Cost rate not set — showing 0. Set your per-minute rate above.';

  const last = a.series.slice(-14);
  const max = Math.max(1, ...last.map(d=>d.minutes));
  $('chart').innerHTML = last.map(d=>{
    const h = Math.round(d.minutes/max*100);
    const lbl = d.date.slice(5);
    return '<div class="col" title="'+d.date+': '+d.minutes+' min">'+
      '<div class="bar" style="height:'+h+'%"></div><div class="cl">'+lbl+'</div></div>';
  }).join('');
}

async function saveSettings(){
  await api('/api/settings','POST',{cost_per_min:$('costPerMin').value, currency:$('currency').value});
  banner('Settings saved', true); loadAnalytics();
}

refresh(); loadAnalytics();
setInterval(refresh, 5000);
setInterval(loadAnalytics, 60000);
</script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_app:app", host="0.0.0.0", port=config.WEB_PORT)
