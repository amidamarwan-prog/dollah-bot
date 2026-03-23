import os
import re
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv

# ==========================
# LOAD TOKEN
# ==========================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
LOG_CHANNEL_NAME = "mod-logs"

# ==========================
# BOT SETUP
# ==========================
INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.guilds = True

bot = commands.Bot(
    command_prefix="?",
    intents=INTENTS,
    help_command=None,
    activity=discord.Activity(type=discord.ActivityType.watching, name="over the server"),
    status=discord.Status.online
)

log_channel = None

# ==========================
# SWEAR FILTER (ENGLISH + SLANG + INTERNATIONAL)
# ==========================
BASE_SWEARS = {
    "fuck", "shit", "bitch", "bastard", "cunt", "asshole", "prick", "dick",
    "slut", "whore", "wanker", "bollocks",
    "puta", "puto", "cabron", "mierda",
    "scheisse", "arschloch",
    "merde", "salope",
    "chuj", "kurwa",
    "pendejo",
}

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text

def contains_swear(text: str) -> bool:
    norm = normalize(text)
    for word in BASE_SWEARS:
        if word in norm:
            return True
    return False

# ==========================
# MOD CHECK
# ==========================
def is_mod(member: discord.Member) -> bool:
    return member.guild_permissions.manage_messages or member.guild_permissions.administrator

# ==========================
# LOGGING
# ==========================
async def log(guild: discord.Guild, message: str):
    global log_channel
    if log_channel is None:
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
    if log_channel:
        await log_channel.send(message)

# ==========================
# ANTI-SPAM / ANTI-REPEAT TRACKING
# ==========================
recent_messages = {}
last_message_content = {}

def is_spam(message: discord.Message) -> bool:
    now = time.time()
    user_id = message.author.id
    timestamps = recent_messages.get(user_id, [])
    timestamps = [t for t in timestamps if now - t < 5]
    timestamps.append(now)
    recent_messages[user_id] = timestamps
    return len(timestamps) >= 5

def is_repeat(message: discord.Message) -> bool:
    user_id = message.author.id
    last = last_message_content.get(user_id)
    last_message_content[user_id] = message.content
    return last is not None and last == message.content and len(message.content) > 5

def has_link(message: discord.Message) -> bool:
    return bool(re.search(r"https?://", message.content))

# ==========================
# WARNING SYSTEM
# ==========================
async def warn_and_log(message: discord.Message, reason: str):
    try:
        await message.delete()
    except:
        pass

    try:
        warn_msg = await message.channel.send(
            f"⚠️ {message.author.mention} Please avoid that here. ({reason})"
        )
        await warn_msg.delete(delay=5)
    except:
        pass

    await log(
        message.guild,
        f"⚠️ **MiniMe Warning**\n"
        f"User: {message.author} ({message.author.id})\n"
        f"Channel: {message.channel.mention}\n"
        f"Reason: {reason}\n"
        f"Content: {message.content}"
    )

# ==========================
# ANTI-GHOST PING
# ==========================
ghost_cache = {}

@bot.event
async def on_message_delete(message: discord.Message):
    data = ghost_cache.pop(message.id, None)
    if not data:
        return

    author_id, mention_ids, guild_id, channel_id = data
    guild = bot.get_guild(guild_id)
    channel = guild.get_channel(channel_id)

    author = guild.get_member(author_id)
    if author and is_mod(author):
        return

    for uid in mention_ids:
        victim = guild.get_member(uid)
        if victim:
            try:
                alert = await channel.send(f"{victim.mention} 👀 You were ghost-pinged.")
                await alert.delete(delay=5)
            except:
                pass

    await log(
        guild,
        f"👻 **Ghost Ping Detected**\n"
        f"Author: {author} ({author_id})\n"
        f"Channel: {channel.mention}\n"
        f"Victims: {', '.join(str(guild.get_member(i)) for i in mention_ids if guild.get_member(i))}"
    )

# ==========================
# MAIN MESSAGE LISTENER
# ==========================
@bot.event
async def on_message(message: discord.Message):
    if not message.guild or message.author.bot:
        return

    if message.mentions:
        ghost_cache[message.id] = (
            message.author.id,
            [m.id for m in message.mentions],
            message.guild.id,
            message.channel.id,
        )

    if is_mod(message.author):
        return await bot.process_commands(message)

    if contains_swear(message.content):
        return await warn_and_log(message, "Swear detected")

    if has_link(message):
        return await warn_and_log(message, "Link detected")

    if is_repeat(message):
        return await warn_and_log(message, "Repeated message")

    if is_spam(message):
        return await warn_and_log(message, "Spam detected")

    await bot.process_commands(message)

# ==========================
# FUN COMMANDS
# ==========================
@bot.command()
async def hello(ctx):
    await ctx.send(f"🐉 MiniMe is watching over you, {ctx.author.mention}.")

@bot.command()
async def coinflip(ctx):
    import random
    await ctx.send(f"🪙 {random.choice(['Heads', 'Tails'])}!")

@bot.command(name="8ball")
async def eight_ball(ctx, *, question=None):
    import random
    if not question:
        return await ctx.send("Ask me something first.")
    answers = [
        "Yes.", "No.", "Maybe.", "Definitely.", "Absolutely not.",
        "Ask again later.", "Looks good.", "Doesn’t look good."
    ]
    await ctx.send(f"🎱 {random.choice(answers)}")

# ==========================
# UTILITY COMMANDS
# ==========================
@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title=guild.name, description="Server info", color=discord.Color.blurple())
    embed.add_field(name="Members", value=guild.member_count)
    embed.add_field(name="Owner", value=guild.owner)
    embed.add_field(name="Created", value=guild.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)

@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=str(member), description="User info", color=discord.Color.green())
    embed.add_field(name="ID", value=member.id)
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Account created", value=member.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)

# ==========================
# READY EVENT
# ==========================
@bot.event
async def on_ready():
    global log_channel
    for guild in bot.guilds:
        log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)
        if log_channel:
            break
    print(f"MiniMe is online as {bot.user}.")

# ==========================
# RUN BOT
# ==========================
bot.run(TOKEN)
