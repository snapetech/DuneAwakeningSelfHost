#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time


ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "backups" / "admin-bot"
STATE_FILE = STATE_DIR / "player-presence.json"
DB = "dune_sb_1_4_0_0"


def read_env_file(path):
    values = {}
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    return values


FILE_ENV = read_env_file(ROOT / os.environ.get("DUNE_ADMIN_BOT_ENV_FILE", ".env"))


def env(name, default=""):
    return os.environ.get(name) or FILE_ENV.get(name) or default


def env_bool(name, default=False):
    return str(env(name, "true" if default else "false")).lower() in ("1", "true", "yes", "on")


def now_iso():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def compose_cmd(*args):
    files = env("COMPOSE_FILES", "compose.yaml").split(":")
    cmd = [env("CONTAINER_RUNTIME", "docker"), "compose"]
    for file in files:
        if file:
            cmd.extend(["-f", file])
    cmd.extend(["--env-file", env("DUNE_ADMIN_BOT_ENV_FILE", ".env")])
    cmd.extend(args)
    return cmd


def run(cmd, timeout=30):
    return subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_FILE)


def online_players():
    sql = """
    select ps.account_id::text, coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name, acc.user as fls_id
    from dune.player_state ps
    left join dune.accounts acc on acc.id = ps.account_id
    where ps.online_status::text = 'Online'
    order by ps.character_name nulls last, ps.account_id;
    """
    result = run(compose_cmd("exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB, "-At", "-F", "\t", "-c", sql), timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")))
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "online player query failed")
    players = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        account_id = parts[0]
        name = parts[1] if len(parts) > 1 else account_id
        fls_id = parts[2] if len(parts) > 2 else ""
        players[account_id] = {
            "name": name or account_id,
            "flsId": fls_id,
        }
    return players


def player_name(player):
    if isinstance(player, dict):
        return player.get("name") or player.get("characterName") or player.get("accountId") or "unknown"
    return str(player)


def player_fls_id(player):
    if isinstance(player, dict):
        return player.get("flsId") or ""
    return ""


def completed_journey_players(story_node_id):
    sql = f"""
    select ps.account_id::text, coalesce(nullif(ps.character_name, ''), ps.account_id::text) as character_name
    from dune.journey_story_node jsn
    join dune.player_state ps on ps.account_id = jsn.account_id
    where jsn.story_node_id = {sql_literal(story_node_id)}
      and jsn.complete_condition_state = 'true'::jsonb
    order by ps.character_name nulls last, ps.account_id;
    """
    result = run(
        compose_cmd(
            "exec", "-T", "postgres", "psql", "-U", "dune", "-d", DB,
            "-At", "-F", "\t", "-c", sql,
        ),
        timeout=int(env("DUNE_PLAYER_PRESENCE_SQL_TIMEOUT_SECONDS", "10")),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "journey completion query failed")
    players = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        account_id, _, name = line.partition("\t")
        players[account_id] = name or account_id
    return players


def announce(message):
    command = env("DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh")))
    if command.startswith("/workspace/"):
        command = str(ROOT / command.removeprefix("/workspace/"))
    timeout = int(env("DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS", env("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45")))
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    child_env["DUNE_ANNOUNCE_MESSAGE"] = message
    child_env["DUNE_ANNOUNCE_JOB_ID"] = "player-presence"
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def private_join_message(player, message):
    fls_id = player_fls_id(player)
    name = player_name(player)
    if not fls_id:
        return {"ok": False, "error": "missing player FLS id", "player": name}
    command = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_COMMAND", env("DUNE_PLAYER_PRESENCE_ANNOUNCE_COMMAND", env("DUNE_ADMIN_ANNOUNCE_COMMAND", str(ROOT / "scripts" / "announce.sh"))))
    if command.startswith("/workspace/"):
        command = str(ROOT / command.removeprefix("/workspace/"))
    timeout = int(env("DUNE_PLAYER_PRESENCE_ANNOUNCE_TIMEOUT_SECONDS", env("DUNE_ADMIN_ANNOUNCEMENT_COMMAND_TIMEOUT_SECONDS", "45")))
    child_env = os.environ.copy()
    child_env.update(FILE_ENV)
    child_env["DUNE_ANNOUNCE_MESSAGE"] = message
    child_env["DUNE_ANNOUNCE_JOB_ID"] = "player-presence-private-welcome"
    child_env["DUNE_ANNOUNCE_WRAP_DASHBOARD_MESSAGES"] = "false"
    child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"] = env("DUNE_PLAYER_PRESENCE_PRIVATE_MESSAGE_CHANNEL", "Private")
    child_env["DUNE_ANNOUNCE_CHAT_USER_NAME_TO"] = name
    child_env["DUNE_ANNOUNCE_CHAT_TARGET_QUEUES"] = f"{fls_id}_queue"
    child_env["DUNE_ANNOUNCE_CHAT_ROUTING_KEYS"] = f"dash.private-welcome.{fls_id}"
    result = subprocess.run([command, message], cwd=ROOT, env=child_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "targetQueue": f"{fls_id}_queue",
        "channel": child_env["DUNE_ANNOUNCE_CHAT_CHANNEL"],
        "userNameTo": name,
        "stdout": result.stdout[-1000:],
        "stderr": result.stderr[-1000:],
    }


def render_template(template, player_name, count):
    return template.format(playername=player_name, player_name=player_name, count=count, player_count=count)


def render_journey_template(template, player_name, story_node_id):
    return template.format(playername=player_name, player_name=player_name, story_node_id=story_node_id)


def check_once():
    state = load_state()
    current = online_players()
    previous = state.get("onlinePlayers")
    current_ids = set(current)
    previous_ids = set(previous or {})
    first_run = previous is None
    joined = sorted(current_ids - previous_ids, key=lambda account_id: player_name(current.get(account_id, account_id)).lower())
    left = sorted(previous_ids - current_ids, key=lambda account_id: player_name(previous.get(account_id, account_id)).lower()) if previous else []
    final_count = len(current)

    results = []
    if env_bool("DUNE_PLAYER_PRESENCE_ANNOUNCE_ENABLED", False) and not first_run:
        join_template = env("DUNE_PLAYER_PRESENCE_JOIN_TEMPLATE", "Welcome {playername}! Current player count is now {count}.")
        leave_template = env("DUNE_PLAYER_PRESENCE_LEAVE_TEMPLATE", "{playername} has left, current count is {count}.")
        for account_id in joined:
            message = render_template(join_template, player_name(current.get(account_id, account_id)), final_count)
            results.append({"event": "join", "accountId": account_id, "message": message, "announce": announce(message)})
        for account_id in left:
            message = render_template(leave_template, player_name(previous.get(account_id, account_id)), final_count)
            results.append({"event": "leave", "accountId": account_id, "message": message, "announce": announce(message)})

    private_welcome_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_ENABLED", False) and not first_run:
        template = env("DUNE_PLAYER_PRESENCE_PRIVATE_WELCOME_TEMPLATE", "Welcome! Please Check https://snape.tech for Server Rules.")
        for account_id in joined:
            player = current.get(account_id, account_id)
            message = render_template(template, player_name(player), final_count)
            private_welcome_results.append({"event": "private-welcome", "accountId": account_id, "message": message, "send": private_join_message(player, message)})

    journey_results = []
    if env_bool("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_ENABLED", False):
        story_node_id = env("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_NODE", "DA_SQ_VermiliusGap.Relocate.RelocateOutsideHBS.Drive north to the Vermilius Gap")
        completed = completed_journey_players(story_node_id)
        journey_state = state.setdefault("announcedJourneyNodes", {})
        previous_completed = set(journey_state.get(story_node_id, []))
        current_completed = set(completed)
        journey_first_run = story_node_id not in journey_state
        newly_completed = sorted(current_completed - previous_completed, key=lambda account_id: completed.get(account_id, account_id).lower())
        if not journey_first_run:
            template = env("DUNE_PLAYER_PRESENCE_VERMILIUS_GAP_TEMPLATE", "Congrats! {playername} has outrun Shai-Hulud!")
            for account_id in newly_completed:
                message = render_journey_template(template, completed.get(account_id, account_id), story_node_id)
                journey_results.append({"event": "vermilius-gap", "accountId": account_id, "message": message, "announce": announce(message)})
        journey_state[story_node_id] = sorted(current_completed)

    state["onlinePlayers"] = current
    state["updatedAt"] = now_iso()
    save_state(state)
    return {
        "ok": True,
        "firstRun": first_run,
        "onlineCount": final_count,
        "joined": [player_name(current[account_id]) for account_id in joined],
        "left": [player_name(previous[account_id]) for account_id in left] if previous else [],
        "announcements": results,
        "privateWelcomeMessages": private_welcome_results,
        "journeyAnnouncements": journey_results,
    }


def main():
    parser = argparse.ArgumentParser(description="Announce Dune player join/leave events through the configured Paul/DASH Admin chat path.")
    parser.add_argument("--once", action="store_true", help="Run one poll and exit.")
    parser.add_argument("--loop", action="store_true", help="Poll forever.")
    args = parser.parse_args()
    if not args.once and not args.loop:
        args.once = True
    while True:
        try:
            print(json.dumps(check_once(), indent=2), flush=True)
        except Exception as exc:
            print(json.dumps({"ok": False, "error": str(exc), "ts": now_iso()}), flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(int(env("DUNE_PLAYER_PRESENCE_POLL_SECONDS", "15")))


if __name__ == "__main__":
    sys.exit(main())
