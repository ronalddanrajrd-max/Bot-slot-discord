import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta

# ============================================================
#  CONFIG
# ============================================================
TOKEN = os.environ.get("TOKEN")
OWNER_ID = 1467602579482480821
ANNOUNCE_CHANNEL_ID = 1485113159726666020
ROLE_ID = 1485439657284993248

LTC_ADDRESS = "VOTRE_ADRESSE_LTC_ICI"
STRIPE_LINK = "VOTRE_LIEN_STRIPE_ICI"

SCRIPT_DM = """
🎉 Bienvenue sur OKV Notifier !

Voici votre accès :
[METTEZ VOTRE SCRIPT/MESSAGE ICI]

Bonne utilisation ! 🚀
"""

MAX_SLOTS = 5
DATA_FILE = "slots.json"

# ============================================================
#  INTENTS & BOT
# ============================================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ============================================================
#  DONNÉES
# ============================================================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {"slots": []}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_active_slots():
    data = load_data()
    now = datetime.utcnow()
    return [s for s in data["slots"] if datetime.fromisoformat(s["expires_at"]) > now]

def slots_remaining():
    return MAX_SLOTS - len(get_active_slots())

def get_main_guild():
    return bot.guilds[0] if bot.guilds else None

# ============================================================
#  MODAL — Saisie des heures
# ============================================================
class HeuresModal(discord.ui.Modal, title="🛒 Acheter un slot OKV"):
    heures = discord.ui.TextInput(
        label="Nombre d'heures (1h = 1€)",
        placeholder="Ex: 3",
        min_length=1,
        max_length=3
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            h = int(self.heures.value)
            if h < 1:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Entrez un nombre valide (minimum 1).", ephemeral=True)

        remaining = slots_remaining()
        if remaining <= 0:
            return await interaction.response.send_message("❌ Tous les slots sont complets !", ephemeral=True)

        embed = discord.Embed(
            title="🛒 OKV Notifier — Achat de slot",
            description=(
                f"**Durée choisie :** `{h}h`\n"
                f"**Prix :** `{h}€`\n"
                f"**Slots restants :** `{remaining}/5`\n\n"
                "Choisissez votre méthode de paiement :"
            ),
            color=0x5865F2
        )
        embed.set_footer(text="OKV Notifier • Paiement sécurisé")
        await interaction.response.send_message(embed=embed, view=PaymentView(interaction.user, h), ephemeral=True)

# ============================================================
#  VIEWS
# ============================================================
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🛒 Acheter un slot", style=discord.ButtonStyle.blurple, custom_id="panel_buy")
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if slots_remaining() <= 0:
            return await interaction.response.send_message("❌ Tous les slots sont complets !", ephemeral=True)
        await interaction.response.send_modal(HeuresModal())

    @discord.ui.button(label="📊 Voir les slots", style=discord.ButtonStyle.grey, custom_id="panel_slots")
    async def slots_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        remaining = slots_remaining()
        active = get_active_slots()
        color = 0x00FF88 if remaining > 0 else 0xFF0000
        embed = discord.Embed(title="📊 OKV Notifier — Slots", color=color)
        embed.add_field(name="🟢 Disponibles", value=f"`{remaining}/5`", inline=True)
        embed.add_field(name="🔴 Occupés", value=f"`{len(active)}/5`", inline=True)
        if active:
            details = ""
            for s in active:
                expires = datetime.fromisoformat(s["expires_at"])
                details += f"<@{s['user_id']}> → <t:{int(expires.timestamp())}:R>\n"
            embed.add_field(name="📋 Slots actifs", value=details, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PaymentView(discord.ui.View):
    def __init__(self, user: discord.Member, hours: int):
        super().__init__(timeout=300)
        self.user = user
        self.hours = hours

    @discord.ui.button(label="💳 Stripe", style=discord.ButtonStyle.blurple)
    async def stripe_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ Ce n'est pas votre panel.", ephemeral=True)
        embed = discord.Embed(
            title="💳 Paiement par Stripe",
            description=(
                f"**Montant :** `{self.hours}€`\n\n"
                f"👉 [Cliquez ici pour payer]({STRIPE_LINK})\n\n"
                "Une fois le paiement effectué, attendez la confirmation."
            ),
            color=0x635BFF
        )
        embed.set_footer(text="OKV Notifier • Paiement sécurisé")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        guild = get_main_guild()
        if guild:
            await notify_owner(guild, self.user, self.hours, "Stripe")

    @discord.ui.button(label="🪙 LTC", style=discord.ButtonStyle.grey)
    async def ltc_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ Ce n'est pas votre panel.", ephemeral=True)
        embed = discord.Embed(
            title="🪙 Paiement par LTC",
            description=(
                f"**Montant :** `{self.hours}€` en LTC\n\n"
                f"📬 **Adresse LTC :**\n```{LTC_ADDRESS}```\n\n"
                "Envoyez le montant exact puis attendez la confirmation."
            ),
            color=0xB8860B
        )
        embed.set_footer(text="OKV Notifier • Paiement crypto")
        await interaction.response.send_message(embed=embed, ephemeral=True)
        guild = get_main_guild()
        if guild:
            await notify_owner(guild, self.user, self.hours, "LTC")


class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, hours: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.hours = hours

    @discord.ui.button(label="✅ Confirmer le paiement", style=discord.ButtonStyle.green)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)

        # DEFER immédiatement pour éviter le timeout Discord
        await interaction.response.defer(ephemeral=True)

        guild = get_main_guild()
        if not guild:
            return await interaction.followup.send("❌ Serveur introuvable.", ephemeral=True)

        try:
            member = await guild.fetch_member(self.user_id)
        except Exception:
            return await interaction.followup.send("❌ Utilisateur introuvable.", ephemeral=True)

        if slots_remaining() <= 0:
            return await interaction.followup.send("❌ Plus de slots disponibles !", ephemeral=True)

        await activate_slot(guild, member, self.hours)
        await interaction.followup.send(f"✅ Slot confirmé pour {member.mention} ({self.hours}h) !", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)

        # DEFER immédiatement pour éviter le timeout Discord
        await interaction.response.defer(ephemeral=True)

        try:
            user = await bot.fetch_user(self.user_id)
            await user.send("❌ Votre paiement n'a pas été confirmé. Contactez le support.")
        except Exception:
            pass

        await interaction.followup.send("❌ Paiement refusé.", ephemeral=True)
        self.stop()

# ============================================================
#  ACTIVATION SLOT
# ============================================================
async def activate_slot(guild: discord.Guild, member: discord.Member, hours: int):
    role = guild.get_role(ROLE_ID)
    if role:
        await member.add_roles(role)

    data = load_data()
    expires_at = datetime.utcnow() + timedelta(hours=hours)
    data["slots"].append({
        "user_id": member.id,
        "hours": hours,
        "started_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat(),
        "alerted": False
    })
    save_data(data)

    try:
        dm_embed = discord.Embed(
            title="🎉 Accès OKV Notifier activé !",
            description=SCRIPT_DM,
            color=0x00FF88
        )
        dm_embed.add_field(name="⏱ Durée", value=f"{hours} heure(s)", inline=True)
        dm_embed.add_field(name="⌛ Expire à", value=f"<t:{int(expires_at.timestamp())}:F>", inline=True)
        await member.send(embed=dm_embed)
    except Exception:
        pass

    channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
    remaining = slots_remaining()
    if channel:
        if remaining == 0:
            embed = discord.Embed(title="🔴 Slots complets !", description="Tous les slots sont occupés.", color=0xFF0000)
        else:
            embed = discord.Embed(title="🟢 Slot activé !", description=f"Il reste **`{remaining}` slot(s)** disponible(s).", color=0x00FF88)
        await channel.send(embed=embed)

# ============================================================
#  NOTIFY OWNER
# ============================================================
async def notify_owner(guild: discord.Guild, user: discord.Member, hours: int, method: str):
    try:
        owner = await guild.fetch_member(OWNER_ID)
    except Exception:
        return
    embed = discord.Embed(
        title="💰 Nouveau paiement en attente !",
        description=(
            f"**Acheteur :** {user.mention} (`{user.id}`)\n"
            f"**Heures :** `{hours}h`\n"
            f"**Montant :** `{hours}€`\n"
            f"**Méthode :** `{method}`"
        ),
        color=0xFFAA00
    )
    embed.set_footer(text="Confirmez ou refusez ci-dessous")
    await owner.send(embed=embed, view=ConfirmView(user.id, hours))

# ============================================================
#  COMMANDES SLASH
# ============================================================
@bot.tree.command(name="panel", description="Envoyer le panel d'achat dans ce salon")
async def panel_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)
    remaining = slots_remaining()
    color = 0x00FF88 if remaining > 0 else 0xFF0000
    embed = discord.Embed(
        title="🎰 OKV Notifier — Slots",
        description=(
            "Bienvenue sur **OKV Notifier** !\n\n"
            f"📦 **Slots disponibles :** `{remaining}/5`\n"
            "💰 **Prix :** 1€ = 1 heure\n\n"
            "Cliquez sur **Acheter un slot** pour commencer !"
        ),
        color=color
    )
    embed.set_footer(text="OKV Notifier • Paiement sécurisé")
    await interaction.response.send_message(embed=embed, view=PanelView())


@bot.tree.command(name="whitelist", description="Donner un slot manuellement")
@app_commands.describe(membre="L'utilisateur", heures="Nombre d'heures")
async def whitelist_cmd(interaction: discord.Interaction, membre: discord.Member, heures: int):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)
    if heures < 1:
        return await interaction.response.send_message("❌ Minimum 1 heure.", ephemeral=True)
    if slots_remaining() <= 0:
        return await interaction.response.send_message("❌ Plus de slots disponibles !", ephemeral=True)

    # DEFER immédiatement pour éviter le timeout Discord
    await interaction.response.defer(ephemeral=True)

    guild = get_main_guild()
    await activate_slot(guild, membre, heures)
    await interaction.followup.send(f"✅ Slot de `{heures}h` attribué à {membre.mention} !", ephemeral=True)


@bot.tree.command(name="unwhitelist", description="Retirer le slot d'un utilisateur")
@app_commands.describe(membre="L'utilisateur à retirer")
async def unwhitelist_cmd(interaction: discord.Interaction, membre: discord.Member):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)

    # DEFER immédiatement pour éviter le timeout Discord
    await interaction.response.defer(ephemeral=True)

    data = load_data()
    new_slots = [s for s in data["slots"] if s["user_id"] != membre.id]
    if len(new_slots) == len(data["slots"]):
        return await interaction.followup.send(f"❌ {membre.mention} n'a pas de slot actif.", ephemeral=True)

    data["slots"] = new_slots
    save_data(data)

    guild = get_main_guild()
    role = guild.get_role(ROLE_ID)
    if role:
        try:
            await membre.remove_roles(role)
        except Exception:
            pass

    try:
        await membre.send("❌ Votre slot OKV Notifier a été retiré.")
    except Exception:
        pass

    channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
    if channel:
        remaining = slots_remaining()
        embed = discord.Embed(
            title="🟢 Un slot vient de se libérer !",
            description=f"**`{remaining}` slot(s)** disponible(s) !",
            color=0x00FF88
        )
        await channel.send(embed=embed)

    await interaction.followup.send(f"✅ Slot retiré pour {membre.mention}.", ephemeral=True)


@bot.tree.command(name="sync", description="Synchroniser les commandes")
async def sync_cmd(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        return await interaction.response.send_message("❌ Non autorisé.", ephemeral=True)
    synced = await bot.tree.sync()
    await interaction.response.send_message(f"✅ {len(synced)} commandes synchronisées !", ephemeral=True)


@bot.tree.command(name="slots", description="Voir les slots disponibles")
async def slots_cmd(interaction: discord.Interaction):
    remaining = slots_remaining()
    active = get_active_slots()
    color = 0x00FF88 if remaining > 0 else 0xFF0000
    embed = discord.Embed(title="📊 OKV Notifier — Slots", color=color)
    embed.add_field(name="🟢 Disponibles", value=f"`{remaining}/5`", inline=True)
    embed.add_field(name="🔴 Occupés", value=f"`{len(active)}/5`", inline=True)
    if active:
        details = ""
        for s in active:
            expires = datetime.fromisoformat(s["expires_at"])
            details += f"<@{s['user_id']}> → <t:{int(expires.timestamp())}:R>\n"
        embed.add_field(name="📋 Slots actifs", value=details, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
#  TIMER
# ============================================================
@tasks.loop(minutes=1)
async def check_slots():
    data = load_data()
    now = datetime.utcnow()
    updated = False
    guild = get_main_guild()
    if not guild:
        return

    for slot in data["slots"][:]:
        expires = datetime.fromisoformat(slot["expires_at"])
        remaining_seconds = (expires - now).total_seconds()

        try:
            member = await guild.fetch_member(slot["user_id"])
        except Exception:
            member = None

        # Alerte 5 minutes avant expiration
        if not slot.get("alerted") and 0 < remaining_seconds <= 300:
            slot["alerted"] = True
            updated = True
            if member:
                try:
                    await member.send(embed=discord.Embed(
                        title="⚠️ Votre slot expire bientôt !",
                        description="Il vous reste **moins de 5 minutes**. Rachetez un slot pour continuer !",
                        color=0xFF6600
                    ))
                except Exception:
                    pass

        # Slot expiré
        if remaining_seconds <= 0:
            data["slots"].remove(slot)
            updated = True
            role = guild.get_role(ROLE_ID)
            if member and role:
                try:
                    await member.remove_roles(role)
                except Exception:
                    pass
            if member:
                try:
                    await member.send(embed=discord.Embed(
                        title="⌛ Slot expiré",
                        description="Votre slot a expiré. Utilisez le panel pour en acheter un nouveau !",
                        color=0xFF0000
                    ))
                except Exception:
                    pass
            channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
            if channel:
                new_remaining = MAX_SLOTS - len(data["slots"])
                await channel.send(embed=discord.Embed(
                    title="🟢 Un slot vient de se libérer !",
                    description=f"**`{new_remaining}` slot(s)** disponible(s) sur OKV Notifier !",
                    color=0x00FF88
                ))

    if updated:
        save_data(data)

# ============================================================
#  EVENTS
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    bot.add_view(PanelView())
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    check_slots.start()

bot.run(TOKEN)
        
    
