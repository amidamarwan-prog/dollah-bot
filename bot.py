import discord
from discord.ext import commands
from datetime import timedelta, datetime
import re
import os
import asyncio

# ---- INTENTS ----
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ---- DATA STORAGE ----
user_infractions = {}      # {user_id: int}
user_last_message = {}     # {user_id: (last_content, repeat_count)}
user_warnings = {}         # {user_id: int}
user_message_times = {}    # {user_id: [timestamps]}

# ---- SETTINGS ----
invite_pattern = re.compile(r"(discord\.gg\/|discord\.com\/invite\/)")
LOG_CHANNEL_NAME = "mod-log"
SPAM_WINDOW_SECONDS = 8
SPAM_MAX_MESSAGES = 5


# ---- HELPERS ----
def get_log_channel(guild: discord.Guild | None):
    if guild is None:
        return None
    return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)


async def send_temp_msg(channel: discord.TextChannel, content: str, delay: int = 5):
    try:
        msg = await channel.send(content)
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        # Never crash the bot over a message or delete error
        pass


def add_message_timestamp(user_id: int):
    now = datetime.utcnow()
    times = user_message_times.get(user_id, [])
    times.append(now)
    # Keep only recent timestamps
    cutoff = now.timestamp() - SPAM_WINDOW_SECONDS
    times = [t for t in times if t.timestamp() >= cutoff]
    user_message_times[user_id] = times
    return len(times)


# ---- BOT READY ----
@bot.event
async def on_ready():
    print(f"Dollah is online as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")


# ---- MESSAGE HANDLER ----
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    guild = message.guild
    log_channel = get_log_channel(guild)
    user_id = message.author.id
    content = message.content.lower()

    # ---- ANTI-SPAM (message frequency) ----
    msg_count = add_message_timestamp(user_id)
    if msg_count > SPAM_MAX_MESSAGES:
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1
        await send_temp_msg(
            message.channel,
            f"{message.author.mention} slow down, you're sending messages too fast.",
            delay=5,
        )
        if log_channel:
            await log_channel.send(
                f"{message.author} flagged for spam. Infractions: {user_infractions[user_id]}"
            )

    # ---- INVITE LINK MODERATION ----
    if invite_pattern.search(content):
        try:
            await message.delete()
        except Exception:
            pass

        await send_temp_msg(
            message.channel,
            f"{message.author.mention} no invite links.",
            delay=5,
        )

        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1

        if log_channel:
            await log_channel.send(
                f"{message.author} posted an invite link. Infractions: {user_infractions[user_id]}"
            )

    # ---- REPEATED MESSAGE MODERATION ----
    last_msg, repeat_count = user_last_message.get(user_id, ("", 0))

    if content == last_msg:
        repeat_count += 1
    else:
        repeat_count = 1

    user_last_message[user_id] = (content, repeat_count)

    if repeat_count == 3:
        await send_temp_msg(
            message.channel,
            f"{message.author.mention} stop repeating the same message.",
            delay=5,
        )
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1

        if log_channel:
            await log_channel.send(
                f"{message.author} repeated messages. Infractions: {user_infractions[user_id]}"
            )# ---- INFRACTION ACTIONS ----
    infractions = user_infractions.get(user_id, 0)

    # Timeout at 2 infractions
    if infractions == 2:
        try:
            await message.author.timeout(timedelta(minutes=10))
        except Exception:
            pass

        await send_temp_msg(
            message.channel,
            f"{message.author.mention} has been timed out for 10 minutes.",
            delay=5,
        )

        if log_channel:
            await log_channel.send(f"{message.author} was timed out (2 infractions).")

    # Ban at 3+ infractions
    154    if infractions >= 3:
        try:
          await guild.ban(message.author, reason="Repeated infractions")
        except Exception:
            pass

        await send_temp_msg(
            message.channel,
            f"{message.author.mention} has been banned for repeated infractions.",
            delay=5,
        )
@bot.command(name="helpme")
async def helpme(ctx):
    """Custom help command."""
    text = (
        "**Dollah Bot Commands**\n"
        "- `!hello` — test if the bot is alive\n"
        "- `!helpme` — show this help message\n"
        "- `!modpanel` — show mod tools (mods only)\n"
        "- `!warn @user [reason]` — warn a user (mods only)\n"
        "- `!warnings @user` — view warnings (mods only)\n"
        "- `!clearwarnings @user` — clear warnings (mods only)\n"
        "- `/ban @user [reason]` — ban via slash command (mods only)\n"
    )
    await ctx.send(text)


# ---- SLASH /BAN COMMAND ----
@bot.tree.command(name="ban", description="Ban a user (mod only).")
@discord.app_commands.checks.has_permissions(ban_members=True)
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    guild = interaction.guild
    log_channel = get_log_channel(guild)

    try:
        await guild.ban(member, reason=reason)
        await interaction.response.send_message(
            f"{member.mention} has been banned. Reason: {reason}", ephemeral=True
        )
        if log_channel:
            await log_channel.send(
                f"{member} was banned via /ban by {interaction.user}. Reason: {reason}"
            )
    except Exception:
        await interaction.response.send_message(
            "I couldn't ban that user. Check my permissions.", ephemeral=True
        )


@ban_slash.error
async def ban_slash_error(interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You don't have permission to use this command.", ephemeral=True
        )
    else:
        try:
            await interaction.response.send_message(
                "Something went wrong using this command.", ephemeral=True
            )
        except Exception:
            pass


# ---- RUN BOT ----
bot.run(os.environ["DISCORD_BOT_TOKEN"])


