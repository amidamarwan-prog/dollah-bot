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
user_infractions = {}
user_last_message = {}
user_warnings = {}
user_message_times = {}

# ---- SETTINGS ----
invite_pattern = re.compile(r"(discord\.gg\/|discord\.com\/invite\/)")
LOG_CHANNEL_NAME = "mod-log"
SPAM_WINDOW_SECONDS = 8
SPAM_MAX_MESSAGES = 5


# ---- HELPERS ----
def get_log_channel(guild):
    if guild is None:
        return None
    return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)


async def send_temp_msg(channel, content, delay=5):
    try:
        msg = await channel.send(content)
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass


def add_message_timestamp(user_id):
    now = datetime.utcnow()
    times = user_message_times.get(user_id, [])
    times.append(now)
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
async def on_message(message):
    if message.author.bot:
        return

    guild = message.guild
    log_channel = get_log_channel(guild)
    user_id = message.author.id
    content = message.content.lower()

    # ---- ANTI-SPAM ----
    msg_count = add_message_timestamp(user_id)
    if msg_count > SPAM_MAX_MESSAGES:
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1
        await send_temp_msg(message.channel, f"{message.author.mention} slow down.", 5)
        if log_channel:
            await log_channel.send(f"{message.author} flagged for spam.")

    # ---- INVITE LINK MOD ----
    if invite_pattern.search(content):
        try:
            await message.delete()
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} no invite links.", 5)
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1

        if log_channel:
            await log_channel.send(f"{message.author} posted an invite link.")

    # ---- REPEATED MESSAGE ----
    last_msg, repeat_count = user_last_message.get(user_id, ("", 0))

    if content == last_msg:
        repeat_count += 1
    else:
        repeat_count = 1

    user_last_message[user_id] = (content, repeat_count)

    if repeat_count == 3:
        await send_temp_msg(message.channel, f"{message.author.mention} stop repeating.", 5)
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1

        if log_channel:
            await log_channel.send(f"{message.author} repeated messages.")

    # ---- INFRACTION ACTIONS ----
    infractions = user_infractions.get(user_id, 0)

    # Timeout at 2
    if infractions == 2:
        try:
            await message.author.timeout(timedelta(minutes=10))
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} timed out.", 5)

        if log_channel:
            await log_channel.send(f"{message.author} was timed out.")

    # Ban at 3+
    if infractions >= 3:
        try:
            await guild.ban(message.author, reason="Repeated infractions")
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} banned.", 5)

        if log_channel:
            await log_channel.send(f"{message.author} was banned.")

    await bot.process_commands(message)


# ---- WARNING SYSTEM ----
def add_warning(user_id):
    user_warnings[user_id] = user_warnings.get(user_id, 0) + 1
    return user_warnings[user_id]


@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason="No reason provided"):
    count = add_warning(member.id)
    await ctx.send(f"{member.mention} warned. Total warnings: {count}. Reason: {reason}")

    log_channel = get_log_channel(ctx.guild)
    if log_channel:
        await log_channel.send(f"{member} warned by {ctx.author}. Reason: {reason}")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnings(ctx, member: discord.Member):
    count = user_warnings.get(member.id, 0)
    await ctx.send(f"{member.mention} has {count} warning(s).")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearwarnings(ctx, member: discord.Member):
    user_warnings[member.id] = 0
    await ctx.send(f"{member.mention}'s warnings cleared.")


# ---- MOD PANEL ----
@bot.command()
@commands.has_permissions(manage_guild=True)
async def modpanel(ctx):
    text = (
        "**Mod Panel**\n"
        "- !warn @user [reason]\n"
        "- !warnings @user\n"
        "- !clearwarnings @user\n"
        "- /ban @user [reason]\n"
    )
    await ctx.send(text)


# ---- BASIC COMMANDS ----
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.user)
async def hello(ctx):
    await ctx.send("Yo, Dollah is here!")


@bot.command(name="helpme")
async def helpme(ctx):
    text = (
        "**Dollah Bot Commands**\n"
        "- !hello\n"
        "- !helpme\n"
        "- !modpanel\n"
        "- !warn @user\n"
        "- !warnings @user\n"
        "- !clearwarnings @user\n"
        "- /ban @user\n"
    )
    await ctx.send(text)


# ---- SLASH BAN ----
@bot.tree.command(name="ban", description="Ban a user (mod only).")
@discord.app_commands.checks.has_permissions(ban_members=True)
async def ban_slash(interaction, member: discord.Member, reason: str = "No reason provided"):
    guild = interaction.guild
    log_channel = get_log_channel(guild)

    try:
        await guild.ban(member, reason=reason)
        await interaction.response.send_message(
            f"{member.mention} banned. Reason: {reason}", ephemeral=True
        )
        if log_channel:
            await log_channel.send(f"{member} banned via /ban by {interaction.user}.")
    except Exception:
        await interaction.response.send_message(
            "I couldn't ban that user. Check my permissions.", ephemeral=True
        )


# ---- RUN BOT ----
bot.run(os.environ["DISCORD_BOT_TOKEN"])



