import discord
from discord.ext import tasks
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =============================
# CONFIGURE AQUI
# =============================
TOKEN = "COLE_SEU_NOVO_TOKEN_AQUI"
CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = None  # opcional: coloque o ID do cargo @Event Ping

# Horário local do usuário (Brasília)
TZ = ZoneInfo("America/Sao_Paulo")

# Eventos importantes (horário REAL de início em Brasília)
DAILY_EVENTS = {
    "Boss Rush": ["10:05"],
    "Room Escape": ["00:05", "08:05", "16:05"],
}

# weekday: Monday=0 ... Sunday=6
WEEKLY_EVENTS = {
    "Dark Zone": {0: [("01:00", "18:59")], 1: [("01:00", "18:59")], 2: [("01:00", "18:59")], 3: [("01:00", "18:59")], 4: [("01:00", "18:59")]},
    "Ranked Arena": {1: [("10:35", "11:35"), ("15:35", "16:35")], 2: [("10:35", "11:35"), ("15:35", "16:35")], 3: [("10:35", "11:35"), ("15:35", "16:35")]},
    "Fortress War": {6: [("10:35", "12:05")]},
    "Raids": {4: [("00:00", "23:59")], 5: [("00:00", "23:59")]},
}

intents = discord.Intents.default()
client = discord.Client(intents=intents)

sent_cache = set()


def role_ping():
    return f"<@&{EVENT_ROLE_ID}>" if EVENT_ROLE_ID else "@Event Ping"


async def send_alert(message: str):
    channel = client.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(message)


@tasks.loop(minutes=1)
async def scheduler():
    now = datetime.now(TZ)
    current = now.strftime("%H:%M")
    today = now.weekday()

    # DAILY: 10 min before + started now
    for event_name, times in DAILY_EVENTS.items():
        for t in times:
            start_dt = datetime.strptime(t, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            warn_dt = start_dt - timedelta(minutes=10)
            warn = warn_dt.strftime("%H:%M")

            key_warn = f"{now.date()}-{event_name}-{warn}-warn"
            key_start = f"{now.date()}-{event_name}-{t}-start"

            if current == warn and key_warn not in sent_cache:
                await send_alert(f"🔔 {role_ping()}\n\n**{event_name}** começa em **10 minutos!**")
                sent_cache.add(key_warn)

            if current == t and key_start not in sent_cache:
                await send_alert(f"🔥 {role_ping()}\n\n**{event_name}** começou agora!")
                sent_cache.add(key_start)

    # WEEKLY: notify at start only
    for event_name, schedule in WEEKLY_EVENTS.items():
        if today in schedule:
            for start, end in schedule[today]:
                key = f"{now.date()}-{event_name}-{start}"
                if current == start and key not in sent_cache:
                    await send_alert(f"📅 {role_ping()}\n\n**{event_name}** começou!\nJanela: {start}–{end}")
                    sent_cache.add(key)


@client.event
async def on_ready():
    print(f"Bot online: {client.user}")
    scheduler.start()


client.run(TOKEN)
