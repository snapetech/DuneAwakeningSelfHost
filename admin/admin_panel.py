#!/usr/bin/env python3
import configparser
import hmac
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
AUDIT_LOG = BACKUP_ROOT / "audit.jsonl"
DATABASE = os.environ.get("DUNE_DATABASE", "dune_sb_1_4_0_0")
ADMIN_TOKEN = os.environ.get("DUNE_ADMIN_TOKEN", "")
MUTATIONS_ENABLED = os.environ.get("DUNE_ADMIN_MUTATIONS_ENABLED", "false").lower() == "true"
ITEM_GRANTS_ENABLED = os.environ.get("DUNE_ADMIN_ITEM_GRANTS_ENABLED", "true").lower() == "true"
MAX_BODY_BYTES = int(os.environ.get("DUNE_ADMIN_MAX_BODY_BYTES", "65536"))
ALLOWED_HOSTS = {
    host.strip().lower()
    for host in os.environ.get("DUNE_ADMIN_ALLOWED_HOSTS", "127.0.0.1:18080,localhost:18080,duneadmin.home").split(",")
    if host.strip()
}
AUTH_FAILURE_WINDOW_SECONDS = 60
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURES = {}

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

AUDIT_FIELD_LIMIT = 240


def audit_safe(value):
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (list, tuple)):
        return [audit_safe(item) for item in value[:20]]
    if isinstance(value, dict):
        return {
            str(key): audit_safe(item)
            for key, item in value.items()
            if "token" not in str(key).lower() and "password" not in str(key).lower() and "secret" not in str(key).lower()
        }
    text = str(value)
    if len(text) > AUDIT_FIELD_LIMIT:
        return text[:AUDIT_FIELD_LIMIT] + "...[truncated]"
    return text


def audit_event(action, ok=True, **fields):
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    event = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "action": action,
        "ok": bool(ok),
    }
    event.update({key: audit_safe(value) for key, value in fields.items()})
    with AUDIT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, default=json_default) + "\n")


def recent_audit_events(limit=100):
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"ts": "", "action": "audit-log-parse-error", "ok": False})
    return events


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
    if length > MAX_BODY_BYTES:
        raise ValueError("request body too large")
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
            return cursor.rowcount


def create_db_backup():
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = BACKUP_ROOT / f"{stamp}-{DATABASE}.dump"
    env = os.environ.copy()
    env["PGPASSWORD"] = os.environ.get("DUNE_ADMIN_DB_PASSWORD", os.environ.get("POSTGRES_DUNE_PASSWORD", ""))
    cmd = [
        "pg_dump",
        "-h", os.environ.get("DUNE_ADMIN_DB_HOST", "postgres"),
        "-p", os.environ.get("DUNE_ADMIN_DB_PORT", "5432"),
        "-U", os.environ.get("DUNE_ADMIN_DB_USER", "dune"),
        "-d", DATABASE,
        "-Fc",
        "-f", str(path),
    ]
    subprocess.run(cmd, check=True, env=env, capture_output=True, text=True)
    return {"path": str(path), "bytes": path.stat().st_size}


class Handler(BaseHTTPRequestHandler):
    server_version = "dune-admin-panel"

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except ConnectionError:
            raise
        except Exception as exc:
            try:
                self.error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception:
                pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            if parsed.path == "/":
                self.html(INDEX)
            elif parsed.path == "/api/status":
                self.json({
                    "database": DATABASE,
                    "mutationsEnabled": MUTATIONS_ENABLED,
                    "itemGrantsEnabled": ITEM_GRANTS_ENABLED,
                    "adminTokenConfigured": bool(ADMIN_TOKEN),
                    "safeEnvKeys": sorted(SAFE_ENV_KEYS),
                    "configs": sorted(ALLOWED_CONFIGS),
                })
            elif parsed.path == "/api/server/state":
                self.require_token()
                self.json({
                    "farmState": query("select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr from dune.farm_state order by map, server_id"),
                    "partitions": query("select partition_id,server_id,map,dimension_index,label from dune.world_partition order by partition_id"),
                    "activeServers": query("select * from dune.active_server_ids order by server_id"),
                })
            elif parsed.path == "/api/ops/health":
                self.require_token()
                self.json(self.ops_health())
            elif parsed.path == "/api/ops/security":
                self.require_token()
                self.json(self.security_audit())
            elif parsed.path == "/api/ops/audit":
                self.require_token()
                self.json({"events": recent_audit_events()})
            elif parsed.path == "/api/ops/optimization":
                self.require_token()
                self.json(self.optimization_signals())
            elif parsed.path == "/api/ops/runbook":
                self.require_token()
                self.json(self.ops_runbook())
            elif parsed.path == "/api/characters":
                self.require_token()
                params = urllib.parse.parse_qs(parsed.query)
                term = (params.get("q", [""])[0] or "").strip()
                self.json(self.characters(term))
            elif parsed.path.startswith("/api/characters/"):
                self.require_token()
                account_id = int(parsed.path.rsplit("/", 1)[-1])
                self.json(self.character_detail(account_id))
            elif parsed.path == "/api/settings/env":
                self.require_token()
                env_values = read_env()
                self.json({key: env_values.get(key, "") for key in sorted(SAFE_ENV_KEYS)})
            elif parsed.path == "/api/settings/configs":
                self.require_token()
                self.json({name: path.read_text(encoding="utf-8") for name, path in ALLOWED_CONFIGS.items() if path.exists()})
            elif parsed.path == "/api/admin/reference":
                self.require_token()
                self.json(self.admin_reference())
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except Exception as exc:
            self.error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_HEAD(self):
        self.validate_host()
        self.send_response(HTTPStatus.NO_CONTENT)
        self.security_headers()
        self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            self.validate_host()
            self.validate_same_origin()
            if parsed.path.startswith("/api/settings/configs/"):
                self.require_token()
                name = parsed.path.rsplit("/", 1)[-1]
                body = parse_body(self)
                self.write_config(name, body.get("content", ""))
                self.audit("config-write", config=name)
                self.json({"ok": True})
            elif parsed.path == "/api/settings/env":
                self.require_token()
                body = parse_body(self)
                updates = {key: str(body.get(key, "")) for key in SAFE_ENV_KEYS if key in body}
                write_safe_env(updates)
                self.audit("env-write", keys=sorted(updates))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/currency":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_currency(body)
                self.audit("currency-update", player_controller_id=body.get("player_controller_id"), currency_id=body.get("currency_id"), amount=body.get("amount"), mode=body.get("mode", "add"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/xp":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.update_xp(body)
                self.audit("xp-update", player_id=body.get("player_id"), track_type=body.get("track_type"), amount=body.get("amount"), mode=body.get("mode", "add"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/keystone":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                result = self.purchase_keystone(body)
                self.audit("keystone-purchase", player_id=body.get("player_id"), keystone=body.get("keystone"))
                self.json(result)
            elif parsed.path == "/api/admin/reset-keystones":
                self.require_token()
                self.require_mutations()
                body = parse_body(self)
                self.reset_keystones(body)
                self.audit("keystone-reset", player_id=body.get("player_id"))
                self.json({"ok": True})
            elif parsed.path == "/api/admin/unsupported":
                self.require_token()
                self.error(HTTPStatus.NOT_IMPLEMENTED, "gear/skill grants need mapped template IDs and table contracts before writes are safe")
            elif parsed.path == "/api/admin/backup":
                self.require_token()
                result = create_db_backup()
                self.audit("database-backup", path=result.get("path"), bytes=result.get("bytes"))
                self.json(result)
            elif parsed.path == "/api/admin/item":
                self.require_token()
                self.require_mutations()
                self.require_item_grants()
                body = parse_body(self)
                result = self.grant_item(body)
                self.audit("item-grant", inventory_id=result.get("inventory_id"), template_id=result.get("template_id"), item_id=result.get("item_id"), stack_size=result.get("stack_size"))
                self.json(result)
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")
        except PermissionError as exc:
            self.audit("post-rejected", ok=False, error=str(exc))
            self.error(HTTPStatus.UNAUTHORIZED, str(exc))
        except NotImplementedError as exc:
            self.audit("post-not-implemented", ok=False, error=str(exc))
            self.error(HTTPStatus.NOT_IMPLEMENTED, str(exc))
        except Exception as exc:
            self.audit("post-failed", ok=False, error=str(exc))
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
            "inventoryItems": query("select * from dune.admin_get_inventory_details(%s)", (account_id,)),
        }

    def admin_reference(self):
        return {
            "currencyIds": query("select distinct currency_id from dune.player_virtual_currency_balances order by currency_id"),
            "specializationTrackTypes": query("""
                select enumlabel as track_type
                from pg_enum e
                join pg_type t on t.oid = e.enumtypid
                where t.typname = 'specializationtracktype'
                order by enumsortorder
            """),
            "observedItemTemplates": query("""
                select template_id, count(*) as count
                from dune.items
                where template_id is not null
                group by template_id
                order by count desc, template_id
                limit 200
            """),
            "recentInventories": query("""
                select ps.account_id, ps.character_name, inv.id as inventory_id, inv.actor_id,
                       inv.inventory_type, inv.max_item_count, count(i.id) as item_count
                from dune.inventories inv
                left join dune.items i on i.inventory_id = inv.id
                left join dune.player_state ps on ps.player_pawn_id = inv.actor_id or ps.player_controller_id = inv.actor_id
                group by ps.account_id, ps.character_name, inv.id, inv.actor_id, inv.inventory_type, inv.max_item_count
                order by ps.character_name nulls last, inv.id
                limit 200
            """),
            "keystones": query("select id, name from dune.specialization_keystones_map order by name"),
            "publicItemDatabase": "https://dune.gaming.tools/items",
        }

    def grant_item(self, body):
        inventory_id = int(body["inventory_id"])
        template_id = str(body["template_id"]).strip()
        stack_size = max(1, int(body.get("stack_size", 1)))
        quality_level = max(0, int(body.get("quality_level", 0)))
        position_index = body.get("position_index", "")
        stats = body.get("stats", {}) or {}
        if isinstance(stats, str):
            stats = json.loads(stats or "{}")
        if not template_id:
            raise ValueError("template_id is required")
        if not query("select 1 from dune.inventories where id=%s", (inventory_id,)):
            raise ValueError("inventory_id does not exist")
        if position_index in ("", None):
            rows = query("select coalesce(max(position_index), -1) + 1 as next_position from dune.items where inventory_id=%s", (inventory_id,))
            position_index = int(rows[0]["next_position"])
        else:
            position_index = int(position_index)
        item_id = query("select dune.advance_items_id_sequencer(1) as item_id")[0]["item_id"]
        acquisition_time = int(body.get("acquisition_time") or time.time() * 1000)
        execute("""
            select dune.save_item((
                %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s
            )::dune.inventoryitem)
        """, (
            item_id,
            inventory_id,
            stack_size,
            position_index,
            template_id,
            True,
            acquisition_time,
            json.dumps(stats),
            quality_level,
            None,
        ))
        return {
            "item_id": item_id,
            "inventory_id": inventory_id,
            "template_id": template_id,
            "stack_size": stack_size,
            "position_index": position_index,
            "quality_level": quality_level,
        }

    def ops_health(self):
        farm = query("select server_id,farm_id,ready,alive,map,revision,game_addr,igw_addr,connected_players from dune.farm_state order by map, server_id")
        partitions = query("select partition_id,server_id,map,dimension_index,label from dune.world_partition order by partition_id")
        active = query("select * from dune.active_server_ids order by server_id")
        player_counts = query("""
            select
              coalesce((select sum(connected_players) from dune.farm_state), 0) as connected_players_reported,
              (select count(*) from dune.get_online_player_controller_ids_on_farm()) as online_controller_ids,
              (select count(*) from dune.get_all_online_or_recently_disconnected_player_online_state()) as online_or_recently_disconnected,
              (select count(*) from dune.get_player_online_state_within_grace_period_for_each_server()) as grace_period_entries
        """)[0]
        verdicts = [
            {"name": "farm ready/alive", "ok": any(row.get("ready") and row.get("alive") for row in farm)},
            {"name": "active server ids", "ok": bool(active)},
            {"name": "world partitions", "ok": bool(partitions)},
            {"name": "player counts query", "ok": True},
        ]
        return {
            "verdicts": verdicts,
            "playerCounts": player_counts,
            "farmState": farm,
            "partitions": partitions,
            "activeServers": active,
        }

    def security_audit(self):
        env_values = read_env()
        checks = [
            {"name": "admin token configured", "ok": bool(ADMIN_TOKEN)},
            {"name": "admin token not placeholder", "ok": ADMIN_TOKEN not in ("", "change-me-admin-token")},
            {"name": "mutations disabled by default", "ok": not MUTATIONS_ENABLED, "value": MUTATIONS_ENABLED},
            {"name": "item grants flag", "ok": ITEM_GRANTS_ENABLED, "value": ITEM_GRANTS_ENABLED},
            {"name": "allowed hosts configured", "ok": bool(ALLOWED_HOSTS), "value": ", ".join(sorted(ALLOWED_HOSTS))},
            {"name": "request body limit", "ok": MAX_BODY_BYTES <= 262144, "value": MAX_BODY_BYTES},
            {"name": "FLS token not editable here", "ok": "FLS_SECRET" not in SAFE_ENV_KEYS},
            {"name": "backup path under ignored backups/", "ok": str(BACKUP_ROOT).startswith(str(ROOT / "backups"))},
            {"name": "audit log under ignored backups/", "ok": str(AUDIT_LOG).startswith(str(ROOT / "backups")), "value": str(AUDIT_LOG.relative_to(ROOT))},
            {"name": "RabbitMQ secret not editable here", "ok": "RMQ_HTTP_TOKEN_AUTH_SECRET" not in SAFE_ENV_KEYS},
            {"name": "database password not editable here", "ok": "POSTGRES_DUNE_PASSWORD" not in SAFE_ENV_KEYS},
            {"name": "external address set", "ok": bool(env_values.get("EXTERNAL_ADDRESS", "")), "value": env_values.get("EXTERNAL_ADDRESS", "")},
        ]
        return {
            "checks": checks,
            "allowedConfigFiles": sorted(ALLOWED_CONFIGS),
            "safeEnvKeys": sorted(SAFE_ENV_KEYS),
            "notes": [
                "Keep the panel bound to localhost or trusted LAN/VPN only.",
                "Do not expose RabbitMQ, Postgres, or this panel directly to the internet.",
                "Use mutations only for deliberate admin edits after taking a backup.",
            ],
        }

    def audit(self, action, ok=True, **fields):
        peer = self.client_address[0] if self.client_address else "unknown"
        audit_event(action, ok=ok, peer=peer, method=self.command, path=urllib.parse.urlparse(self.path).path, **fields)

    def optimization_signals(self):
        return {
            "memory": [
                {"name": "Survival guardrail", "value": "12Gi", "why": "Matches Funcom's official Survival_1 workload limit."},
                {"name": "Tight caps", "value": "avoid initially", "why": "Observed high-water memory can be much higher than later idle RSS."},
            ],
            "storage": [
                {"name": "Game image", "value": "~10.3GB", "why": "Large content/tooling layers dominate local image storage."},
                {"name": "Delete-in-child image", "value": "not enough", "why": "Deleting files in a child layer does not reclaim base image size."},
            ],
            "network": [
                {"name": "Gateway Postgres TIME_WAIT", "value": "watch", "why": "May indicate short-lived DB connections."},
                {"name": "TextRouter Postgres CLOSE_WAIT", "value": "watch", "why": "A growing count would indicate stale socket cleanup trouble."},
                {"name": "Public ports", "value": "7777/udp and 7888/udp only", "why": "RabbitMQ, Postgres, and admin surfaces should remain private."},
            ],
            "knobs": [
                {"name": "compose.limits.example.yaml", "value": "optional", "why": "Conservative memory guardrails without changing default topology."},
                {"name": "safe env settings", "value": sorted(SAFE_ENV_KEYS), "why": "Editable operational values that do not include secrets."},
            ],
        }

    def ops_runbook(self):
        return {
            "safeCliOnly": True,
            "why": "The panel deliberately does not mount the container runtime socket or execute arbitrary shell commands.",
            "commands": [
                {"name": "Status", "command": "./scripts/status.sh .env", "when": "Quick health and high-signal logs."},
                {"name": "Routing capture before transition", "command": "./scripts/capture-routing.sh .env hagga-to-deep-desert-before", "when": "Before attempting a broken transition."},
                {"name": "Routing capture after transition", "command": "./scripts/capture-routing.sh .env hagga-to-deep-desert-after", "when": "Immediately after a failed transition."},
                {"name": "Runtime profile", "command": "./scripts/profile-runtime.sh .env", "when": "Memory/storage/network/process teardown."},
                {"name": "Summarize runtime profile", "command": "./scripts/summarize-runtime-profile.sh captures/YYYYMMDDTHHMMSSZ-runtime-profile", "when": "Compare profile captures."},
                {"name": "Network watch", "command": "./scripts/watch-network.sh .env", "when": "Check Postgres/RabbitMQ socket churn."},
                {"name": "Backup state", "command": "./scripts/backup-state.sh .env", "when": "Before upgrades, config surgery, or admin mutations."},
            ],
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
        level = float(body.get("level", 0))
        mode = body.get("mode", "add")
        if mode == "set":
            execute("select dune.set_specialization_xp_and_level(%s, %s::dune.specializationtracktype, %s, %s)", (player_id, track_type, amount, level))
        elif mode == "add":
            existing = query("select xp_amount, level from dune.specialization_tracks where player_id=%s and track_type::text=%s", (player_id, track_type))
            current_xp = existing[0]["xp_amount"] if existing else 0
            current_level = existing[0]["level"] if existing else level
            execute("select dune.set_specialization_xp_and_level(%s, %s::dune.specializationtracktype, %s, %s)", (player_id, track_type, current_xp + amount, current_level))
        else:
            raise ValueError("mode must be add or set")

    def purchase_keystone(self, body):
        player_id = int(body["player_id"])
        keystone = str(body["keystone"]).strip()
        result = query("select dune.purchase_specialization_keystone(%s, %s) as purchased", (player_id, keystone))[0]["purchased"]
        if not result:
            raise ValueError("keystone was not purchased; it may be unknown or already present")
        return {"ok": True, "player_id": player_id, "keystone": keystone}

    def reset_keystones(self, body):
        player_id = int(body["player_id"])
        execute("select dune.reset_specialization_keystones(%s)", (player_id,))

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
        peer = self.client_address[0] if self.client_address else "unknown"
        now = time.time()
        failures = [ts for ts in AUTH_FAILURES.get(peer, []) if now - ts < AUTH_FAILURE_WINDOW_SECONDS]
        AUTH_FAILURES[peer] = failures
        if len(failures) >= AUTH_FAILURE_LIMIT:
            self.audit("auth-throttled", ok=False, failures=len(failures))
            raise PermissionError("too many failed admin token attempts")
        provided = self.headers.get("X-Admin-Token", "")
        if not hmac.compare_digest(provided, ADMIN_TOKEN):
            failures.append(now)
            AUTH_FAILURES[peer] = failures
            self.audit("auth-failed", ok=False, failures=len(failures))
            raise PermissionError("invalid admin token")
        AUTH_FAILURES.pop(peer, None)

    def require_mutations(self):
        if not MUTATIONS_ENABLED:
            raise PermissionError("mutations are disabled; set DUNE_ADMIN_MUTATIONS_ENABLED=true")

    def require_item_grants(self):
        if not ITEM_GRANTS_ENABLED:
            raise PermissionError("item grants are disabled; set DUNE_ADMIN_ITEM_GRANTS_ENABLED=true")

    def validate_host(self):
        if not ALLOWED_HOSTS:
            return
        host = self.headers.get("Host", "").lower()
        if host not in ALLOWED_HOSTS:
            self.audit("host-rejected", ok=False, host=host)
            raise PermissionError("host is not allowed for admin panel")

    def validate_same_origin(self):
        host = self.headers.get("Host", "").lower()
        expected = {f"http://{host}", f"https://{host}"}
        origin = self.headers.get("Origin")
        if origin and origin.rstrip("/") not in expected:
            self.audit("origin-rejected", ok=False, origin=origin)
            raise PermissionError("cross-origin admin request rejected")
        referer = self.headers.get("Referer")
        if referer:
            parsed = urllib.parse.urlparse(referer)
            referer_origin = f"{parsed.scheme}://{parsed.netloc}".lower()
            if referer_origin not in expected:
                self.audit("referer-rejected", ok=False, referer_origin=referer_origin)
                raise PermissionError("cross-origin admin request rejected")

    def html(self, body):
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def json(self, value):
        data = json.dumps(value, default=json_default, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def error(self, status, message):
        data = json.dumps({"error": message}).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.security_headers()
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def security_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'unsafe-inline' 'self'; style-src 'unsafe-inline' 'self'; connect-src 'self'; frame-ancestors 'none'")

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
        <button class="tab" onclick="show('ops')">Ops</button>
        <button class="tab" onclick="show('security')">Security</button>
        <button class="tab" onclick="show('runbook')">Runbook</button>
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
let token = sessionStorage.getItem('duneAdminToken') || '';
document.getElementById('token').value = token;
let current = 'overview';

function saveToken(){ token = document.getElementById('token').value; sessionStorage.setItem('duneAdminToken', token); load(); }
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
function options(rows, key, fallback=''){
  const vals = (rows || []).map(r => r[key]).filter(v => v !== undefined && v !== null);
  if (!vals.length && fallback) vals.push(fallback);
  return vals.map(v => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
}
function inventoryOptions(rows){
  const vals = rows || [];
  if (!vals.length) return '<option value="">No inventories observed</option>';
  return vals.map(r => `<option value="${esc(r.inventory_id)}">${esc(r.character_name || 'unowned')} | inv ${esc(r.inventory_id)} | type ${esc(r.inventory_type)} | ${esc(r.item_count)} items</option>`).join('');
}
function checks(rows){
  return `<table><thead><tr><th>Check</th><th>Status</th><th>Value</th></tr></thead><tbody>${(rows || []).map(r=>`<tr><td>${esc(r.name)}</td><td class="${r.ok ? 'ok' : 'dangerText'}">${r.ok ? 'OK' : 'Needs attention'}</td><td>${esc(r.value ?? '')}</td></tr>`).join('')}</tbody></table>`;
}
function signalList(groups){
  return Object.entries(groups || {}).map(([group, rows]) => `<div class="card"><h2>${esc(group)}</h2><table><thead><tr><th>Name</th><th>Value</th><th>Why</th></tr></thead><tbody>${(rows || []).map(r=>`<tr><td>${esc(r.name)}</td><td>${esc(Array.isArray(r.value) ? r.value.join(', ') : r.value)}</td><td>${esc(r.why)}</td></tr>`).join('')}</tbody></table></div>`).join('');
}
function show(name){ current=name; document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.textContent.toLowerCase().startsWith(name.slice(0,6)))); load(); }
async function refreshStatus(){ document.getElementById('status').textContent = JSON.stringify(await api('/api/status'), null, 2); }
async function load(){
  await refreshStatus().catch(e => document.getElementById('status').textContent = e.message);
  try {
    if (current === 'overview') return overview();
    if (current === 'ops') return ops();
    if (current === 'security') return security();
    if (current === 'runbook') return runbook();
    if (current === 'characters') return characters();
    if (current === 'settings') return settings();
    if (current === 'mutations') return mutations();
  } catch (e) {
    view.innerHTML = `<div class="card"><h2>Access Required</h2><p class="dangerText">${esc(e.message)}</p><p class="muted">Enter the admin token in the header. Data APIs require <code>X-Admin-Token</code>.</p></div>`;
  }
}
async function overview(){
  const state = await api('/api/server/state');
  view.innerHTML = `<div class="card"><h2>Farm State</h2>${table(state.farmState)}</div><div class="card"><h2>Partitions</h2>${table(state.partitions)}</div><div class="card"><h2>Active Servers</h2>${table(state.activeServers)}</div>`;
}
async function ops(){
  const health = await api('/api/ops/health');
  const opt = await api('/api/ops/optimization');
  view.innerHTML = `<div class="card"><h2>Health Verdict</h2>${checks(health.verdicts)}</div><div class="card"><h2>Player Counts</h2><pre>${esc(JSON.stringify(health.playerCounts, null, 2))}</pre></div><div class="card"><h2>Farm State</h2>${table(health.farmState)}</div><div class="card"><h2>Partitions</h2>${table(health.partitions)}</div>${signalList(opt)}`;
}
async function security(){
  const audit = await api('/api/ops/security');
  const events = await api('/api/ops/audit');
  view.innerHTML = `<div class="card"><h2>Security Checks</h2>${checks(audit.checks)}</div><div class="card"><h2>Recent Audit Events</h2>${table(events.events)}</div><div class="card"><h2>Notes</h2><ul>${audit.notes.map(n=>`<li>${esc(n)}</li>`).join('')}</ul></div><div class="card"><h2>Editable Env Keys</h2><pre>${esc(JSON.stringify(audit.safeEnvKeys, null, 2))}</pre></div><div class="card"><h2>Editable Config Files</h2><pre>${esc(JSON.stringify(audit.allowedConfigFiles, null, 2))}</pre></div>`;
}
async function runbook(){
  const data = await api('/api/ops/runbook');
  view.innerHTML = `<div class="card"><h2>Operational Runbook</h2><p class="muted">${esc(data.why)}</p>${table(data.commands)}</div>`;
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
  const p = d.player || {};
  const firstCurrency = (d.currency && d.currency[0]) || {};
  const firstTrack = (d.specialization && d.specialization[0]) || {};
  document.getElementById('detail').innerHTML = `<div class="card"><h2>${esc(p.character_name || 'Character')}</h2><div class="grid"><div><b>Account</b><br>${esc(p.account_id)}</div><div><b>Controller</b><br>${esc(p.player_controller_id)}</div><div><b>Pawn</b><br>${esc(p.player_pawn_id)}</div><div><b>Status</b><br>${esc(p.online_status)}</div></div></div><div class="card"><h2>Quick Admin</h2><p class="dangerText">Back up first. Mutations require server-side enablement.</p><div class="grid"><label>Currency ID<input id="detailCurId" value="${esc(firstCurrency.currency_id ?? 1)}"></label><label>Amount<input id="detailCurAmount" value="1000"></label><label>Mode<select id="detailCurMode"><option>add</option><option>set</option></select></label></div><p><button class="primary" onclick="currencyFor('${esc(p.player_controller_id)}')">Apply currency</button></p><div class="grid"><label>Track type<input id="detailTrack" value="${esc(firstTrack.track_type ?? '')}"></label><label>XP amount<input id="detailXpAmount" value="1000"></label><label>Mode<select id="detailXpMode"><option>add</option><option>set</option></select></label></div><p><button class="primary" onclick="xpFor('${esc(p.player_controller_id)}')">Apply XP</button></p></div><div class="card"><h2>Inventory Items</h2>${table(d.inventoryItems)}</div><div class="card"><h2>Raw Detail</h2><pre>${esc(JSON.stringify(d, null, 2))}</pre></div>`;
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
  const ref = await api('/api/admin/reference');
  view.innerHTML = `<div class="card"><h2>Backups</h2><p>Creates a Postgres custom-format dump under <code>backups/admin-panel</code>.</p><button class="primary" onclick="backup()">Create DB backup</button><pre id="backupResult"></pre></div><div class="card"><h2>Currency and XP</h2><p class="dangerText">Writes require <code>DUNE_ADMIN_MUTATIONS_ENABLED=true</code> and a valid admin token. Back up first.</p><div class="grid"><label>Player controller ID<input id="pcid"></label><label>Currency ID<select id="curid">${options(ref.currencyIds, 'currency_id', '1')}</select></label><label>Amount<input id="amount" value="1000"></label><label>Mode<select id="mode"><option>add</option><option>set</option></select></label></div><p><button class="primary" onclick="currency()">Apply currency</button></p><div class="grid"><label>Player/controller ID<input id="xpid"></label><label>Track type<select id="track">${options(ref.specializationTrackTypes, 'track_type')}</select></label><label>XP amount<input id="xpamount" value="1000"></label><label>Level for set/new track<input id="xplevel" value="0"></label><label>Mode<select id="xpmode"><option>add</option><option>set</option></select></label></div><p><button class="primary" onclick="xp()">Apply XP</button></p></div><div class="card"><h2>Specialization Keystones</h2><div class="grid"><label>Player/controller ID<input id="keyPlayer"></label><label>Keystone<select id="keystone">${options(ref.keystones, 'name')}</select></label></div><p><button class="primary" onclick="purchaseKeystone()">Purchase keystone</button> <button class="danger" onclick="resetKeystones()">Reset all keystones</button></p><pre id="keystoneResult"></pre></div><div class="card"><h2>Experimental Item Grant</h2><p class="dangerText">Use exact server template IDs. Public databases such as <a href="${esc(ref.publicItemDatabase)}" target="_blank" rel="noreferrer">gaming.tools</a> expose useful item slugs, but verify against observed server data before bulk grants.</p><div class="grid"><label>Known inventory<select id="grantInventorySelect" onchange="grantInventory.value=this.value">${inventoryOptions(ref.recentInventories)}</select></label><label>Inventory ID<input id="grantInventory"></label><label>Template ID<input id="grantTemplate" placeholder="smg_unique_largemag_06"></label><label>Stack size<input id="grantStack" value="1"></label><label>Quality level<input id="grantQuality" value="0"></label><label>Position index<input id="grantPosition" placeholder="auto"></label></div><label>Stats JSON<textarea id="grantStats">{}</textarea></label><p><button class="danger" onclick="grantItem()">Grant item</button></p><pre id="grantResult"></pre></div><div class="card"><h2>Observed Item Templates</h2><p class="muted">Read-only reference from this server's current <code>dune.items</code> rows.</p>${table(ref.observedItemTemplates)}</div><div class="card"><h2>Recent Inventories</h2>${table(ref.recentInventories)}</div><div class="card"><h2>Recipe Unlocks</h2><p class="muted">Not implemented yet. The DB exposes removal helpers and actor JSON recipe arrays, but no safe grant function has been mapped.</p><button class="danger" onclick="unsupported()">Test unsupported endpoint</button></div>`;
  const invSelect = document.getElementById('grantInventorySelect');
  if (invSelect && invSelect.value) document.getElementById('grantInventory').value = invSelect.value;
}
async function currency(){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:pcid.value,currency_id:curid.value,amount:amount.value,mode:mode.value})});
  alert('Currency updated');
}
async function currencyFor(playerControllerId){
  await api('/api/admin/currency', {method:'POST', body:JSON.stringify({player_controller_id:playerControllerId,currency_id:detailCurId.value,amount:detailCurAmount.value,mode:detailCurMode.value})});
  alert('Currency updated');
}
async function xp(){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:xpid.value,track_type:track.value,amount:xpamount.value,level:xplevel.value,mode:xpmode.value})});
  alert('XP updated');
}
async function xpFor(playerId){
  await api('/api/admin/xp', {method:'POST', body:JSON.stringify({player_id:playerId,track_type:detailTrack.value,amount:detailXpAmount.value,mode:detailXpMode.value})});
  alert('XP updated');
}
async function backup(){
  const result = await api('/api/admin/backup', {method:'POST', body:'{}'});
  document.getElementById('backupResult').textContent = JSON.stringify(result, null, 2);
}
async function purchaseKeystone(){
  const result = await api('/api/admin/keystone', {method:'POST', body:JSON.stringify({player_id:keyPlayer.value,keystone:keystone.value})});
  document.getElementById('keystoneResult').textContent = JSON.stringify(result, null, 2);
}
async function resetKeystones(){
  if (!confirm('Reset all purchased keystones for this player?')) return;
  const result = await api('/api/admin/reset-keystones', {method:'POST', body:JSON.stringify({player_id:keyPlayer.value})});
  document.getElementById('keystoneResult').textContent = JSON.stringify(result, null, 2);
}
async function grantItem(){
  const result = await api('/api/admin/item', {method:'POST', body:JSON.stringify({inventory_id:grantInventory.value,template_id:grantTemplate.value,stack_size:grantStack.value,quality_level:grantQuality.value,position_index:grantPosition.value,stats:grantStats.value})});
  document.getElementById('grantResult').textContent = JSON.stringify(result, null, 2);
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
