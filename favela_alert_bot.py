import os
import asyncio
import discord
from discord.ext import tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =============================
# CONFIGURE AQUI
# =============================
TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149

# =============================
# EVENTOS (HORÁRIO DE BRASÍLIA)
# HORÁRIO REAL DE INÍCIO
# =============================
DAILY_EVENTS = {
    "Boss Rush": ["10:05"],
    "Room Escape": ["00:05", "08:05", "16:05"],
}

# =============================
# DISCORD CONFIG
# =============================
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)


def role_ping():
    return f"<@&{EVENT_ROLE_ID}>" if EVENT_ROLE_ID else "@Event Ping"


async def send_alert(message):
    channel = client.get_channel(CHANNEL_ID)

    if channel:
        await channel.send(
            "━━━━━━━━━━━━━━━━━━\n"
            "⚔️ **FAVELA ALERT SYSTEM** ⚔️\n\n"
            f"{role_ping()}\n"
            f"{message}\n\n"
            "🔥 **Favela unida jamais será abatida!**\n"
            "━━━━━━━━━━━━━━━━━━"
        )


@client.event
async def on_ready():
    print(f"Bot online: {client.user}")
    check_events.start()


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    cmd = message.content.lower()

    if cmd == "!teste" or cmd == "!ping":
        await send_alert(
            "🔔 **TESTE: Boss Rush em 10 minutos!**\n"
            "Prepare seus equipamentos e fique atento."
        )

        await message.channel.send(
            "⏳ Aguarde 5 segundos para simular o início do evento..."
        )

        await asyncio.sleep(5)

        await send_alert(
            "🚨 **TESTE: Boss Rush começou AGORA!**\n"
            "Corre pro evento!"
        )


@tasks.loop(minutes=1)
async def check_events():
    now = datetime.now(ZoneInfo("America/Sao_Paulo"))
    current = now.strftime("%H:%M")

    for event_name, times in DAILY_EVENTS.items():
        for start_time in times:
            start_dt = datetime.strptime(start_time, "%H:%M")
            warn_dt = start_dt - timedelta(minutes=10)

            warn_time = warn_dt.strftime("%H:%M")

            # AVISO 10 MINUTOS ANTES
            if current == warn_time:
                await send_alert(
                    f"🔔 **{event_name} em 10 minutos!**\n"
                    "Prepare seus equipamentos e fique atento."
                )

            # EVENTO COMEÇOU
            if current == start_time:
                await send_alert(
                    f"🚨 **{event_name} começou AGORA!**\n"
                    "Corre pro evento!"
                )


client.run(TOKEN)
