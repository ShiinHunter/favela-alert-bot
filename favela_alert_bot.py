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
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149

EVENT_FILE = "events.json"
NOTIFIED_FILE = "notified.json"

PORT = int(os.getenv("PORT", 8080))

LOCAL_TZ = ZoneInfo("America/Sao_Paulo")

# =========================================================
# INTENTS
# =========================================================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBALS
# =========================================================

channel_cache = None

active_countdowns = {}

panel_message = None

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
# NOTIFIED PERSISTENCE
# =========================================================

def load_notified():

    if not os.path.exists(NOTIFIED_FILE):
        return set()

    try:

        with open(NOTIFIED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        return set(data)

    except:
        return set()

def save_notified():

    with open(NOTIFIED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(notified), f, indent=4)

notified = load_notified()

# =========================================================
# ROLE PING
# =========================================================

def role_ping():

    if EVENT_ROLE_ID:
        return f"<@&{EVENT_ROLE_ID}>"

    return "@everyone"

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

async def send_alert(title, description, color=0x00ffcc):

    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )

    embed.set_footer(text="Aero Tales")
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

def get_next_events(limit=5):

    now = datetime.now(LOCAL_TZ)

    upcoming = []

    today_events = get_today_events()

    for event in today_events:

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
                "time": event_dt,
                "diff": diff
            })

    upcoming.sort(key=lambda x: x["diff"])

    return upcoming[:limit]

# =========================================================
# UPDATE PANEL
# =========================================================

async def update_panel():

    global panel_message

    next_events = get_next_events()

    embed = discord.Embed(
        title="📅 Próximos Eventos",
        color=0x00ffcc
    )

    if not next_events:

        embed.description = "Nenhum evento encontrado."

    else:

        text = ""

        for event in next_events:

            text += (
                f"⏳ **{event['name']}**\n"
                f"🕒 {event['time'].strftime('%H:%M')}\n"
                f"⌛ {format_countdown(event['diff'])}\n\n"
            )

        embed.description = text

    embed.set_footer(text="Atualiza automaticamente")

    try:

        if panel_message is None:

            panel_message = await channel_cache.send(embed=embed)

        else:

            await panel_message.edit(embed=embed)

    except Exception as e:

        logging.error(f"Erro painel: {e}")

# =========================================================
# COUNTDOWN
# =========================================================

async def countdown_event(event_id, event_name, event_dt):

    try:

        embed_message = None

        while True:

            now = datetime.now(LOCAL_TZ)

            remaining = (event_dt - now).total_seconds()

            if remaining <= 0:
                break

            embed = discord.Embed(
                title=f"⏳ {event_name}",
                description=(
                    f"{role_ping()}\n\n"
                    f"⚔️ Evento começa em:\n"
                    f"**{format_countdown(remaining)}**"
                ),
                color=0xffcc00
            )

            embed.timestamp = event_dt

            if embed_message is None:

                embed_message = await channel_cache.send(embed=embed)

                active_countdowns[event_id] = embed_message

            else:

                try:
                    await embed_message.edit(embed=embed)
                except:
                    break

            await asyncio.sleep(15)

        final_embed = discord.Embed(
            title=f"🚨 {event_name}",
            description=(
                f"{role_ping()}\n\n"
                f"🔥 Evento começou AGORA!"
            ),
            color=0xff0000
        )

        if embed_message:
            await embed_message.edit(embed=final_embed)

    except Exception as e:

        logging.error(f"Erro countdown {event_name}: {e}")

    finally:

        if event_id in active_countdowns:
            del active_countdowns[event_id]

# =========================================================
# CLEAN NOTIFIED
# =========================================================

@tasks.loop(hours=24)
async def clean_notified():

    global notified

    notified = set()

    save_notified()

    logging.info("Notificações resetadas.")

# =========================================================
# PANEL LOOP
# =========================================================

@tasks.loop(seconds=60)
async def panel_loop():

    await update_panel()

# =========================================================
# CHECK EVENTS LOOP
# =========================================================

@tasks.loop(seconds=15)
async def check_events():

    global EVENTS

    EVENTS = load_events()

    now = datetime.now(LOCAL_TZ)

    today_events = get_today_events()

    for event in today_events:

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

            unique_id = f"{event_name}-{event_dt}"

            warn_key = f"warn-{unique_id}"
            start_key = f"start-{unique_id}"

            # WARNING

            if (
                warn_key not in notified
                and warn_dt <= now < warn_dt + timedelta(seconds=15)
            ):

                notified.add(warn_key)

                save_notified()

                await send_alert(
                    f"🔔 {event_name}",
                    (
                        f"{role_ping()}\n\n"
                        f"⏳ Começa em 5 minutos.\n"
                        f"🕒 Horário: {event_dt.strftime('%H:%M')}"
                    ),
                    0xffcc00
                )

                if unique_id not in active_countdowns:

                    asyncio.create_task(
                        countdown_event(
                            unique_id,
                            event_name,
                            event_dt
                        )
                    )

            # START EVENT

            if (
                start_key not in notified
                and event_dt <= now < event_dt + timedelta(seconds=15)
            ):

                notified.add(start_key)

                save_notified()

                await send_alert(
                    f"🚨 {event_name}",
                    (
                        f"{role_ping()}\n\n"
                        f"⚔️ O evento começou!"
                    ),
                    0xff0000
                )

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(name="teste", description="Inicia um teste de countdown")
async def slash_teste(interaction: discord.Interaction):

    fake_dt = datetime.now(LOCAL_TZ) + timedelta(minutes=1)

    asyncio.create_task(
        countdown_event(
            "teste",
            "Boss Rush TESTE",
            fake_dt
        )
    )

    await interaction.response.send_message(
        "✅ Teste iniciado.",
        ephemeral=True
    )

@bot.tree.command(name="reload", description="Recarrega os eventos")
async def slash_reload(interaction: discord.Interaction):

    global EVENTS

    EVENTS = load_events()

    await interaction.response.send_message(
        "🔄 Eventos recarregados.",
        ephemeral=True
    )

@bot.tree.command(name="eventos", description="Lista os eventos")
async def slash_eventos(interaction: discord.Interaction):

    EVENTS = load_events()

    embed = discord.Embed(
        title="📅 Eventos Configurados",
        color=0x00ffcc
    )

    daily_text = ""

    for event in EVENTS.get("daily", []):

        times = ", ".join(event["times"])

        daily_text += f"**{event['name']}**\n{times}\n\n"

    if not daily_text:
        daily_text = "Nenhum evento diário."

    embed.add_field(
        name="🌎 Eventos Diários",
        value=daily_text,
        inline=False
    )

    weekly_text = ""

    for day, events in EVENTS.get("weekly", {}).items():

        weekly_text += f"**{day.capitalize()}**\n"

        for event in events:

            times = ", ".join(event["times"])

            weekly_text += f"- {event['name']} → {times}\n"

        weekly_text += "\n"

    if not weekly_text:
        weekly_text = "Nenhum evento semanal."

    embed.add_field(
        name="🗓️ Eventos Semanais",
        value=weekly_text,
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# =========================================================
# HEALTHCHECK RAILWAY
# =========================================================

async def healthcheck(request):
    return web.Response(text="Bot Online")

async def run_webserver():

    app = web.Application()

    app.router.add_get("/", healthcheck)

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)

    await site.start()

    logging.info(f"Healthcheck rodando na porta {PORT}")

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    global channel_cache

    logging.info(f"BOT ONLINE: {bot.user}")

    channel_cache = bot.get_channel(CHANNEL_ID)

    if channel_cache is None:

        logging.error("Canal não encontrado.")

        return

    try:

        synced = await bot.tree.sync()

        logging.info(f"Slash commands sincronizados: {len(synced)}")

    except Exception as e:

        logging.error(f"Erro slash commands: {e}")

    if not check_events.is_running():
        check_events.start()

    if not panel_loop.is_running():
        panel_loop.start()

    if not clean_notified.is_running():
        clean_notified.start()

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
