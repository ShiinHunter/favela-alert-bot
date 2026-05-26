import os
import json
import asyncio
import logging
import discord

from aiohttp import web
from discord.ext import commands, tasks
from discord.ui import View, Button

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149

EVENT_FILE = "events.json"
PANEL_FILE = "panel.json"

PORT = int(os.getenv("PORT", 8080))

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()

intents.guilds = True
intents.members = True
intents.message_content = True

# =========================================================
# BOT
# =========================================================

class FavelaBot(commands.Bot):

    async def setup_hook(self):

        logging.info("Sincronizando slash commands...")

        await self.tree.sync()

        logging.info("Slash commands sincronizados.")

bot = FavelaBot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBALS
# =========================================================

channel_cache = None

panel_message = None
role_message = None

# =========================================================
# EVENT EMOJIS
# =========================================================

EVENT_EMOJIS = {
    "Escape Room": "🚪",
    "Boss Rush": "👹",
    "Ranked Arena": "⚔️",
    "Gold Fish": "🐟",
    "Fortress War": "🏰",
    "Raids": "🐉"
}

# =========================================================
# LOAD EVENTS
# =========================================================

def load_events():

    if not os.path.exists(EVENT_FILE):

        return {
            "daily": [],
            "weekly": {}
        }

    with open(EVENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

EVENTS = load_events()

# =========================================================
# PANEL SAVE
# =========================================================

def save_panel_data(panel_id=None, role_id=None):

    with open(PANEL_FILE, "w", encoding="utf-8") as f:

        json.dump({
            "panel_message_id": panel_id,
            "role_message_id": role_id
        }, f)

def load_panel_data():

    if not os.path.exists(PANEL_FILE):
        return {}

    try:

        with open(PANEL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except:
        return {}

# =========================================================
# EMOJIS
# =========================================================

def event_emoji(event_name):

    return EVENT_EMOJIS.get(event_name, "🎮")

# =========================================================
# ROLE PING
# =========================================================

def role_ping():

    return f"<@&{EVENT_ROLE_ID}>"

# =========================================================
# FORMAT COUNTDOWN
# =========================================================

def format_countdown(seconds):

    if seconds <= 0:
        return "AGORA"

    hours, remainder = divmod(int(seconds), 3600)

    minutes, seconds = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}h {minutes:02d}m"

    return f"{minutes:02d}m {seconds:02d}s"

# =========================================================
# SEND ALERT
# =========================================================

async def send_alert(event_name, description, color=0x00ffcc):

    global channel_cache

    if channel_cache is None:
        return

    emoji = event_emoji(event_name)

    embed = discord.Embed(
        title=f"{emoji} {event_name}",
        description=description,
        color=color
    )

    embed.timestamp = datetime.now(LOCAL_TZ)

    await channel_cache.send(embed=embed)

# =========================================================
# GET TODAY EVENTS
# =========================================================

def get_today_events():

    events = []

    for event in EVENTS.get("daily", []):
        events.append(event)

    weekdays = {
        "monday": "segunda",
        "tuesday": "terca",
        "wednesday": "quarta",
        "thursday": "quinta",
        "friday": "sexta",
        "saturday": "sabado",
        "sunday": "domingo"
    }

    weekday_en = datetime.now(LOCAL_TZ).strftime("%A").lower()

    weekday_pt = weekdays.get(weekday_en)

    weekly_events = EVENTS.get("weekly", {}).get(weekday_pt, [])

    for event in weekly_events:
        events.append(event)

    return events

# =========================================================
# NEXT EVENTS
# =========================================================

def get_next_events():

    now = datetime.now(LOCAL_TZ)

    upcoming = []

    for event in get_today_events():

        for event_time in event["times"]:

            hour, minute = map(int, event_time.split(":"))

            event_dt = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )

            if event_dt < now:
                continue

            diff = (event_dt - now).total_seconds()

            upcoming.append({
                "name": event["name"],
                "time": event_time,
                "diff": diff
            })

    upcoming.sort(key=lambda x: x["diff"])

    return upcoming[:10]

# =========================================================
# ROLE BUTTON
# =========================================================

class NotificationView(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Receber Notificações",
        style=discord.ButtonStyle.green,
        emoji="🔔",
        custom_id="notification_button"
    )
    async def notification_button(
        self,
        interaction: discord.Interaction,
        button: Button
    ):

        role = interaction.guild.get_role(EVENT_ROLE_ID)

        if role is None:

            await interaction.response.send_message(
                "❌ Cargo não encontrado.",
                ephemeral=True
            )

            return

        try:

            if role in interaction.user.roles:

                await interaction.user.remove_roles(role)

                await interaction.response.send_message(
                    "❌ Notificações removidas.",
                    ephemeral=True
                )

            else:

                await interaction.user.add_roles(role)

                await interaction.response.send_message(
                    "✅ Notificações ativadas.",
                    ephemeral=True
                )

        except Exception as e:

            logging.error(f"Erro cargo: {e}")

            await interaction.response.send_message(
                "❌ Não consegui alterar seu cargo.",
                ephemeral=True
            )

# =========================================================
# ROLE PANEL
# =========================================================

async def setup_role_panel():

    global role_message
    global channel_cache

    panel_data = load_panel_data()

    embed = discord.Embed(
        title="🔔 Notificações de Eventos",
        description=(
            "Clique no botão abaixo para\n"
            "receber alertas automáticos dos eventos."
        ),
        color=0xffcc00
    )

    embed.add_field(
        name="📢 Eventos Notificados",
        value=(
            "🚪 Escape Room\n"
            "👹 Boss Rush\n"
            "⚔️ Ranked Arena\n"
            "🏰 Fortress War\n"
            "🐉 Raids"
        ),
        inline=False
    )

    view = NotificationView()

    try:

        role_message_id = panel_data.get("role_message_id")

        if role_message_id:

            try:

                role_message = await channel_cache.fetch_message(
                    role_message_id
                )

            except:
                role_message = None

        if role_message is None:

            role_message = await channel_cache.send(
                embed=embed,
                view=view
            )

            save_panel_data(
                panel_data.get("panel_message_id"),
                role_message.id
            )

            logging.info("Painel de cargo criado.")

        else:

            await role_message.edit(
                embed=embed,
                view=view
            )

            logging.info("Painel de cargo atualizado.")

    except Exception as e:

        logging.error(f"Erro painel cargo: {e}")

# =========================================================
# PANEL
# =========================================================

async def update_panel():

    global panel_message
    global channel_cache

    if channel_cache is None:
        return

    events = get_next_events()

    description = ""

    for event in events:

        emoji = event_emoji(event["name"])

        description += (
            f"{emoji} **{event['name']}**\n"
            f"🕒 {event['time']}\n"
            f"⏳ {format_countdown(event['diff'])}\n\n"
        )

    embed = discord.Embed(
        title="📅 Próximos Eventos",
        description=description if description else "Nenhum evento encontrado.",
        color=0x00ffcc
    )

    embed.set_footer(
        text="Atualiza automaticamente"
    )

    try:

        panel_data = load_panel_data()

        if panel_message is None:

            panel_id = panel_data.get("panel_message_id")

            if panel_id:

                try:

                    panel_message = await channel_cache.fetch_message(panel_id)

                except:
                    panel_message = None

        if panel_message is None:

            panel_message = await channel_cache.send(embed=embed)

            save_panel_data(
                panel_message.id,
                panel_data.get("role_message_id")
            )

            logging.info("Painel criado.")

        else:

            await panel_message.edit(embed=embed)

    except Exception as e:

        logging.error(f"Erro painel: {e}")

# =========================================================
# PANEL LOOP
# =========================================================

@tasks.loop(seconds=60)
async def panel_loop():

    await update_panel()

# =========================================================
# EVENT LOOP
# =========================================================

@tasks.loop(seconds=15)
async def check_events():

    now = datetime.now(LOCAL_TZ)

    for event in get_today_events():

        event_name = event["name"]

        for event_time in event["times"]:

            hour, minute = map(int, event_time.split(":"))

            event_dt = now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )

            warn_dt = event_dt - timedelta(minutes=5)

            if warn_dt <= now < warn_dt + timedelta(seconds=15):

                await send_alert(
                    event_name,
                    (
                        f"{role_ping()}\n\n"
                        f"⏳ Começa em 5 minutos\n"
                        f"🕒 {event_time}"
                    ),
                    0xffcc00
                )

            if event_dt <= now < event_dt + timedelta(seconds=15):

                await send_alert(
                    event_name,
                    (
                        f"{role_ping()}\n\n"
                        f"🔥 Evento começou!"
                    ),
                    0xff0000
                )

# =========================================================
# TEST EVENT
# =========================================================

async def simulated_event():

    embed = discord.Embed(
        title="👹 Boss Rush",
        description=(
            f"{role_ping()}\n\n"
            f"⏳ Começa em:\n"
            f"**01m 00s**"
        ),
        color=0xffcc00
    )

    message = await channel_cache.send(embed=embed)

    remaining = 60

    while remaining > 0:

        embed.description = (
            f"{role_ping()}\n\n"
            f"⏳ Começa em:\n"
            f"**{format_countdown(remaining)}**"
        )

        await message.edit(embed=embed)

        await asyncio.sleep(5)

        remaining -= 5

    start_embed = discord.Embed(
        title="👹 Boss Rush",
        description=(
            f"{role_ping()}\n\n"
            f"🔥 Evento começou!"
        ),
        color=0xff0000
    )

    await message.edit(embed=start_embed)

# =========================================================
# COMMANDS
# =========================================================

@bot.tree.command(
    name="teste",
    description="Simula um evento"
)
async def teste(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    asyncio.create_task(simulated_event())

    await interaction.followup.send(
        "✅ Evento de teste iniciado.",
        ephemeral=True
    )

@bot.tree.command(
    name="painel",
    description="Atualiza o painel"
)
async def painel(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    await update_panel()

    await interaction.followup.send(
        "✅ Painel atualizado.",
        ephemeral=True
    )

@bot.tree.command(
    name="eventos",
    description="Lista eventos do dia"
)
async def eventos(interaction: discord.Interaction):

    events = get_today_events()

    embed = discord.Embed(
        title="📅 Eventos de Hoje",
        color=0x00ffcc
    )

    text = ""

    for event in events:

        emoji = event_emoji(event["name"])

        text += (
            f"{emoji} **{event['name']}**\n"
            f"🕒 {' | '.join(event['times'])}\n\n"
        )

    embed.description = text

    await interaction.response.send_message(
        embed=embed,
        ephemeral=True
    )

# =========================================================
# HEALTHCHECK
# =========================================================

async def healthcheck(request):

    return web.Response(text="ONLINE")

async def run_webserver():

    app = web.Application()

    app.router.add_get("/", healthcheck)

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        PORT
    )

    await site.start()

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    global channel_cache

    logging.info(f"BOT ONLINE: {bot.user}")

    try:

        channel_cache = await bot.fetch_channel(CHANNEL_ID)

        logging.info("Canal carregado.")

    except Exception as e:

        logging.error(f"Erro canal: {e}")

        return

    bot.add_view(NotificationView())

    await setup_role_panel()

    await update_panel()

    if not panel_loop.is_running():
        panel_loop.start()

    if not check_events.is_running():
        check_events.start()

# =========================================================
# MAIN
# =========================================================

async def main():

    async with bot:

        await run_webserver()

        await bot.start(TOKEN)

# =========================================================
# RUN
# =========================================================

asyncio.run(main())
