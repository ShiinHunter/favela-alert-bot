import os
import json
import asyncio
import discord
from discord.ext import tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =============================
# CONFIG
# =============================
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149
EVENT_FILE = "events.json"

intents = discord.Intents.default()
client = discord.Client(intents=intents)

notified = set()
active_countdowns = {}  # evento -> mensagem embed


# =============================
# LOAD EVENTS
# =============================
def load_events():
    if not os.path.exists(EVENT_FILE):
        return {}
    with open(EVENT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


DAILY_EVENTS = load_events()


# =============================
# ROLE PING
# =============================
def role_ping():
    return f"<@&{EVENT_ROLE_ID}>" if EVENT_ROLE_ID else "@Event Ping"


# =============================
# FORMAT COUNTDOWN
# =============================
def format_countdown(seconds):
    if seconds <= 0:
        return "AGORA"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s"


# =============================
# ALERT EMBED
# =============================
async def send_alert(message):
    channel = await client.fetch_channel(CHANNEL_ID)

    embed = discord.Embed(
        title="🎮 Aero Tales",
        description=f"⚔️ **Favela Alerta** ⚔️\n\n{role_ping()}\n\n{message}",
        color=0x00ffcc
    )

    embed.set_image(url="https://i.imgur.com/SEU_BANNER_AQUI.png")

    await channel.send(embed=embed)


# =============================
# COUNTDOWN EMBED UPDATE
# =============================
async def update_countdown(event_name, event_dt):
    channel = await client.fetch_channel(CHANNEL_ID)

    while True:
        now = datetime.now(ZoneInfo("America/Sao_Paulo"))
        diff = (event_dt - now).total_seconds()

        if diff <= 0:
            break

        embed = discord.Embed(
            title=f"🎮 Aero Tales - {event_name}",
            description=(
                "⚔️ **Favela Alerta** ⚔️\n\n"
                f"⏳ **Começa em:** {format_countdown(diff)}\n"
                f"{role_ping()}"
            ),
            color=0xffcc00
        )

        embed.set_image(url="https://i.imgur.com/SEU_BANNER_AQUI.png")

        if event_name in active_countdowns:
            msg = active_countdowns[event_name]
            await msg.edit(embed=embed)
        else:
            msg = await channel.send(embed=embed)
            active_countdowns[event_name] = msg

        await asyncio.sleep(20)


# =============================
# EVENT LOOP
# =============================
@tasks.loop(seconds=20)
async def check_events():
    global DAILY_EVENTS

    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    today = now.date()

    for event_name, times in DAILY_EVENTS.items():
        for t in times:

            hour, minute = map(int, t.split(":"))

            event_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            warn_dt = event_dt - timedelta(minutes=5)

            warn_key = f"{event_name}-warn-{today}-{t}"
            start_key = f"{event_name}-start-{today}-{t}"
            countdown_key = f"{event_name}-cd-{today}-{t}"

            # =====================
            # 5 MIN WARNING
            # =====================
            if warn_key not in notified:
                if warn_dt <= now < warn_dt + timedelta(seconds=30):
                    notified.add(warn_key)

                    await send_alert(
                        f"🔔 **{event_name} em 5 minutos!**\n⏳ Horário: {t}"
                    )

            # =====================
            # START EVENT
            # =====================
            if start_key not in notified:
                if event_dt <= now < event_dt + timedelta(seconds=30):
                    notified.add(start_key)

                    await send_alert(
                        f"🚨 **{event_name} COMEÇOU!**\n⚔️ Horário: {t}"
                    )

            # =====================
            # COUNTDOWN START (5 min antes)
            # =====================
            if countdown_key not in notified:
                if warn_dt <= now < warn_dt + timedelta(seconds=30):
                    notified.add(countdown_key)

                    asyncio.create_task(update_countdown(event_name, event_dt))


# =============================
# READY
# =============================
@client.event
async def on_ready():
    print(f"Bot online: {client.user}")

    global DAILY_EVENTS
    DAILY_EVENTS = load_events()

    check_events.start()


# =============================
# TEST
# =============================
@client.event
async def on_message(message):
    if message.author == client.user:
        return

    if message.content == "!teste":
        await send_alert("🔔 Boss Rush em 5 minutos (TESTE)")
        await asyncio.sleep(2)
        await send_alert("🚨 Boss Rush começou (TESTE)")


# =============================
# RUN
# =============================
client.run(TOKEN)
