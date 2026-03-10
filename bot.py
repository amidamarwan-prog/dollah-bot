import discord
from discord.ext import commands
from datetime import timedelta, datetime
import re
import os
import asyncio
import time

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
user_message_history = {}

# ---- SETTINGS ----
invite_pattern = re.compile(r"(discord\.gg\/|discord\.com\/invite\/)")
LOG_CHANNEL_NAME = "mod-log"

SPAM_WINDOW_SECONDS = 8
SPAM_MAX_MESSAGES = 5

# ---- MODERATION SETTINGS ----
TIMEOUT_DURATION = timedelta(minutes=30)

# Mild profanity (soft mode)
BANNED_MILD = {
    "bitch",
    "fuck",
}

# Serious profanity (hard mode)
# Add your serious words here PRIVATELY on your machine
BANNED_STRICT = {
    # "your_serious_word_here",
}

# ---- NSFW FILTER SETTINGS ----
NSFW_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
NSFW_KEYWORDS = {
    "nsfw",
    "18+",
    "explicit",
    "not-safe",
    "adult",
}
NSFW_DOMAINS = {
    "exampleadultsite.com",
    "unsafeimages.net",
}

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


def ts():
    return f"[{datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}]"


def spam_embed(user):
    embed = discord.Embed(
        title="⚠️ Slow Down",
        description=f"{user.mention}, you're sending messages too quickly.",
        color=discord.Color.orange()
    )
    embed.set_footer(text=f"Timestamp: {datetime.utcnow()}")
    return embed


async def apply_timeout(member, reason, channel):
    try:
        await member.timeout_for(TIMEOUT_DURATION, reason=reason)
        await channel.send(
            f"{member.mention}, you’ve been timed out for 30 minutes. Reason: {reason}"
        )
    except Exception:
        await channel.send("I tried to timeout this user but something went wrong.")


async def handle_nsfw_content(message):
    guild = message.guild
    log_channel = get_log_channel(guild)

    # ---- Check attachments ----
    for attachment in message.attachments:
        filename = attachment.filename.lower()

        # Check extension
        if any(filename.endswith(ext) for ext in NSFW_EXTENSIONS):
            # Check filename keywords
            if any(keyword in filename for keyword in NSFW_KEYWORDS):
                try:
                    await message.delete()
                except Exception:
                    pass

                if log_channel:
                    await log_channel.send(
                        f"{ts()} Deleted possible NSFW image from {message.author} (filename flagged)."
                    )
                return

    # ---- Check links in message ----
    content = message.content.lower()

    for domain in NSFW_DOMAINS:
        if domain in content:
            try:
                await message.delete()
            except Exception:
                pass

            if log_channel:
                await log_channel.send(
                    f"{ts()} Deleted message from {message.author} containing unsafe domain."
                )
            return


# ---- MOD DASHBOARD VIEW ----
class ModDashboard(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Warnings", style=discord.ButtonStyle.primary)
    async def warnings_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!warnings @user` to view a user's warnings.",
            ephemeral=True
        )

    @discord.ui.button(label="Clear Warnings", style=discord.ButtonStyle.danger)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!clearwarnings @user` to clear a user's warnings.",
            ephemeral=True
        )

    @discord.ui.button(label="Mod Panel", style=discord.ButtonStyle.secondary)
    async def modpanel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!modpanel` to view all moderation commands.",
            ephemeral=True
        )

    @discord.ui.button(label="Infractions", style=discord.ButtonStyle.success)
    async def infractions_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Use: `!warnings @user` or check mod-log for infractions.",
            ephemeral=True
        )


# ---- BOT READY ----
@bot.event
async def on_ready():
    print(f"Dollah is online as {bot.user}")
    try:
        await bot.tree.sync()
        print("Slash commands synced.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")


# ---- AUTO-ROLE SYSTEM ----
@bot.event
async def on_member_join(member):
    guild = member.guild
    log_channel = get_log_channel(guild)

    auto_role_name = "Member"
    role = discord.utils.get(guild.roles, name=auto_role_name)

    if role is None:
        if log_channel:
            await log_channel.send(
                f"{ts()} Auto-role failed: Role '{auto_role_name}' not found."
            )
        return

    try:
        await member.add_roles(role, reason="Auto-role assignment")
        if log_channel:
            await log_channel.send(
                f"{ts()} Gave {member} the '{auto_role_name}' role automatically."
            )
    except Exception as e:
        if log_channel:
            await log_channel.send(
                f"{ts()} Failed to assign auto-role to {member}. Error: {e}"
            )


# ---- ANTI-GHOST PING ----
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return

    guild = message.guild
    log_channel = get_log_channel(guild)

    if message.mentions:
        mentioned_users = ", ".join([user.mention for user in message.mentions])

        alert_text = (
            f"{mentioned_users}, you were pinged by {message.author.mention} "
            "but the message was deleted."
        )

        try:
            await message.channel.send(alert_text)
        except Exception:
            pass

        if log_channel:
            await log_channel.send(
                f"{ts()} Ghost ping detected: {message.author} pinged {mentioned_users} and deleted the message."
            )


# ---- MESSAGE HANDLER ----
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # NSFW check
    await handle_nsfw_content(message)

    guild = message.guild
    log_channel = get_log_channel(guild)
    user_id = message.author.id
    content = message.content.lower()

    # ---- STRICT BANNED WORDS (hard mode) ----
    for word in BANNED_STRICT:
        if word and word in content:
            try:
                await message.delete()
            except Exception:
                pass

            await apply_timeout(
                message.author,
                reason="Use of extreme banned language",
                channel=message.channel,
            )
            return

    # ---- MILD BANNED WORDS (soft mode) ----
    for word in BANNED_MILD:
        if word and word in content:
            try:
                await message.delete()
            except Exception:
                pass

            await send_temp_msg(
                message.channel,
                f"{message.author.mention}, please avoid using that kind of language.",
                5,
            )
            break

    # ---- LINK PROTECTION ----
    if "http://" in content or "https://" in content:
        trusted_role_name = "Trusted"
        has_trusted = any(r.name == trusted_role_name for r in message.author.roles)

        if not has_trusted:
            try:
                await message.delete()
            except Exception:
                pass

            await apply_timeout(
                message.author,
                reason="Posting links without permission",
                channel=message.channel,
            )
            return

    # ---- SPAM DETECTION (timeout-based) ----
    now = time.time()
    history = user_message_history.get(user_id, [])
    history = [t for t in history if now - t <= SPAM_WINDOW_SECONDS]
    history.append(now)
    user_message_history[user_id] = history

    if len(history) > SPAM_MAX_MESSAGES:
        await apply_timeout(
            message.author,
            reason="Spam / flooding messages",
            channel=message.channel,
        )
        return

    # ---- ORIGINAL ANTI-SPAM (infractions) ----
    msg_count = add_message_timestamp(user_id)
    if msg_count > SPAM_MAX_MESSAGES:
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1
        try:
            await message.channel.send(embed=spam_embed(message.author))
        except Exception:
            pass

        if log_channel:
            await log_channel.send(f"{ts()} {message.author} flagged for spam.")

    # ---- INVITE LINK MOD ----
    if invite_pattern.search(content):
        try:
            await message.delete()
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} no invite links.", 5)
        user_infractions[user_id] = user_infractions.get(user_id, 0) + 1

        if log_channel:
            await log_channel.send(f"{ts()} {message.author} posted an invite link.")

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
            await log_channel.send(f"{ts()} {message.author} repeated messages.")

    # ---- INFRACTION ACTIONS ----
    infractions = user_infractions.get(user_id, 0)

    if infractions == 2:
        try:
            await message.author.timeout(timedelta(minutes=10))
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} timed out.", 5)

        if log_channel:
            await log_channel.send(f"{ts()} {message.author} was timed out.")

    if infractions >= 3:
        try:
            await guild.ban(message.author, reason="Repeated infractions")
        except Exception:
            pass

        await send_temp_msg(message.channel, f"{message.author.mention} banned.", 5)

        if log_channel:
            await log_channel.send(f"{ts()} {message.author} was banned.")

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
        await log_channel.send(f"{ts()} {member} warned by {ctx.author}. Reason: {reason}")


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
        "- /dashboard\n"
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
        "- /dashboard\n"
    )
    await ctx.send(text)


# ---- SLASH BAN ----
@bot.tree.command(name="ban", description="Ban a user (mod only).")
@discord.app_commands.checks.has_permissions(ban_members=True)
async def ban_slash(interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
    guild = interaction.guild
    log_channel = get_log_channel(guild)

    try:
        await guild.ban(member, reason=reason)
        await interaction.response.send_message(
            f"{member.mention} banned. Reason: {reason}", ephemeral=True
        )
        if log_channel:
            await log_channel.send(f"{ts()} {member} banned via /ban by {interaction.user}.")
    except Exception:
        await interaction.response.send_message(
            "I couldn't ban that user. Check my permissions.", ephemeral=True
        )


# ---- MOD DASHBOARD COMMAND ----
@bot.tree.command(name="dashboard", description="Open the moderation dashboard.")
@discord.app_commands.checks.has_permissions(manage_guild=True)
async def dashboard(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛠️ Moderation Dashboard",
        description=(
            "Welcome to the Dollah Moderation Dashboard.\n"
            "Use the buttons below to quickly access moderation tools."
        ),
        color=discord.Color.blue()
    )

    embed.add_field(
        name="Available Tools",
        value=(
            "- View warnings\n"
            "- Clear warnings\n"
            "- Open mod panel\n"
            "- Check infractions\n"
        ),
        inline=False
    )

    embed.set_footer(text=f"Timestamp: {datetime.utcnow()}")

    await interaction.response.send_message(embed=embed, view=ModDashboard(), ephemeral=True)


# ---- RUN BOT ----
bot.run(os.environ["DISCORD_BOT_TOKEN"])
