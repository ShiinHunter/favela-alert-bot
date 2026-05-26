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

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBALS
# =========================================================

channel_cache = None
panel_message = None

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
# PANEL SAVE
# =========================================================

def save_panel(message_id):

    with open(PANEL_FILE, "w", encoding="utf-8") as f:

        json.dump({
            "panel_message_id": message_id
        }, f)

def load_panel():

    if not os.path.exists(PANEL_FILE):
        return None

    try:

        with open(PANEL_FILE, "r", encoding="utf-8") as f:

            data = json.load(f)

        return data.get("panel_message_id")

    except:
        return None

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

        if panel_message is None:

            panel_id = load_panel()

            if panel_id:

                try:

                    panel_message = await channel_cache.fetch_message(panel_id)

                except:
                    panel_message = None

        if panel_message is None:

            panel_message = await channel_cache.send(embed=embed)

            save_panel(panel_message.id)

            logging.info("Painel criado.")

        else:

            await panel_message.edit(embed=embed)

            logging.info("Painel atualizado.")

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
# COMMANDS
# =========================================================

@bot.tree.command(
    name="teste",
    description="Teste do bot",
    guild=discord.Object(id=GUILD_ID)
)
async def teste(interaction: discord.Interaction):

    logging.info("/teste executado")

    await interaction.response.defer(ephemeral=True)

    await send_alert(
        "Boss Rush",
        "🔥 TESTE MANUAL",
        0xff0000
    )

    await interaction.followup.send(
        "✅ Teste enviado.",
        ephemeral=True
    )

@bot.tree.command(
    name="painel",
    description="Atualiza o painel",
    guild=discord.Object(id=GUILD_ID)
)
async def painel(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    await update_panel()

    await interaction.followup.send(
        "✅ Painel atualizado.",
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

    try:

        guild = discord.Object(id=GUILD_ID)

        synced = await bot.tree.sync(guild=guild)

        logging.info(f"Slash sincronizados: {len(synced)}")

    except Exception as e:

        logging.error(f"Erro slash sync: {e}")

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
