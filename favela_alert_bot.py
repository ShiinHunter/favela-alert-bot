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

# =========================================================
# CANAIS
# =========================================================

PANEL_CHANNEL_ID = 1508595763855229048
ALERT_CHANNEL_ID = 1509274540600201216

# =========================================================
# CARGO
# =========================================================

EVENT_ROLE_ID = 1508823642958594149

# =========================================================
# ARQUIVOS
# =========================================================

EVENT_FILE = "events.json"
PANEL_FILE = "panel.json"

# =========================================================
# PORTA RAILWAY
# =========================================================

PORT = int(os.getenv("PORT", 8080))

# =========================================================
# TIMEZONE
# =========================================================

BR_TZ = ZoneInfo("America/Sao_Paulo")

# SERVER = BR +5
SERVER_OFFSET = 5

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
# CACHE
# =========================================================

panel_channel = None
alert_channel = None

panel_message = None
role_message = None

notified = set()

# =========================================================
# EVENT EMOJIS
# =========================================================

EVENT_EMOJIS = {
    "Escape Room": "🚪",
    "Boss Rush": "👹",
    "Ranked Arena": "⚔️",
    "Fortress War": "🏰",
    "Raids": "🐉",
    "Gold Fish": "🐟"
}

# =========================================================
# TIME UTILS
# =========================================================

def get_br_time():

    return datetime.now(BR_TZ)

def get_server_time():

    return get_br_time() + timedelta(hours=SERVER_OFFSET)

def server_to_br(server_dt):

    return server_dt - timedelta(hours=SERVER_OFFSET)

def get_server_weekday():

    weekdays = {
        "monday": "segunda",
        "tuesday": "terca",
        "wednesday": "quarta",
        "thursday": "quinta",
        "friday": "sexta",
        "saturday": "sabado",
        "sunday": "domingo"
    }

    server_now = get_server_time()

    return weekdays[
        server_now.strftime("%A").lower()
    ]

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
# PANEL DATA
# =========================================================

def save_panel_data(
    panel_id=None,
    role_id=None
):

    with open(
        PANEL_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump({
            "panel_message_id": panel_id,
            "role_message_id": role_id
        }, f)

def load_panel_data():

    if not os.path.exists(PANEL_FILE):
        return {}

    try:

        with open(
            PANEL_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except:
        return {}

# =========================================================
# HELPERS
# =========================================================

def role_ping():

    return f"<@&{EVENT_ROLE_ID}>"

def event_emoji(event_name):

    return EVENT_EMOJIS.get(
        event_name,
        "🎮"
    )

def format_countdown(seconds):

    if seconds <= 0:
        return "AGORA"

    hours, remainder = divmod(
        int(seconds),
        3600
    )

    minutes, seconds = divmod(
        remainder,
        60
    )

    if hours > 0:

        return f"{hours:02d}h {minutes:02d}m"

    return f"{minutes:02d}m {seconds:02d}s"

# =========================================================
# GET EVENTS FROM DAY
# =========================================================

def get_events_from_day(day_name):

    events = []

    # DAILY
    for event in EVENTS.get(
        "daily",
        []
    ):

        events.append(event)

    # WEEKLY
    weekly_events = EVENTS.get(
        "weekly",
        {}
    ).get(day_name, [])

    for event in weekly_events:

        events.append(event)

    return events

# =========================================================
# NEXT EVENTS
# =========================================================

def get_next_events():

    upcoming = []

    server_now = get_server_time()

    server_days = [
        "segunda",
        "terca",
        "quarta",
        "quinta",
        "sexta",
        "sabado",
        "domingo"
    ]

    current_day_index = server_days.index(
        get_server_weekday()
    )

    # HOJE + AMANHÃ
    for offset_day in range(2):

        day_index = (
            current_day_index + offset_day
        ) % 7

        day_name = server_days[day_index]

        day_events = get_events_from_day(
            day_name
        )

        for event in day_events:

            for event_time in event["times"]:

                hour, minute = map(
                    int,
                    event_time.split(":")
                )

                server_event_dt = (
                    server_now + timedelta(days=offset_day)
                ).replace(
                    hour=hour,
                    minute=minute,
                    second=0,
                    microsecond=0
                )

                # evento começa +5min
                server_event_dt += timedelta(minutes=5)

                br_event_dt = server_to_br(
                    server_event_dt
                )

                diff = (
                    br_event_dt - get_br_time()
                ).total_seconds()

                if diff <= 0:
                    continue

                upcoming.append({
                    "name": event["name"],
                    "time": br_event_dt.strftime("%d/%m %H:%M"),
                    "diff": diff
                })

    upcoming.sort(
        key=lambda x: x["diff"]
    )

    return upcoming[:10]

# =========================================================
# SEND ALERT
# =========================================================

async def send_alert(
    event_name,
    message,
    color
):

    if alert_channel is None:
        return

    embed = discord.Embed(
        title=f"{event_emoji(event_name)} {event_name}",
        description=message,
        color=color
    )

    embed.timestamp = get_br_time()

    await alert_channel.send(
        embed=embed
    )

# =========================================================
# ROLE BUTTON
# =========================================================

class NotificationView(View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

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

        role = interaction.guild.get_role(
            EVENT_ROLE_ID
        )

        if role is None:

            await interaction.response.send_message(
                "❌ Cargo não encontrado.",
                ephemeral=True
            )

            return

        try:

            if role in interaction.user.roles:

                await interaction.user.remove_roles(
                    role
                )

                await interaction.response.send_message(
                    "❌ Notificações removidas.",
                    ephemeral=True
                )

            else:

                await interaction.user.add_roles(
                    role
                )

                await interaction.response.send_message(
                    "✅ Notificações ativadas.",
                    ephemeral=True
                )

        except Exception as e:

            logging.error(
                f"Erro cargo: {e}"
            )

            await interaction.response.send_message(
                "❌ Não consegui alterar seu cargo.",
                ephemeral=True
            )

# =========================================================
# ROLE PANEL
# =========================================================

async def setup_role_panel():

    global role_message

    panel_data = load_panel_data()

    embed = discord.Embed(
        title="🔔 Notificações de Eventos",
        description=(
            "Clique no botão abaixo para\n"
            "receber alertas automáticos."
        ),
        color=0xffcc00
    )

    embed.add_field(
        name="📢 Eventos",
        value=(
            "🚪 Escape Room\n"
            "👹 Boss Rush\n"
            "⚔️ Ranked Arena\n"
            "🏰 Fortress War\n"
            "🐉 Raids\n"
            "🐟 Gold Fish"
        ),
        inline=False
    )

    view = NotificationView()

    try:

        role_message_id = panel_data.get(
            "role_message_id"
        )

        if role_message_id:

            try:

                role_message = await panel_channel.fetch_message(
                    role_message_id
                )

            except:

                role_message = None

        if role_message is None:

            role_message = await panel_channel.send(
                embed=embed,
                view=view
            )

            save_panel_data(
                panel_data.get(
                    "panel_message_id"
                ),
                role_message.id
            )

        else:

            await role_message.edit(
                embed=embed,
                view=view
            )

    except Exception as e:

        logging.error(
            f"Erro painel cargo: {e}"
        )

# =========================================================
# UPDATE PANEL
# =========================================================

async def update_panel():

    global panel_message

    if panel_channel is None:
        return

    upcoming = get_next_events()

    description = ""

    if not upcoming:

        description = (
            "Nenhum evento encontrado."
        )

    else:

        for event in upcoming:

            description += (
                f"{event_emoji(event['name'])} "
                f"**{event['name']}**\n"
                f"🕒 {event['time']}\n"
                f"⏳ {format_countdown(event['diff'])}\n\n"
            )

    embed = discord.Embed(
        title="📅 Próximos Eventos",
        description=description,
        color=0x00ffcc
    )

    embed.set_footer(
        text="Atualização automática"
    )

    panel_data = load_panel_data()

    try:

        panel_message_id = panel_data.get(
            "panel_message_id"
        )

        if panel_message_id:

            try:

                panel_message = await panel_channel.fetch_message(
                    panel_message_id
                )

            except:

                panel_message = None

        if panel_message is None:

            panel_message = await panel_channel.send(
                embed=embed
            )

            save_panel_data(
                panel_message.id,
                panel_data.get(
                    "role_message_id"
                )
            )

        else:

            await panel_message.edit(
                embed=embed
            )

    except Exception as e:

        logging.error(
            f"Erro painel: {e}"
        )

# =========================================================
# PANEL LOOP
# =========================================================

@tasks.loop(seconds=60)
async def panel_loop():

    await update_panel()

# =========================================================
# CHECK EVENTS
# =========================================================

@tasks.loop(seconds=15)
async def check_events():

    server_now = get_server_time()

    current_day = get_server_weekday()

    events_today = get_events_from_day(
        current_day
    )

    for event in events_today:

        event_name = event["name"]

        for event_time in event["times"]:

            hour, minute = map(
                int,
                event_time.split(":")
            )

            server_event_dt = server_now.replace(
                hour=hour,
                minute=minute,
                second=0,
                microsecond=0
            )

            # evento real começa +5min
            server_event_dt += timedelta(minutes=5)

            warn_dt = (
                server_event_dt
                - timedelta(minutes=5)
            )

            warn_key = (
                f"{event_name}-warn-"
                f"{server_event_dt.strftime('%Y%m%d%H%M')}"
            )

            start_key = (
                f"{event_name}-start-"
                f"{server_event_dt.strftime('%Y%m%d%H%M')}"
            )

            # 5 MIN
            if (
                warn_key not in notified
                and warn_dt <= server_now < warn_dt + timedelta(seconds=20)
            ):

                notified.add(
                    warn_key
                )

                await send_alert(
                    event_name,
                    (
                        f"{role_ping()}\n\n"
                        f"⏳ Começa em 5 minutos"
                    ),
                    0xffcc00
                )

            # START
            if (
                start_key not in notified
                and server_event_dt <= server_now < server_event_dt + timedelta(seconds=20)
            ):

                notified.add(
                    start_key
                )

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

    msg = await alert_channel.send(
        embed=embed
    )

    remaining = 60

    while remaining > 0:

        embed.description = (
            f"{role_ping()}\n\n"
            f"⏳ Começa em:\n"
            f"**{format_countdown(remaining)}**"
        )

        await msg.edit(
            embed=embed
        )

        await asyncio.sleep(5)

        remaining -= 5

    embed = discord.Embed(
        title="👹 Boss Rush",
        description=(
            f"{role_ping()}\n\n"
            f"🔥 Evento começou!"
        ),
        color=0xff0000
    )

    await msg.edit(
        embed=embed
    )

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="teste",
    description="Simula um evento"
)
async def teste(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    asyncio.create_task(
        simulated_event()
    )

    await interaction.followup.send(
        "✅ Evento teste iniciado.",
        ephemeral=True
    )

@bot.tree.command(
    name="painel",
    description="Atualiza o painel"
)
async def painel(
    interaction: discord.Interaction
):

    await interaction.response.defer(
        ephemeral=True
    )

    await update_panel()

    await interaction.followup.send(
        "✅ Painel atualizado.",
        ephemeral=True
    )

# =========================================================
# HEALTHCHECK
# =========================================================

async def healthcheck(request):

    return web.Response(
        text="ONLINE"
    )

async def run_webserver():

    app = web.Application()

    app.router.add_get(
        "/",
        healthcheck
    )

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

    global panel_channel
    global alert_channel

    logging.info(
        f"BOT ONLINE: {bot.user}"
    )

    try:

        panel_channel = await bot.fetch_channel(
            PANEL_CHANNEL_ID
        )

        alert_channel = await bot.fetch_channel(
            ALERT_CHANNEL_ID
        )

        logging.info(
            "Canais carregados."
        )

    except Exception as e:

        logging.error(
            f"Erro canais: {e}"
        )

        return

    bot.add_view(
        NotificationView()
    )

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
