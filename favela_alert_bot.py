import os
import json
import asyncio
import logging
import discord

from aiohttp import web
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149
GUILD_ID = 1508595762965774417

EVENT_FILE = "events.json"

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

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBAL
# =========================================================

channel_cache = None

# =========================================================
# EMOJIS
# =========================================================

EVENT_EMOJIS = {
    "Escape Room": "🚪",
    "Boss Rush": "🔥",
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
# EVENT EMOJI
# =========================================================

def event_emoji(event_name):

    return EVENT_EMOJIS.get(event_name, "🎮")

# =========================================================
# ROLE PING
# =========================================================

def role_ping():

    return f"<@&{EVENT_ROLE_ID}>"

# =========================================================
# FORMAT TIME
# =========================================================

def format_countdown(seconds):

    if seconds <= 0:
        return "AGORA"

    minutes, seconds = divmod(int(seconds), 60)

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
# PANEL
# =========================================================

async def update_panel():

    global channel_cache

    if channel_cache is None:
        return

    now = datetime.now(LOCAL_TZ)

    text = ""

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

            emoji = event_emoji(event["name"])

            text += (
                f"{emoji} **{event['name']}**\n"
                f"🕒 {event_time}\n"
                f"⏳ {format_countdown(diff)}\n\n"
            )

    embed = discord.Embed(
        title="📅 Próximos Eventos",
        description=text if text else "Nenhum evento encontrado.",
        color=0x00ffcc
    )

    await channel_cache.send(embed=embed)

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

            # WARNING

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

            # START

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
# COMMAND TEST
# =========================================================

@bot.tree.command(
    name="teste",
    description="Teste do bot",
    guild=discord.Object(id=GUILD_ID)
)
async def teste(interaction: discord.Interaction):

    try:

        logging.info("/teste executado")

        await interaction.response.send_message(
            "✅ BOT FUNCIONANDO",
            ephemeral=True
        )

        await send_alert(
            "Boss Rush",
            "🔥 TESTE MANUAL",
            0xff0000
        )

    except Exception as e:

        logging.error(f"Erro /teste: {e}")

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

    try:

        guild = discord.Object(id=GUILD_ID)

        synced = await bot.tree.sync(guild=guild)

        logging.info(f"Slash sincronizados: {len(synced)}")

    except Exception as e:

        logging.error(f"Erro slash sync: {e}")

    try:

        await update_panel()

    except Exception as e:

        logging.error(f"Erro painel: {e}")

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
