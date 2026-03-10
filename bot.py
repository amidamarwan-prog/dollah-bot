import discord
from discord.ext import commands
from datetime import timedelta
import re
import os
import asyncio

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

user_infractions = {}
user_last_message = {}

invite_pattern = re.compile(r"(discord\.gg\/|discord\.com\/invite\/)")
LOG_CHANNEL_NAME = "mod-log"

@bot.event
async def on_ready():
    print(f"Dollah is online as {bot.user}")

def get_log_channel(guild):
    return discord.utils.get(guild.text_channels, name=LOG_CHANNEL_NAME)

async def send_temp_msg(channel, content, delay=5):
    msg = await channel.send(content)
    await asyncio.sleep(delay)
    await msg.delete()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    user_id = message.author.id
    content = message.content.lower()
    log_channel = get_log_channel(message.guild)

    # Invite link moderation
    if invite_pattern.search(content):
        await message.delete()
        await send_temp_msg(message.channel, f"{message.author.mention} no invite links.", delay=5)
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1
        if log_channel:
            await log_channel.send(f"{message.author} posted an invite link. Infractions: {user_infractions[user_id]}")

    # Repeated message moderation
    last_msg, repeat_count = user_last_message.get(user_id, ("", 0))
    if content == last_msg:
        repeat_count += 1
    else:
        repeat_count = 1
    user_last_message[user_id] = (content, repeat_count)

    if repeat_count == 3:
        await send_temp_msg(message.channel, f"{message.author.mention} stop repeating.", delay=5)
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1
        if log_channel:
            await log_channel.send(f"{message.author} repeated messages. Infractions: {user_infractions[user_id]}")

    # Actions based on infractions
    infractions = user_infractions.get(user_id, 0)

    if infractions == 2:
        await message.author.timeout(timedelta(minutes=10))
        await send_temp_msg(message.channel, f"{message.author.mention} timed out.", delay=5)
        if log_channel:
            await log_channel.send(f"{message.author} was timed out.")

    if infractions >= 3:
        await message.guild.ban(message.author, reason="Repeated infractions")
        await send_temp_msg(message.channel, f"{message.author.mention} banned.", delay=5)
        if log_channel:
            await log_channel.send(f"{message.author} was banned.")

    await bot.process_commands(message)

@bot.command()
async def hello(ctx):
    await ctx.send("Yo, Dollah is here!")

bot.run(os.environ["DISCORD_BOT_TOKEN"])