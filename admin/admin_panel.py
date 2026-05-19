#!/usr/bin/env python3
import configparser
import html
import json
import os
import pathlib
import shutil
import subprocess
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg2
import psycopg2.extras


ROOT = pathlib.Path(os.environ.get("ADMIN_WORKSPACE", "/workspace"))
CONFIG_ROOT = ROOT / "config"
ENV_FILE = ROOT / ".env"
BACKUP_ROOT = ROOT / "backups" / "admin-panel"
DATABASE = os.environ.get("DUNE_DATABASE", "dune_sb_1_4_0_0")
ADMIN_TOKEN = os.environ.get("DUNE_ADMIN_TOKEN", "")
MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_MUTATIONS_ENABLED", "false").lower() == "true"

ALLOWED_CONFIGS = {
    "director.ini": CONFIG_ROOT / "director.ini",
    "gateway.ini": CONFIG_ROOT / "gateway.ini",
    "rabbitmq-admin.conf": CONFIG_ROOT / "rabbitmq-admin.conf",
    "rabbitmq-game.conf": CONFIG_ROOT / "rabbitmq-game.conf",
}

SAFE_ENV_KEYS = {
    "DUNE_IMAGE_TAG",
    "WORLD_NAME",
    "WORLD_UNIQUE_NAME",
    "WORLD_REGION",
    "EXTERNAL_ADDRESS",
}


def db_connect():
    return psycopg2.connect(
        host=os.environ.get("DUNE_ADMIN_DB_HOST", "postgres"),
        port=int(os.environ.get("DUNE_ADMIN_DB_PORT", "5432")),
        database=DATABASE,
        user=os.environ.get("DUNE_ADMIN_DB_USER", "dune"),
        password=os.environ.get("DUNE_ADMIN_DB_PASSWORD", os.environ.get("POSTGRES_DUNE_PASSWORD", "")),
    )


def json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def read_env():
    values = {}
    if not ENV_FILE.exists():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def write_safe_env(updates):
    original = ENV_FILE.read_text(encoding="utf-8").splitlines()
    seen = set()
    rendered = []
    for line in original:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            rendered.append(line)
            continue
        key, _ = line.split("=", 1)
        key = key.strip()
        if key in SAFE_ENV_KEYS and key in updates:
            rendered.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            rendered.append(line)
    for key in sorted(SAFE_ENV_KEYS - seen):
        if key in updates:
            rendered.append(f"{key}={updates[key]}")
    backup_file(ENV_FILE)
    ENV_FILE.write_text("\n".join(rendered) + "\n", encoding="utf-8")


def backup_file(path):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    shutil.copy2(path, BACKUP_ROOT / f"{stamp}-{path.name}")


def parse_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    data = handler.rfile.read(length) if length else b"{}"
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        return json.loads(data.decode("utf-8") or "{}")
    parsed = urllib.parse.parse_qs(data.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def query(sql, params=None):
    with db_connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(sql, params or ())
            if cursor.description:
                return list(cursor.fetchall())
            return []


def execute(sql, params=None):
    with db_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params or ())


class Handler(BaseHTTPRequestHandler):
    server_version = "dune-admin-panel"

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.html(INDEX)
        elif parsed.path == "/api/status":
            self.json({
                "database": DATABASE,
                "mutationsEnabled": MUTATIONS_ENABLED,
                "safeEnvKeys": sorted(SAFE_ENV_KEYS),
                "configs": sorted(ALLOWED_CONFIGS),
            })
        elif parsed.path == "/api/server/state":
            self.json({
                "farmState": query("select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr from dune.farm_state order by map, server_id"),
                "partitions": query("select partition_id,server_id,map,dimension_index,label from dune.world_partition order by partition_id"),
                "activeServers": query("select * from dune.active_server_ids order by server_id"),
            })
        elif parsed.path == "/api/characters":
            params = urllib.parse.parse_qs(parsed.query)
            term = (params.get("q", [""])[0] or "").strip()
            self.json(self.characters(term))
        elif parsed.path.startswith("/api/characters/"):
            account_id = int(parsed.path.rsplit("/", 1)[-1])
            self.json(self.character_detail(account_id))
        elif parsed.path == "/api/settings/env":
            env_values = read_env()
            self.json({key: env_values.get(key, "") for key in sorted(SAFE_ENV_KEYS)})
        elif parsed.path == "/api/settings/configs":
            self.json({name: path.read_text(encoding="utf-8") for name, path in ALLOWED_CONFIGS.items() if path.exists()})
        else:
            self.error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path.startswith("/api/settings/configs/"):
                self.require_token()
                name = parsed.path.rsplit("/", 1)[-1]
                body = parse_body(self)
                self.write_config(name, body.get("content", ""))
                self.json({"ok": True})
            elif parsed.path == "/api/settings/env":
                self.require_token()
                body = parse_body(self)
                updates = {key: str(body.get(key, "")) for key in SAFE_ENV_KEYS if key in body}
                write_safe_env(updates)
                self.json({"ok": True})
            elif parsed.path == "/api/admin/currency":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_currency(body)
                self.json({"ok": True})
            elif parsed.path == "/api/admin/xp":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_xp(body)
                self.json({"ok": True})
            elif parsed.path == "/api/admin/unsupported":
                self.require_token()
                self.error(HTTPStatus.NOT_IMPLEMENTED, "gear/skill grants need mapped template IDs and table contracts before writes are safe")
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except NotImplementedError as exc:
            self.error(HTTPStatus.NOT_IMPLEMENTED, str(exc))
        except Exception as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def characters(self, term):
        like = f"%{term}%"
        sql = """
            select ps.account_id, ps.character_name, ps.online_status::text, ps.life_state::text,
                   ps.server_id, ps.player_controller_id, ps.player_pawn_id, ps.player_state_id,
                   ps.last_login_time, a.funcom_id, a.platform_name, a.platform_id
            from dune.player_state ps
            left join dune.accounts a on a.id = ps.account_id
            where (%s = '' or ps.character_name ilike %s or a.funcom_id ilike %s or a.platform_id ilike %s)
            order by ps.last_login_time desc nulls last, ps.account_id
            limit 100
        """
        return query(sql, (term, like, like, like))

    def character_detail(self, account_id):
        player = query("select * from dune.player_state where account_id=%s", (account_id,))
        if not player:
            self.error(HTTPStatus.NOT_FOUND, "character not found")
            return {}
        controller_id = player[0].get("player_controller_id")
        pawn_id = player[0].get("player_pawn_id")
        return {
            "player": player[0],
            "account": query("select id, funcom_id, platform_name, platform_id, takeoverable from dune.accounts where id=%s", (account_id,)),
            "currency": query("select * from dune.player_virtual_currency_balances where player_controller_id=%s order by currency_id", (controller_id,)),
            "specialization": query("select * from dune.specialization_tracks where player_id=%s order by track_type::text", (controller_id,)),
            "faction": query("select * from dune.player_faction where actor_id=%s order by faction_id", (pawn_id,)),
            "reputation": query("select * from dune.player_faction_reputation where actor_id=%s order by faction_id", (pawn_id,)),
            "inventories": query("select * from dune.inventories where actor_id in (%s,%s) order by id", (controller_id, pawn_id)),
        }

    def update_currency(self, body):
        controller_id = int(body["player_controller_id"])
        currency_id = int(body["currency_id"])
        amount = int(body["amount"])
        mode = body.get("mode", "add")
        if mode == "set":
            execute("""
                insert into dune.player_virtual_currency_balances(player_controller_id,currency_id,balance)
                values (%s,%s,%s)
                on conflict (player_controller_id,currency_id) do update set balance=excluded.balance
            """, (controller_id, currency_id, amount))
        elif mode == "add":
            execute("""
                insert into dune.player_virtual_currency_balances(player_controller_id,currency_id,balance)
                values (%s,%s,%s)
                on conflict (player_controller_id,currency_id) do update set balance=dune.player_virtual_currency_balances.balance + excluded.balance
            """, (controller_id, currency_id, amount))
        else:
            raise ValueError("mode must be add or set")

    def update_xp(self, body):
        player_id = int(body["player_id"])
        track_type = str(body["track_type"])
        amount = int(body["amount"])
        mode = body.get("mode", "add")
        if mode == "set":
            execute("update dune.specialization_tracks set xp_amount=%s where player_id=%s and track_type::text=%s", (amount, player_id, track_type))
        elif mode == "add":
            execute("update dune.specialization_tracks set xp_amount=xp_amount + %s where player_id=%s and track_type::text=%s", (amount, player_id, track_type))
        else:
            raise ValueError("mode must be add or set")

    def write_config(self, name, content):
        if name not in ALLOWED_CONFIGS:
            raise ValueError("config file not allowed")
        path = ALLOWED_CONFIGS[name]
        if name.endswith(".ini"):
            parser = configparser.ConfigParser()
            parser.read_string(content)
        backup_file(path)
        path.write_text(content, encoding="utf-8")

    def require_token(self):
        if not ADMIN_TOKEN:
            raise PermissionError("DUNE_ADMIN_TOKEN is not configured")
        provided = self.headers.get("X-Admin-Token", "")
        if provided != ADMIN_TOKEN:
            raise PermissionError("invalid admin token")

    def require_mutations(self):
        if not MUTATIONS_ENABLED:
            raise PermissionError("mutations are disabled; set DUNE_ADMIN_MUTATIONS_ENABLED=true")

    def html(self, body):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json(self, value):
        data = json.dumps(value, default=json_default, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        data = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        return


INDEX = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dune Admin</title>
  <style>
    :root { color-scheme: dark; --bg:#111411; --panel:#191d19; --muted:#9da89e; --line:#30382f; --text:#ecf2e8; --accent:#d7a64a; --danger:#d66b5f; --ok:#7bbf74; }
    body { margin:0; font:14px/1.45 system-ui, sans-serif; background:var(--bg); color:var(--text); }
    header { display:flex; justify-content:space-between; align-items:center; gap:16px; padding:14px 18px; border-bottom:1px solid var(--line); background:#151915; position:sticky; top:0; }
    h1 { font-size:18px; margin:0; }
    main { display:grid; grid-template-columns:320px 1fr; min-height:calc(100vh - 58px); }
    nav { border-right:1px solid var(--line); padding:14px; }
    section { padding:18px; }
    button, input, select, textarea { font:inherit; border:1px solid var(--line); background:#101310; color:var(--text); border-radius:6px; padding:8px 10px; }
    button { cursor:pointer; background:#22291f; }
    button.primary { background:var(--accent); color:#16120a; border-color:#e0b45e; font-weight:700; }
    button.danger { background:#35201e; color:#ffd5d0; border-color:#78423c; }
    input, select { width:100%; box-sizing:border-box; }
    textarea { width:100%; min-height:340px; box-sizing:border-box; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; }
    .tabs { display:flex; gap:8px; flex-wrap:wrap; }
    .tab { padding:8px 10px; }
    .tab.active { border-color:var(--accent); color:var(--accent); }
    .card { border:1px solid var(--line); border-radius:8px; background:var(--panel); padding:14px; margin-bottom:14px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }
    .row { display:flex; gap:8px; align-items:center; margin:8px 0; }
    .muted { color:var(--muted); }
    .ok { color:var(--ok); }
    .dangerText { color:var(--danger); }
    table { width:100%; border-collapse:collapse; }
    th, td { text-align:left; border-bottom:1px solid var(--line); padding:7px 6px; vertical-align:top; }
    pre { white-space:pre-wrap; overflow:auto; background:#0d100d; border:1px solid var(--line); padding:10px; border-radius:6px; }
    @media (max-width: 820px) { main { grid-template-columns:1fr; } nav { border-right:0; border-bottom:1px solid var(--line); } }
  </style>
</head>
<body>
  <header>
    <h1>Dune Admin</h1>
    <div class="row"><input id="token" type="password" placeholder="Admin token"><button onclick="saveToken()">Use token</button></div>
  </header>
  <main>
    <nav>
      <div class="tabs">
        <button class="tab active" onclick="show('overview')">Overview</button>
        <button class="tab" onclick="show('characters')">Characters</button>
        <button class="tab" onclick="show('settings')">Settings</button>
        <button class="tab" onclick="show('mutations')">Admin Actions</button>
      </div>
      <div class="card"><div class="muted">Host this behind local DNS as <code>duneadmin.home</code>. Keep it LAN/VPN-only.</div></div>
      <pre id="status"></pre>
    </nav>
    <section id="view"></section>
  </main>
<script>
let token = localStorage.getItem('duneAdminToken') || '';
document.getElementById('token').value = token;
let current = 'overview';

function saveToken(){ token = document.getElementById('token').value; localStorage.setItem('duneAdminToken', token); }
async function api(path, opts={}) {
  opts.headers = Object.assign({'Content-Type':'application/json'}, opts.headers || {});
  if (token) opts.headers['X-Admin-Token'] = token;
  const res = await fetch(path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}
function esc(v){ return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function table(rows){
  if (!rows || !rows.length) return '<div class="muted">No rows.</div>';
  const keys = Object.keys(rows[0]);
  return `<table><thead><tr>${keys.map(k=>`<th>${esc(k)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr data-id="${esc(r.account_id ?? '')}">${keys.map(k=>`<td>${esc(r[k])}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}
function show(name){ current=name; document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.textContent.toLowerCase().startsWith(name.slice(0,6)))); load(); }
async function refreshStatus(){ document.getElementById('status').textContent = JSON.stringify(await api('/api/status'), null, 2); }
async function load(){
  await refreshStatus().catch(e => document.getElementById('status').textContent = e.message);
  if (current === 'overview') return overview();
  if (current === 'characters') return characters();
  if (current === 'settings') return settings();
  if (current === 'mutations') return mutations();
}
async function overview(){
  const state = await api('/api/server/state');
  view.innerHTML = `<div class="card"><h2>Farm State</h2>${table(state.farmState)}</div><div class="card"><h2>Partitions</h2>${table(state.partitions)}</div><div class="card"><h2>Active Servers</h2>${table(state.activeServers)}</div>`;
}
async function characters(){
  view.innerHTML = `<div class="card"><div class="row"><input id="q" placeholder="Character, Funcom ID, platform ID"><button class="primary" onclick="searchCharacters()">Search</button></div><div id="results"></div></div><div id="detail"></div>`;
}
async function searchCharacters(){
  const rows = await api('/api/characters?q=' + encodeURIComponent(document.getElementById('q').value));
  const results = document.getElementById('results');
  results.innerHTML = table(rows);
  results.querySelectorAll('tbody tr').forEach(row => row.onclick = () => pickCharacter(row));
}
async function pickCharacter(row){
  const id = row.dataset.id || row.children[0].textContent;
  if (!id) return;
  const d = await api('/api/characters/' + encodeURIComponent(id));
  document.getElementById('detail').innerHTML = `<div class="card"><h2>Character Detail</h2><pre>${esc(JSON.stringify(d, null, 2))}</pre></div>`;
}
async function settings(){
  const env = await api('/api/settings/env');
  const configs = await api('/api/settings/configs');
  view.innerHTML = `<div class="card"><h2>Safe Env Settings</h2><div class="grid">${Object.entries(env).map(([k,v])=>`<label>${esc(k)}<input id="env_${esc(k)}" value="${esc(v)}"></label>`).join('')}</div><p><button class="primary" onclick="saveEnv()">Save env settings</button></p></div><div class="card"><h2>Config Files</h2><select id="cfg" onchange="selectCfg()">${Object.keys(configs).map(k=>`<option>${esc(k)}</option>`).join('')}</select><textarea id="cfgText"></textarea><p><button class="primary" onclick="saveCfg()">Save config with backup</button></p></div>`;
  window.configs = configs; selectCfg();
}
function selectCfg(){ const name=document.getElementById('cfg').value; document.getElementById('cfgText').value = window.configs[name] || ''; }
async function saveEnv(){
  const body={}; document.querySelectorAll('[id^=env_]').forEach(i=>body[i.id.slice(4)]=i.value);
  await api('/api/settings/env', {method:'POST', body:JSON.stringify(body)}); alert('Saved .env safe keys');
}
async function saveCfg(){
  const name=document.getElementById('cfg').value;
  await api('/api/settings/configs/' + encodeURIComponent(name), {method:'POST', body:JSON.stringify({content:document.getElementById('cfgText').value})});
  alert('Saved ' + name);
}
async function mutations(){
  view.innerHTML = `<div class="card"><h2>Admin Actions</h2><p class="dangerText">Writes require <code>DUNE_ADMIN_MUTATIONS_ENABLED=true</code> and a valid admin token. Back up first.</p><div class="grid"><label>Player controller ID<input id="pcid"></label><label>Currency ID<input id="curid" value="1"></label><label>Amount<input id="amount" value="1000"></label><label>Mode<select id="mode"><option>add</option><option>set</option></select></label></div><p><button class="primary" onclick="currency()">Apply currency</button></p></div><div class="card"><h2>Gear and Skill Grants</h2><p class="muted">Not implemented yet. We need validated template IDs and table contracts before this panel writes item rows or unlock data.</p><button class="danger" onclick="unsupported()">Test unsupported endpoint</button></div>`;
}
async function currency(){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:pcid.value,currency_id:curid.value,amount:amount.value,mode:mode.value})});
  alert('Currency updated');
}
async function unsupported(){ try { await api('/api/admin/unsupported', {method:'POST', body:'{}'}); } catch(e) { alert(e.message); } }
load();
</script>
</body>
</html>
"""


def main():
    port = int(os.environ.get("DUNE_ADMIN_PORT", "8080"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
