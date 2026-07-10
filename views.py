"""
╔══════════════════════════════════════════════════════════════╗
║          GRIM VPS MANAGER  —  VIEWS.PY                      ║
║   Discord UI: Buttons · Selects · Modals · Panels            ║
╚══════════════════════════════════════════════════════════════╝
"""
import asyncio, shlex, re, json
from datetime import datetime
from typing import Optional, Dict

import discord
from discord.ext import commands

from core import (
    BOT_NAME, PREFIX, EM, CFG, OS_OPTIONS, YOUR_SERVER_IP, FOOTER_TEXT,
    DEFAULT_STORAGE_POOL, DEVELOPER_ID, OWNER_ID, MAIN_ADMIN_ID,
    vps_data, admin_data, logger,
    get_node, get_nodes, find_node_id_for_container, get_current_vps_count,
    get_or_create_vps_role, apply_lxc_config, apply_internal_permissions,
    recreate_port_forwards, execute_lxc, get_container_stats,
    save_vps_data, get_user_allocation, get_user_used_ports, get_user_forwards,
    create_port_forward, remove_port_forward, get_available_host_port,
    success_embed, error_embed, info_embed, warn_embed, field, make_embed,
    C_GOLD, C_SUCCESS, C_ERROR, C_INFO, _bar,
    get_giveaway, add_giveaway_entry, get_giveaway_entry_count,
    auto_setup_ports, add_trial_vps, create_subscription,
    get_kvm_vps, get_kvm_vps_for_user, kvm_start, kvm_stop, kvm_restart, kvm_delete,
    kvm_is_running, add_kvm_port_forward_record, remove_kvm_port_forward_record,
    allocate_kvm_port, KVM_OS_OPTIONS, get_subscription, execute_raw,
    run_in_kvm_guest, script_reset_password, TOOL_SCRIPTS, generate_giftcode, get_db,
)

# ════════════════════════════════════════════════════════
#  REINSTALL — OS SELECT + CUSTOM OS MODAL
# ════════════════════════════════════════════════════════

class CustomOSModal(discord.ui.Modal, title="✨ Custom OS Link"):
    link = discord.ui.TextInput(
        label="OS Download URL (.tar.gz / .tar.xz)",
        placeholder="https://example.com/custom-os.tar.gz",
        required=True, max_length=500)

    def __init__(self, parent_view):
        super().__init__()
        self.parent = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        url = self.link.value.strip()
        if not url.startswith("http"):
            return await interaction.response.send_message(
                embed=error_embed("Invalid URL", "Must start with http:// or https://"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.parent.do_reinstall(interaction, f"custom:{url}")


class ReinstallOSSelectView(discord.ui.View):
    def __init__(self, parent_view, container_name, owner_id, actual_idx, ram_gb, cpu, storage_gb, node_id):
        super().__init__(timeout=300)
        self.parent_view   = parent_view
        self.container_name = container_name
        self.owner_id      = owner_id
        self.actual_idx    = actual_idx
        self.ram_gb        = ram_gb
        self.cpu           = cpu
        self.storage_gb    = storage_gb
        self.node_id       = node_id
        sel = discord.ui.Select(
            placeholder=f"{EM['vps']} Choose an OS for reinstall…",
            options=[discord.SelectOption(label=o["label"], value=o["value"]) for o in OS_OPTIONS])
        sel.callback = self.select_os
        self.add_item(sel)

    async def select_os(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "custom":
            return await interaction.response.send_modal(CustomOSModal(self))
        for item in self.children:
            item.disabled = True
        e = info_embed("Reinstalling…", f"Deploying `{val}` on `{self.container_name}`… please wait.")
        await interaction.response.edit_message(embed=e, view=self)
        await self.do_reinstall(interaction, val)

    async def do_reinstall(self, interaction: discord.Interaction, os_version: str):
        ram_mb    = self.ram_gb * 1024
        is_custom = os_version.startswith("custom:")
        custom_url = os_version[7:] if is_custom else None
        display_os = f"Custom OS ({custom_url})" if is_custom else os_version
        try:
            if is_custom:
                img_file = f"/tmp/custom_os_{self.container_name}.tar.gz"
                dl_cmd = f"wget -q -O {img_file} '{custom_url}' && lxc image import {img_file} --alias custom-{self.container_name} && rm -f {img_file}"
                proc = await asyncio.create_subprocess_shell(dl_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if proc.returncode != 0:
                    raise Exception(f"Custom OS import failed: {stderr.decode()[:300]}")
                lxc_os = f"custom-{self.container_name}"
            else:
                lxc_os = os_version

            await execute_lxc(self.container_name, f"init {lxc_os} {self.container_name} -s {DEFAULT_STORAGE_POOL}", node_id=self.node_id)
            await execute_lxc(self.container_name, f"config set {self.container_name} limits.memory {ram_mb}MB", node_id=self.node_id)
            await execute_lxc(self.container_name, f"config set {self.container_name} limits.cpu {self.cpu}", node_id=self.node_id)
            await execute_lxc(self.container_name, f"config device set {self.container_name} root size={self.storage_gb}GB", node_id=self.node_id)
            await apply_lxc_config(self.container_name, self.node_id)
            await execute_lxc(self.container_name, f"start {self.container_name}", node_id=self.node_id)
            await apply_internal_permissions(self.container_name, self.node_id)
            await recreate_port_forwards(self.container_name)

            target = vps_data[self.owner_id][self.actual_idx]
            target["os_version"] = display_os
            target["status"]     = "running"
            target["suspended"]  = False
            target["config"]     = f"{self.ram_gb}GB RAM / {self.cpu} CPU / {self.storage_gb}GB Disk"
            save_vps_data()

            e = success_embed("Reinstall Complete",
                f"{EM['vps']} `{self.container_name}` is live with **{display_os}**!")
            field(e, "Resources", f"**RAM** {self.ram_gb}GB  |  **CPU** {self.cpu}c  |  **Disk** {self.storage_gb}GB", True)
            field(e, "Features", "Docker-ready · Nesting · Privileged · FUSE", True)
            await interaction.followup.send(embed=e, ephemeral=True)
            self.stop()
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Reinstall Failed", str(ex)), ephemeral=True)
            self.stop()


# ════════════════════════════════════════════════════════
#  CMD MODAL + PANEL
# ════════════════════════════════════════════════════════

class CMDModal(discord.ui.Modal, title="💻 Run Linux Command"):
    command = discord.ui.TextInput(
        label="Command",
        placeholder="e.g. apt update | df -h | systemctl status ssh",
        required=True, max_length=500, style=discord.TextStyle.paragraph)

    def __init__(self, container_name: str, node_id: int):
        super().__init__()
        self.container_name = container_name
        self.node_id = node_id

    async def on_submit(self, interaction: discord.Interaction):
        cmd = self.command.value.strip()
        await interaction.response.defer(ephemeral=True)
        try:
            out = await execute_lxc(self.container_name,
                f"exec {self.container_name} -- sh -c {shlex.quote(cmd)}",
                node_id=self.node_id, timeout=30)
            out = (out.strip() if out else "(no output)")[:1800]
            e = make_embed("💻 CMD Output", f"`{self.container_name}`", C_SUCCESS)
            field(e, "Command", f"```sh\n{cmd}\n```")
            field(e, "Output",  f"```\n{out}\n```")
            await interaction.followup.send(embed=e, ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("CMD Failed", str(ex)), ephemeral=True)


class CMDPanelView(discord.ui.View):
    def __init__(self, container_name: str, node_id: int):
        super().__init__(timeout=120)
        self.container_name = container_name
        self.node_id = node_id

    @discord.ui.button(label="⌨️ Type Command", style=discord.ButtonStyle.primary)
    async def type_cmd(self, interaction: discord.Interaction, btn: discord.ui.Button):
        await interaction.response.send_modal(CMDModal(self.container_name, self.node_id))

    @discord.ui.button(label="📄 Upload .sh Script", style=discord.ButtonStyle.secondary)
    async def upload_sh(self, interaction: discord.Interaction, btn: discord.ui.Button):
        e = info_embed("Upload Script",
            f"Send your `.sh` file as an **attachment** now.\n"
            f"⏳ Waiting 60 seconds…")
        await interaction.response.send_message(embed=e, ephemeral=True)
        def check(m):
            return (m.author.id == interaction.user.id
                    and m.channel.id == interaction.channel.id
                    and m.attachments
                    and m.attachments[0].filename.endswith(".sh"))
        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            return await interaction.followup.send(embed=error_embed("Timeout", "No .sh file received."), ephemeral=True)

        att = msg.attachments[0]
        if att.size > 512 * 1024:
            return await interaction.followup.send(embed=error_embed("File Too Large", "Max 512KB."), ephemeral=True)

        await interaction.followup.send(embed=info_embed("Running…", f"Executing `{att.filename}`…"), ephemeral=True)
        try:
            tmp = f"/tmp/vps_script_{self.container_name}_{att.filename}"
            dl = await asyncio.create_subprocess_shell(
                f"wget -q -O {shlex.quote(tmp)} {shlex.quote(att.url)}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, dl_err = await asyncio.wait_for(dl.communicate(), timeout=30)
            if dl.returncode != 0:
                raise Exception(f"Download failed: {dl_err.decode()[:200]}")

            push = await asyncio.create_subprocess_shell(
                f"lxc file push {shlex.quote(tmp)} {self.container_name}/tmp/{att.filename}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, push_err = await asyncio.wait_for(push.communicate(), timeout=30)

            rm = await asyncio.create_subprocess_shell(f"rm -f {shlex.quote(tmp)}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await rm.communicate()

            if push.returncode != 0:
                raise Exception(f"Push failed: {push_err.decode()[:300]}")

            out = await execute_lxc(self.container_name,
                f"exec {self.container_name} -- sh -c 'chmod +x /tmp/{att.filename} && bash /tmp/{att.filename} 2>&1'",
                node_id=self.node_id, timeout=120)
            out = (out.strip() if out else "(no output)")[:1800]
            e = make_embed("📄 Script Result", f"`{self.container_name}`", C_SUCCESS)
            field(e, "Script", f"`{att.filename}` ({att.size} bytes)", True)
            field(e, "Output", f"```\n{out}\n```")
            await interaction.followup.send(embed=e, ephemeral=True)
            try:
                await execute_lxc(self.container_name,
                    f"exec {self.container_name} -- rm -f /tmp/{att.filename}",
                    node_id=self.node_id)
            except Exception:
                pass
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Script Failed", str(ex)), ephemeral=True)


# ════════════════════════════════════════════════════════
#  MANAGE VIEW  (Main VPS Control Panel)
# ════════════════════════════════════════════════════════

class ManageView(discord.ui.View):
    def __init__(self, user_id: str, vps_list: list,
                 is_shared: bool = False, owner_id: str = None,
                 is_admin: bool = False, actual_index: int = None):
        super().__init__(timeout=300)
        self.user_id       = user_id
        self.vps_list      = vps_list[:]
        self.is_shared     = is_shared
        self.owner_id      = owner_id or user_id
        self.is_admin      = is_admin
        self.actual_index  = actual_index
        self.selected_index = None
        self.indices       = list(range(len(vps_list)))

        if is_shared and actual_index is None:
            raise ValueError("actual_index required for shared views")

        if len(vps_list) > 1:
            opts = [discord.SelectOption(
                label=f"VPS {i+1} — {v.get('config','?')}",
                description=f"Status: {v.get('status','unknown').upper()}",
                value=str(i)) for i, v in enumerate(vps_list)]
            sel = discord.ui.Select(placeholder=f"{EM['vps']} Select a VPS to manage…", options=opts)
            sel.callback = self.select_vps
            self.add_item(sel)
            self._initial_embed = self._list_embed()
        else:
            self.selected_index = 0
            self._initial_embed = None
            self._add_buttons()

    def _list_embed(self):
        e = make_embed("VPS Management", "Select a VPS from the dropdown below.", C_GOLD)
        lines = [f"{EM['vps']} **VPS {i+1}:** `{v['container_name']}` — `{v.get('status','?').upper()}`"
                 for i, v in enumerate(self.vps_list)]
        field(e, "Your VPS", "\n".join(lines))
        return e

    async def get_initial_embed(self, bot_client=None):
        if self._initial_embed: return self._initial_embed
        self._initial_embed = await self._vps_embed(self.selected_index, bot_client=bot_client)
        return self._initial_embed

    async def _vps_embed(self, idx: int, bot_client=None):
        vps  = self.vps_list[idx]
        node = get_node(vps["node_id"])
        node_name  = node["name"] if node else "Unknown"
        status     = vps.get("status", "unknown")
        suspended  = vps.get("suspended", False)
        whitelisted = vps.get("whitelisted", False)

        color = C_SUCCESS if (status == "running" and not suspended) \
               else 0xFFAB00 if suspended else C_ERROR
        cname = vps["container_name"]

        stats = await get_container_stats(cname)

        owner_txt = ""
        if self.is_admin and self.owner_id != self.user_id:
            if bot_client:
                try:
                    ou = await bot_client.fetch_user(int(self.owner_id))
                    owner_txt = f"\n**Owner:** {ou.mention}"
                except Exception:
                    owner_txt = f"\n**Owner ID:** `{self.owner_id}`"
            else:
                owner_txt = f"\n**Owner ID:** `{self.owner_id}`"

        status_str = stats["status"].upper()
        if suspended:   status_str += " ⛔ SUSPENDED"
        if whitelisted: status_str += " ✅ WHITELISTED"

        e = make_embed(f"VPS {idx+1} — {cname}",
                       f"{EM['node']} Node: **{node_name}**{owner_txt}", color)

        # Resources block
        field(e, f"{EM['vps']} Configuration",
              f"**RAM** `{vps['ram']}`  |  **CPU** `{vps['cpu']}c`  |  **Disk** `{vps['storage']}`\n"
              f"**OS** `{vps.get('os_version','ubuntu:22.04')}`  |  **Status** `{status_str}`", False)

        # Live stats block
        ram_d = stats["ram"]
        cpu_pct = stats["cpu"]
        ram_pct = ram_d["pct"]
        field(e, f"{EM['chart']} Live Stats",
              f"**CPU** {cpu_pct:.1f}%  {_bar(cpu_pct)}\n"
              f"**RAM** {ram_d['used']}/{ram_d['total']} MB ({ram_pct:.1f}%)  {_bar(ram_pct)}\n"
              f"**Disk** {stats['disk']}  |  **Uptime** {stats['uptime']}", False)

        if suspended:
            field(e, f"{EM['warning']} Suspended", "Contact an admin to unsuspend.", False)
        if whitelisted:
            field(e, f"{EM['check']} Whitelisted", "Exempt from auto-suspension.", False)

        field(e, f"{EM['terminal']} Controls", "Use the buttons below.", False)
        return e

    def _add_buttons(self):
        if not self.is_shared and not self.is_admin:
            btn = discord.ui.Button(label="🔄 Reinstall", style=discord.ButtonStyle.danger, row=1)
            btn.callback = lambda i: self._action(i, "reinstall")
            self.add_item(btn)

        defs = [
            ("▶ Start",   discord.ButtonStyle.success,   "start",  0),
            ("⏸ Stop",    discord.ButtonStyle.secondary,  "stop",   0),
            ("🔁 Restart", discord.ButtonStyle.danger,     "restart", 0),
            ("🔑 SSH",    discord.ButtonStyle.primary,    "tmate",  0),
            ("🌐 SSHx",   discord.ButtonStyle.primary,    "sshx",   1),
            ("📊 Stats",  discord.ButtonStyle.secondary,  "stats",  1),
            ("💻 CMD",    discord.ButtonStyle.secondary,  "cmd",    1),
        ]
        for label, style, action, row in defs:
            btn = discord.ui.Button(label=label, style=style, row=row)
            btn.callback = lambda i, a=action: self._action(i, a)
            self.add_item(btn)

    async def select_vps(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            return await interaction.response.send_message(
                embed=error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
        self.selected_index = int(interaction.data["values"][0])
        await interaction.response.defer()
        emb = await self._vps_embed(self.selected_index, bot_client=interaction.client)
        self.clear_items(); self._add_buttons()
        await interaction.edit_original_response(embed=emb, view=self)

    async def _action(self, interaction: discord.Interaction, action: str):
        if str(interaction.user.id) != self.user_id and not self.is_admin:
            return await interaction.response.send_message(
                embed=error_embed("Access Denied", "This is not your VPS!"), ephemeral=True)
        if self.selected_index is None:
            return await interaction.response.send_message(
                embed=error_embed("No VPS Selected", "Select a VPS first."), ephemeral=True)

        actual_idx  = self.actual_index if self.is_shared else self.indices[self.selected_index]
        target_vps  = vps_data[self.owner_id][actual_idx]
        suspended   = target_vps.get("suspended", False)
        cname       = target_vps["container_name"]
        node_id     = target_vps["node_id"]

        if suspended and not self.is_admin and action not in ("stats",):
            return await interaction.response.send_message(
                embed=error_embed("Suspended", "VPS is suspended. Contact an admin."), ephemeral=True)

        # ── STATS ────────────────────────────────────────────
        if action == "stats":
            await interaction.response.defer(ephemeral=True)
            stats = await get_container_stats(cname, node_id)
            ram_d = stats["ram"]
            e = info_embed("Live Statistics", f"`{cname}`")
            field(e, "Status",  f"`{stats['status'].upper()}`", True)
            field(e, f"{EM['cpu']} CPU",    f"{stats['cpu']:.1f}%  {_bar(stats['cpu'])}", True)
            field(e, f"{EM['ram']} RAM",
                  f"{ram_d['used']}/{ram_d['total']} MB ({ram_d['pct']:.1f}%)  {_bar(ram_d['pct'])}", True)
            field(e, f"{EM['disk']} Disk",   stats["disk"], True)
            field(e, f"{EM['clock']} Uptime", stats["uptime"], True)
            return await interaction.followup.send(embed=e, ephemeral=True)

        # ── REINSTALL ────────────────────────────────────────
        if action == "reinstall":
            if self.is_shared or self.is_admin:
                return await interaction.response.send_message(
                    embed=error_embed("Access Denied", "Only the VPS owner can reinstall."), ephemeral=True)
            ram_gb     = int(target_vps["ram"].replace("GB",""))
            cpu        = int(target_vps["cpu"])
            storage_gb = int(target_vps["storage"].replace("GB",""))

            class ConfirmView(discord.ui.View):
                def __init__(self_, pv, cn, oid, aidx, r, c, s, nid):
                    super().__init__(timeout=60)
                    self_.pv=pv; self_.cn=cn; self_.oid=oid
                    self_.aidx=aidx; self_.r=r; self_.c=c; self_.s=s; self_.nid=nid

                @discord.ui.button(label="⚠️ Confirm Wipe", style=discord.ButtonStyle.danger)
                async def confirm(self_, inter: discord.Interaction, btn):
                    await inter.response.defer(ephemeral=True)
                    try:
                        await inter.followup.send(embed=info_embed("Deleting", f"Removing `{self_.cn}`…"), ephemeral=True)
                        await execute_lxc(self_.cn, f"delete {self_.cn} --force", node_id=self_.nid)
                        view = ReinstallOSSelectView(self_.pv, self_.cn, self_.oid, self_.aidx, self_.r, self_.c, self_.s, self_.nid)
                        e = info_embed("Select OS", "Choose the new operating system.")
                        await inter.followup.send(embed=e, view=view, ephemeral=True)
                    except Exception as ex:
                        await inter.followup.send(embed=error_embed("Delete Failed", str(ex)), ephemeral=True)

                @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
                async def cancel(self_, inter: discord.Interaction, btn):
                    await inter.response.edit_message(embed=info_embed("Cancelled", "Reinstall cancelled."), view=None)

            conf = warn_embed("⚠️ Reinstall Warning",
                f"All data on `{cname}` will be **permanently erased**.\n\nAre you sure?")
            return await interaction.response.send_message(
                embed=conf,
                view=ConfirmView(self, cname, self.owner_id, actual_idx,
                                 ram_gb, cpu, storage_gb, node_id),
                ephemeral=True)

        # Defer for remaining actions
        await interaction.response.defer(ephemeral=True)

        # ── START ────────────────────────────────────────────
        if action == "start":
            try:
                await execute_lxc(cname, f"start {cname}", node_id=node_id)
                target_vps["status"] = "running"
                if suspended: target_vps["suspended"] = False
                save_vps_data()
                await apply_internal_permissions(cname, node_id)
                n_pf = await recreate_port_forwards(cname)
                e = success_embed("VPS Started", f"`{cname}` is now **running**!")
                field(e, "Port Forwards", f"Re-applied **{n_pf}** forward(s).", True)
                await interaction.followup.send(embed=e, ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(embed=error_embed("Start Failed", str(ex)), ephemeral=True)

        # ── STOP ─────────────────────────────────────────────
        elif action == "stop":
            try:
                await execute_lxc(cname, f"stop {cname}", timeout=120, node_id=node_id)
                target_vps["status"] = "stopped"
                save_vps_data()
                await interaction.followup.send(
                    embed=success_embed("VPS Stopped", f"`{cname}` has been stopped."), ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(embed=error_embed("Stop Failed", str(ex)), ephemeral=True)

        # ── RESTART ──────────────────────────────────────────
        elif action == "restart":
            try:
                await execute_lxc(cname, f"restart {cname}", timeout=120, node_id=node_id)
                target_vps["status"] = "running"
                if suspended: target_vps["suspended"] = False
                save_vps_data()
                await apply_internal_permissions(cname, node_id)
                n_pf = await recreate_port_forwards(cname)
                e = success_embed(f"{EM['bolt']} VPS Restarted", f"`{cname}` has been restarted.")
                field(e, "Port Forwards", f"Re-applied **{n_pf}** forward(s).", True)
                await interaction.followup.send(embed=e, ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(embed=error_embed("Restart Failed", str(ex)), ephemeral=True)

        # ── SSH (tmate) ──────────────────────────────────────
        elif action == "tmate":
            await interaction.followup.send(embed=info_embed("SSH", "Generating SSH session…"), ephemeral=True)
            try:
                # Install tmate if missing
                try:
                    await execute_lxc(cname, f"exec {cname} -- which tmate", node_id=node_id)
                except Exception:
                    # Preflight network check — if the container has no working
                    # IPv4/DNS route, apt will just fail with a wall of text.
                    # Detect that up front and give a clear, actionable error.
                    try:
                        await execute_lxc(cname,
                            f"exec {cname} -- sh -c 'curl -4 -sS -o /dev/null --max-time 8 http://archive.ubuntu.com'",
                            node_id=node_id, timeout=15)
                    except Exception:
                        return await interaction.followup.send(embed=error_embed(
                            "No Internet in Container",
                            f"`{cname}` can't reach the internet over IPv4 (DNS/route issue on the host's "
                            f"container network — not this bot).\nAn admin can run `{PREFIX}vps-netcheck {cname}` "
                            f"to diagnose it."), ephemeral=True)

                    await interaction.followup.send(embed=info_embed("Installing", "Installing `tmate`…"), ephemeral=True)
                    # Kill any locked apt, force IPv4 (avoids unreachable-IPv6 hangs), retry on failure
                    setup = (
                        "killall apt apt-get dpkg 2>/dev/null; "
                        "rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend /var/cache/apt/archives/lock; "
                        "dpkg --configure -a 2>/dev/null || true; "
                        "apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 update -y && "
                        "apt-get -o Acquire::ForceIPv4=true install -y tmate"
                    )
                    try:
                        await execute_lxc(cname,
                            f"exec {cname} -- bash -c {shlex.quote(setup)}",
                            node_id=node_id, timeout=240)
                    except Exception as ex:
                        return await interaction.followup.send(embed=error_embed(
                            "tmate Install Failed",
                            f"Package install failed even over IPv4.\n```\n{str(ex)[:500]}\n```"), ephemeral=True)
                    await interaction.followup.send(embed=success_embed("Installed", "`tmate` installed!"), ephemeral=True)

                sess = f"grim-{datetime.now().strftime('%H%M%S')}"
                await execute_lxc(cname,
                    f"exec {cname} -- tmate -S /tmp/{sess}.sock new-session -d",
                    node_id=node_id)
                await asyncio.sleep(3)
                ssh_url = await execute_lxc(cname,
                    f"exec {cname} -- tmate -S /tmp/{sess}.sock display -p '#{{tmate_ssh}}'",
                    node_id=node_id)
                ssh_url = ssh_url.strip() if ssh_url else ""
                if ssh_url:
                    e = make_embed("🔑 SSH Access", f"`{cname}`", C_SUCCESS)
                    field(e, "SSH Command", f"```\n{ssh_url}\n```")
                    field(e, f"{EM['warning']} Security", "Temporary link — do not share!", True)
                    try:
                        await interaction.user.send(embed=e)
                        await interaction.followup.send(
                            embed=success_embed("SSH Sent", "Check your **DMs** for the SSH command!"), ephemeral=True)
                    except discord.Forbidden:
                        await interaction.followup.send(embed=e, ephemeral=True)
                else:
                    await interaction.followup.send(embed=error_embed("SSH Failed", "No URL generated. Try again."), ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(embed=error_embed("SSH Error", str(ex)), ephemeral=True)

        # ── SSHx ─────────────────────────────────────────────
        elif action == "sshx":
            await interaction.followup.send(embed=info_embed("SSHx", "Setting up SSHx browser terminal…"), ephemeral=True)
            try:
                # Preflight network check first — avoids a confusing 60s timeout
                # when the container simply has no working internet route.
                try:
                    await execute_lxc(cname,
                        f"exec {cname} -- sh -c 'curl -4 -sS -o /dev/null --max-time 8 https://sshx.io'",
                        node_id=node_id, timeout=15)
                except Exception:
                    return await interaction.followup.send(embed=error_embed(
                        "No Internet in Container",
                        f"`{cname}` can't reach sshx.io over IPv4 (DNS/route issue on the host's container "
                        f"network — not this bot).\nAn admin can run `{PREFIX}vps-netcheck {cname}` to diagnose it."),
                        ephemeral=True)

                # Install curl if missing, then install sshx (force IPv4, retry once)
                curl_install = (
                    "which curl || ("
                    "killall apt apt-get dpkg 2>/dev/null; "
                    "rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend /var/cache/apt/archives/lock; "
                    "dpkg --configure -a 2>/dev/null || true; "
                    "apt-get -o Acquire::ForceIPv4=true -o Acquire::Retries=3 update -y && "
                    "apt-get -o Acquire::ForceIPv4=true install -y curl)"
                )
                await execute_lxc(cname,
                    f"exec {cname} -- sh -c {shlex.quote(curl_install)}",
                    node_id=node_id, timeout=240)

                sshx_installed = False
                last_err = None
                for attempt in range(2):
                    try:
                        await execute_lxc(cname,
                            f"exec {cname} -- sh -c 'curl -4 -sSf https://sshx.io/get | sh -s -- -q'",
                            node_id=node_id, timeout=100)
                        sshx_installed = True
                        break
                    except Exception as ex:
                        last_err = ex
                if not sshx_installed:
                    return await interaction.followup.send(embed=error_embed(
                        "SSHx Install Failed",
                        f"Couldn't install sshx after 2 attempts.\n```\n{str(last_err)[:400]}\n```"), ephemeral=True)

                # Start sshx detached in the background so it KEEPS RUNNING
                # after this command returns (the old `timeout 12 sshx | grep`
                # approach killed the session the instant the link was
                # captured, so the link never actually worked). Also route
                # through execute_lxc() instead of a raw local subprocess —
                # a raw `lxc exec` on the bot's own host silently does nothing
                # useful when the VPS lives on a remote node.
                start_script = (
                    "pkill sshx 2>/dev/null; rm -f /tmp/sshx.log; "
                    "setsid nohup sshx > /tmp/sshx.log 2>&1 < /dev/null & "
                    "sleep 3; cat /tmp/sshx.log 2>/dev/null || true"
                )
                result = await execute_lxc(cname,
                    f"exec {cname} -- sh -c {shlex.quote(start_script)}",
                    node_id=node_id, timeout=20)
                sshx_out = result if isinstance(result, str) else ""
                match = re.search(r"https://sshx\.io[^\s]*", sshx_out)
                sshx_link = match.group(0) if match else ""

                e = make_embed("🌐 SSHx Terminal", f"`{cname}`", C_INFO)
                if sshx_link and "sshx.io" in sshx_link:
                    field(e, "🔗 Browser Link", f"```\n{sshx_link}\n```")
                else:
                    field(e, "ℹ️ Note", "Run `sshx` manually inside the VPS to get the link.")
                field(e, f"{EM['warning']} Security", "Do not share this link with anyone!", True)

                try:
                    await interaction.user.send(embed=e)
                    await interaction.followup.send(
                        embed=success_embed("SSHx Sent", "Check your **DMs** for the SSHx link!"), ephemeral=True)
                except discord.Forbidden:
                    await interaction.followup.send(embed=e, ephemeral=True)
            except Exception as ex:
                await interaction.followup.send(embed=error_embed("SSHx Error", str(ex)), ephemeral=True)

        # ── CMD ──────────────────────────────────────────────
        elif action == "cmd":
            panel_e = make_embed("💻 CMD Panel", f"`{cname}`", C_GOLD)
            field(panel_e, "⌨️ Type Command", "Run a single Linux command.")
            field(panel_e, "📄 Upload Script", "Upload a `.sh` script and run it.")
            panel_v = CMDPanelView(cname, node_id)
            return await interaction.followup.send(embed=panel_e, view=panel_v, ephemeral=True)

        # Refresh embed
        new_emb = await self._vps_embed(self.selected_index, bot_client=interaction.client)
        await interaction.edit_original_response(embed=new_emb, view=self)


# ════════════════════════════════════════════════════════
#  NODE SELECT VIEW  (for admin VPS creation)
# ════════════════════════════════════════════════════════

class OSSelectView(discord.ui.View):
    """Select OS after RAM/CPU/Disk are picked."""
    def __init__(self, ram, cpu, disk, user, ctx, node_id, auto_ports: int = 0, trial_seconds: int = 0,
                 plan_name: str = None, renewal_days: int = 0, renewal_price: int = 0):
        super().__init__(timeout=300)
        self.ram = ram; self.cpu = cpu; self.disk = disk
        self.user = user; self.ctx = ctx; self.node_id = node_id
        self.auto_ports = auto_ports
        self.trial_seconds = trial_seconds
        self.plan_name = plan_name; self.renewal_days = renewal_days; self.renewal_price = renewal_price
        sel = discord.ui.Select(
            placeholder=f"{EM['vps']} Choose Operating System…",
            options=[discord.SelectOption(label=o["label"], value=o["value"]) for o in OS_OPTIONS])
        sel.callback = self.select_os
        self.add_item(sel)

    async def select_os(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "custom":
            return await interaction.response.send_modal(CustomOSCreateModal(self))
        for i in self.children: i.disabled = True
        e = info_embed("Creating VPS…",
            f"Deploying **{val}** for {self.user.mention} — please wait…")
        await interaction.response.edit_message(embed=e, view=self)
        await self.do_create(interaction, val)

    async def do_create(self, interaction: discord.Interaction, os_version: str):
        is_custom  = os_version.startswith("custom:")
        custom_url = os_version[7:] if is_custom else None
        display_os = f"Custom ({custom_url})" if is_custom else os_version
        ram_mb = self.ram * 1024

        from core import vps_data, save_vps_data, BOT_NAME
        user_id = str(self.user.id)
        vps_count = sum(len(v) for v in vps_data.values()) + 1
        ts = int(datetime.now().timestamp() * 1000)
        cname = f"vm-{BOT_NAME.lower().replace(' ','-')}-vps-{self.user.id}-{ts}"

        try:
            if is_custom:
                node = get_node(self.node_id)
                if not node or not node.get("is_local"):
                    raise Exception(
                        "Custom OS download links currently only work when deploying to the **local** "
                        "node (importing an image needs direct disk/LXD access on that node). Pick the "
                        "local node, or use a preset OS for remote nodes.")

                img_file = f"/tmp/custom_os_{cname}.tar.gz"
                image_alias = f"custom-{cname}"
                # Force IPv4 (avoids the same IPv6-unreachable hangs seen with
                # apt/curl elsewhere) and retry once; fall back to curl if
                # wget isn't installed on this host.
                dl_cmd = (
                    f"("
                    f"wget -4 -q --tries=2 --timeout=60 -O {img_file} {shlex.quote(custom_url)} "
                    f"|| curl -4 -fsSL --retry 2 --max-time 90 -o {img_file} {shlex.quote(custom_url)}"
                    f") && lxc image import {img_file} --alias {image_alias}"
                )
                proc = await asyncio.create_subprocess_shell(dl_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                try:
                    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                except asyncio.TimeoutError:
                    proc.kill(); await proc.wait()
                    raise Exception("Download/import timed out after 300s — the link may be too slow or unreachable.")
                finally:
                    # Always clean the temp file regardless of success/failure
                    await asyncio.create_subprocess_shell(f"rm -f {img_file}")
                if proc.returncode != 0:
                    raise Exception(
                        f"Custom OS import failed.\n```\n{stderr.decode()[:400]}\n```\n"
                        f"Note: the URL must point to a **unified LXD image tarball** "
                        f"(built with distrobuilder / from images.linuxcontainers.org), "
                        f"not a generic ISO, cloud image, or plain rootfs archive.")
                lxc_os = image_alias
            else:
                lxc_os = os_version

            await execute_lxc(cname, f"init {lxc_os} {cname} -s {DEFAULT_STORAGE_POOL}", node_id=self.node_id)
            await execute_lxc(cname, f"config set {cname} limits.memory {ram_mb}MB",    node_id=self.node_id)
            await execute_lxc(cname, f"config set {cname} limits.cpu {self.cpu}",       node_id=self.node_id)
            await execute_lxc(cname, f"config device set {cname} root size={self.disk}GB", node_id=self.node_id)
            await apply_lxc_config(cname, self.node_id)
            await execute_lxc(cname, f"start {cname}", node_id=self.node_id)
            await apply_internal_permissions(cname, self.node_id)

            if is_custom:
                # The alias was a one-off for this container — delete it now
                # that the container has its own copy, so disk usage doesn't
                # grow unbounded every time someone imports a custom OS.
                try:
                    await execute_lxc(cname, f"image delete {image_alias}", node_id=self.node_id)
                except Exception:
                    pass

            config_str = f"{self.ram}GB RAM / {self.cpu} CPU / {self.disk}GB Disk"
            new_vps = {
                "user_id": user_id, "node_id": self.node_id,
                "container_name": cname, "ram": f"{self.ram}GB", "cpu": str(self.cpu),
                "storage": f"{self.disk}GB", "config": config_str,
                "os_version": display_os, "status": "running",
                "suspended": False, "whitelisted": False,
                "created_at": datetime.now().isoformat(),
                "shared_with": [], "suspension_history": [], "id": None,
            }
            if user_id not in vps_data: vps_data[user_id] = []
            vps_data[user_id].append(new_vps)
            save_vps_data()

            # Role
            if self.ctx.guild:
                role = await get_or_create_vps_role(self.ctx.guild)
                if role:
                    try: await self.user.add_roles(role)
                    except discord.Forbidden: pass

            # Optional included ports (from a plan/giveaway that has some
            # configured) — entirely skippable, only runs if auto_ports > 0
            ports_created = 0
            if self.auto_ports and self.auto_ports > 0:
                try:
                    ports_created = await auto_setup_ports(user_id, cname, self.node_id, self.auto_ports)
                except Exception as pe:
                    logger.error(f"Auto port setup failed for {cname}: {pe}")

            # Trial VPS — register the expiry so the background watcher can
            # auto-suspend it later (entirely skipped if trial_seconds == 0)
            trial_expiry_line = ""
            if self.trial_seconds and self.trial_seconds > 0:
                add_trial_vps(user_id, cname, self.node_id, self.trial_seconds)
                hrs = self.trial_seconds // 3600
                trial_expiry_line = f"⏳ This is a **trial VPS** — auto-suspends in **{hrs}h** (or sooner)."

            # Renewal subscription — only for paid plans with a renewal
            # period configured (renewal_days > 0). Skipped entirely otherwise.
            renewal_line = ""
            if self.renewal_days and self.renewal_days > 0:
                create_subscription(cname, user_id, "lxc", self.plan_name or "Custom",
                                     self.renewal_days, self.renewal_price)
                renewal_line = (f"📅 Renews every **{self.renewal_days} day(s)** for "
                                 f"**{self.renewal_price:,}** {EM['coin']} — use `{PREFIX}renew {cname}` before it expires.")

            e = success_embed("VPS Created!", f"{EM['vps']} Container deployed for {self.user.mention}")
            field(e, "VPS ID",    f"#{vps_count}", True)
            field(e, "Container", f"`{cname}`", True)
            field(e, "Node",      get_node(self.node_id)["name"], True)
            field(e, "Resources", f"**RAM** {self.ram}GB  |  **CPU** {self.cpu}c  |  **Disk** {self.disk}GB")
            field(e, "OS",        display_os, True)
            field(e, "Features",  "Docker-ready · Nesting · Privileged · FUSE", True)
            if ports_created:
                field(e, f"{EM['port']} Ports Included", f"**{ports_created}** port(s) auto-forwarded — see `{PREFIX}ports`", True)
            if trial_expiry_line:
                field(e, f"{EM['clock']} Trial", trial_expiry_line)
            if renewal_line:
                field(e, f"{EM['clock']} Renewal", renewal_line)
            await interaction.followup.send(embed=e)

            # DM user — includes a nudge to leave feedback once they've tried it
            dm = success_embed("Your VPS is Ready!", f"**{BOT_NAME}** has deployed your VPS!")
            field(dm, "Details",
                  f"**ID** #{vps_count} | **Container** `{cname}`\n"
                  f"**Config** {config_str} | **OS** {display_os}")
            field(dm, "Usage", f"Use `{PREFIX}manage` to start, stop, SSH or reinstall your VPS.")
            if trial_expiry_line:
                field(dm, f"{EM['clock']} Trial", trial_expiry_line)
            if renewal_line:
                field(dm, f"{EM['clock']} Renewal", renewal_line)
            field(dm, f"{EM['gold']} Enjoying it?", f"Once you've tried it out, drop us a `{PREFIX}vouch <1-5> <message>` — it really helps!")
            try: await self.user.send(embed=dm)
            except discord.Forbidden: pass
            self.stop()
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Creation Failed", str(ex)))
            self.stop()


class CustomOSCreateModal(discord.ui.Modal, title="✨ Custom OS Download Link"):
    link = discord.ui.TextInput(
        label="OS Download URL (.tar.gz / .tar.xz)",
        placeholder="https://example.com/custom-os.tar.gz",
        required=True, max_length=500)

    def __init__(self, parent: OSSelectView):
        super().__init__()
        self.parent = parent

    async def on_submit(self, interaction: discord.Interaction):
        url = self.link.value.strip()
        if not url.startswith("http"):
            return await interaction.response.send_message(
                embed=error_embed("Invalid URL", "Must start with http:// or https://"), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.parent.do_create(interaction, f"custom:{url}")


class NodeSelectView(discord.ui.View):
    """Admin chooses node → then OS selection. Includes an 'Auto (Least
    Loaded)' option that picks the node with the most free VPS capacity."""
    def __init__(self, ram, cpu, disk, user, ctx, auto_ports: int = 0, trial_seconds: int = 0,
                 plan_name: str = None, renewal_days: int = 0, renewal_price: int = 0):
        super().__init__(timeout=180)
        self.ram = ram; self.cpu = cpu; self.disk = disk
        self.user = user; self.ctx = ctx; self.auto_ports = auto_ports
        self.trial_seconds = trial_seconds
        self.plan_name = plan_name; self.renewal_days = renewal_days; self.renewal_price = renewal_price
        nodes = get_nodes()
        opts  = [discord.SelectOption(
            label="🎯 Auto (Least Loaded)",
            description="Let the bot pick the emptiest node",
            value="auto")]
        opts += [discord.SelectOption(
            label=f"{n['name']} ({n['location']})",
            description=f"{get_current_vps_count(n['id'])}/{n['total_vps']} VPS",
            value=str(n["id"])) for n in nodes]
        sel = discord.ui.Select(placeholder=f"{EM['node']} Select deployment node…", options=opts)
        sel.callback = self.pick_node
        self.add_item(sel)

    async def pick_node(self, interaction: discord.Interaction):
        raw = interaction.data["values"][0]
        if raw == "auto":
            nodes = get_nodes()
            if not nodes:
                for i in self.children: i.disabled = True
                return await interaction.response.edit_message(
                    embed=error_embed("No Nodes", "No nodes are configured."), view=self)
            # Pick the node with the most free capacity (total_vps - current usage)
            best = max(nodes, key=lambda n: n["total_vps"] - get_current_vps_count(n["id"]))
            node_id = best["id"]
        else:
            node_id = int(raw)
        for i in self.children: i.disabled = True
        node = get_node(node_id)
        e = info_embed("Select OS", f"Node: **{node['name']}**\nNow choose an operating system.")
        view = OSSelectView(self.ram, self.cpu, self.disk, self.user, self.ctx, node_id,
                             auto_ports=self.auto_ports, trial_seconds=self.trial_seconds,
                             plan_name=self.plan_name, renewal_days=self.renewal_days,
                             renewal_price=self.renewal_price)
        await interaction.response.edit_message(embed=e, view=view)


# ════════════════════════════════════════════════════════
#  HELP VIEW
# ════════════════════════════════════════════════════════

class HelpView(discord.ui.View):
    """
    Dynamic help menu — built straight from the live bot.commands list so it
    can never fall out of sync / hide commands again. Each command is tagged
    into a category via CATEGORY_MAP below; anything NOT explicitly tagged
    (including any brand-new command added later) automatically falls into
    the "🗂️ Other" category instead of silently disappearing.
    """

    CATEGORY_LABELS = {
        "user":   "👤 User",
        "shop":   "🛒 Shop & Offers",
        "invite": "📨 Invites",
        "boost":  "🚀 Boost",
        "admin":  "🛡️ Admin",
        "nodes":  "🌐 Nodes",
        "system": "⚙️ System",
        "other":  "🗂️ Other",
    }

    # command name -> category key
    CATEGORY_MAP = {
        # user
        "myvps": "user", "manage": "user", "manage-shared": "user",
        "share-user": "user", "share-ruser": "user", "vpsinfo": "user",
        "ports": "user",
        # shop / offers
        "shop": "shop", "offerlist": "shop", "offers": "shop",
        "plans": "shop", "plan-add": "admin", "plan-remove": "admin",
        "buy-plan": "shop", "freeplans": "shop",
        "freeplan-add": "admin", "inviteplan-add": "admin",
        "boostplan-add": "admin", "freeplan-remove": "admin",
        "claim-freeplan": "shop",
        "coins": "shop", "coin-add": "admin", "coin-remove": "admin",
        "coin-set": "admin", "coin-leaderboard": "shop",
        "create-giftcode": "admin", "giftcode-create": "admin", "gencode": "admin",
        "redeem": "shop", "giftcode-list": "admin", "giftcodes": "admin",
        "giftcode-delete": "admin", "trialplan-add": "admin", "kvmplan-add": "admin",
        # KVM
        "node-kvm-enable": "admin", "node-kvm-disable": "admin", "create-kvm": "admin",
        "kvm-check": "admin",
        "kvm-list": "user", "kvm-start": "user", "kvm-stop": "user", "kvm-restart": "user",
        "kvm-delete": "admin", "kvm-port-add": "user", "kvm-port-remove": "user",
        "kvm-info": "user", "renew": "shop", "my-usage": "user", "myusage": "user",
        "ssh-fixer": "user", "reset-password": "user", "passwd-reset": "user",
        "install-tool": "user",
        # invites
        "invites": "invite", "invite-add": "admin", "invite-remove": "admin",
        "invite-leaderboard": "invite",
        # boost
        "check-boost": "boost", "boost-set": "admin", "boosters": "boost",
        "boost-give": "admin", "boost-tracker": "boost", "resetboost": "admin",
        # giveaways
        "giveaway-start": "other", "gstart": "other",
        "giveaway-vps": "other", "gstart-vps": "other",
        "giveaway-end": "other", "gend": "other",
        "giveaway-reroll": "other", "greroll": "other",
        "giveaway-list": "other", "glist": "other",
        "my-claims": "shop", "sync-invites": "admin", "sync-boosts": "admin",
        # admin / vps ops
        "create": "admin", "delete-vps": "admin", "add-resources": "admin",
        "suspend-vps": "admin", "unsuspend-vps": "admin", "whitelist-vps": "admin",
        "apply-permissions": "admin", "restart-vps": "admin", "clone-vps": "admin",
        "vps-stats": "admin", "vps-logs": "admin", "vps-processes": "admin",
        "exec": "admin", "suspension-logs": "admin",
        "ports-add-user": "admin", "ports-remove-user": "admin", "ports-revoke": "admin",
        "vps-list": "admin", "list-all": "admin", "status": "admin",
        "admin-stats": "admin", "userinfo": "admin", "admin-add": "admin",
        "admin-remove": "admin", "admin-list": "admin",
        "stop-vps-all": "admin", "resource-check": "admin", "vps-netcheck": "admin",
        "snapshot": "admin", "list-snapshots": "admin", "restore-snapshot": "admin",
        "lxc-list": "admin", "dm": "admin",
        "autoresponder-add": "admin", "ar-add": "admin",
        "autoresponder-list": "system", "ar-list": "system",
        "autoresponder-remove": "admin", "ar-remove": "admin",
        "vouch": "shop", "vouches": "shop", "vouch-delete": "admin",
        "overview": "admin", "dashboard": "admin",
        # nodes
        "node": "nodes", "node-add": "nodes", "node-check": "nodes",
        "migrate-vps": "nodes",
        # system
        "ping": "system", "uptime": "system", "developer": "system",
        "set-prefix": "admin", "set-threshold": "admin", "thresholds": "admin",
        "set-status": "admin", "set-presence": "admin", "serverstats": "admin",
        "botinfo": "system", "serverinfo": "system",
        "help": "system",
    }

    ADMIN_ONLY_HINTS = {
        "admin", "nodes",
    }

    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx     = ctx
        self.bot     = ctx.bot
        self.current = "user"
        self._build_select()

    def _grouped(self) -> Dict[str, list]:
        groups: Dict[str, list] = {k: [] for k in self.CATEGORY_LABELS}
        for cmd in sorted(self.bot.commands, key=lambda c: c.name):
            if cmd.hidden:
                continue
            key = self.CATEGORY_MAP.get(cmd.name, "other")
            desc = (cmd.help or "").strip().splitlines()[0] if cmd.help else "No description."
            usage = f"{cmd.name} {cmd.signature}".strip()
            groups[key].append((usage, desc))
        return groups

    def _build_select(self):
        self.clear_items()
        groups = self._grouped()
        opts = [
            discord.SelectOption(
                label=f"{label} ({len(groups.get(key, []))})",
                value=key,
                default=(key == self.current),
            )
            for key, label in self.CATEGORY_LABELS.items()
            if groups.get(key)
        ]
        sel = discord.ui.Select(placeholder="📖 Browse help categories…", options=opts)
        sel.callback = self._pick
        self.add_item(sel)

    async def _pick(self, interaction: discord.Interaction):
        self.current = interaction.data["values"][0]
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    def _build_embed(self) -> discord.Embed:
        groups = self._grouped()
        cmds = groups.get(self.current, [])
        label = self.CATEGORY_LABELS.get(self.current, self.current)
        e = make_embed(f"Help — {label}",
            f"Prefix: `{PREFIX}`  |  Mention prefix: `@{BOT_NAME}`\n"
            f"Use `{PREFIX}developer` for bot info • `{PREFIX}offerlist` for all VPS offers.", C_GOLD)
        if not cmds:
            field(e, "Commands", "No commands in this category.")
        else:
            lines = [f"`{PREFIX}{usage}` — {desc}" for usage, desc in cmds]
            # Split into chunks so no single field exceeds Discord's 1024 char limit
            chunk, size = [], 0
            chunk_no = 1
            for line in lines:
                if size + len(line) + 1 > 950:
                    field(e, f"Commands ({chunk_no})", "\n".join(chunk))
                    chunk, size = [], 0
                    chunk_no += 1
                chunk.append(line); size += len(line) + 1
            if chunk:
                field(e, f"Commands ({chunk_no})" if chunk_no > 1 else "Commands", "\n".join(chunk))
        total = sum(len(v) for v in groups.values())
        e.set_footer(text=f"{FOOTER_TEXT} • {total} commands total • "
                          f"{EM['dev']} Dev: {CFG['developer_info']['name']}")
        return e

class KVMPortForwardModal(discord.ui.Modal, title="🔌 Add Port Forward"):
    guest_port = discord.ui.TextInput(label="Port inside the VM (guest port)", placeholder="e.g. 80", max_length=5)
    host_port = discord.ui.TextInput(label="Public port (leave blank to auto-pick)", required=False, max_length=5)

    def __init__(self, view: "KVMManageView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            gp = int(str(self.guest_port))
            hp = int(str(self.host_port)) if str(self.host_port).strip() else allocate_kvm_port()
            if not (1 <= gp <= 65535) or not (1 <= hp <= 65535):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(
                embed=error_embed("Invalid Port", "Ports must be numbers 1-65535."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        vps = self.parent_view.current_vm()
        try:
            add_kvm_port_forward_record(vps["container_name"], hp, gp)
            await kvm_restart(vps["node_id"], get_kvm_vps(vps["container_name"]))
            await interaction.followup.send(embed=success_embed(f"{EM['port']} Port Forwarded",
                f"`{YOUR_SERVER_IP}:{hp}` → guest port `{gp}` (VM restarted to apply)."), ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Failed", str(ex)), ephemeral=True)


class KVMPasswordModal(discord.ui.Modal, title="🔑 Reset Password"):
    new_password = discord.ui.TextInput(label="New password", placeholder="Leave blank for a random one", required=False)

    def __init__(self, view: "KVMManageView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        vps = self.parent_view.current_vm()
        pwd = str(self.new_password).strip() or generate_giftcode("PW").replace("-", "")
        try:
            script = script_reset_password(vps["username"], pwd)
            await run_in_kvm_guest(vps["node_id"], vps, script, timeout=30)
            conn = get_db(); cur = conn.cursor()
            cur.execute("UPDATE kvm_vps SET password = ? WHERE container_name = ?", (pwd, vps["container_name"]))
            conn.commit(); conn.close()
            await interaction.followup.send(embed=success_embed("Password Reset", f"New password: `{pwd}`"), ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Failed", str(ex)), ephemeral=True)


class KVMToolSelectView(discord.ui.View):
    """Ephemeral follow-up select for one-click tool installs."""
    def __init__(self, vps: Dict):
        super().__init__(timeout=120)
        self.vps = vps
        opts = [discord.SelectOption(label=info["label"], value=key) for key, info in TOOL_SCRIPTS.items()]
        sel = discord.ui.Select(placeholder="Choose a tool to install…", options=opts)
        sel.callback = self.pick
        self.add_item(sel)

    async def pick(self, interaction: discord.Interaction):
        tool = interaction.data["values"][0]
        info = TOOL_SCRIPTS[tool]
        await interaction.response.edit_message(
            embed=info_embed(f"Installing {info['label']}…", "This can take a few minutes…"), view=None)
        try:
            result = str(await run_in_kvm_guest(self.vps["node_id"], self.vps, info["script"], timeout=400))
            if "TOOL_PARTIAL_OK" in result:
                await interaction.followup.send(embed=warn_embed(f"{info['label']} — One More Step",
                    f"Prerequisites installed. SSH in and run `/root/ptero-installer.sh` to finish."), ephemeral=True)
            elif "TOOL_OK" in result:
                await interaction.followup.send(embed=success_embed(f"{info['label']} Installed!", ""), ephemeral=True)
            else:
                await interaction.followup.send(embed=warn_embed("Finished — unclear result", f"```\n{result[:400]}\n```"), ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Install Failed", str(ex)), ephemeral=True)


class KVMManageView(discord.ui.View):
    """Interactive manage panel for KVM VMs — mirrors the LXC ManageView."""
    def __init__(self, user_id: str, vms: list, is_admin: bool = False):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.vms = vms
        self.is_admin = is_admin
        self.idx = 0
        self._build_buttons()

    def current_vm(self) -> Dict:
        return get_kvm_vps(self.vms[self.idx]["container_name"]) or self.vms[self.idx]

    def _build_buttons(self):
        self.clear_items()
        if len(self.vms) > 1:
            prev_b = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=2)
            next_b = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=2)
            prev_b.callback = self._prev; next_b.callback = self._next
            self.add_item(prev_b); self.add_item(next_b)

        defs = [
            ("▶ Start",    discord.ButtonStyle.success,   "start",  0),
            ("⏸ Stop",     discord.ButtonStyle.secondary, "stop",   0),
            ("🔁 Restart", discord.ButtonStyle.danger,     "restart", 0),
            ("🔌 Port Forward", discord.ButtonStyle.primary, "port", 1),
            ("🛠️ Tools",   discord.ButtonStyle.primary,   "tools",  1),
            ("🔑 Reset Password", discord.ButtonStyle.secondary, "resetpw", 1),
        ]
        for label, style, action, row in defs:
            btn = discord.ui.Button(label=label, style=style, row=row)
            btn.callback = self._make_cb(action)
            self.add_item(btn)
        if self.is_admin:
            del_btn = discord.ui.Button(label="🗑️ Delete", style=discord.ButtonStyle.danger, row=2)
            del_btn.callback = self._delete
            self.add_item(del_btn)

    async def _prev(self, interaction):
        self.idx = (self.idx - 1) % len(self.vms)
        self._build_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(), view=self)

    async def _next(self, interaction):
        self.idx = (self.idx + 1) % len(self.vms)
        self._build_buttons()
        await interaction.response.edit_message(embed=await self.get_embed(), view=self)

    def _make_cb(self, action):
        async def cb(interaction: discord.Interaction):
            await self._action(interaction, action)
        return cb

    async def _action(self, interaction: discord.Interaction, action: str):
        vps = self.current_vm()
        if action == "port":
            return await interaction.response.send_modal(KVMPortForwardModal(self))
        if action == "resetpw":
            return await interaction.response.send_modal(KVMPasswordModal(self))
        if action == "tools":
            return await interaction.response.send_message(
                embed=info_embed("Install a Tool", "Pick one below:"),
                view=KVMToolSelectView(vps), ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            if action == "start":
                await kvm_start(vps["node_id"], vps)
                await interaction.followup.send(embed=success_embed("Started", f"`{vps['container_name']}` is running."), ephemeral=True)
            elif action == "stop":
                await kvm_stop(vps["node_id"], vps)
                await interaction.followup.send(embed=success_embed("Stopped", f"`{vps['container_name']}` stopped."), ephemeral=True)
            elif action == "restart":
                await kvm_restart(vps["node_id"], vps)
                await interaction.followup.send(embed=success_embed("Restarted", f"`{vps['container_name']}` restarted."), ephemeral=True)
            await interaction.edit_original_response(embed=await self.get_embed(), view=self)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Action Failed", str(ex)), ephemeral=True)

    async def _delete(self, interaction: discord.Interaction):
        vps = self.current_vm()
        await interaction.response.defer(ephemeral=True)
        try:
            await kvm_delete(vps["node_id"], vps)
            self.vms.pop(self.idx)
            if not self.vms:
                for c in self.children: c.disabled = True
                return await interaction.followup.send(embed=success_embed("Deleted", "VM removed. No VMs left."), ephemeral=True)
            self.idx = min(self.idx, len(self.vms) - 1)
            self._build_buttons()
            await interaction.edit_original_response(embed=await self.get_embed(), view=self)
            await interaction.followup.send(embed=success_embed("Deleted", f"`{vps['container_name']}` removed."), ephemeral=True)
        except Exception as ex:
            await interaction.followup.send(embed=error_embed("Delete Failed", str(ex)), ephemeral=True)

    async def get_embed(self) -> discord.Embed:
        vps = self.current_vm()
        osinfo = KVM_OS_OPTIONS.get(vps["os_key"], {"label": vps["os_key"]})
        live = "🟢 running" if await kvm_is_running(vps["node_id"], vps) else "🔴 stopped"
        forwards = json.loads(vps["port_forwards"])
        e = make_embed(f"{EM['vps']} {vps['container_name']} ({self.idx+1}/{len(self.vms)})", "", C_GOLD)
        field(e, "OS", osinfo["label"], True)
        field(e, "Status", live, True)
        field(e, "Node", get_node(vps["node_id"])["name"], True)
        field(e, "Resources", f"**RAM** {vps['memory_mb']}MB | **CPU** {vps['cpus']}c | **Disk** {vps['disk_gb']}GB")
        field(e, "SSH", f"`ssh {vps['username']}@{YOUR_SERVER_IP} -p {vps['ssh_port']}`\n**Password:** `{vps['password']}`")
        if forwards:
            field(e, f"{EM['port']} Extra Ports",
                  "\n".join(f"`{YOUR_SERVER_IP}:{f['host']}` → guest `{f['guest']}`" for f in forwards))
        sub = get_subscription(vps["container_name"])
        if sub:
            field(e, f"{EM['clock']} Renewal", f"Expires **{sub['expires_at'][:10]}** — {sub['renewal_price']:,} coins/{sub['renewal_days']}d")
        return e

    async def get_initial_embed(self) -> discord.Embed:
        return await self.get_embed()

class GiveawayView(discord.ui.View):
    """Posted on a giveaway announcement. Persists across restarts if
    re-registered via bot.add_view(GiveawayView(gid)) in on_ready — the
    custom_id encodes the giveaway id so it keeps working either way."""
    def __init__(self, giveaway_id: int):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id
        btn = discord.ui.Button(
            label="🎉 Join Giveaway", style=discord.ButtonStyle.success,
            custom_id=f"grimvps_giveaway_join_{giveaway_id}")
        btn.callback = self.join
        self.add_item(btn)

    async def join(self, interaction: discord.Interaction):
        gw = get_giveaway(self.giveaway_id)
        if not gw or gw["ended"]:
            return await interaction.response.send_message(
                embed=error_embed("Giveaway Ended", "This giveaway has already ended."), ephemeral=True)
        added = add_giveaway_entry(self.giveaway_id, str(interaction.user.id))
        if added:
            count = get_giveaway_entry_count(self.giveaway_id)
            await interaction.response.send_message(
                embed=success_embed("🎉 You're In!", f"Good luck! **{count}** total entries so far."),
                ephemeral=True)
        else:
            await interaction.response.send_message(
                embed=info_embed("Already Joined", "You've already entered this giveaway!"), ephemeral=True)
