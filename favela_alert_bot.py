import os
import json
import asyncio
import logging
import discord

from aiohttp import web
from discord.ext import commands, tasks
from discord.ui import View

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# =========================================================
# CONFIG
# =========================================================

TOKEN = os.getenv("DISCORD_TOKEN")

CHANNEL_ID = 1508595763855229048
EVENT_ROLE_ID = 1508823642958594149

# ID DO SERVIDOR
GUILD_ID = 1508595762965774417

EVENT_FILE = "events.json"

NOTIFIED_FILE = "notified.json"
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

intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# =========================================================
# GLOBALS
# =========================================================

channel_cache = None

panel_message = None
role_message = None

active_countdowns = {}

# =========================================================
# EVENT EMOJIS
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

def save_panel_data(panel_id=None, role_id=None):

    data = {
        "panel_message_id": panel_id,
        "role_message_id": role_id
    }

    with open(PANEL_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def load_panel_data():

    if not os.path.exists(PANEL_FILE):
        return {}

    with open(PANEL_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# =========================================================
# NOTIFIED
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
# EVENT EMOJI
# =========================================================

def event_emoji(event_name):

    return EVENT_EMOJIS.get(event_name, "🎮")

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

async def send_alert(event_name, description, color):

    emoji = event_emoji(event_name)

    embed = discord.Embed(
        title=f"{emoji} {event_name}",
        description=description,
        color=color
    )

    embed.timestamp = datetime.now(LOCAL_TZ)

    await channel_cache.send(embed=embed)

# =========================================================
# GET EVENTS
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
                "time": event_dt,
                "diff": diff
            })

    upcoming.sort(key=lambda x: x["diff"])

    return upcoming[:limit]

# =========================================================
# UPDATE STATUS
# =========================================================

async def update_status():

    next_events = get_next_events(1)

    if not next_events:
        return

    event = next_events[0]

    await bot.change_presence(
        activity=discord.Game(
            name=f"{event['name']} em {format_countdown(event['diff'])}"
        )
    )

# =========================================================
# PANEL
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

            emoji = event_emoji(event["name"])

            text += (
                f"{emoji} **{event['name']}**\n"
                f"🕒 {event['time'].strftime('%H:%M')}\n"
                f"⏳ {format_countdown(event['diff'])}\n\n"
            )

        embed.description = text

    embed.set_footer(
        text="Atualiza automaticamente"
    )

    panel_data = load_panel_data()

    try:

        if panel_message is None:

            if panel_data.get("panel_message_id"):

                try:

                    panel_message = await channel_cache.fetch_message(
                        panel_data["panel_message_id"]
                    )

                except:
                    panel_message = None

        if panel_message is None:

            panel_message = await channel_cache.send(embed=embed)

            save_panel_data(
                panel_id=panel_message.id,
                role_id=panel_data.get("role_message_id")
            )

        else:

            await panel_message.edit(embed=embed)

    except Exception as e:

        logging.error(f"Erro painel: {e}")

# =========================================================
# ROLE BUTTON
# =========================================================

class RoleButton(View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Notificações",
        emoji="🔔",
        style=discord.ButtonStyle.green,
        custom_id="event_role_button"
    )
    async def role_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        role = interaction.guild.get_role(EVENT_ROLE_ID)

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

# =========================================================
# ROLE MESSAGE
# =========================================================

async def setup_role_message():

    global role_message

    panel_data = load_panel_data()

    embed = discord.Embed(
        title="🔔 Notificações de Eventos",
        description=(
            "Clique no botão abaixo para\n"
            "receber notificações dos eventos."
        ),
        color=0xffcc00
    )

    view = RoleButton()

    try:

        if panel_data.get("role_message_id"):

            try:

                role_message = await channel_cache.fetch_message(
                    panel_data["role_message_id"]
                )

            except:
                role_message = None

        if role_message is None:

            role_message = await channel_cache.send(
                embed=embed,
                view=view
            )

            save_panel_data(
                panel_id=panel_data.get("panel_message_id"),
                role_id=role_message.id
            )

        else:

            await role_message.edit(
                embed=embed,
                view=view
            )

    except Exception as e:

        logging.error(f"Erro role message: {e}")

# =========================================================
# COUNTDOWN
# =========================================================

async def countdown_event(event_id, event_name, event_dt):

    try:

        embed_message = None

        emoji = event_emoji(event_name)

        while True:

            now = datetime.now(LOCAL_TZ)

            remaining = (event_dt - now).total_seconds()

            if remaining <= 0:
                break

            embed = discord.Embed(
                title=f"{emoji} {event_name}",
                description=(
                    f"{role_ping()}\n\n"
                    f"⏳ Começa em:\n"
                    f"**{format_countdown(remaining)}**"
                ),
                color=0xffcc00
            )

            embed.timestamp = event_dt

            if embed_message is None:

                embed_message = await channel_cache.send(
                    embed=embed
                )

                active_countdowns[event_id] = embed_message

            else:

                try:
                    await embed_message.edit(embed=embed)
                except:
                    break

            await asyncio.sleep(15)

        final_embed = discord.Embed(
            title=f"{emoji} {event_name}",
            description=(
                f"{role_ping()}\n\n"
                f"🔥 Evento começou!"
            ),
            color=0xff0000
        )

        if embed_message:

            await embed_message.edit(embed=final_embed)

            await asyncio.sleep(120)

            try:
                await embed_message.delete()
            except:
                pass

    except Exception as e:

        logging.error(f"Erro countdown {event_name}: {e}")

# =========================================================
# CLEAN NOTIFIED
# =========================================================

@tasks.loop(hours=24)
async def clean_notified():

    global notified

    notified = set()

    save_notified()

# =========================================================
# PANEL LOOP
# =========================================================

@tasks.loop(seconds=60)
async def panel_loop():

    await update_panel()

    await update_status()

# =========================================================
# CHECK EVENTS
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

            if (
                warn_key not in notified
                and warn_dt <= now < warn_dt + timedelta(seconds=15)
            ):

                notified.add(warn_key)

                save_notified()

                await send_alert(
                    event_name,
                    (
                        f"{role_ping()}\n\n"
                        f"⏳ Começa em 5 minutos\n"
                        f"🕒 {event_dt.strftime('%H:%M')}"
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

            if (
                start_key not in notified
                and event_dt <= now < event_dt + timedelta(seconds=15)
            ):

                notified.add(start_key)

                save_notified()

                await send_alert(
                    event_name,
                    (
                        f"{role_ping()}\n\n"
                        f"🔥 Evento começou!"
                    ),
                    0xff0000
                )

# =========================================================
# SLASH COMMANDS
# =========================================================

@bot.tree.command(
    name="teste",
    description="Testa o bot",
    guild=discord.Object(id=GUILD_ID)
)
async def teste(interaction: discord.Interaction):

    logging.info("/teste executado")

    await interaction.response.defer(ephemeral=True)

    fake_dt = datetime.now(LOCAL_TZ) + timedelta(minutes=1)

    asyncio.create_task(
        countdown_event(
            "teste",
            "Boss Rush",
            fake_dt
        )
    )

    await interaction.followup.send(
        "✅ Teste iniciado.",
        ephemeral=True
    )

@bot.tree.command(
    name="reload",
    description="Recarrega eventos",
    guild=discord.Object(id=GUILD_ID)
)
async def reload(interaction: discord.Interaction):

    global EVENTS

    EVENTS = load_events()

    await interaction.response.send_message(
        "🔄 Eventos recarregados.",
        ephemeral=True
    )

@bot.tree.command(
    name="eventos",
    description="Lista eventos",
    guild=discord.Object(id=GUILD_ID)
)
async def eventos(interaction: discord.Interaction):

    embed = discord.Embed(
        title="📅 Eventos",
        color=0x00ffcc
    )

    text = ""

    for event in EVENTS.get("daily", []):

        emoji = event_emoji(event["name"])

        text += (
            f"{emoji} **{event['name']}**\n"
            f"{', '.join(event['times'])}\n\n"
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

    channel_cache = await bot.fetch_channel(CHANNEL_ID)

    guild = discord.Object(id=GUILD_ID)

    synced = await bot.tree.sync(guild=guild)

    logging.info(f"Slash sincronizados: {len(synced)}")

    bot.add_view(RoleButton())

    await setup_role_message()

    await update_panel()

    await update_status()

    if not panel_loop.is_running():
        panel_loop.start()

    if not clean_notified.is_running():
        clean_notified.start()

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
