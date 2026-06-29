"""
╔══════════════════════════════════════════════════════════════╗
║          GRIM VPS MANAGER  —  CORE.PY                       ║
║   Database · Helpers · LXC Engine · Embed System            ║
╚══════════════════════════════════════════════════════════════╝
"""

# ─── Auto library installer ───────────────────────────────────
import sys, subprocess, importlib

REQUIRED = [
    ("discord", "discord.py==2.3.2"),
    ("aiohttp", "aiohttp"),
    ("requests", "requests"),
    ("psutil", "psutil"),
]

def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])

for mod, pip_pkg in REQUIRED:
    try:
        importlib.import_module(mod)
    except ImportError:
        print(f"[GrimVPS] Installing {pip_pkg}...")
        _install(pip_pkg)

# ─── Imports ─────────────────────────────────────────────────
import json, os, asyncio, shlex, logging, shutil, sqlite3, random, time
from datetime import datetime
from typing import Optional, List, Dict, Any
import threading
import discord
import requests

# ─── Load config ─────────────────────────────────────────────
_CFG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(_CFG_PATH, "r") as _f:
    CFG = json.load(_f)

# Shortcuts
BOT_CFG   = CFG["bot"]
IDS       = CFG["ids"]
DEV_INFO  = CFG["developer_info"]
EM        = CFG["emojis"]
COLORS    = CFG["colors"]
OS_OPTIONS = CFG["os_options"]

DISCORD_TOKEN        = BOT_CFG["token"]
BOT_NAME             = BOT_CFG["name"]
BOT_VERSION          = BOT_CFG["version"]
PREFIX               = BOT_CFG["prefix"]
YOUR_SERVER_IP       = BOT_CFG["server_ip"]
DEFAULT_STORAGE_POOL = BOT_CFG["default_storage_pool"]
THUMBNAIL            = CFG.get("thumbnail_url", "")

OWNER_ID       = int(IDS["owner_id"])
DEVELOPER_ID   = int(IDS["developer_id"])
MAIN_ADMIN_ID  = int(IDS["main_admin_id"])
VPS_USER_ROLE_ID = int(IDS["vps_user_role_id"])

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log"), logging.StreamHandler()],
)
logger = logging.getLogger("grimvps")

# ════════════════════════════════════════════════════════
#  DATABASE
# ════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect("vps.db")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur  = conn.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY
    )""")
    cur.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (str(MAIN_ADMIN_ID),))

    cur.execute("""CREATE TABLE IF NOT EXISTS nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        location TEXT,
        total_vps INTEGER,
        tags TEXT DEFAULT '[]',
        api_key TEXT,
        url TEXT,
        is_local INTEGER DEFAULT 0
    )""")
    cur.execute("SELECT COUNT(*) FROM nodes WHERE is_local = 1")
    if cur.fetchone()[0] == 0:
        cur.execute("""INSERT INTO nodes
            (name, location, total_vps, tags, api_key, url, is_local)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("Local Node", "Local", 100, "[]", None, None, 1))

    cur.execute("""CREATE TABLE IF NOT EXISTS vps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        node_id INTEGER NOT NULL DEFAULT 1,
        container_name TEXT UNIQUE NOT NULL,
        ram TEXT NOT NULL,
        cpu TEXT NOT NULL,
        storage TEXT NOT NULL,
        config TEXT NOT NULL,
        os_version TEXT DEFAULT 'ubuntu:22.04',
        status TEXT DEFAULT 'stopped',
        suspended INTEGER DEFAULT 0,
        whitelisted INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        shared_with TEXT DEFAULT '[]',
        suspension_history TEXT DEFAULT '[]'
    )""")

    # Migrations
    cur.execute("PRAGMA table_info(vps)")
    cols = [c[1] for c in cur.fetchall()]
    if "os_version" not in cols:
        cur.execute("ALTER TABLE vps ADD COLUMN os_version TEXT DEFAULT 'ubuntu:22.04'")
    if "node_id" not in cols:
        cur.execute("ALTER TABLE vps ADD COLUMN node_id INTEGER DEFAULT 1")

    cur.execute("""CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""")
    for k, v in [("cpu_threshold", "90"), ("ram_threshold", "90"), ("prefix", PREFIX)]:
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

    cur.execute("""CREATE TABLE IF NOT EXISTS port_allocations (
        user_id TEXT PRIMARY KEY,
        allocated_ports INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS port_forwards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        vps_container TEXT NOT NULL,
        vps_port INTEGER NOT NULL,
        host_port INTEGER NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS coins (
        user_id TEXT PRIMARY KEY,
        balance INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        ram INTEGER NOT NULL,
        cpu INTEGER NOT NULL,
        disk INTEGER NOT NULL,
        price INTEGER NOT NULL,
        description TEXT DEFAULT ''
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inviter_id TEXT NOT NULL,
        invitee_id TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS invite_points (
        user_id TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS free_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        ram INTEGER NOT NULL,
        cpu INTEGER NOT NULL,
        disk INTEGER NOT NULL,
        boost_multiplier REAL DEFAULT 1.0,
        invite_required INTEGER DEFAULT 0,
        plan_type TEXT DEFAULT 'normal'
    )""")
    cur.execute("PRAGMA table_info(free_plans)")
    fp_cols = [c[1] for c in cur.fetchall()]
    if "plan_type" not in fp_cols:
        cur.execute("ALTER TABLE free_plans ADD COLUMN plan_type TEXT DEFAULT 'normal'")

    cur.execute("""CREATE TABLE IF NOT EXISTS boosts (
        user_id TEXT PRIMARY KEY,
        boosted_at TEXT,
        active INTEGER DEFAULT 0
    )""")
    conn.commit()
    conn.close()

# ─── Settings helpers ─────────────────────────────────────────
def get_setting(key: str, default: Any = None):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone(); conn.close()
    return row[0] if row else default

def set_setting(key: str, value: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit(); conn.close()

# ─── Coin helpers ─────────────────────────────────────────────
def get_coins(user_id: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT balance FROM coins WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone(); conn.close()
    return row["balance"] if row else 0

def add_coins(user_id: str, amount: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO coins (user_id, balance) VALUES (?, 0)", (str(user_id),))
    cur.execute("UPDATE coins SET balance = balance + ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit(); conn.close()

def remove_coins(user_id: str, amount: int) -> bool:
    if get_coins(user_id) < amount: return False
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE coins SET balance = balance - ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit(); conn.close(); return True

def set_coins(user_id: str, amount: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO coins (user_id, balance) VALUES (?, ?)", (str(user_id), amount))
    conn.commit(); conn.close()

# ─── Plan helpers ─────────────────────────────────────────────
def get_plans() -> List[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM plans ORDER BY price ASC")
    rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

def get_plan_by_name(name: str) -> Optional[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM plans WHERE name = ?", (name,))
    row = cur.fetchone(); conn.close()
    return dict(row) if row else None

def get_free_plans() -> List[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM free_plans ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]; conn.close(); return rows

def get_free_plan_by_name(name: str) -> Optional[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM free_plans WHERE name = ?", (name,))
    row = cur.fetchone(); conn.close()
    return dict(row) if row else None

# ─── Invite helpers ───────────────────────────────────────────
def get_invite_count(user_id: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM invites WHERE inviter_id = ?", (str(user_id),))
    row = cur.fetchone(); conn.close()
    return row["cnt"] if row else 0

def record_invite(inviter_id: str, invitee_id: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT INTO invites (inviter_id, invitee_id, created_at) VALUES (?, ?, ?)",
                (str(inviter_id), str(invitee_id), datetime.now().isoformat()))
    conn.commit(); conn.close()

def get_invite_points(user_id: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT points FROM invite_points WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone(); conn.close()
    return row["points"] if row else 0

def add_invite_points(user_id: str, amount: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO invite_points (user_id, points) VALUES (?, 0)", (str(user_id),))
    cur.execute("UPDATE invite_points SET points = points + ? WHERE user_id = ?", (amount, str(user_id)))
    conn.commit(); conn.close()

def get_total_invites(user_id: str) -> int:
    return get_invite_count(user_id) + get_invite_points(user_id)

# ─── Boost helpers ────────────────────────────────────────────
def is_boosting(user_id: str) -> bool:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT active FROM boosts WHERE user_id = ?", (str(user_id),))
    row = cur.fetchone(); conn.close()
    return bool(row and row["active"])

def set_boost(user_id: str, active: bool):
    conn = get_db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO boosts (user_id, boosted_at, active) VALUES (?, ?, ?)",
                (str(user_id), datetime.now().isoformat(), 1 if active else 0))
    conn.commit(); conn.close()

# ─── Node helpers ─────────────────────────────────────────────
def get_nodes() -> List[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM nodes")
    rows = cur.fetchall(); conn.close()
    nodes = [dict(r) for r in rows]
    for n in nodes: n["tags"] = json.loads(n["tags"])
    return nodes

def get_node(node_id: int) -> Optional[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    row = cur.fetchone(); conn.close()
    if row:
        n = dict(row); n["tags"] = json.loads(n["tags"]); return n
    return None

def get_current_vps_count(node_id: int) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM vps WHERE node_id = ?", (node_id,))
    count = cur.fetchone()[0]; conn.close(); return count

def find_node_id_for_container(container_name: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT node_id FROM vps WHERE container_name = ?", (container_name,))
    row = cur.fetchone(); conn.close()
    return row[0] if row else 1

# ─── VPS helpers ─────────────────────────────────────────────
def get_vps_data() -> Dict[str, List[Dict[str, Any]]]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM vps"); rows = cur.fetchall(); conn.close()
    data: Dict[str, List[Dict]] = {}
    for row in rows:
        uid = row["user_id"]
        if uid not in data: data[uid] = []
        vps = dict(row)
        vps["shared_with"] = json.loads(vps["shared_with"])
        vps["suspension_history"] = json.loads(vps["suspension_history"])
        vps["suspended"]    = bool(vps["suspended"])
        vps["whitelisted"]  = bool(vps["whitelisted"])
        vps["os_version"]   = vps.get("os_version", "ubuntu:22.04")
        data[uid].append(vps)
    return data

def save_vps_data():
    """Persist in-memory vps_data back to DB"""
    conn = get_db(); cur = conn.cursor()
    for uid, vps_list in vps_data.items():
        for vps in vps_list:
            shared_json  = json.dumps(vps["shared_with"])
            history_json = json.dumps(vps["suspension_history"])
            sus_int  = 1 if vps["suspended"] else 0
            wl_int   = 1 if vps.get("whitelisted", False) else 0
            os_ver   = vps.get("os_version", "ubuntu:22.04")
            created  = vps.get("created_at", datetime.now().isoformat())
            node_id  = vps.get("node_id", 1)
            if "id" not in vps or vps["id"] is None:
                cur.execute("""INSERT OR IGNORE INTO vps
                    (user_id, node_id, container_name, ram, cpu, storage, config,
                     os_version, status, suspended, whitelisted, created_at, shared_with, suspension_history)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (uid, node_id, vps["container_name"], vps["ram"], vps["cpu"],
                     vps["storage"], vps["config"], os_ver, vps["status"],
                     sus_int, wl_int, created, shared_json, history_json))
                vps["id"] = cur.lastrowid
            else:
                cur.execute("""UPDATE vps SET user_id=?, node_id=?, container_name=?, ram=?, cpu=?,
                    storage=?, config=?, os_version=?, status=?, suspended=?, whitelisted=?,
                    shared_with=?, suspension_history=? WHERE id=?""",
                    (uid, node_id, vps["container_name"], vps["ram"], vps["cpu"],
                     vps["storage"], vps["config"], os_ver, vps["status"],
                     sus_int, wl_int, shared_json, history_json, vps["id"]))
    conn.commit(); conn.close()

def get_admins() -> List[str]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM admins")
    rows = cur.fetchall(); conn.close()
    return [r["user_id"] for r in rows]

def save_admin_data():
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM admins")
    for aid in admin_data["admins"]:
        cur.execute("INSERT INTO admins (user_id) VALUES (?)", (aid,))
    conn.commit(); conn.close()

# ─── Port helpers ─────────────────────────────────────────────
def get_user_allocation(user_id: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT allocated_ports FROM port_allocations WHERE user_id = ?", (user_id,))
    row = cur.fetchone(); conn.close()
    return row[0] if row else 0

def get_user_used_ports(user_id: str) -> int:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM port_forwards WHERE user_id = ?", (user_id,))
    row = cur.fetchone(); conn.close()
    return row[0]

def allocate_ports(user_id: str, amount: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""INSERT OR REPLACE INTO port_allocations (user_id, allocated_ports)
        VALUES (?, COALESCE((SELECT allocated_ports FROM port_allocations WHERE user_id = ?), 0) + ?)""",
        (user_id, user_id, amount))
    conn.commit(); conn.close()

def deallocate_ports(user_id: str, amount: int):
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE port_allocations SET allocated_ports = MAX(0, allocated_ports - ?) WHERE user_id = ?",
                (amount, user_id))
    conn.commit(); conn.close()

def get_available_host_port(node_id: int) -> Optional[int]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT host_port FROM port_forwards WHERE vps_container IN (SELECT container_name FROM vps WHERE node_id = ?)", (node_id,))
    used = {r[0] for r in cur.fetchall()}; conn.close()
    for _ in range(200):
        p = random.randint(20000, 50000)
        if p not in used: return p
    return None

def get_user_forwards(user_id: str) -> List[Dict]:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM port_forwards WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall(); conn.close()
    return [dict(r) for r in rows]

# ════════════════════════════════════════════════════════
#  EMBED SYSTEM  (Golden Premium Theme)
# ════════════════════════════════════════════════════════

GOLD      = COLORS["gold"]       # 0x2A2A2A -> #FFD700 equivalent in decimal
C_GOLD    = 0xFFD700
C_SUCCESS = 0x00C851
C_ERROR   = 0xFF1744
C_INFO    = 0xFFAB00
C_WARN    = 0xFF6D00
C_DARK    = 0x1C1C1E

def _trunc(text: str, n: int) -> str:
    if not text: return text
    return text if len(text) <= n else text[: n - 3] + "..."

def _bar(pct: float, width: int = 12) -> str:
    filled = int(pct / 100 * width)
    return "▰" * filled + "▱" * (width - filled)

def make_embed(title: str, description: str = "", color: int = C_GOLD) -> discord.Embed:
    em = discord.Embed(
        title=_trunc(f"{EM['crown']} {BOT_NAME} ⟶ {title}", 256),
        description=_trunc(description, 4096),
        color=color,
    )
    em.set_thumbnail(url=THUMBNAIL)
    em.set_footer(
        text=f"{BOT_NAME} v{BOT_VERSION} • {datetime.now().strftime('%d %b %Y %H:%M')}",
        icon_url=THUMBNAIL,
    )
    return em

def success_embed(title: str, desc: str = "") -> discord.Embed:
    return make_embed(f"{EM['check']} {title}", desc, C_SUCCESS)

def error_embed(title: str, desc: str = "") -> discord.Embed:
    return make_embed(f"{EM['cross']} {title}", desc, C_ERROR)

def info_embed(title: str, desc: str = "") -> discord.Embed:
    return make_embed(f"{EM['bolt']} {title}", desc, C_INFO)

def warn_embed(title: str, desc: str = "") -> discord.Embed:
    return make_embed(f"{EM['warning']} {title}", desc, C_WARN)

def field(embed: discord.Embed, name: str, value: str, inline: bool = False) -> discord.Embed:
    embed.add_field(
        name=_trunc(f"◈ {name}", 256),
        value=_trunc(value, 1024),
        inline=inline,
    )
    return embed

# ════════════════════════════════════════════════════════
#  LXC ENGINE
# ════════════════════════════════════════════════════════

async def execute_lxc(container_name: str, command: str, timeout: int = 120,
                       node_id: Optional[int] = None) -> Any:
    if node_id is None:
        node_id = find_node_id_for_container(container_name)
    node = get_node(node_id)
    if not node:
        raise Exception(f"Node {node_id} not found")

    full_cmd = f"lxc {command}"

    if node["is_local"]:
        # ── LOCAL ─────────────────────────────────────────
        # Use /snap/bin/lxc if snap lxc is installed but bare 'lxc' maps to it
        # We bypass the snap confine issue by calling lxc via sudo if needed
        lxc_bin = _find_lxc_binary()
        parts = shlex.split(f"{lxc_bin} {command}")
        try:
            proc = await asyncio.create_subprocess_exec(
                *parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill(); await proc.wait()
                raise asyncio.TimeoutError(f"LXC command timed out after {timeout}s: {full_cmd}")

            if proc.returncode != 0:
                err = stderr.decode().strip() if stderr else "No error output"
                raise Exception(f"LXC failed:\n```\n{err}\n```\n`cmd: {lxc_bin} {command}`")
            return stdout.decode().strip() if stdout else True
        except asyncio.TimeoutError:
            raise
        except Exception:
            raise
    else:
        # ── REMOTE ────────────────────────────────────────
        url = f"{node['url']}/api/execute"
        try:
            resp = requests.post(url, json={"command": full_cmd},
                                 params={"api_key": node["api_key"]}, timeout=timeout)
            resp.raise_for_status()
            res = resp.json()
            if res.get("returncode", 1) != 0:
                raise Exception(f"Remote LXC on {node['name']}: {res.get('stderr','failed')}")
            return res.get("stdout", True)
        except requests.exceptions.RequestException as e:
            raise Exception(f"Remote node {node['name']} unreachable: {e}")

def _find_lxc_binary() -> str:
    """
    Returns the best LXC binary path that avoids the snap-confine cap_fowner error.
    Priority:
      1. /snap/bin/lxc run via sudo (works when bot runs as non-root in privileged env)
      2. /usr/bin/lxc  (apt package — no snap issues)
      3. lxd.lxc       (LXD snap companion tool)
      4. fallback: lxc (whatever is in PATH)
    """
    import shutil as _shutil
    candidates = [
        "/usr/bin/lxc",        # apt-installed, no snap-confine
        "/usr/local/bin/lxc",  # compiled from source
        "lxc",                 # PATH fallback
    ]
    for c in candidates:
        if _shutil.which(c) or (c.startswith("/") and os.path.isfile(c)):
            # Quick test: does 'lxc version' work without snap error?
            try:
                result = subprocess.run([c, "version"], capture_output=True, text=True, timeout=5)
                if "snap-confine" not in result.stderr and result.returncode == 0:
                    return c
            except Exception:
                continue
    # Last resort: try with sudo prefix embedded in every command via subprocess shell
    return "lxc"

async def apply_lxc_config(container_name: str, node_id: int):
    """Apply Docker-ready LXC config to a container."""
    try:
        cmds = [
            f"config set {container_name} security.nesting true",
            f"config set {container_name} security.privileged true",
            f"config set {container_name} security.syscalls.intercept.mknod true",
            f"config set {container_name} security.syscalls.intercept.setxattr true",
            f"config set {container_name} linux.kernel_modules overlay,loop,nf_nat,ip_tables,ip6_tables,netlink_diag,br_netfilter",
        ]
        for cmd in cmds:
            await execute_lxc(container_name, cmd, node_id=node_id)
        try:
            await execute_lxc(container_name,
                f"config device add {container_name} fuse unix-char path=/dev/fuse",
                node_id=node_id)
        except Exception:
            pass

        raw_cfg = (
            "lxc.apparmor.profile = unconfined\n"
            "lxc.apparmor.allow_nesting = 1\n"
            "lxc.apparmor.allow_incomplete = 1\n"
            "lxc.cap.drop =\n"
            "lxc.cgroup.devices.allow = a\n"
            "lxc.cgroup2.devices.allow = a\n"
            "lxc.mount.auto = proc:rw sys:rw cgroup:rw shmounts:rw\n"
            "lxc.mount.entry = /dev/fuse dev/fuse none bind,create=file 0 0\n"
        )
        await execute_lxc(container_name,
            f"config set {container_name} raw.lxc '{raw_cfg}'",
            node_id=node_id)
        logger.info(f"LXC config applied to {container_name}")
    except Exception as e:
        logger.error(f"apply_lxc_config failed for {container_name}: {e}")

async def apply_internal_permissions(container_name: str, node_id: int):
    """Apply sysctl settings inside container after start."""
    try:
        await asyncio.sleep(3)
        cmds = [
            "mkdir -p /etc/sysctl.d/",
            "echo 'net.ipv4.ip_unprivileged_port_start=0' > /etc/sysctl.d/99-custom.conf",
            "echo 'net.ipv4.ping_group_range=0 2147483647' >> /etc/sysctl.d/99-custom.conf",
            "echo 'fs.inotify.max_user_watches=524288' >> /etc/sysctl.d/99-custom.conf",
            "echo 'kernel.unprivileged_userns_clone=1' >> /etc/sysctl.d/99-custom.conf",
            "sysctl -p /etc/sysctl.d/99-custom.conf 2>/dev/null || true",
        ]
        for cmd in cmds:
            try:
                await execute_lxc(container_name,
                    f"exec {container_name} -- bash -c {shlex.quote(cmd)}",
                    node_id=node_id)
            except Exception as e:
                logger.warning(f"Internal perm cmd failed in {container_name}: {e}")
    except Exception as e:
        logger.error(f"apply_internal_permissions failed: {e}")

# ════════════════════════════════════════════════════════
#  CONTAINER STATS  (Fixed — robust parsing)
# ════════════════════════════════════════════════════════

async def get_container_status_local(name: str) -> str:
    try:
        lxc = _find_lxc_binary()
        proc = await asyncio.create_subprocess_exec(
            lxc, "info", name,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        for line in out.decode().splitlines():
            if line.strip().startswith("Status:"):
                return line.split(":", 1)[1].strip().lower()
        return "unknown"
    except Exception:
        return "unknown"

async def get_container_cpu_pct_local(name: str) -> float:
    try:
        proc = await asyncio.create_subprocess_exec(
            _find_lxc_binary(), "exec", name, "--", "cat", "/proc/stat",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        lines = out.decode().splitlines()
        for line in lines:
            if line.startswith("cpu "):
                parts = list(map(int, line.split()[1:]))
                total = sum(parts)
                idle  = parts[3] + (parts[4] if len(parts) > 4 else 0)
                if total == 0: return 0.0
                return round((1 - idle / total) * 100, 1)
        return 0.0
    except Exception:
        return 0.0

async def get_container_ram_local(name: str) -> Dict:
    empty = {"used": 0, "total": 0, "pct": 0.0}
    try:
        proc = await asyncio.create_subprocess_exec(
            _find_lxc_binary(), "exec", name, "--", "cat", "/proc/meminfo",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        info: Dict[str, int] = {}
        for line in out.decode().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                info[parts[0].rstrip(":")] = int(parts[1])
        total = info.get("MemTotal", 0) // 1024
        avail = info.get("MemAvailable", info.get("MemFree", 0)) // 1024
        used  = total - avail
        pct   = round(used / total * 100, 1) if total > 0 else 0.0
        return {"used": used, "total": total, "pct": pct}
    except Exception:
        return empty

async def get_container_disk_local(name: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            _find_lxc_binary(), "exec", name, "--", "df", "-h", "/",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        lines = out.decode().strip().splitlines()
        if len(lines) >= 2:
            p = lines[1].split()
            return f"{p[2]}/{p[1]} ({p[4]})"
        return "Unknown"
    except Exception:
        return "Unknown"

async def get_container_uptime_local(name: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            _find_lxc_binary(), "exec", name, "--", "cat", "/proc/uptime",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        secs = float(out.decode().split()[0])
        h = int(secs // 3600); m = int((secs % 3600) // 60); s = int(secs % 60)
        return f"{h}h {m}m {s}s"
    except Exception:
        return "Unknown"

async def get_container_stats(container_name: str, node_id: Optional[int] = None) -> Dict:
    if node_id is None:
        node_id = find_node_id_for_container(container_name)
    node = get_node(node_id)
    if node and node["is_local"]:
        status = await get_container_status_local(container_name)
        if status != "running":
            return {"status": status, "cpu": 0.0,
                    "ram": {"used": 0, "total": 0, "pct": 0.0},
                    "disk": "N/A", "uptime": "N/A"}
        cpu, ram, disk, uptime = await asyncio.gather(
            get_container_cpu_pct_local(container_name),
            get_container_ram_local(container_name),
            get_container_disk_local(container_name),
            get_container_uptime_local(container_name),
        )
        return {"status": status, "cpu": cpu, "ram": ram, "disk": disk, "uptime": uptime}
    else:
        url = f"{node['url']}/api/get_container_stats"
        try:
            resp = requests.post(url, json={"container": container_name},
                                 params={"api_key": node["api_key"]}, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return {"status": "unknown", "cpu": 0.0,
                    "ram": {"used": 0, "total": 0, "pct": 0.0},
                    "disk": "Unknown", "uptime": "Unknown"}

# ════════════════════════════════════════════════════════
#  HOST STATS
# ════════════════════════════════════════════════════════

def get_host_cpu_usage() -> float:
    try:
        with open("/proc/stat") as f:
            line = f.readline()
        parts = list(map(int, line.split()[1:]))
        total = sum(parts); idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        return round((1 - idle / total) * 100, 1) if total else 0.0
    except Exception:
        return 0.0

def get_host_ram_usage() -> float:
    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        if len(lines) > 1:
            m = lines[1].split()
            return round(int(m[2]) / int(m[1]) * 100, 1) if int(m[1]) else 0.0
        return 0.0
    except Exception:
        return 0.0

def get_host_disk_usage() -> str:
    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True)
        lines = result.stdout.splitlines()
        if len(lines) > 1:
            p = lines[1].split()
            return f"{p[2]}/{p[1]} ({p[4]})"
        return "Unknown"
    except Exception:
        return "Unknown"

async def get_host_stats(node_id: int) -> Dict:
    node = get_node(node_id)
    if node and node["is_local"]:
        return {"cpu": get_host_cpu_usage(), "ram": get_host_ram_usage(),
                "disk": get_host_disk_usage()}
    try:
        resp = requests.get(f"{node['url']}/api/get_host_stats",
                            params={"api_key": node["api_key"]}, timeout=10)
        resp.raise_for_status()
        stats = resp.json()
        stats.setdefault("disk", "Unknown")
        return stats
    except Exception:
        return {"cpu": 0.0, "ram": 0.0, "disk": "Unknown"}

async def get_node_status(node_id: int) -> str:
    node = get_node(node_id)
    if not node: return "❓ Unknown"
    if node["is_local"]: return "🟢 Online (Local)"
    try:
        resp = requests.get(f"{node['url']}/api/ping",
                            params={"api_key": node["api_key"]}, timeout=5)
        return "🟢 Online" if resp.status_code == 200 else "🔴 Offline"
    except Exception:
        return "🔴 Offline"

# ════════════════════════════════════════════════════════
#  PORT FORWARDING
# ════════════════════════════════════════════════════════

async def create_port_forward(user_id: str, container: str, vps_port: int,
                               node_id: int) -> Optional[int]:
    host_port = get_available_host_port(node_id)
    if not host_port: return None
    try:
        await execute_lxc(container, f"config device add {container} tcp_proxy_{host_port} proxy "
                          f"listen=tcp:0.0.0.0:{host_port} connect=tcp:127.0.0.1:{vps_port}",
                          node_id=node_id)
        await execute_lxc(container, f"config device add {container} udp_proxy_{host_port} proxy "
                          f"listen=udp:0.0.0.0:{host_port} connect=udp:127.0.0.1:{vps_port}",
                          node_id=node_id)
        conn = get_db(); cur = conn.cursor()
        cur.execute("INSERT INTO port_forwards (user_id, vps_container, vps_port, host_port, created_at) VALUES (?, ?, ?, ?, ?)",
                    (user_id, container, vps_port, host_port, datetime.now().isoformat()))
        conn.commit(); conn.close()
        return host_port
    except Exception as e:
        logger.error(f"Port forward failed: {e}"); return None

async def remove_port_forward(fid: int) -> tuple:
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT user_id, vps_container, host_port FROM port_forwards WHERE id = ?", (fid,))
    row = cur.fetchone()
    if not row: conn.close(); return False, None
    user_id, container, host_port = row
    node_id = find_node_id_for_container(container)
    try:
        await execute_lxc(container, f"config device remove {container} tcp_proxy_{host_port}", node_id=node_id)
        await execute_lxc(container, f"config device remove {container} udp_proxy_{host_port}", node_id=node_id)
        cur.execute("DELETE FROM port_forwards WHERE id = ?", (fid,))
        conn.commit(); conn.close()
        return True, user_id
    except Exception as e:
        logger.error(f"Remove port forward failed: {e}"); conn.close(); return False, None

async def recreate_port_forwards(container_name: str) -> int:
    node_id = find_node_id_for_container(container_name)
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT vps_port, host_port FROM port_forwards WHERE vps_container = ?", (container_name,))
    rows = cur.fetchall(); conn.close()
    count = 0
    for row in rows:
        try:
            await execute_lxc(container_name, f"config device add {container_name} tcp_proxy_{row['host_port']} "
                              f"proxy listen=tcp:0.0.0.0:{row['host_port']} connect=tcp:127.0.0.1:{row['vps_port']}",
                              node_id=node_id)
            await execute_lxc(container_name, f"config device add {container_name} udp_proxy_{row['host_port']} "
                              f"proxy listen=udp:0.0.0.0:{row['host_port']} connect=udp:127.0.0.1:{row['vps_port']}",
                              node_id=node_id)
            count += 1
        except Exception:
            pass
    return count

# ════════════════════════════════════════════════════════
#  VPS ROLE
# ════════════════════════════════════════════════════════

async def get_or_create_vps_role(guild) -> Optional[discord.Role]:
    global VPS_USER_ROLE_ID
    me = guild.me
    if not me or not me.guild_permissions.manage_roles: return None
    role_name = f"{BOT_NAME} VPS User"
    if VPS_USER_ROLE_ID:
        role = guild.get_role(VPS_USER_ROLE_ID)
        if role and role < me.top_role: return role
        VPS_USER_ROLE_ID = 0
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        if role >= me.top_role:
            try: await role.delete(reason="Role above bot")
            except: return None
            role = None
        else:
            VPS_USER_ROLE_ID = role.id; return role
    try:
        role = await guild.create_role(name=role_name, color=discord.Color.gold(),
                                       permissions=discord.Permissions.none())
        await role.edit(position=me.top_role.position - 1)
        VPS_USER_ROLE_ID = role.id; return role
    except Exception as e:
        logger.error(f"VPS role creation failed: {e}"); return None

# ════════════════════════════════════════════════════════
#  ADMIN CHECK DECORATORS
# ════════════════════════════════════════════════════════

def is_admin():
    async def pred(ctx):
        uid = str(ctx.author.id)
        if uid in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)):
            return True
        if uid in admin_data.get("admins", []):
            return True
        raise discord.ext.commands.CheckFailure(
            f"{EM['cross']} You need **Admin** permissions for this command.")
    return discord.ext.commands.check(pred)

def is_main_admin():
    async def pred(ctx):
        uid = str(ctx.author.id)
        if uid in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)):
            return True
        raise discord.ext.commands.CheckFailure(
            f"{EM['cross']} Only the **Main Admin / Owner / Developer** can use this.")
    return discord.ext.commands.check(pred)

# ════════════════════════════════════════════════════════
#  RESOURCE MONITOR (background thread)
# ════════════════════════════════════════════════════════

resource_monitor_active = True

def resource_monitor():
    backup_interval = 3600
    last_backup = time.time()
    while resource_monitor_active:
        try:
            if time.time() - last_backup > backup_interval:
                bk = f"vps_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                try:
                    shutil.copy("vps.db", bk)
                    logger.info(f"DB backup created: {bk}")
                    last_backup = time.time()
                except Exception as e:
                    logger.error(f"Backup failed: {e}")
            time.sleep(60)
        except Exception as e:
            logger.error(f"Monitor error: {e}"); time.sleep(60)

# ════════════════════════════════════════════════════════
#  INIT
# ════════════════════════════════════════════════════════

init_db()
vps_data   = get_vps_data()
admin_data = {"admins": get_admins()}
CPU_THRESHOLD = int(get_setting("cpu_threshold", 90))
RAM_THRESHOLD = int(get_setting("ram_threshold", 90))

_monitor_thread = threading.Thread(target=resource_monitor, daemon=True)
_monitor_thread.start()
