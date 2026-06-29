"""
╔══════════════════════════════════════════════════════════════╗
║          GRIM VPS MANAGER  —  VIEWS.PY                      ║
║   Discord UI: Buttons · Selects · Modals · Panels            ║
╚══════════════════════════════════════════════════════════════╝
"""
import asyncio, shlex
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from core import (
    BOT_NAME, PREFIX, EM, CFG, OS_OPTIONS, YOUR_SERVER_IP,
    DEFAULT_STORAGE_POOL, DEVELOPER_ID, OWNER_ID, MAIN_ADMIN_ID,
    vps_data, admin_data, logger,
    get_node, get_nodes, find_node_id_for_container, get_current_vps_count,
    get_or_create_vps_role, apply_lxc_config, apply_internal_permissions,
    recreate_port_forwards, execute_lxc, get_container_stats,
    save_vps_data, get_user_allocation, get_user_used_ports, get_user_forwards,
    create_port_forward, remove_port_forward, get_available_host_port,
    success_embed, error_embed, info_embed, warn_embed, field, make_embed,
    C_GOLD, C_SUCCESS, C_ERROR, C_INFO, _bar,
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
            ("🔑 SSH",    discord.ButtonStyle.primary,    "tmate",  0),
            ("🌐 SSHx",   discord.ButtonStyle.primary,    "sshx",   0),
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

        # ── SSH (tmate) ──────────────────────────────────────
        elif action == "tmate":
            await interaction.followup.send(embed=info_embed("SSH", "Generating SSH session…"), ephemeral=True)
            try:
                # Install tmate if missing
                try:
                    await execute_lxc(cname, f"exec {cname} -- which tmate", node_id=node_id)
                except Exception:
                    await interaction.followup.send(embed=info_embed("Installing", "Installing `tmate`…"), ephemeral=True)
                    # Kill any locked apt and install
                    setup = (
                        "killall apt apt-get dpkg 2>/dev/null; "
                        "rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend /var/cache/apt/archives/lock; "
                        "dpkg --configure -a 2>/dev/null || true; "
                        "apt-get update -y && apt-get install -y tmate"
                    )
                    await execute_lxc(cname,
                        f"exec {cname} -- bash -c {shlex.quote(setup)}",
                        node_id=node_id, timeout=180)
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
                # Install curl if missing, then install sshx
                curl_install = (
                    "which curl || ("
                    "killall apt apt-get dpkg 2>/dev/null; "
                    "rm -f /var/lib/apt/lists/lock /var/lib/dpkg/lock-frontend /var/cache/apt/archives/lock; "
                    "dpkg --configure -a 2>/dev/null || true; "
                    "apt-get update -y && apt-get install -y curl)"
                )
                await execute_lxc(cname,
                    f"exec {cname} -- sh -c {shlex.quote(curl_install)}",
                    node_id=node_id, timeout=180)
                await execute_lxc(cname,
                    f"exec {cname} -- sh -c 'curl -sSf https://sshx.io/get | sh -s -- -q'",
                    node_id=node_id, timeout=60)

                # Start sshx and capture link
                await execute_lxc(cname,
                    f"exec {cname} -- sh -c 'pkill sshx 2>/dev/null; true'",
                    node_id=node_id)
                await asyncio.sleep(1)

                proc = await asyncio.create_subprocess_shell(
                    f"lxc exec {cname} -- sh -c \"timeout 12 sshx 2>&1 | grep -o 'https://sshx.io[^ ]*' | head -1\"",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                sshx_out, _ = await asyncio.wait_for(proc.communicate(), timeout=20)
                sshx_link   = sshx_out.decode().strip()

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
    def __init__(self, ram, cpu, disk, user, ctx, node_id):
        super().__init__(timeout=300)
        self.ram = ram; self.cpu = cpu; self.disk = disk
        self.user = user; self.ctx = ctx; self.node_id = node_id
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
                img_file = f"/tmp/custom_os_{cname}.tar.gz"
                dl_cmd = (f"wget -q -O {img_file} '{custom_url}' "
                          f"&& lxc image import {img_file} --alias custom-{cname} "
                          f"&& rm -f {img_file}")
                proc = await asyncio.create_subprocess_shell(dl_cmd,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if proc.returncode != 0:
                    raise Exception(f"Custom OS import failed: {stderr.decode()[:300]}")
                lxc_os = f"custom-{cname}"
            else:
                lxc_os = os_version

            await execute_lxc(cname, f"init {lxc_os} {cname} -s {DEFAULT_STORAGE_POOL}", node_id=self.node_id)
            await execute_lxc(cname, f"config set {cname} limits.memory {ram_mb}MB",    node_id=self.node_id)
            await execute_lxc(cname, f"config set {cname} limits.cpu {self.cpu}",       node_id=self.node_id)
            await execute_lxc(cname, f"config device set {cname} root size={self.disk}GB", node_id=self.node_id)
            await apply_lxc_config(cname, self.node_id)
            await execute_lxc(cname, f"start {cname}", node_id=self.node_id)
            await apply_internal_permissions(cname, self.node_id)

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

            e = success_embed("VPS Created!", f"{EM['vps']} Container deployed for {self.user.mention}")
            field(e, "VPS ID",    f"#{vps_count}", True)
            field(e, "Container", f"`{cname}`", True)
            field(e, "Node",      get_node(self.node_id)["name"], True)
            field(e, "Resources", f"**RAM** {self.ram}GB  |  **CPU** {self.cpu}c  |  **Disk** {self.disk}GB")
            field(e, "OS",        display_os, True)
            field(e, "Features",  "Docker-ready · Nesting · Privileged · FUSE", True)
            await interaction.followup.send(embed=e)

            # DM user
            dm = success_embed("Your VPS is Ready!", f"**{BOT_NAME}** has deployed your VPS!")
            field(dm, "Details",
                  f"**ID** #{vps_count} | **Container** `{cname}`\n"
                  f"**Config** {config_str} | **OS** {display_os}")
            field(dm, "Usage", f"Use `{PREFIX}manage` to start, stop, SSH or reinstall your VPS.")
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
    """Admin chooses node → then OS selection."""
    def __init__(self, ram, cpu, disk, user, ctx):
        super().__init__(timeout=180)
        self.ram = ram; self.cpu = cpu; self.disk = disk
        self.user = user; self.ctx = ctx
        nodes = get_nodes()
        opts  = [discord.SelectOption(
            label=f"{n['name']} ({n['location']})",
            description=f"{get_current_vps_count(n['id'])}/{n['total_vps']} VPS",
            value=str(n["id"])) for n in nodes]
        sel = discord.ui.Select(placeholder=f"{EM['node']} Select deployment node…", options=opts)
        sel.callback = self.pick_node
        self.add_item(sel)

    async def pick_node(self, interaction: discord.Interaction):
        node_id = int(interaction.data["values"][0])
        for i in self.children: i.disabled = True
        node = get_node(node_id)
        e = info_embed("Select OS", f"Node: **{node['name']}**\nNow choose an operating system.")
        view = OSSelectView(self.ram, self.cpu, self.disk, self.user, self.ctx, node_id)
        await interaction.response.edit_message(embed=e, view=view)


# ════════════════════════════════════════════════════════
#  HELP VIEW
# ════════════════════════════════════════════════════════

class HelpView(discord.ui.View):
    CATEGORIES = {
        "user": {
            "label": "👤 User",
            "cmds": [
                ("manage", "Manage your VPS (start/stop/SSH/reinstall)"),
                ("myvps", "List your VPS"),
                ("vpsinfo [container]", "VPS details"),
                ("ports add <n> <port>", "Add port forward"),
                ("ports list", "List your port forwards"),
                ("ports remove <id>", "Remove port forward"),
                ("share-user @user <n>", "Share VPS access"),
                ("share-ruser @user <n>", "Revoke shared access"),
                ("manage-shared @owner <n>", "Manage shared VPS"),
            ]
        },
        "shop": {
            "label": "🛒 Shop",
            "cmds": [
                ("shop", "Browse plans & balance"),
                ("plans", "Paid VPS plans"),
                ("freeplans", "Free VPS plans"),
                ("buy-plan <name>", "Purchase a plan"),
                ("claim-freeplan <name>", "Claim free plan"),
                ("coins [@user]", "Check coin balance"),
                ("invites [@user]", "Check invite count"),
                ("invite-leaderboard", "Top inviters"),
                ("check-boost [@user]", "Check boost status"),
            ]
        },
        "admin": {
            "label": "🛡️ Admin",
            "cmds": [
                ("create <ram> <cpu> <disk> @user", "Deploy a VPS"),
                ("delete-vps @user <n> [reason]", "Delete VPS"),
                ("add-resources <container> [ram] [cpu] [disk]", "Add resources"),
                ("suspend-vps <container> [reason]", "Suspend VPS"),
                ("unsuspend-vps <container>", "Unsuspend VPS"),
                ("status", "Full system status"),
                ("admin-stats", "Admin overview"),
                ("userinfo @user", "User dashboard"),
                ("list-all", "All VPS list"),
                ("vps-list [node_id]", "Node VPS dashboard"),
            ]
        },
        "nodes": {
            "label": "🌐 Nodes",
            "cmds": [
                ("node list", "List all nodes"),
                ("node create", "Add a node"),
                ("node status <id>", "Node status & stats"),
                ("node edit <id>", "Edit node"),
                ("node delete <id>", "Delete node"),
                ("node-check <id>", "Node diagnostics"),
                ("migrate-vps <container> <node_id>", "Migrate VPS"),
            ]
        },
        "system": {
            "label": "⚙️ System",
            "cmds": [
                ("ping", "Bot latency"),
                ("uptime", "Host uptime"),
                ("serverstats", "Server statistics"),
                ("set-threshold <cpu> <ram>", "Set alert thresholds"),
                ("thresholds", "View thresholds"),
                ("developer", "Developer info"),
                ("set-status <type> <name>", "Set bot status"),
            ]
        },
    }

    def __init__(self, ctx):
        super().__init__(timeout=300)
        self.ctx     = ctx
        self.current = "user"
        self._build_select()

    def _build_select(self):
        self.clear_items()
        opts = [discord.SelectOption(
            label=v["label"], value=k,
            default=(k == self.current)) for k, v in self.CATEGORIES.items()]
        sel = discord.ui.Select(placeholder="📖 Browse help categories…", options=opts)
        sel.callback = self._pick
        self.add_item(sel)

    async def _pick(self, interaction: discord.Interaction):
        self.current = interaction.data["values"][0]
        self._build_select()
        await interaction.response.edit_message(embed=self._build_embed(), view=self)

    def _build_embed(self) -> discord.Embed:
        cat = self.CATEGORIES[self.current]
        e = make_embed(f"Help — {cat['label']}",
            f"Prefix: `{PREFIX}`  |  Mention prefix: `@{BOT_NAME}`\n"
            f"Use `{PREFIX}developer` for bot info.", C_GOLD)
        lines = [f"`{PREFIX}{cmd}` — {desc}" for cmd, desc in cat["cmds"]]
        field(e, "Commands", "\n".join(lines))
        e.set_footer(text=f"{BOT_NAME} v{CFG['bot']['version']} • {EM['dev']} Dev: {CFG['developer_info']['name']}")
        return e

    def get_initial_embed(self) -> discord.Embed:
        return self._build_embed()
