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
#  GESTION DES DONNÉES
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
    active = []
    for slot in data["slots"]:
        expires = datetime.fromisoformat(slot["expires_at"])
        if expires > now:
            active.append(slot)
    return active

def slots_remaining():
    return MAX_SLOTS - len(get_active_slots())

def get_main_guild():
    return bot.guilds[0] if bot.guilds else None

# ============================================================
#  VIEWS
# ============================================================

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
                "Une fois le paiement effectué, attendez la confirmation du propriétaire."
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
            title="🪙 Paiement par LTC (Litecoin)",
            description=(
                f"**Montant :** `{self.hours}€` en LTC\n\n"
                f"📬 **Adresse LTC :**\n```{LTC_ADDRESS}```\n\n"
                "Envoyez exactement le montant équivalent puis attendez la confirmation."
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
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé.", ephemeral=True)

        guild = get_main_guild()
        if not guild:
            return await interaction.response.send_message("❌ Serveur introuvable.", ephemeral=True)

        try:
            member = await guild.fetch_member(self.user_id)
        except:
            return await interaction.response.send_message("❌ Utilisateur introuvable.", ephemeral=True)

        if slots_remaining() <= 0:
            return await interaction.response.send_message("❌ Plus de slots disponibles !", ephemeral=True)

        role = guild.get_role(ROLE_ID)
        if role:
            await member.add_roles(role)

        data = load_data()
        expires_at = datetime.utcnow() + timedelta(hours=self.hours)
        slot = {
            "user_id": self.user_id,
            "hours": self.hours,
            "started_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat(),
            "alerted": False
        }
        data["slots"].append(slot)
        save_data(data)

        try:
            dm_embed = discord.Embed(
                title="🎉 Accès OKV Notifier activé !",
                description=SCRIPT_DM,
                color=0x00FF88
            )
            dm_embed.add_field(name="⏱ Durée", value=f"{self.hours} heure(s)", inline=True)
            dm_embed.add_field(name="⌛ Expire à", value=f"<t:{int(expires_at.timestamp())}:F>", inline=True)
            await member.send(embed=dm_embed)
        except:
            pass

        channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
        remaining = slots_remaining()
        if channel:
            if remaining == 0:
                announce_embed = discord.Embed(
                    title="🔴 Slots complets !",
                    description="Tous les slots sont occupés. Revenez plus tard !",
                    color=0xFF0000
                )
            else:
                announce_embed = discord.Embed(
                    title="🟢 Slot activé !",
                    description=f"Un slot vient d'être acheté.\n**Il reste `{remaining}` slot(s) disponible(s).**",
                    color=0x00FF88
                )
            await channel.send(embed=announce_embed)

        await interaction.response.send_message(f"✅ Slot confirmé pour {member.mention} ({self.hours}h) !", ephemeral=True)
        self.stop()

    @discord.ui.button(label="❌ Refuser", style=discord.ButtonStyle.red)
    async def deny_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != OWNER_ID:
            return await interaction.response.send_message("❌ Vous n'êtes pas autorisé.", ephemeral=True)
        try:
            user = await bot.fetch_user(self.user_id)
            await user.send("❌ Votre paiement n'a pas pu être confirmé. Contactez le support.")
        except:
            pass
        await interaction.response.send_message("❌ Paiement refusé.", ephemeral=True)
        self.stop()


# ============================================================
#  NOTIFY OWNER
# ============================================================
async def notify_owner(guild: discord.Guild, user: discord.Member, hours: int, method: str):
    try:
        owner = await guild.fetch_member(OWNER_ID)
    except:
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
#  SLASH COMMANDS
# ============================================================

@bot.tree.command(name="acheter", description="Acheter un slot OKV Notifier")
@app_commands.describe(heures="Nombre d'heures à acheter (1h = 1€)")
async def acheter(interaction: discord.Interaction, heures: int):
    if heures < 1:
        return await interaction.response.send_message("❌ Minimum 1 heure.", ephemeral=True)

    remaining = slots_remaining()
    if remaining <= 0:
        return await interaction.response.send_message(
            "❌ Tous les slots sont complets ! Revenez plus tard.", ephemeral=True
        )

    embed = discord.Embed(
        title="🛒 OKV Notifier — Achat de slot",
        description=(
            f"**Durée choisie :** `{heures}h`\n"
            f"**Prix :** `{heures}€`\n"
            f"**Slots restants :** `{remaining}/5`\n\n"
            "Choisissez votre méthode de paiement :"
        ),
        color=0x5865F2
    )
    embed.set_footer(text="OKV Notifier • Paiement sécurisé")
    await interaction.response.send_message(embed=embed, view=PaymentView(interaction.user, heures), ephemeral=True)


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
#  TASK — Timer
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
        except:
            member = None

        if not slot.get("alerted") and 0 < remaining_seconds <= 300:
            slot["alerted"] = True
            updated = True
            if member:
                try:
                    alert_embed = discord.Embed(
                        title="⚠️ Votre slot expire bientôt !",
                        description="Il vous reste **moins de 5 minutes** sur votre slot OKV Notifier.\nRachetez un slot pour continuer !",
                        color=0xFF6600
                    )
                    await member.send(embed=alert_embed)
                except:
                    pass

        if remaining_seconds <= 0:
            data["slots"].remove(slot)
            updated = True

            role = guild.get_role(ROLE_ID)
            if member and role:
                try:
                    await member.remove_roles(role)
                except:
                    pass

            if member:
                try:
                    exp_embed = discord.Embed(
                        title="⌛ Slot expiré",
                        description="Votre slot OKV Notifier a expiré. Utilisez `/acheter` pour en prendre un nouveau !",
                        color=0xFF0000
                    )
                    await member.send(embed=exp_embed)
                except:
                    pass

            channel = guild.get_channel(ANNOUNCE_CHANNEL_ID)
            if channel:
                new_remaining = MAX_SLOTS - len(data["slots"])
                free_embed = discord.Embed(
                    title="🟢 Un slot vient de se libérer !",
                    description=f"**`{new_remaining}` slot(s) disponible(s)** sur OKV Notifier !\nUtilisez `/acheter` pour en profiter.",
                    color=0x00FF88
                )
                await channel.send(embed=free_embed)

    if updated:
        save_data(data)


# ============================================================
#  EVENTS
# ============================================================
@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ {len(synced)} commande(s) synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    check_slots.start()


bot.run(TOKEN)
    
