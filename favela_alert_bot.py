import os
import json
import asyncio
import discord

from discord.ext import commands, tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149

EVENT_FILE = "events.json"

# Horário do jogo (UTC-5)
GAME_TZ = ZoneInfo("Etc/GMT+5")

# Horário Brasil
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

notified = set()

active_countdowns = {}

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

    minutes, seconds = divmod(int(seconds), 60)

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

        print(f"[ERRO COUNTDOWN] {event_name}: {e}")

    finally:

        if event_id in active_countdowns:
            del active_countdowns[event_id]

# =========================================================
# GET TODAY EVENTS
# =========================================================

def get_today_events():

    events = []

    # DAILY EVENTS
    for event in EVENTS.get("daily", []):
        events.append(event)

    # WEEKLY EVENTS
    weekday = datetime.now(LOCAL_TZ).strftime("%A").lower()

    weekly_events = EVENTS.get("weekly", {}).get(weekday, [])

    for event in weekly_events:
        events.append(event)

    return events

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

        for game_time in event["times"]:

            hour, minute = map(int, game_time.split(":"))

            # =========================================
            # HORÁRIO DO JOGO (UTC-5)
            # =========================================

            game_now = datetime.now(GAME_TZ)

            game_dt = game_now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )

            # Se já passou hoje, pula
            if game_dt < game_now:
                continue

            # =========================================
            # CONVERTE PRA BRASIL
            # =========================================

            local_dt = game_dt.astimezone(LOCAL_TZ)

            warn_dt = local_dt - timedelta(minutes=5)

            unique_id = f"{event_name}-{local_dt}"

            warn_key = f"warn-{unique_id}"
            start_key = f"start-{unique_id}"

            # =========================================
            # WARNING
            # =========================================

            if (
                warn_key not in notified
                and warn_dt <= now < warn_dt + timedelta(seconds=15)
            ):

                notified.add(warn_key)

                await send_alert(
                    f"🔔 {event_name}",
                    (
                        f"{role_ping()}\n\n"
                        f"⏳ Começa em 5 minutos.\n"
                        f"🕒 Horário: {local_dt.strftime('%H:%M')}"
                    ),
                    0xffcc00
                )

                if unique_id not in active_countdowns:

                    asyncio.create_task(
                        countdown_event(
                            unique_id,
                            event_name,
                            local_dt
                        )
                    )

            # =========================================
            # START EVENT
            # =========================================

            if (
                start_key not in notified
                and local_dt <= now < local_dt + timedelta(seconds=15)
            ):

                notified.add(start_key)

                await send_alert(
                    f"🚨 {event_name}",
                    (
                        f"{role_ping()}\n\n"
                        f"⚔️ O evento começou!"
                    ),
                    0xff0000
                )

# =========================================================
# READY
# =========================================================

@bot.event
async def on_ready():

    global channel_cache

    print("=" * 50)
    print(f"BOT ONLINE: {bot.user}")
    print("=" * 50)

    channel_cache = bot.get_channel(CHANNEL_ID)

    if channel_cache is None:
        print("ERRO: Canal não encontrado.")
        return

    if not check_events.is_running():
        check_events.start()

# =========================================================
# TEST COMMAND
# =========================================================

@bot.command()
async def teste(ctx):

    fake_dt = datetime.now(LOCAL_TZ) + timedelta(minutes=1)

    asyncio.create_task(
        countdown_event(
            "teste",
            "Boss Rush TESTE",
            fake_dt
        )
    )

    await ctx.send("✅ Teste iniciado.")

# =========================================================
# RELOAD EVENTS
# =========================================================

@bot.command()
async def reload(ctx):

    global EVENTS

    EVENTS = load_events()

    await ctx.send("🔄 Eventos recarregados.")

# =========================================================
# LIST EVENTS
# =========================================================

@bot.command()
async def eventos(ctx):

    EVENTS = load_events()

    embed = discord.Embed(
        title="📅 Eventos Configurados",
        color=0x00ffcc
    )

    # DAILY
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

    # WEEKLY
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

    await ctx.send(embed=embed)

# =========================================================
# ERROR HANDLER
# =========================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CommandNotFound):
        return

    await ctx.send(f"❌ Erro: {error}")

    print(error)

# =========================================================
# RUN
# =========================================================

bot.run(TOKEN)
