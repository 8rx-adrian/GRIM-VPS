"""
╔══════════════════════════════════════════════════════════════╗
║          GRIM VPS MANAGER  —  MAIN.PY                       ║
║   All Bot Commands · Events · Auto-library Install           ║
╚══════════════════════════════════════════════════════════════╝
Run:  python main.py
"""

# ─── Auto library installer (runs before anything) ───────────
import sys, subprocess, importlib, os, json, asyncio, shlex, logging
import sqlite3, random, time, shutil, threading
from datetime import datetime
from typing import Optional, List, Dict, Any

REQUIRED = [
    ("discord", "discord.py==2.3.2"),
    ("aiohttp", "aiohttp"),
    ("requests", "requests"),
    ("psutil",  "psutil"),
]
def _install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])

for _mod, _pkg in REQUIRED:
    try:
        importlib.import_module(_mod)
    except ImportError:
        print(f"[GrimVPS] Installing {_pkg}...")
        _install(_pkg)

import discord
from discord.ext import commands
import requests

# ─── Core + Views ────────────────────────────────────────────
from core import (
    CFG, BOT_CFG, IDS, DEV_INFO, EM, COLORS, OS_OPTIONS,
    DISCORD_TOKEN, BOT_NAME, BOT_VERSION, PREFIX,
    YOUR_SERVER_IP, DEFAULT_STORAGE_POOL, THUMBNAIL,
    OWNER_ID, DEVELOPER_ID, MAIN_ADMIN_ID,
    # DB
    get_db, vps_data, admin_data, save_vps_data, save_admin_data,
    get_vps_data, get_admins, get_node, get_nodes,
    get_current_vps_count, find_node_id_for_container,
    get_user_allocation, get_user_used_ports, get_user_forwards,
    allocate_ports, deallocate_ports, get_available_host_port,
    create_port_forward, remove_port_forward, recreate_port_forwards,
    # Coins
    get_coins, add_coins, remove_coins, set_coins,
    # Plans
    get_plans, get_plan_by_name, get_free_plans, get_free_plan_by_name,
    # Invites
    get_invite_count, record_invite, get_invite_points,
    add_invite_points, get_total_invites,
    # Boost
    is_boosting, set_boost,
    # LXC
    execute_lxc, apply_lxc_config, apply_internal_permissions,
    get_container_stats, get_host_cpu_usage, get_host_ram_usage,
    get_host_disk_usage, get_host_stats, get_node_status,
    get_or_create_vps_role,
    # Helpers
    get_setting, set_setting, CPU_THRESHOLD, RAM_THRESHOLD,
    # Embeds
    make_embed, success_embed, error_embed, info_embed, warn_embed,
    field, C_GOLD, C_SUCCESS, C_ERROR, C_INFO, C_DARK, _bar,
    # Checks
    is_admin, is_main_admin,
    logger,
)
from views import (
    ManageView, NodeSelectView, HelpView,
    ReinstallOSSelectView, CMDModal, CMDPanelView,
)

# ════════════════════════════════════════════════════════
#  BOT SETUP
# ════════════════════════════════════════════════════════

def get_prefix(bot_instance, message):
    """Dynamic prefix — reads from DB so it can be changed live."""
    db_prefix = get_setting("prefix", PREFIX)
    return commands.when_mentioned_or(db_prefix)(bot_instance, message)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=get_prefix, intents=intents, help_command=None)
bot_start_time = datetime.now()

# ════════════════════════════════════════════════════════
#  EVENTS
# ════════════════════════════════════════════════════════

@bot.event
async def on_ready():
    logger.info(f"[GrimVPS] Logged in as {bot.user} (ID: {bot.user.id})")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{sum(len(v) for v in vps_data.values())} VPS | {PREFIX}help"))
    print(f"""
╔══════════════════════════════════════════╗
║  {BOT_NAME} v{BOT_VERSION} — ONLINE           ║
║  User : {bot.user}
║  Prefix: {get_setting('prefix', PREFIX)}
║  VPS   : {sum(len(v) for v in vps_data.values())} active
╚══════════════════════════════════════════╝""")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send(embed=error_embed("Access Denied", str(error)), delete_after=8)
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=error_embed("Missing Argument",
            f"Usage: `{PREFIX}{ctx.command.qualified_name} {ctx.command.signature}`"), delete_after=10)
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send(embed=error_embed("Member Not Found", str(error)), delete_after=8)
    elif isinstance(error, commands.BadArgument):
        await ctx.send(embed=error_embed("Bad Argument", str(error)), delete_after=8)
    elif isinstance(error, commands.CommandNotFound):
        pass  # silently ignore
    else:
        logger.error(f"Unhandled error in {ctx.command}: {error}", exc_info=True)

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    # Mention-prefix support
    if message.content.strip() in (f"<@{bot.user.id}>", f"<@!{bot.user.id}>"):
        p = get_setting("prefix", PREFIX)
        e = info_embed(f"{BOT_NAME} is here!", f"My prefix is `{p}` · Use `{p}help` to get started.")
        return await message.channel.send(embed=e)
    await bot.process_commands(message)

# ════════════════════════════════════════════════════════
#  UTILITY COMMANDS
# ════════════════════════════════════════════════════════

@bot.command(name="ping")
async def ping(ctx):
    ms = round(bot.latency * 1000)
    e = success_embed("Pong!", f"{EM['ping']} Latency: **{ms}ms**")
    await ctx.send(embed=e)

@bot.command(name="uptime")
async def uptime_cmd(ctx):
    delta = datetime.now() - bot_start_time
    h, rem = divmod(int(delta.total_seconds()), 3600)
    m, s   = divmod(rem, 60)
    e = info_embed("Uptime", f"{EM['clock']} Bot has been running for **{h}h {m}m {s}s**")
    await ctx.send(embed=e)

@bot.command(name="developer", aliases=["dev"])
async def developer(ctx):
    """Show developer info."""
    e = make_embed(f"{EM['dev']} Developer Info",
                   f"Built by **{DEV_INFO['name']}**", C_GOLD)
    field(e, "👤 Developer",
          f"**Name:** {DEV_INFO['name']}\n"
          f"**Username:** `{DEV_INFO['username']}`\n"
          f"**User ID:** `{DEV_INFO['user_id']}`", True)
    field(e, "🌐 Dev Server",
          f"[{DEV_INFO['server_name']}]({DEV_INFO['server_invite']})", True)
    field(e, "🤖 Bot Info",
          f"**Name:** {BOT_NAME}\n**Version:** v{BOT_VERSION}", True)
    await ctx.send(embed=e)

@bot.command(name="set-prefix")
@is_admin()
async def set_prefix(ctx, new_prefix: str):
    """Change the bot prefix (also works via @mention)."""
    if len(new_prefix) > 5:
        return await ctx.send(embed=error_embed("Too Long", "Prefix must be ≤ 5 characters."))
    set_setting("prefix", new_prefix)
    e = success_embed("Prefix Updated",
        f"New prefix: `{new_prefix}`\nYou can also always use `@{BOT_NAME}` as a prefix.")
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  HELP
# ════════════════════════════════════════════════════════

@bot.command(name="help")
async def help_cmd(ctx):
    view = HelpView(ctx)
    await ctx.send(embed=view.get_initial_embed(), view=view)

# ════════════════════════════════════════════════════════
#  VPS MANAGEMENT
# ════════════════════════════════════════════════════════

@bot.command(name="myvps")
async def my_vps(ctx):
    uid = str(ctx.author.id)
    vlist = vps_data.get(uid, [])
    if not vlist:
        e = error_embed("No VPS", "You don't have any VPS yet. Contact an admin.")
        return await ctx.send(embed=e)
    e = make_embed(f"{EM['vps']} Your VPS", f"{len(vlist)} VPS found", C_GOLD)
    for i, vps in enumerate(vlist, 1):
        status = vps.get("status","?").upper()
        if vps.get("suspended"): status = f"⛔ SUSPENDED"
        elif status == "RUNNING": status = f"{EM['online']} RUNNING"
        else: status = f"{EM['offline']} STOPPED"
        node = get_node(vps["node_id"])
        field(e,
              f"VPS {i} — `{vps['container_name']}`",
              f"**Status** {status}\n"
              f"**Resources** {vps.get('config','N/A')}\n"
              f"**OS** `{vps.get('os_version','?')}`\n"
              f"**Node** {node['name'] if node else 'Unknown'}",
              True)
    field(e, "Management", f"Use `{PREFIX}manage` to control your VPS.")
    await ctx.send(embed=e)

@bot.command(name="manage")
async def manage_vps(ctx, user: discord.Member = None):
    if user:
        uid = str(ctx.author.id)
        if uid not in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)) \
           and uid not in admin_data.get("admins", []):
            return await ctx.send(embed=error_embed("Access Denied", "Only admins can manage other users' VPS."))
        target_id = str(user.id)
        vlist = vps_data.get(target_id, [])
        if not vlist:
            return await ctx.send(embed=error_embed("No VPS", f"{user.mention} has no VPS."))
        view = ManageView(str(ctx.author.id), vlist, is_admin=True, owner_id=target_id)
        emb = await view.get_initial_embed(bot_client=bot)
        return await ctx.send(embed=emb, view=view)

    uid   = str(ctx.author.id)
    vlist = vps_data.get(uid, [])
    if not vlist:
        e = error_embed("No VPS", "You don't have any VPS. Contact an admin.")
        field(e, "Get Started", f"Ask an admin to run `{PREFIX}create` for you.")
        return await ctx.send(embed=e)
    view = ManageView(uid, vlist)
    emb  = await view.get_initial_embed(bot_client=bot)
    await ctx.send(embed=emb, view=view)

@bot.command(name="manage-shared")
async def manage_shared_vps(ctx, owner: discord.Member, vps_number: int):
    uid      = str(ctx.author.id)
    owner_id = str(owner.id)
    if owner_id not in vps_data or vps_number < 1 or vps_number > len(vps_data[owner_id]):
        return await ctx.send(embed=error_embed("Invalid VPS", "Invalid VPS number or owner."))
    vps = vps_data[owner_id][vps_number - 1]
    if uid not in vps.get("shared_with", []):
        return await ctx.send(embed=error_embed("Access Denied", "You don't have access to this VPS."))
    view = ManageView(uid, [vps], is_shared=True, owner_id=owner_id, actual_index=vps_number - 1)
    emb  = await view.get_initial_embed(bot_client=bot)
    await ctx.send(embed=emb, view=view)

@bot.command(name="share-user")
async def share_user(ctx, shared_user: discord.Member, vps_number: int):
    uid = str(ctx.author.id)
    if uid not in vps_data or vps_number < 1 or vps_number > len(vps_data[uid]):
        return await ctx.send(embed=error_embed("Invalid VPS", "Invalid VPS number."))
    vps = vps_data[uid][vps_number - 1]
    vps.setdefault("shared_with", [])
    sid = str(shared_user.id)
    if sid in vps["shared_with"]:
        return await ctx.send(embed=error_embed("Already Shared", f"{shared_user.mention} already has access."))
    vps["shared_with"].append(sid); save_vps_data()
    await ctx.send(embed=success_embed("VPS Shared", f"Shared VPS #{vps_number} with {shared_user.mention}!"))
    try: await shared_user.send(embed=info_embed("VPS Access Granted",
        f"You now have access to VPS #{vps_number} from {ctx.author.mention}.\n"
        f"Use `{PREFIX}manage-shared {ctx.author.mention} {vps_number}` to manage it."))
    except discord.Forbidden: pass

@bot.command(name="share-ruser")
async def revoke_share(ctx, shared_user: discord.Member, vps_number: int):
    uid = str(ctx.author.id)
    if uid not in vps_data or vps_number < 1 or vps_number > len(vps_data[uid]):
        return await ctx.send(embed=error_embed("Invalid VPS", "Invalid VPS number."))
    vps = vps_data[uid][vps_number - 1]
    sid = str(shared_user.id)
    if sid not in vps.get("shared_with", []):
        return await ctx.send(embed=error_embed("Not Shared", f"{shared_user.mention} doesn't have access."))
    vps["shared_with"].remove(sid); save_vps_data()
    await ctx.send(embed=success_embed("Access Revoked", f"Revoked {shared_user.mention}'s access to VPS #{vps_number}."))
    try: await shared_user.send(embed=warn_embed("VPS Access Revoked",
        f"Your access to VPS #{vps_number} by {ctx.author.mention} has been removed."))
    except discord.Forbidden: pass

@bot.command(name="vpsinfo")
async def vps_info_cmd(ctx, container_name: str = None):
    uid   = str(ctx.author.id)
    vlist = vps_data.get(uid, [])
    if not vlist:
        return await ctx.send(embed=error_embed("No VPS", "You have no VPS."))
    if container_name:
        vps = next((v for v in vlist if v["container_name"] == container_name), None)
        if not vps:
            return await ctx.send(embed=error_embed("Not Found", f"No VPS named `{container_name}`."))
    else:
        vps = vlist[0]
    node   = get_node(vps["node_id"])
    stats  = await get_container_stats(vps["container_name"])
    ram_d  = stats["ram"]
    e = make_embed(f"{EM['vps']} VPS Info — {vps['container_name']}", "", C_GOLD)
    field(e, "Container",  f"`{vps['container_name']}`", True)
    field(e, "Node",       node["name"] if node else "Unknown", True)
    field(e, "OS",         vps.get("os_version","?"), True)
    field(e, "Status",     stats["status"].upper(), True)
    field(e, "Config",     vps.get("config","?"), True)
    field(e, "Created",    vps.get("created_at","?")[:10], True)
    field(e, f"{EM['cpu']} CPU",  f"{stats['cpu']:.1f}%", True)
    field(e, f"{EM['ram']} RAM",
          f"{ram_d['used']}/{ram_d['total']} MB ({ram_d['pct']:.1f}%)", True)
    field(e, f"{EM['disk']} Disk", stats["disk"], True)
    field(e, f"{EM['clock']} Uptime", stats["uptime"], True)
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  ADMIN: CREATE / DELETE VPS
# ════════════════════════════════════════════════════════

@bot.command(name="create")
@is_admin()
async def create_vps(ctx, ram: int, cpu: int, disk: int, user: discord.Member):
    if ram <= 0 or cpu <= 0 or disk <= 0:
        return await ctx.send(embed=error_embed("Invalid Specs", "RAM, CPU and Disk must be positive integers."))
    e = info_embed("VPS Creation", f"Creating VPS for {user.mention} — {ram}GB RAM / {cpu} CPU / {disk}GB Disk\nSelect a node below.")
    await ctx.send(embed=e, view=NodeSelectView(ram, cpu, disk, user, ctx))

@bot.command(name="delete-vps")
@is_admin()
async def delete_vps(ctx, user: discord.Member, vps_number: int, *, reason: str = "No reason"):
    uid = str(user.id)
    if uid not in vps_data or vps_number < 1 or vps_number > len(vps_data[uid]):
        return await ctx.send(embed=error_embed("Invalid VPS", "VPS not found."))
    vps    = vps_data[uid][vps_number - 1]
    cname  = vps["container_name"]
    node_id = vps.get("node_id", 1)
    await ctx.send(embed=info_embed("Deleting VPS", f"Removing VPS #{vps_number} for {user.mention}…"))

    # Attempt LXC delete
    node_result = "Not attempted"
    try:
        await execute_lxc(cname, f"delete {cname} --force", node_id=node_id)
        node_result = "Container deleted."
    except Exception as ex:
        err = str(ex).lower()
        if any(x in err for x in ["not found","does not exist","no such"]):
            node_result = "Container not found — DB cleaned."
        else:
            node_result = f"LXC error: {str(ex)[:100]}"

    # DB cleanup
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM vps WHERE container_name = ?", (cname,))
    cur.execute("DELETE FROM port_forwards WHERE vps_container = ?", (cname,))
    conn.commit(); conn.close()

    # Memory cleanup
    del vps_data[uid][vps_number - 1]
    if not vps_data[uid]:
        del vps_data[uid]
        if ctx.guild:
            role = await get_or_create_vps_role(ctx.guild)
            if role and role in user.roles:
                try: await user.remove_roles(role)
                except discord.Forbidden: pass

    save_vps_data()
    e = success_embed("VPS Deleted", f"VPS #{vps_number} for {user.mention} removed.")
    field(e, "Container", cname, True)
    field(e, "Node Result", node_result, True)
    field(e, "Reason", reason, False)
    await ctx.send(embed=e)
    try: await user.send(embed=warn_embed("VPS Deleted",
        f"Your VPS `{cname}` has been deleted by an admin.\n**Reason:** {reason}"))
    except discord.Forbidden: pass

@bot.command(name="add-resources")
@is_admin()
async def add_resources(ctx, vps_id: str, ram: int = None, cpu: int = None, disk: int = None):
    if ram is None and cpu is None and disk is None:
        return await ctx.send(embed=error_embed("Missing Params",
            f"Usage: `{PREFIX}add-resources <container> [ram] [cpu] [disk]`"))
    found_vps = uid = vps_idx = None
    for u, lst in vps_data.items():
        for i, v in enumerate(lst):
            if v["container_name"] == vps_id:
                found_vps = v; uid = u; vps_idx = i; break
        if found_vps: break
    if not found_vps:
        return await ctx.send(embed=error_embed("Not Found", f"No VPS `{vps_id}`."))
    node_id    = found_vps["node_id"]
    was_running = found_vps.get("status") == "running" and not found_vps.get("suspended")
    if was_running:
        await ctx.send(embed=info_embed("Stopping VPS", f"Stopping `{vps_id}` to apply changes…"))
        try:
            await execute_lxc(vps_id, f"stop {vps_id}", node_id=node_id)
            found_vps["status"] = "stopped"; save_vps_data()
        except Exception as ex:
            return await ctx.send(embed=error_embed("Stop Failed", str(ex)))
    changes = []
    try:
        cur_ram  = int(found_vps["ram"].replace("GB",""))
        cur_cpu  = int(found_vps["cpu"])
        cur_disk = int(found_vps["storage"].replace("GB",""))
        new_ram  = cur_ram  + (ram  if ram  and ram  > 0 else 0)
        new_cpu  = cur_cpu  + (cpu  if cpu  and cpu  > 0 else 0)
        new_disk = cur_disk + (disk if disk and disk > 0 else 0)
        if ram and ram > 0:
            await execute_lxc(vps_id, f"config set {vps_id} limits.memory {new_ram*1024}MB", node_id=node_id)
            changes.append(f"RAM +{ram}GB → {new_ram}GB")
        if cpu and cpu > 0:
            await execute_lxc(vps_id, f"config set {vps_id} limits.cpu {new_cpu}", node_id=node_id)
            changes.append(f"CPU +{cpu}c → {new_cpu}c")
        if disk and disk > 0:
            await execute_lxc(vps_id, f"config device set {vps_id} root size={new_disk}GB", node_id=node_id)
            changes.append(f"Disk +{disk}GB → {new_disk}GB")
        found_vps["ram"] = f"{new_ram}GB"
        found_vps["cpu"] = str(new_cpu)
        found_vps["storage"] = f"{new_disk}GB"
        found_vps["config"]  = f"{new_ram}GB RAM / {new_cpu} CPU / {new_disk}GB Disk"
        vps_data[uid][vps_idx] = found_vps
        if was_running:
            await execute_lxc(vps_id, f"start {vps_id}", node_id=node_id)
            found_vps["status"] = "running"
            await apply_internal_permissions(vps_id, node_id)
            await recreate_port_forwards(vps_id)
        save_vps_data()
        e = success_embed("Resources Updated", f"`{vps_id}` upgraded!")
        field(e, "Changes", "\n".join(changes) if changes else "No changes applied.")
        if disk and disk > 0:
            field(e, "Note", "Run `resize2fs /` inside the VPS to expand the filesystem.")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("Update Failed", str(ex)))

@bot.command(name="suspend-vps")
@is_admin()
async def suspend_vps(ctx, container_name: str, *, reason: str = "Admin action"):
    node_id = find_node_id_for_container(container_name)
    for uid, lst in vps_data.items():
        for vps in lst:
            if vps["container_name"] == container_name:
                if vps.get("status") != "running":
                    return await ctx.send(embed=error_embed("Cannot Suspend", "VPS must be running to suspend."))
                try:
                    await execute_lxc(container_name, f"stop {container_name}", node_id=node_id)
                    vps["status"] = "stopped"; vps["suspended"] = True
                    vps.setdefault("suspension_history", []).append({
                        "time": datetime.now().isoformat(), "reason": reason,
                        "by": f"{ctx.author.name} ({ctx.author.id})"})
                    save_vps_data()
                    await ctx.send(embed=success_embed("Suspended", f"`{container_name}` suspended.\n**Reason:** {reason}"))
                    try:
                        owner = await bot.fetch_user(int(uid))
                        await owner.send(embed=warn_embed("VPS Suspended",
                            f"Your VPS `{container_name}` was suspended.\n**Reason:** {reason}\nContact an admin to unsuspend."))
                    except Exception: pass
                except Exception as ex:
                    await ctx.send(embed=error_embed("Suspend Failed", str(ex)))
                return
    await ctx.send(embed=error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name="unsuspend-vps")
@is_admin()
async def unsuspend_vps(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    for uid, lst in vps_data.items():
        for vps in lst:
            if vps["container_name"] == container_name:
                if not vps.get("suspended"):
                    return await ctx.send(embed=error_embed("Not Suspended", "VPS is not suspended."))
                try:
                    vps["suspended"] = False; vps["status"] = "running"
                    await execute_lxc(container_name, f"start {container_name}", node_id=node_id)
                    await apply_internal_permissions(container_name, node_id)
                    await recreate_port_forwards(container_name)
                    save_vps_data()
                    await ctx.send(embed=success_embed("Unsuspended", f"`{container_name}` is running again!"))
                    try:
                        owner = await bot.fetch_user(int(uid))
                        await owner.send(embed=success_embed("VPS Unsuspended",
                            f"Your VPS `{container_name}` has been unsuspended!"))
                    except Exception: pass
                except Exception as ex:
                    await ctx.send(embed=error_embed("Start Failed", str(ex)))
                return
    await ctx.send(embed=error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name="whitelist-vps")
@is_admin()
async def whitelist_vps(ctx, container_name: str, action: str):
    if action.lower() not in ("add", "remove"):
        return await ctx.send(embed=error_embed("Invalid Action", "Use `add` or `remove`."))
    for lst in vps_data.values():
        for vps in lst:
            if vps["container_name"] == container_name:
                vps["whitelisted"] = (action.lower() == "add")
                save_vps_data()
                msg = "added to" if action.lower() == "add" else "removed from"
                return await ctx.send(embed=success_embed("Whitelist Updated",
                    f"`{container_name}` has been {msg} the whitelist."))
    await ctx.send(embed=error_embed("Not Found", f"VPS `{container_name}` not found."))

@bot.command(name="apply-permissions")
@is_admin()
async def apply_permissions(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    await ctx.send(embed=info_embed("Applying…", f"Applying Docker-ready permissions to `{container_name}`…"))
    try:
        await apply_lxc_config(container_name, node_id)
        await execute_lxc(container_name, f"start {container_name}", node_id=node_id)
        await apply_internal_permissions(container_name, node_id)
        await recreate_port_forwards(container_name)
        for lst in vps_data.values():
            for vps in lst:
                if vps["container_name"] == container_name:
                    vps["status"] = "running"; vps["suspended"] = False; save_vps_data(); break
        await ctx.send(embed=success_embed("Done", f"`{container_name}` is Docker-ready!"))
    except Exception as ex:
        await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="restart-vps")
@is_admin()
async def restart_vps(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    await ctx.send(embed=info_embed("Restarting…", f"Restarting `{container_name}`…"))
    try:
        await execute_lxc(container_name, f"restart {container_name}", timeout=120, node_id=node_id)
        await apply_internal_permissions(container_name, node_id)
        await recreate_port_forwards(container_name)
        for lst in vps_data.values():
            for vps in lst:
                if vps["container_name"] == container_name:
                    vps["status"] = "running"; save_vps_data(); break
        await ctx.send(embed=success_embed("Restarted", f"`{container_name}` is running!"))
    except Exception as ex:
        await ctx.send(embed=error_embed("Restart Failed", str(ex)))

@bot.command(name="clone-vps")
@is_admin()
async def clone_vps(ctx, container_name: str, new_name: str = None):
    if not new_name:
        ts = int(time.time())
        new_name = f"{container_name}-clone-{ts}"
    node_id = find_node_id_for_container(container_name)
    await ctx.send(embed=info_embed("Cloning…", f"`{container_name}` → `{new_name}`"))
    found_vps = uid = None
    for u, lst in vps_data.items():
        for v in lst:
            if v["container_name"] == container_name:
                found_vps = v; uid = u; break
        if found_vps: break
    if not found_vps:
        return await ctx.send(embed=error_embed("Not Found", f"No VPS `{container_name}`."))
    try:
        await execute_lxc(container_name, f"copy {container_name} {new_name}", node_id=node_id)
        await apply_lxc_config(new_name, node_id)
        await execute_lxc(new_name, f"start {new_name}", node_id=node_id)
        await apply_internal_permissions(new_name, node_id)
        new_vps = {**found_vps, "container_name": new_name, "status": "running",
                   "suspended": False, "whitelisted": False, "suspension_history": [],
                   "shared_with": [], "created_at": datetime.now().isoformat(), "id": None}
        if uid not in vps_data: vps_data[uid] = []
        vps_data[uid].append(new_vps); save_vps_data()
        await ctx.send(embed=success_embed("Cloned!", f"`{container_name}` → `{new_name}` ✅"))
    except Exception as ex:
        await ctx.send(embed=error_embed("Clone Failed", str(ex)))

@bot.command(name="vps-stats")
@is_admin()
async def vps_stats_cmd(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    stats   = await get_container_stats(container_name, node_id)
    ram_d   = stats["ram"]
    e = make_embed(f"{EM['chart']} VPS Stats — {container_name}", "", C_INFO)
    field(e, "Status",  stats["status"].upper(), True)
    field(e, f"{EM['cpu']} CPU", f"{stats['cpu']:.1f}%  {_bar(stats['cpu'])}", True)
    field(e, f"{EM['ram']} RAM",
          f"{ram_d['used']}/{ram_d['total']} MB ({ram_d['pct']:.1f}%)  {_bar(ram_d['pct'])}", True)
    field(e, f"{EM['disk']} Disk",  stats["disk"], True)
    field(e, f"{EM['clock']} Uptime", stats["uptime"], True)
    await ctx.send(embed=e)

@bot.command(name="vps-logs")
@is_admin()
async def vps_logs(ctx, container_name: str, lines: int = 50):
    node_id = find_node_id_for_container(container_name)
    try:
        out = await execute_lxc(container_name,
            f"exec {container_name} -- journalctl -n {lines}", node_id=node_id)
        out = (out or "(empty)")[:1800]
        e = make_embed(f"{EM['log']} Logs — {container_name}", f"Last {lines} lines", C_DARK)
        field(e, "Output", f"```\n{out}\n```")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("Log Error", str(ex)))

@bot.command(name="vps-processes")
@is_admin()
async def vps_processes(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    try:
        out = await execute_lxc(container_name, f"exec {container_name} -- ps aux", node_id=node_id)
        out = (out or "(empty)")[:1800]
        e = make_embed("⚙️ Processes", container_name, C_DARK)
        field(e, "Process List", f"```\n{out}\n```")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("Process Error", str(ex)))

@bot.command(name="exec")
@is_admin()
async def exec_cmd(ctx, container_name: str, *, command: str):
    node_id = find_node_id_for_container(container_name)
    try:
        out = await execute_lxc(container_name,
            f"exec {container_name} -- sh -c {shlex.quote(command)}", node_id=node_id, timeout=60)
        out = (out or "(no output)")[:1800]
        e = make_embed("💻 Exec", container_name, C_SUCCESS)
        field(e, "Command", f"```sh\n{command}\n```")
        field(e, "Output",  f"```\n{out}\n```")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("Exec Failed", str(ex)))

@bot.command(name="migrate-vps")
@is_admin()
async def migrate_vps(ctx, container_name: str, target_node_id: int):
    src_node_id = find_node_id_for_container(container_name)
    target_node = get_node(target_node_id)
    if not target_node:
        return await ctx.send(embed=error_embed("Node Not Found", f"Node {target_node_id} doesn't exist."))
    await ctx.send(embed=info_embed("Migrating…", f"`{container_name}` → **{target_node['name']}**"))
    try:
        await execute_lxc(container_name, f"stop {container_name}", node_id=src_node_id)
        temp = f"{container_name}-mig-{int(time.time())}"
        await execute_lxc(container_name, f"copy {container_name} {temp} -s {DEFAULT_STORAGE_POOL}", node_id=target_node_id)
        await execute_lxc(container_name, f"delete {container_name} --force", node_id=src_node_id)
        await execute_lxc(temp, f"rename {temp} {container_name}", node_id=target_node_id)
        await apply_lxc_config(container_name, target_node_id)
        await execute_lxc(container_name, f"start {container_name}", node_id=target_node_id)
        await apply_internal_permissions(container_name, target_node_id)
        await recreate_port_forwards(container_name)
        for lst in vps_data.values():
            for vps in lst:
                if vps["container_name"] == container_name:
                    vps["node_id"] = target_node_id; vps["status"] = "running"
                    save_vps_data(); break
        await ctx.send(embed=success_embed("Migrated!", f"`{container_name}` is now on **{target_node['name']}**!"))
    except Exception as ex:
        await ctx.send(embed=error_embed("Migration Failed", str(ex)))

@bot.command(name="suspension-logs")
@is_admin()
async def suspension_logs(ctx, container_name: str = None):
    if container_name:
        for lst in vps_data.values():
            for vps in lst:
                if vps["container_name"] == container_name:
                    history = vps.get("suspension_history", [])
                    if not history:
                        return await ctx.send(embed=info_embed("No History", f"No suspensions for `{container_name}`."))
                    e = make_embed(f"{EM['log']} Suspension Logs", container_name, C_INFO)
                    text = "\n".join(
                        f"**{h['time'][:16]}** — {h['reason']} (by {h['by']})"
                        for h in sorted(history, key=lambda x: x["time"], reverse=True)[:10])
                    field(e, "History", text)
                    return await ctx.send(embed=e)
        return await ctx.send(embed=error_embed("Not Found", f"VPS `{container_name}` not found."))
    else:
        all_logs = []
        for uid, lst in vps_data.items():
            for vps in lst:
                for h in vps.get("suspension_history", []):
                    all_logs.append(f"**{h['time'][:16]}** `{vps['container_name']}` <@{uid}> — {h['reason']}")
        if not all_logs:
            return await ctx.send(embed=info_embed("No Logs", "No suspension events recorded."))
        text = "\n".join(sorted(all_logs, reverse=True)[:20])
        e = make_embed(f"{EM['log']} All Suspension Logs", "Latest 20 events", C_INFO)
        field(e, "Events", text)
        await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  PORT FORWARDING
# ════════════════════════════════════════════════════════

@bot.command(name="ports")
async def ports_cmd(ctx, subcmd: str = None, *args):
    uid       = str(ctx.author.id)
    allocated = get_user_allocation(uid)
    used      = get_user_used_ports(uid)
    available = allocated - used

    if subcmd is None:
        e = info_embed("Port Forwarding", f"**Quota:** {used}/{allocated} used · {available} free")
        field(e, "Commands",
              f"`{PREFIX}ports add <vps_num> <port>` — Forward a port\n"
              f"`{PREFIX}ports list` — List forwards\n"
              f"`{PREFIX}ports remove <id>` — Remove forward")
        return await ctx.send(embed=e)

    if subcmd == "add":
        if len(args) < 2:
            return await ctx.send(embed=error_embed("Usage", f"`{PREFIX}ports add <vps_number> <port>`"))
        try:
            vps_num  = int(args[0])
            vps_port = int(args[1])
            if not (1 <= vps_port <= 65535): raise ValueError
        except ValueError:
            return await ctx.send(embed=error_embed("Invalid Input", "VPS number and port must be valid integers."))
        vlist = vps_data.get(uid, [])
        if vps_num < 1 or vps_num > len(vlist):
            return await ctx.send(embed=error_embed("Invalid VPS", f"VPS #{vps_num} not found."))
        vps  = vlist[vps_num - 1]
        if used >= allocated:
            return await ctx.send(embed=error_embed("Quota Exceeded",
                f"You have {used}/{allocated} ports used. Ask an admin for more."))
        host_port = await create_port_forward(uid, vps["container_name"], vps_port, vps["node_id"])
        if host_port:
            e = success_embed("Port Forward Created",
                f"VPS #{vps_num} port **{vps_port}** → host port **{host_port}** (TCP+UDP)")
            field(e, "Access", f"`{YOUR_SERVER_IP}:{host_port}` → VPS `{vps_port}`", True)
            field(e, "Quota",  f"{used+1}/{allocated}", True)
            await ctx.send(embed=e)
        else:
            await ctx.send(embed=error_embed("Failed", "Could not allocate host port. Try again."))

    elif subcmd == "list":
        forwards = get_user_forwards(uid)
        e = info_embed("Your Port Forwards", f"**Quota:** {used}/{allocated} · {available} free")
        if not forwards:
            field(e, "Forwards", "None yet. Use `ports add` to create one.")
        else:
            lines = []
            for f_row in forwards:
                n = next((i+1 for i, v in enumerate(vps_data.get(uid, []))
                          if v["container_name"] == f_row["vps_container"]), "?")
                lines.append(f"**ID {f_row['id']}** VPS#{n}: `{f_row['vps_port']}` → `{f_row['host_port']}`")
            field(e, "Active", "\n".join(lines[:15]))
        await ctx.send(embed=e)

    elif subcmd == "remove":
        if not args:
            return await ctx.send(embed=error_embed("Usage", f"`{PREFIX}ports remove <id>`"))
        try: fid = int(args[0])
        except ValueError:
            return await ctx.send(embed=error_embed("Invalid ID", "Must be an integer."))
        ok, _ = await remove_port_forward(fid)
        if ok: await ctx.send(embed=success_embed("Removed", f"Port forward #{fid} removed."))
        else:   await ctx.send(embed=error_embed("Not Found", f"ID #{fid} not found."))
    else:
        await ctx.send(embed=error_embed("Unknown Subcommand", "Use: `add`, `list`, `remove`"))

@bot.command(name="ports-add-user")
@is_admin()
async def ports_add_user(ctx, amount: int, user: discord.Member):
    if amount <= 0:
        return await ctx.send(embed=error_embed("Invalid Amount", "Must be positive."))
    allocate_ports(str(user.id), amount)
    total = get_user_allocation(str(user.id))
    e = success_embed("Ports Allocated", f"Gave {user.mention} **{amount}** port slots.")
    field(e, "Total Quota", f"{total} slots", True)
    await ctx.send(embed=e)
    try: await user.send(embed=info_embed("Port Slots Added",
        f"An admin granted you **{amount}** port forwarding slots. Total: **{total}**."))
    except discord.Forbidden: pass

@bot.command(name="ports-remove-user")
@is_admin()
async def ports_remove_user(ctx, amount: int, user: discord.Member):
    if amount <= 0:
        return await ctx.send(embed=error_embed("Invalid Amount", "Must be positive."))
    current = get_user_allocation(str(user.id))
    actual  = min(amount, current)
    deallocate_ports(str(user.id), actual)
    remaining = get_user_allocation(str(user.id))
    e = success_embed("Ports Reduced", f"Removed {actual} port slots from {user.mention}.")
    field(e, "Remaining", f"{remaining} slots", True)
    await ctx.send(embed=e)

@bot.command(name="ports-revoke")
@is_admin()
async def ports_revoke(ctx, forward_id: int):
    ok, uid = await remove_port_forward(forward_id)
    if ok:
        await ctx.send(embed=success_embed("Revoked", f"Port forward #{forward_id} revoked."))
        if uid:
            try:
                u = await bot.fetch_user(int(uid))
                await u.send(embed=warn_embed("Port Forward Revoked",
                    f"Port forward #{forward_id} was revoked by an admin."))
            except Exception: pass
    else:
        await ctx.send(embed=error_embed("Not Found", f"ID #{forward_id} not found."))

# ════════════════════════════════════════════════════════
#  VPS LISTING / SYSTEM STATUS
# ════════════════════════════════════════════════════════

@bot.command(name="vps-list")
@is_admin()
async def vps_list_cmd(ctx, node_id: int = 1):
    node = get_node(node_id)
    if not node:
        return await ctx.send(embed=error_embed("Not Found", f"Node {node_id} not found."))
    status = await get_node_status(node_id)
    is_online = status.startswith("🟢")
    stats = await get_host_stats(node_id)
    cpu_u = stats.get("cpu", 0.0); ram_u = stats.get("ram", 0.0); disk_u = stats.get("disk","?")

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT * FROM vps WHERE node_id = ?", (node_id,))
    rows = cur.fetchall(); conn.close()

    running = stopped = suspended = 0
    vps_info = []
    for i, row in enumerate(rows, 1):
        vps = dict(row); uid = vps["user_id"]
        try: u = await bot.fetch_user(int(uid)); uname = u.name
        except: uname = f"ID:{uid}"
        s = vps.get("status","?"); sus = vps.get("suspended",False)
        if sus: suspended += 1
        elif s == "running": running += 1
        else: stopped += 1
        emoji  = EM["online"] if s == "running" and not sus else EM["warning"] if sus else EM["offline"]
        status_txt = f"{s.upper()}" + (" ⛔" if sus else "") + (" ✅" if vps.get("whitelisted") else "")
        vps_info.append(f"{emoji} **{i}.** {uname} · `{vps['container_name']}`\n   _{status_txt} | {vps.get('config','?')}_")

    cap = node["total_vps"]; cur_count = get_current_vps_count(node_id)
    color = C_SUCCESS if is_online else C_ERROR
    e = make_embed(f"{EM['node']} VPS Dashboard — {node['name']}",
                   f"**Location:** {node['location']} | **Capacity:** {cur_count}/{cap}", color)
    field(e, "Node Status", status, True)
    if is_online:
        field(e, f"{EM['chart']} Resources",
              f"**CPU** {cpu_u:.1f}%  {_bar(cpu_u)}\n"
              f"**RAM** {ram_u:.1f}%  {_bar(ram_u)}\n"
              f"**Disk** {disk_u}", False)
    field(e, "Summary",
          f"{EM['online']} Running: **{running}** | {EM['offline']} Stopped: **{stopped}** | ⛔ Suspended: **{suspended}**",
          False)
    if vps_info:
        for chunk_start in range(0, len(vps_info), 6):
            chunk = vps_info[chunk_start:chunk_start+6]
            field(e, f"VPS List ({chunk_start+1}–{chunk_start+len(chunk)})", "\n".join(chunk))
    else:
        field(e, "VPS List", "No VPS on this node yet.")
    await ctx.send(embed=e)

@bot.command(name="list-all")
@is_admin()
async def list_all(ctx):
    total = running = stopped = suspended = whitelisted = 0
    lines = []
    for uid, vlist in vps_data.items():
        for vps in vlist:
            total += 1
            s = vps.get("status","?"); sus = vps.get("suspended",False)
            if sus: suspended += 1
            elif s == "running": running += 1
            else: stopped += 1
            if vps.get("whitelisted"): whitelisted += 1
            emoji = EM["online"] if s=="running" and not sus else EM["warning"] if sus else EM["offline"]
            node = get_node(vps.get("node_id",1))
            lines.append(f"{emoji} `{vps['container_name']}` <@{uid}> | {vps.get('config','?')} | {node['name'] if node else '?'}")

    e = make_embed(f"{EM['list']} All VPS", f"**{total}** total deployments", C_INFO)
    field(e, "Summary",
          f"{EM['online']} **{running}** Running  |  {EM['offline']} **{stopped}** Stopped  |  ⛔ **{suspended}** Suspended  |  ✅ **{whitelisted}** Whitelisted")
    if lines:
        for i in range(0, len(lines), 10):
            field(e, f"VPS ({i+1}–{min(i+10,len(lines))})", "\n".join(lines[i:i+10]))
    await ctx.send(embed=e)

@bot.command(name="status")
@is_admin()
async def system_status(ctx):
    start = time.time()
    nodes = get_nodes()
    running_nodes = stopped_nodes = local_nodes = remote_nodes = 0
    node_details = []
    for node in nodes:
        if node["is_local"]:
            local_nodes += 1; running_nodes += 1; ns = "🟢 Online (Local)"
        else:
            remote_nodes += 1
            try:
                resp = requests.get(f"{node['url']}/api/ping", params={"api_key": node["api_key"]}, timeout=5)
                if resp.status_code == 200: running_nodes += 1; ns = "🟢 Online"
                else: stopped_nodes += 1; ns = "🔴 Offline"
            except: stopped_nodes += 1; ns = "🔴 Offline"
        vc = get_current_vps_count(node["id"]); cap = node["total_vps"]
        node_details.append(f"**{node['name']}** — {ns}\n📍 {node['location']} | {vc}/{cap} VPS")

    total_vps = sum(len(v) for v in vps_data.values())
    total_users = len(vps_data)
    running_vps = stopped_vps = suspended_vps = whitelisted_vps = 0
    total_ram = total_cpu = total_disk = 0
    for lst in vps_data.values():
        for vps in lst:
            sus = vps.get("suspended",False)
            if sus: suspended_vps += 1
            elif vps.get("status") == "running": running_vps += 1
            else: stopped_vps += 1
            if vps.get("whitelisted"): whitelisted_vps += 1
            try: total_ram  += int(vps["ram"].replace("GB",""))
            except: pass
            try: total_cpu  += int(vps["cpu"])
            except: pass
            try: total_disk += int(vps["storage"].replace("GB",""))
            except: pass

    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT SUM(allocated_ports) FROM port_allocations")
    ports_alloc = cur.fetchone()[0] or 0
    cur.execute("SELECT COUNT(*) FROM port_forwards")
    ports_used  = cur.fetchone()[0] or 0
    conn.close()

    ms  = (time.time() - start) * 1000
    h, r = divmod(int((datetime.now() - bot_start_time).total_seconds()), 3600)
    m, s = divmod(r, 60)
    uptime_str = f"{h}h {m}m {s}s"

    e = make_embed(f"{EM['chart']} System Status",
                   f"**{BOT_NAME} v{BOT_VERSION}** — generated in {ms:.0f}ms", C_GOLD)
    field(e, "🤖 Bot",
          f"**Uptime** {uptime_str}\n**Latency** {round(bot.latency*1000)}ms", True)
    field(e, f"{EM['node']} Nodes",
          f"**Total** {len(nodes)} | {EM['online']} **{running_nodes}** | {EM['offline']} **{stopped_nodes}**\n"
          f"**Local** {local_nodes} | **Remote** {remote_nodes}", True)
    field(e, f"{EM['vps']} VPS",
          f"**Total** {total_vps} | **Users** {total_users}\n"
          f"{EM['online']} **{running_vps}** Running  {EM['offline']} **{stopped_vps}** Stopped\n"
          f"⛔ **{suspended_vps}** Suspended  ✅ **{whitelisted_vps}** Whitelisted", True)
    field(e, f"{EM['cpu']} Allocated Resources",
          f"**RAM** {total_ram}GB | **CPU** {total_cpu}c | **Disk** {total_disk}GB", True)
    field(e, f"{EM['port']} Ports",
          f"**Allocated** {ports_alloc} | **In Use** {ports_used} | **Free** {ports_alloc-ports_used}", True)
    field(e, f"{EM['admin']} Admins",
          f"**Total:** {len(admin_data.get('admins',[]))+1}", True)
    if node_details:
        field(e, f"{EM['node']} Node Details", "\n\n".join(node_details))
    health = "✅ All Systems Operational" if running_nodes > 0 and stopped_nodes == 0 \
        else "⚠️ Some Nodes Offline" if stopped_nodes > 0 else "🔴 No Nodes Online"
    field(e, "🏥 Health", health)
    await ctx.send(embed=e)

@bot.command(name="admin-stats")
@is_admin()
async def admin_stats(ctx):
    """Admin overview: list all admins with stats."""
    admins_list = admin_data.get("admins", [])
    e = make_embed(f"{EM['admin']} Admin Stats", f"**{len(admins_list)+1}** admins total", C_GOLD)

    # Main admin
    try:
        main_user = await bot.fetch_user(MAIN_ADMIN_ID)
        field(e, f"{EM['crown']} Main Admin",
              f"{main_user.mention}\n`{main_user.name}` | ID: `{MAIN_ADMIN_ID}`", True)
    except Exception:
        field(e, f"{EM['crown']} Main Admin", f"ID: `{MAIN_ADMIN_ID}`", True)

    # Developer (if different)
    if DEVELOPER_ID != MAIN_ADMIN_ID:
        try:
            dev_user = await bot.fetch_user(DEVELOPER_ID)
            field(e, f"{EM['dev']} Developer",
                  f"{dev_user.mention}\n`{dev_user.name}`", True)
        except Exception:
            field(e, f"{EM['dev']} Developer", f"ID: `{DEVELOPER_ID}`", True)

    # Additional admins
    if admins_list:
        lines = []
        for aid in admins_list:
            if int(aid) in (MAIN_ADMIN_ID, DEVELOPER_ID): continue
            try:
                au = await bot.fetch_user(int(aid))
                vps_count = len(vps_data.get(aid, []))
                lines.append(f"• {au.mention} (`{au.name}`) — {vps_count} VPS")
            except Exception:
                lines.append(f"• ID: `{aid}`")
        if lines:
            field(e, f"{EM['shield']} Admins", "\n".join(lines))
    else:
        field(e, f"{EM['shield']} Admins", "No additional admins.")

    field(e, "Management",
          f"`{PREFIX}admin-add @user` — Add admin\n"
          f"`{PREFIX}admin-remove @user` — Remove admin\n"
          f"`{PREFIX}admin-list` — Full list", False)
    await ctx.send(embed=e)

@bot.command(name="userinfo")
@is_admin()
async def user_info(ctx, user: discord.Member):
    uid   = str(user.id)
    vlist = vps_data.get(uid, [])
    e = make_embed(f"{EM['user']} User Dashboard", f"Stats for {user.mention}", C_GOLD)
    field(e, "User",
          f"**Name** {user.name}\n**ID** `{user.id}`\n"
          f"**Joined** {user.joined_at.strftime('%Y-%m-%d') if user.joined_at else '?'}", True)
    is_a = uid in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)) \
           or uid in admin_data.get("admins",[])
    field(e, f"{EM['admin']} Admin", "✅ Yes" if is_a else "❌ No", True)
    field(e, f"{EM['vps']} VPS", f"`{len(vlist)}` VPS", True)
    if vlist:
        total_ram = total_cpu = total_disk = running = suspended = 0
        lines = []
        for i, vps in enumerate(vlist, 1):
            ram = int(vps.get("ram","0GB").replace("GB",""))
            cpu = int(vps.get("cpu",0))
            disk = int(vps.get("storage","0GB").replace("GB",""))
            total_ram += ram; total_cpu += cpu; total_disk += disk
            sus = vps.get("suspended",False)
            if sus: suspended += 1; st = "⛔ SUSPENDED"
            elif vps.get("status") == "running": running += 1; st = f"{EM['online']} RUNNING"
            else: st = f"{EM['offline']} STOPPED"
            node = get_node(vps.get("node_id",1))
            lines.append(f"**{i}.** `{vps['container_name']}` — {st}\n   {ram}GB / {cpu}c / {disk}GB | {node['name'] if node else '?'}")
        field(e, "Summary",
              f"{EM['online']} {running} Running | ⛔ {suspended} Suspended | "
              f"**RAM** {total_ram}GB | **CPU** {total_cpu}c | **Disk** {total_disk}GB")
        for i in range(0, len(lines), 5):
            field(e, f"VPS List ({i+1}–{min(i+5,len(lines))})", "\n".join(lines[i:i+5]))
    field(e, f"{EM['port']} Ports",
          f"{get_user_used_ports(uid)}/{get_user_allocation(uid)} used", True)
    field(e, f"{EM['coin']} Coins",  f"{get_coins(uid):,}", True)
    field(e, f"{EM['invite']} Invites", f"{get_total_invites(uid):,}", True)
    await ctx.send(embed=e)

@bot.command(name="serverstats")
@is_admin()
async def server_stats(ctx):
    total = running = stopped = suspended = wl = 0
    total_ram = total_cpu = total_disk = 0
    for lst in vps_data.values():
        for vps in lst:
            total += 1
            s = vps.get("status","?"); sus = vps.get("suspended",False)
            if sus: suspended += 1
            elif s == "running": running += 1
            else: stopped += 1
            if vps.get("whitelisted"): wl += 1
            try: total_ram  += int(vps["ram"].replace("GB",""))
            except: pass
            try: total_cpu  += int(vps["cpu"])
            except: pass
            try: total_disk += int(vps["storage"].replace("GB",""))
            except: pass
    e = make_embed(f"{EM['chart']} Server Stats", f"**{BOT_NAME}** infrastructure overview", C_GOLD)
    field(e, "VPS",
          f"**Total** {total} | {EM['online']} **{running}** | {EM['offline']} **{stopped}** | ⛔ **{suspended}** | ✅ **{wl}**")
    field(e, "Resources",
          f"**RAM** {total_ram}GB | **CPU** {total_cpu}c | **Disk** {total_disk}GB")
    field(e, "Users", f"**{len(vps_data)}** with VPS | **{len(admin_data.get('admins',[]))+1}** admins")
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  ADMIN MANAGEMENT
# ════════════════════════════════════════════════════════

@bot.command(name="admin-add")
@is_main_admin()
async def admin_add(ctx, user: discord.Member):
    uid = str(user.id)
    if uid in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)):
        return await ctx.send(embed=error_embed("Already Admin", "This user is already a super admin."))
    if uid in admin_data.get("admins",[]):
        return await ctx.send(embed=error_embed("Already Admin", f"{user.mention} is already an admin."))
    admin_data["admins"].append(uid); save_admin_data()
    await ctx.send(embed=success_embed("Admin Added", f"{user.mention} is now an admin!"))
    try: await user.send(embed=success_embed("Admin Role Granted",
        f"You have been made an admin of **{BOT_NAME}** by {ctx.author.mention}!"))
    except discord.Forbidden: pass

@bot.command(name="admin-remove")
@is_main_admin()
async def admin_remove(ctx, user: discord.Member):
    uid = str(user.id)
    if uid in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)):
        return await ctx.send(embed=error_embed("Cannot Remove", "Cannot remove a super admin."))
    if uid not in admin_data.get("admins",[]):
        return await ctx.send(embed=error_embed("Not Admin", f"{user.mention} is not an admin."))
    admin_data["admins"].remove(uid); save_admin_data()
    await ctx.send(embed=success_embed("Admin Removed", f"{user.mention} is no longer an admin."))
    try: await user.send(embed=warn_embed("Admin Role Removed",
        f"Your admin role in **{BOT_NAME}** was removed by {ctx.author.mention}."))
    except discord.Forbidden: pass

@bot.command(name="admin-list")
@is_admin()
async def admin_list(ctx):
    e = make_embed(f"{EM['admin']} Admin Team", "All current administrators", C_GOLD)
    try:
        main_u = await bot.fetch_user(MAIN_ADMIN_ID)
        field(e, f"{EM['crown']} Main Admin", f"{main_u.mention} (`{main_u.name}`)", False)
    except Exception:
        field(e, f"{EM['crown']} Main Admin", f"ID: `{MAIN_ADMIN_ID}`", False)

    admins = [a for a in admin_data.get("admins",[]) if int(a) not in (MAIN_ADMIN_ID, OWNER_ID, DEVELOPER_ID)]
    if admins:
        lines = []
        for aid in admins:
            try: au = await bot.fetch_user(int(aid)); lines.append(f"• {au.mention} (`{au.name}`)")
            except: lines.append(f"• ID: `{aid}`")
        field(e, f"{EM['shield']} Admins", "\n".join(lines))
    else:
        field(e, f"{EM['shield']} Admins", "No additional admins.")
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  NODES
# ════════════════════════════════════════════════════════

@bot.command(name="node")
@is_admin()
async def node_cmd(ctx, sub: str = None, *args):
    if sub == "list":
        nodes = get_nodes()
        e = make_embed(f"{EM['node']} Nodes", f"**{len(nodes)}** nodes", C_GOLD)
        for n in nodes:
            vc = get_current_vps_count(n["id"]); cap = n["total_vps"]
            t = "Local" if n["is_local"] else "Remote"
            field(e, f"#{n['id']} {n['name']} ({t})",
                  f"📍 {n['location']} | 🖥️ {vc}/{cap} VPS | Tags: {', '.join(n['tags']) or 'none'}")
        await ctx.send(embed=e)

    elif sub == "status":
        if not args: return await ctx.send(embed=error_embed("Usage", f"`{PREFIX}node status <id>`"))
        nid = int(args[0]); node = get_node(nid)
        if not node: return await ctx.send(embed=error_embed("Not Found", f"Node {nid} not found."))
        ns = await get_node_status(nid)
        e = info_embed(f"Node — {node['name']}", ns)
        if node["is_local"]:
            cpu = get_host_cpu_usage(); ram = get_host_ram_usage(); disk = get_host_disk_usage()
            field(e, f"{EM['cpu']} CPU",  f"{cpu:.1f}%  {_bar(cpu)}", True)
            field(e, f"{EM['ram']} RAM",  f"{ram:.1f}%  {_bar(ram)}", True)
            field(e, f"{EM['disk']} Disk", disk, True)
        vc = get_current_vps_count(nid); cap = node["total_vps"]
        field(e, "Capacity", f"{vc}/{cap} ({vc/cap*100:.0f}%)", True)
        field(e, "Location", node["location"], True)
        await ctx.send(embed=e)

    elif sub == "create":
        # Interactive node creation via modals would be complex; use args for simplicity
        e = info_embed("Node Creation",
            f"Use: `{PREFIX}node-add <name> <location> <capacity> <url> <api_key>`\n"
            f"For local node, url and api_key can be `local`.")
        await ctx.send(embed=e)

    elif sub == "delete":
        if not args: return await ctx.send(embed=error_embed("Usage", f"`{PREFIX}node delete <id>`"))
        nid = int(args[0]); node = get_node(nid)
        if not node: return await ctx.send(embed=error_embed("Not Found"))
        if node["is_local"]: return await ctx.send(embed=error_embed("Cannot Delete", "Cannot delete local node."))
        if get_current_vps_count(nid) > 0:
            return await ctx.send(embed=error_embed("Has VPS", "Migrate or delete all VPS first."))
        conn = get_db(); cur = conn.cursor()
        cur.execute("DELETE FROM nodes WHERE id = ?", (nid,)); conn.commit(); conn.close()
        await ctx.send(embed=success_embed("Node Deleted", f"Node #{nid} **{node['name']}** removed."))
    else:
        e = info_embed("Node Management",
            f"`{PREFIX}node list` — Show all nodes\n"
            f"`{PREFIX}node status <id>` — Node diagnostics\n"
            f"`{PREFIX}node create` — Add a node\n"
            f"`{PREFIX}node delete <id>` — Remove a node")
        await ctx.send(embed=e)

@bot.command(name="node-add")
@is_admin()
async def node_add(ctx, name: str, location: str, capacity: int, url: str = None, api_key: str = None):
    is_local = (url is None or url.lower() == "local")
    if not is_local and api_key is None:
        return await ctx.send(embed=error_embed("Missing API Key", "Remote nodes need an API key."))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO nodes (name, location, total_vps, tags, api_key, url, is_local) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (name, location, capacity, "[]", api_key, url if not is_local else None, 1 if is_local else 0))
        conn.commit(); nid = cur.lastrowid; conn.close()
        e = success_embed("Node Added", f"**{name}** added as node #{nid}!")
        field(e, "Type", "Local" if is_local else f"Remote ({url})", True)
        field(e, "Capacity", f"{capacity} VPS", True)
        await ctx.send(embed=e)
    except Exception as ex:
        conn.close(); await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="node-check")
@is_admin()
async def node_check(ctx, node_id: int):
    node = get_node(node_id)
    if not node: return await ctx.send(embed=error_embed("Not Found", f"Node {node_id} not found."))
    ns = await get_node_status(node_id)
    e = info_embed(f"Node Diagnostics — {node['name']}", ns)
    if ns.startswith("🟢"):
        try:
            pools = await execute_lxc("", "storage list", node_id=node_id, timeout=20)
            field(e, "Storage Pools", f"```{(pools or 'N/A')[:400]}```")
        except Exception as ex:
            field(e, "Storage Pools", f"Error: {str(ex)[:200]}")
    await ctx.send(embed=e)

@bot.command(name="lxc-list")
@is_admin()
async def lxc_list(ctx, node_id: int = 1):
    node = get_node(node_id)
    if not node: return await ctx.send(embed=error_embed("Not Found", f"Node {node_id} not found."))
    try:
        out = await execute_lxc("", "list --format compact", node_id=node_id, timeout=20)
        out = (out or "(empty)")[:1800]
        e = make_embed(f"{EM['list']} LXC Containers — {node['name']}", "", C_INFO)
        field(e, "Containers", f"```\n{out}\n```")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("LXC Error", str(ex)))

# ════════════════════════════════════════════════════════
#  SNAPSHOTS
# ════════════════════════════════════════════════════════

@bot.command(name="snapshot")
@is_admin()
async def snapshot(ctx, container_name: str, snap_name: str = None):
    node_id = find_node_id_for_container(container_name)
    if not snap_name:
        snap_name = f"snap-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        await execute_lxc(container_name, f"snapshot {container_name} {snap_name}", node_id=node_id)
        await ctx.send(embed=success_embed("Snapshot Created",
            f"Snapshot `{snap_name}` created for `{container_name}`."))
    except Exception as ex:
        await ctx.send(embed=error_embed("Snapshot Failed", str(ex)))

@bot.command(name="list-snapshots")
@is_admin()
async def list_snapshots(ctx, container_name: str):
    node_id = find_node_id_for_container(container_name)
    try:
        out = await execute_lxc(container_name, f"info {container_name}", node_id=node_id)
        snaps = [l for l in (out or "").splitlines() if "snap" in l.lower()]
        e = info_embed(f"{EM['snapshot']} Snapshots — {container_name}",
                       "\n".join(snaps) if snaps else "No snapshots found.")
        await ctx.send(embed=e)
    except Exception as ex:
        await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="restore-snapshot")
@is_admin()
async def restore_snapshot(ctx, container_name: str, snap_name: str):
    node_id = find_node_id_for_container(container_name)
    try:
        await execute_lxc(container_name, f"restore {container_name} {snap_name}", node_id=node_id)
        await ctx.send(embed=success_embed("Restored",
            f"`{container_name}` restored to snapshot `{snap_name}`."))
    except Exception as ex:
        await ctx.send(embed=error_embed("Restore Failed", str(ex)))

# ════════════════════════════════════════════════════════
#  SYSTEM SETTINGS
# ════════════════════════════════════════════════════════

@bot.command(name="set-threshold")
@is_admin()
async def set_threshold(ctx, cpu_pct: int, ram_pct: int):
    if not (0 < cpu_pct <= 100 and 0 < ram_pct <= 100):
        return await ctx.send(embed=error_embed("Invalid", "Values must be 1–100."))
    set_setting("cpu_threshold", str(cpu_pct))
    set_setting("ram_threshold", str(ram_pct))
    await ctx.send(embed=success_embed("Thresholds Updated",
        f"CPU: **{cpu_pct}%** | RAM: **{ram_pct}%**"))

@bot.command(name="thresholds")
@is_admin()
async def thresholds(ctx):
    cpu = get_setting("cpu_threshold","90"); ram = get_setting("ram_threshold","90")
    e = info_embed("Resource Thresholds",
                   f"{EM['cpu']} CPU alert: **{cpu}%**\n{EM['ram']} RAM alert: **{ram}%**")
    await ctx.send(embed=e)

@bot.command(name="set-status")
@is_admin()
async def set_status(ctx, status_type: str, *, name: str):
    types = {"watching": discord.ActivityType.watching,
             "playing":  discord.ActivityType.playing,
             "listening": discord.ActivityType.listening}
    if status_type.lower() not in types:
        return await ctx.send(embed=error_embed("Invalid Type", "Use: watching, playing, listening"))
    await bot.change_presence(activity=discord.Activity(type=types[status_type.lower()], name=name))
    await ctx.send(embed=success_embed("Status Updated", f"Now **{status_type}** `{name}`"))

# ════════════════════════════════════════════════════════
#  ECONOMY — COINS
# ════════════════════════════════════════════════════════

@bot.command(name="coins")
async def coins_cmd(ctx, user: discord.Member = None):
    target = user or ctx.author
    if user and str(ctx.author.id) not in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)) \
       and str(ctx.author.id) not in admin_data.get("admins",[]):
        return await ctx.send(embed=error_embed("Access Denied", "Only admins can check others' coins."))
    bal = get_coins(str(target.id))
    e = info_embed(f"{EM['coin']} Coin Balance", f"{target.mention}'s balance")
    field(e, "Balance", f"**{bal:,}** {EM['coin']}", False)
    await ctx.send(embed=e)

@bot.command(name="coin-add")
@is_admin()
async def coin_add(ctx, user: discord.Member, amount: int):
    if amount <= 0: return await ctx.send(embed=error_embed("Invalid", "Amount must be positive."))
    add_coins(str(user.id), amount)
    bal = get_coins(str(user.id))
    e = success_embed("Coins Added", f"+**{amount:,}** {EM['coin']} → {user.mention}")
    field(e, "New Balance", f"**{bal:,}** {EM['coin']}", True)
    await ctx.send(embed=e)

@bot.command(name="coin-remove")
@is_admin()
async def coin_remove(ctx, user: discord.Member, amount: int):
    if amount <= 0: return await ctx.send(embed=error_embed("Invalid", "Amount must be positive."))
    ok = remove_coins(str(user.id), amount)
    if not ok: return await ctx.send(embed=error_embed("Insufficient Funds", f"{user.mention} doesn't have enough coins."))
    bal = get_coins(str(user.id))
    e = success_embed("Coins Removed", f"−**{amount:,}** {EM['coin']} from {user.mention}")
    field(e, "New Balance", f"**{bal:,}** {EM['coin']}", True)
    await ctx.send(embed=e)

@bot.command(name="coin-set")
@is_admin()
async def coin_set(ctx, user: discord.Member, amount: int):
    if amount < 0: return await ctx.send(embed=error_embed("Invalid", "Amount cannot be negative."))
    set_coins(str(user.id), amount)
    e = success_embed("Balance Set", f"{user.mention}'s balance set to **{amount:,}** {EM['coin']}")
    await ctx.send(embed=e)

@bot.command(name="coin-leaderboard")
async def coin_leaderboard(ctx):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT user_id, balance FROM coins ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall(); conn.close()
    e = make_embed(f"{EM['gold']} Coin Leaderboard", "Top 10 richest users", C_GOLD)
    if not rows:
        field(e, "Rankings", "No coin data yet.")
    else:
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        lines = []
        for i, row in enumerate(rows):
            try: u = await bot.fetch_user(int(row["user_id"])); name = u.name
            except: name = f"User {row['user_id']}"
            lines.append(f"{medals[i]} **{name}** — {row['balance']:,} {EM['coin']}")
        field(e, "Rankings", "\n".join(lines))
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  ECONOMY — PLANS
# ════════════════════════════════════════════════════════

@bot.command(name="plans")
async def list_plans(ctx):
    plans = get_plans()
    e = make_embed(f"{EM['shop']} Paid VPS Plans", f"Buy with `{PREFIX}buy-plan <name>`", C_GOLD)
    if not plans:
        field(e, "Plans", "No paid plans yet.")
    else:
        for p in plans:
            field(e, f"{EM['vps']} {p['name']}",
                  f"**RAM** {p['ram']}GB | **CPU** {p['cpu']}c | **Disk** {p['disk']}GB\n"
                  f"**Price** {p['price']:,} {EM['coin']}\n"
                  + (f"_{p['description']}_" if p.get("description") else ""), True)
    await ctx.send(embed=e)

@bot.command(name="plan-add")
@is_admin()
async def plan_add(ctx, name: str, ram: int, cpu: int, disk: int, price: int, *, description: str = ""):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO plans (name, ram, cpu, disk, price, description) VALUES (?, ?, ?, ?, ?, ?)",
                    (name, ram, cpu, disk, price, description))
        conn.commit(); conn.close()
        e = success_embed("Plan Created", f"Plan **{name}** added!")
        field(e, "Specs", f"**RAM** {ram}GB | **CPU** {cpu}c | **Disk** {disk}GB | **Price** {price:,} {EM['coin']}")
        await ctx.send(embed=e)
    except Exception as ex:
        conn.close(); await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="plan-remove")
@is_admin()
async def plan_remove(ctx, name: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM plans WHERE name = ?", (name,))
    if cur.rowcount == 0:
        conn.close(); return await ctx.send(embed=error_embed("Not Found", f"No plan `{name}`."))
    conn.commit(); conn.close()
    await ctx.send(embed=success_embed("Plan Removed", f"Plan `{name}` deleted."))

@bot.command(name="buy-plan")
async def buy_plan(ctx, *, name: str):
    uid  = str(ctx.author.id)
    plan = get_plan_by_name(name)
    if not plan:
        return await ctx.send(embed=error_embed("Not Found",
            f"No plan `{name}`. Use `{PREFIX}plans` to see available plans."))
    bal = get_coins(uid)
    if bal < plan["price"]:
        return await ctx.send(embed=error_embed("Insufficient Funds",
            f"You need **{plan['price']:,}** {EM['coin']} but only have **{bal:,}**."))
    remove_coins(uid, plan["price"])
    await ctx.send(embed=info_embed("Deploying VPS…",
        f"Purchased **{name}**! Deploying your VPS…"))
    await create_vps(ctx, plan["ram"], plan["cpu"], plan["disk"], ctx.author)
    e = success_embed("Plan Purchased!",
        f"**{name}** — {plan['ram']}GB / {plan['cpu']}c / {plan['disk']}GB\n"
        f"Spent: **{plan['price']:,}** {EM['coin']} | Balance: **{get_coins(uid):,}** {EM['coin']}")
    await ctx.send(embed=e)

@bot.command(name="freeplans")
async def list_free_plans(ctx):
    plans = get_free_plans()
    e = make_embed(f"{EM['check']} Free VPS Plans", f"Claim with `{PREFIX}claim-freeplan <name>`", C_GOLD)
    if not plans:
        field(e, "Plans", "No free plans yet.")
    else:
        for p in plans:
            ptype = p.get("plan_type","normal")
            icon = EM["invite"] if ptype == "invite" else EM["boost"] if ptype == "boost" else "🆓"
            reqs = []
            if p["invite_required"] > 0: reqs.append(f"{EM['invite']} {p['invite_required']} invites")
            if p["boost_multiplier"] > 1.0: reqs.append(f"{EM['boost']} Server boost (×{p['boost_multiplier']} RAM)")
            field(e, f"{icon} {p['name']}",
                  f"**RAM** {p['ram']}GB | **CPU** {p['cpu']}c | **Disk** {p['disk']}GB\n"
                  + (f"**Requires:** {' | '.join(reqs)}" if reqs else "✅ Free — no requirements"),
                  True)
    await ctx.send(embed=e)

@bot.command(name="freeplan-add")
@is_admin()
async def freeplan_add(ctx, name: str, ram: int, cpu: int, disk: int):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO free_plans (name, ram, cpu, disk, invite_required, boost_multiplier, plan_type) VALUES (?, ?, ?, ?, 0, 1.0, 'normal')",
                    (name, ram, cpu, disk))
        conn.commit(); conn.close()
        await ctx.send(embed=success_embed("Free Plan Created", f"**{name}** — {ram}GB / {cpu}c / {disk}GB"))
    except Exception as ex:
        conn.close(); await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="inviteplan-add")
@is_admin()
async def inviteplan_add(ctx, name: str, ram: int, cpu: int, disk: int, invite_required: int):
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO free_plans (name, ram, cpu, disk, invite_required, boost_multiplier, plan_type) VALUES (?, ?, ?, ?, ?, 1.0, 'invite')",
                    (name, ram, cpu, disk, invite_required))
        conn.commit(); conn.close()
        e = success_embed("Invite Plan Created", f"**{name}** — requires {invite_required} invite(s)")
        field(e, "Specs", f"**RAM** {ram}GB | **CPU** {cpu}c | **Disk** {disk}GB")
        await ctx.send(embed=e)
    except Exception as ex:
        conn.close(); await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="boostplan-add")
@is_admin()
async def boostplan_add(ctx, name: str, ram: int, cpu: int, disk: int, boost_multiplier: float = 1.5):
    if boost_multiplier < 1.0:
        return await ctx.send(embed=error_embed("Invalid", "Multiplier must be ≥ 1.0"))
    conn = get_db(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO free_plans (name, ram, cpu, disk, invite_required, boost_multiplier, plan_type) VALUES (?, ?, ?, ?, 0, ?, 'boost')",
                    (name, ram, cpu, disk, boost_multiplier))
        conn.commit(); conn.close()
        e = success_embed("Boost Plan Created",
            f"**{name}** — requires server boost\nRAM ×{boost_multiplier} = {int(ram*boost_multiplier)}GB for boosters")
        await ctx.send(embed=e)
    except Exception as ex:
        conn.close(); await ctx.send(embed=error_embed("Failed", str(ex)))

@bot.command(name="freeplan-remove")
@is_admin()
async def freeplan_remove(ctx, name: str):
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM free_plans WHERE name = ?", (name,))
    if cur.rowcount == 0:
        conn.close(); return await ctx.send(embed=error_embed("Not Found", f"No free plan `{name}`."))
    conn.commit(); conn.close()
    await ctx.send(embed=success_embed("Removed", f"Free plan `{name}` deleted."))

@bot.command(name="claim-freeplan")
async def claim_freeplan(ctx, *, plan_name: str):
    uid  = str(ctx.author.id)
    plan = get_free_plan_by_name(plan_name)
    if not plan:
        return await ctx.send(embed=error_embed("Not Found",
            f"No free plan `{plan_name}`. Use `{PREFIX}freeplans` to browse."))
    ptype = plan.get("plan_type","normal")
    if ptype == "invite" or plan["invite_required"] > 0:
        total_inv = get_total_invites(uid)
        if total_inv < plan["invite_required"]:
            return await ctx.send(embed=error_embed(f"{EM['invite']} Invite Requirement",
                f"Need **{plan['invite_required']}** invites — you have **{total_inv}**."))
    if ptype == "boost" or plan["boost_multiplier"] > 1.0:
        member = ctx.guild.get_member(int(uid))
        actually_boosting = member and member.premium_since is not None
        if actually_boosting: set_boost(uid, True)
        if not is_boosting(uid) and not actually_boosting:
            return await ctx.send(embed=error_embed(f"{EM['boost']} Boost Required",
                "You must be boosting this server to claim this plan!"))
    ram = int(plan["ram"] * plan["boost_multiplier"]) if plan["boost_multiplier"] > 1.0 and is_boosting(uid) else plan["ram"]
    await ctx.send(embed=info_embed("Deploying…",
        f"Claiming **{plan_name}** and deploying your free VPS!"
        + (f"\n{EM['boost']} Boost bonus: **{ram}GB RAM**!" if ram > plan["ram"] else "")))
    await create_vps(ctx, ram, plan["cpu"], plan["disk"], ctx.author)

# ════════════════════════════════════════════════════════
#  INVITES
# ════════════════════════════════════════════════════════

@bot.command(name="invites")
async def my_invites(ctx, user: discord.Member = None):
    target = user or ctx.author
    if user and str(ctx.author.id) not in (str(MAIN_ADMIN_ID), str(OWNER_ID), str(DEVELOPER_ID)) \
       and str(ctx.author.id) not in admin_data.get("admins",[]):
        return await ctx.send(embed=error_embed("Access Denied", "Only admins can check others' invites."))
    total = get_total_invites(str(target.id))
    e = info_embed(f"{EM['invite']} Invite Stats", f"{target.mention}'s invites")
    field(e, "Total Invites", f"**{total:,}**", True)
    field(e, "Logged", f"**{get_invite_count(str(target.id))}**", True)
    field(e, "Bonus", f"**{get_invite_points(str(target.id)):,}**", True)
    await ctx.send(embed=e)

@bot.command(name="invite-add")
@is_admin()
async def invite_add_admin(ctx, inviter: discord.Member, amount_or_invitee: str = "1"):
    invitee_member = None
    amount = 1
    if amount_or_invitee.startswith("<@"):
        try:
            uid = int(amount_or_invitee.strip("<@!>"))
            invitee_member = ctx.guild.get_member(uid) or await bot.fetch_user(uid)
        except Exception: pass
    if invitee_member:
        record_invite(str(inviter.id), str(invitee_member.id))
        total = get_total_invites(str(inviter.id))
        e = success_embed(f"{EM['invite']} Invite Recorded",
            f"{inviter.mention} → invited → {invitee_member.mention}\nTotal: **{total}**")
    else:
        try: amount = max(1, int(amount_or_invitee))
        except ValueError: amount = 1
        add_invite_points(str(inviter.id), amount)
        total = get_total_invites(str(inviter.id))
        e = success_embed(f"{EM['invite']} Invites Added",
            f"Added **{amount:,}** invites to {inviter.mention}\nTotal: **{total:,}**")
    await ctx.send(embed=e)

@bot.command(name="invite-leaderboard")
async def invite_leaderboard(ctx):
    conn = get_db(); cur = conn.cursor()
    cur.execute("""SELECT user_id, SUM(cnt) as total FROM (
        SELECT inviter_id as user_id, COUNT(*) as cnt FROM invites GROUP BY inviter_id
        UNION ALL SELECT user_id, points as cnt FROM invite_points WHERE points > 0
    ) GROUP BY user_id ORDER BY total DESC LIMIT 10""")
    rows = cur.fetchall(); conn.close()
    e = make_embed(f"{EM['gold']} Invite Leaderboard", "Top inviters", C_GOLD)
    if not rows:
        field(e, "Rankings", "No invites recorded yet.")
    else:
        medals = ["🥇","🥈","🥉"] + ["🏅"]*7
        lines = []
        for i, row in enumerate(rows):
            try: u = await bot.fetch_user(int(row["user_id"])); name = u.name
            except: name = f"User {row['user_id']}"
            lines.append(f"{medals[i]} **{name}** — **{row['total']:,}** invites")
        field(e, "Rankings", "\n".join(lines))
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  BOOST
# ════════════════════════════════════════════════════════

@bot.command(name="check-boost")
async def check_boost(ctx, user: discord.Member = None):
    target = user or ctx.author
    member = ctx.guild.get_member(target.id)
    boosting = member and member.premium_since is not None
    if boosting: set_boost(str(target.id), True)
    e = info_embed(f"{EM['boost']} Boost Status", f"{target.mention}'s boost status")
    field(e, "Status", f"✅ Boosting since {member.premium_since.strftime('%Y-%m-%d')}" if boosting else "❌ Not boosting")
    await ctx.send(embed=e)

@bot.command(name="boost-set")
@is_admin()
async def boost_set(ctx, user: discord.Member, active: str):
    val = active.lower() in ("true","1","yes","on")
    set_boost(str(user.id), val)
    await ctx.send(embed=success_embed("Boost Updated",
        f"{user.mention}'s boost set to **{'Active' if val else 'Inactive'}**"))

@bot.command(name="boosters")
async def list_boosters(ctx):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT user_id, boosted_at FROM boosts WHERE active = 1")
    rows = cur.fetchall(); conn.close()
    e = info_embed(f"{EM['boost']} Active Boosters", "")
    if not rows:
        field(e, "Boosters", "No active boosters recorded.")
    else:
        lines = []
        for row in rows:
            try: u = await bot.fetch_user(int(row["user_id"])); name = u.name
            except: name = f"User {row['user_id']}"
            since = row["boosted_at"][:10] if row["boosted_at"] else "unknown"
            lines.append(f"• **{name}** (since {since})")
        field(e, "Boosters", "\n".join(lines))
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  SHOP OVERVIEW
# ════════════════════════════════════════════════════════

@bot.command(name="shop")
async def shop(ctx):
    uid    = str(ctx.author.id)
    bal    = get_coins(uid)
    plans  = get_plans()
    fplans = get_free_plans()
    member = ctx.guild.get_member(int(uid))
    boosting = member and member.premium_since is not None
    invites  = get_total_invites(uid)
    e = make_embed(f"{EM['shop']} VPS Shop", "Your one-stop VPS marketplace", C_GOLD)
    field(e, f"{EM['coin']} Balance",      f"**{bal:,}** coins", True)
    field(e, f"{EM['invite']} Invites",    f"**{invites:,}**", True)
    field(e, f"{EM['boost']} Boost",       "✅ Active" if boosting else "❌ Inactive", True)
    if plans:
        field(e, f"{EM['vps']} Paid Plans",
              "\n".join(f"**{p['name']}** — {p['ram']}GB/{p['cpu']}c/{p['disk']}GB | {p['price']:,} {EM['coin']}"
                        for p in plans)
              + f"\n\nBuy: `{PREFIX}buy-plan <name>`")
    if fplans:
        field(e, "🆓 Free Plans",
              "\n".join(f"**{p['name']}** — {p['ram']}GB/{p['cpu']}c/{p['disk']}GB"
                        for p in fplans)
              + f"\n\nClaim: `{PREFIX}claim-freeplan <name>`")
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  STOP ALL VPS (emergency)
# ════════════════════════════════════════════════════════

@bot.command(name="stop-vps-all")
@is_main_admin()
async def stop_all(ctx):
    await ctx.send(embed=warn_embed("Stopping All VPS", "Sending stop signal to every running container…"))
    count = 0; failed = 0
    for lst in vps_data.values():
        for vps in lst:
            if vps.get("status") == "running":
                try:
                    await execute_lxc(vps["container_name"], f"stop {vps['container_name']}",
                                      node_id=vps.get("node_id",1), timeout=60)
                    vps["status"] = "stopped"; count += 1
                except Exception: failed += 1
    save_vps_data()
    await ctx.send(embed=success_embed("Done",
        f"Stopped **{count}** VPS. Failed: **{failed}**."))

# ════════════════════════════════════════════════════════
#  RESOURCE CHECK
# ════════════════════════════════════════════════════════

@bot.command(name="resource-check")
@is_admin()
async def resource_check(ctx):
    cpu = get_host_cpu_usage(); ram = get_host_ram_usage(); disk = get_host_disk_usage()
    ct = int(get_setting("cpu_threshold",90)); rt = int(get_setting("ram_threshold",90))
    e = make_embed(f"{EM['chart']} Resource Check", "Current host resource usage", C_GOLD)
    field(e, f"{EM['cpu']} CPU",  f"{cpu:.1f}%  {_bar(cpu)} (threshold: {ct}%)", False)
    field(e, f"{EM['ram']} RAM",  f"{ram:.1f}%  {_bar(ram)} (threshold: {rt}%)", False)
    field(e, f"{EM['disk']} Disk", disk, False)
    if cpu > ct: field(e, f"{EM['warning']} CPU Alert", f"CPU usage exceeds {ct}% threshold!")
    if ram > rt: field(e, f"{EM['warning']} RAM Alert", f"RAM usage exceeds {rt}% threshold!")
    await ctx.send(embed=e)

# ════════════════════════════════════════════════════════
#  MAIN ENTRY
# ════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not DISCORD_TOKEN or DISCORD_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ ERROR: Set your bot token in config.json → bot.token")
        sys.exit(1)
    print(f"[GrimVPS] Starting {BOT_NAME} v{BOT_VERSION}…")
    bot.run(DISCORD_TOKEN)
