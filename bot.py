import os
import re
import json
import datetime
import pathlib

import aiohttp
import discord
from discord import app_commands
from discord.ui import Button, Modal, TextInput, View
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN: str = os.getenv("DISCORD_TOKEN", "")
VERIFIED_ROLE_NAME: str = os.getenv("VERIFIED_ROLE_NAME", "Verified Redditor")
VERIFICATION_CHANNEL_ID: int = int(os.getenv("VERIFICATION_CHANNEL_ID") or "0")
GUILD_ID: int = int(os.getenv("GUILD_ID") or "0")

MIN_KARMA: int = 30
MIN_ACCOUNT_AGE_DAYS: int = 7

REDDIT_API_BASE = "https://ghostddit.aeddit.com/api/reddit/user-archive/about?author={}"
REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

PANEL_TITLE = "🔥 Welcome to IndiaTech!"
VERIFIED_DB_PATH = pathlib.Path("verified_users.json")


def _load_verified_db() -> dict[str, str]:
    if VERIFIED_DB_PATH.exists():
        try:
            return json.loads(VERIFIED_DB_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_verified_db(db: dict[str, str]) -> None:
    VERIFIED_DB_PATH.write_text(
        json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8"
    )


verified_db: dict[str, str] = _load_verified_db()


def _sanitize_username(raw: str) -> str:
    clean = raw.strip()
    clean = re.sub(r"^/?[ur]/", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def _format_account_age(created_utc: float) -> str:
    created = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc)
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    delta = now - created
    years, remainder = divmod(delta.days, 365)
    months = remainder // 30
    if years > 0:
        return f"{years}y {months}mo"
    if months > 0:
        return f"{months} month(s)"
    return f"{delta.days} day(s)"


def _account_age_days(created_utc: float) -> int:
    created = datetime.datetime.fromtimestamp(created_utc, tz=datetime.timezone.utc)
    return (datetime.datetime.now(tz=datetime.timezone.utc) - created).days


def _verification_panel_embed() -> discord.Embed:
    embed = discord.Embed(
        title=PANEL_TITLE,
        description=(
            "To keep our community safe and ensure everyone is a real member of our subreddit, "
            "we require a quick Reddit verification to unlock the server.\n\n"
            "**How to get verified:**\n"
            "1️⃣ Click the **Verify with Reddit** button below.\n"
            "2️⃣ Enter your exact Reddit username in the popup window.\n"
            "3️⃣ Our bot will instantly verify your account and grant you access.\n\n"
            "⚠️ **Requirements:**\n"
            f"• Minimum **{MIN_KARMA} karma** on your Reddit account.\n"
            f"• Account must be at least **{MIN_ACCOUNT_AGE_DAYS} days old**.\n\n"
            "⚙️ **Important Details:**\n"
            "• This process is completely secure, one-time, and permanent.\n"
            "• Your Discord nickname will be automatically locked to match your Reddit username."
        ),
        color=discord.Color.from_rgb(255, 69, 0),
    )
    embed.set_thumbnail(url="https://www.redditinc.com/assets/images/site/reddit-logo.png")
    embed.set_footer(text="IndiaTech Authentication System 🛡️")
    return embed


def _success_embed(
    reddit_username: str,
    total_karma: int,
    account_age: str,
    member: discord.Member,
    role: discord.Role,
) -> discord.Embed:
    embed = discord.Embed(
        title="🎉 Verification Successful!",
        description=f"Welcome to **IndiaTech**, {member.mention}! You now have full access to the server.",
        color=discord.Color.from_rgb(46, 204, 113),
    )
    embed.add_field(name="👤 Reddit Account", value=f"**u/{reddit_username}**", inline=True)
    embed.add_field(name="📈 Total Karma", value=f"**{total_karma:,}**", inline=True)
    embed.add_field(name="🎂 Account Age", value=f"**{account_age}**", inline=True)
    embed.add_field(name="🛡️ Role Granted", value=role.mention, inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Your nickname has been permanently synced to your Reddit username.")
    return embed


def _error_embed(title: str, description: str) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=discord.Color.red())


def _already_verified_embed(reddit_username: str) -> discord.Embed:
    return discord.Embed(
        title="🔒 Already Verified",
        description=(
            f"Your account is permanently linked to **u/{reddit_username}**.\n\n"
            "Verification cannot be changed. Contact an admin if there is an issue."
        ),
        color=discord.Color.orange(),
    )


async def _run_verification(
    interaction: discord.Interaction,
    raw_username: str,
    bot: "VerifierClient",
) -> None:
    user_id = str(interaction.user.id)

    if user_id in verified_db:
        await interaction.followup.send(
            embed=_already_verified_embed(verified_db[user_id]), ephemeral=True
        )
        return

    clean_username = _sanitize_username(raw_username)
    if not clean_username:
        await interaction.followup.send(
            embed=_error_embed("❌ Invalid Username", "Please enter a valid Reddit username."),
            ephemeral=True,
        )
        return

    try:
        async with bot.http_session.get(
            REDDIT_API_BASE.format(clean_username), headers=REDDIT_HEADERS
        ) as resp:
            if resp.status == 404:
                await interaction.followup.send(
                    embed=_error_embed(
                        "❌ Account Not Found",
                        f"No Reddit account exists for **u/{clean_username}**. Check the spelling and try again.",
                    ),
                    ephemeral=True,
                )
                return
            if resp.status != 200:
                await interaction.followup.send(
                    embed=_error_embed(
                        "⚠️ API Error",
                        f"The API proxy returned an unexpected status `{resp.status}`. Try again later.",
                    ),
                    ephemeral=True,
                )
                return
            payload = await resp.json()
    except aiohttp.ClientConnectorError:
        await interaction.followup.send(
            embed=_error_embed("🔌 Connection Error", "Could not reach Reddit's API. Try again."),
            ephemeral=True,
        )
        return
    except Exception as exc:
        print(f"[Error] Unexpected error fetching Reddit profile: {exc}")
        await interaction.followup.send(
            embed=_error_embed("💥 Unexpected Error", "Something went wrong. Please try again."),
            ephemeral=True,
        )
        return

    data = payload.get("data", {})

    if data.get("is_suspended", False):
        await interaction.followup.send(
            embed=_error_embed(
                "🚫 Account Suspended",
                f"**u/{clean_username}** has been suspended by Reddit and cannot be used for verification.",
            ),
            ephemeral=True,
        )
        return

    if not data.get("name"):
        await interaction.followup.send(
            embed=_error_embed(
                "❌ Invalid Profile",
                "Reddit returned an incomplete profile. The account may be in a broken state.",
            ),
            ephemeral=True,
        )
        return

    verified_name: str = str(data["name"])
    total_karma: int = int(data.get("total_karma", 0))
    created_utc: float = float(data.get("created_utc", 0.0))
    account_age = _format_account_age(created_utc) if created_utc else "Unknown"
    age_days = _account_age_days(created_utc) if created_utc else 0

    if total_karma < MIN_KARMA:
        await interaction.followup.send(
            embed=_error_embed(
                "📉 Insufficient Karma",
                f"**u/{verified_name}** only has **{total_karma:,} karma**.\n\n"
                f"You need at least **{MIN_KARMA} karma** to verify.\n"
                "Keep contributing to Reddit and try again!",
            ),
            ephemeral=True,
        )
        return

    if age_days < MIN_ACCOUNT_AGE_DAYS:
        await interaction.followup.send(
            embed=_error_embed(
                "🗓️ Account Too New",
                f"**u/{verified_name}** is only **{age_days} day(s) old**.\n\n"
                f"Your account must be at least **{MIN_ACCOUNT_AGE_DAYS} days old** to verify.\n"
                "Please try again once your account is older.",
            ),
            ephemeral=True,
        )
        return

    guild = interaction.guild
    if guild is None:
        await interaction.followup.send(
            embed=_error_embed("⚠️ Guild Error", "This must be used inside a server."),
            ephemeral=True,
        )
        return

    role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    if role is None:
        await interaction.followup.send(
            embed=_error_embed(
                "⚙️ Role Not Found",
                f'The role **"{VERIFIED_ROLE_NAME}"** does not exist. Ask an admin to create it.',
            ),
            ephemeral=True,
        )
        return

    member: discord.Member = interaction.user  # type: ignore[assignment]

    try:
        await member.add_roles(role, reason=f"Reddit verification: u/{verified_name}")
    except discord.Forbidden:
        await interaction.followup.send(
            embed=_error_embed(
                "🔒 Permission Denied",
                f"The bot cannot assign **{role.name}**.\n\n"
                f"**Fix:** Go to **Server Settings → Roles** and drag the bot's role **above** {role.name}.",
            ),
            ephemeral=True,
        )
        return
    except discord.HTTPException as exc:
        print(f"[Error] Role assignment failed for {member}: {exc}")
        await interaction.followup.send(
            embed=_error_embed("⚠️ Role Error", "Failed to assign your role. Please try again."),
            ephemeral=True,
        )
        return

    try:
        await member.edit(
            nick=verified_name,
            reason=f"Reddit verification nickname sync: u/{verified_name}",
        )
    except discord.Forbidden:
        pass
    except discord.HTTPException as exc:
        print(f"[Warning] Could not set nickname for {member}: {exc}")

    verified_db[user_id] = verified_name
    _save_verified_db(verified_db)
    print(f"[Verify] {member} (ID: {user_id}) linked to u/{verified_name} | karma={total_karma} age={age_days}d")

    await interaction.followup.send(
        embed=_success_embed(
            reddit_username=verified_name,
            total_karma=total_karma,
            account_age=account_age,
            member=member,
            role=role,
        ),
        ephemeral=True,
    )


class VerifyModal(Modal, title="Reddit Verification"):
    reddit_username: TextInput = TextInput(
        label="Your Reddit Username",
        placeholder="e.g.  spez   (don't include u/)",
        min_length=3,
        max_length=20,
        required=True,
    )

    def __init__(self, bot: "VerifierClient") -> None:
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True, ephemeral=True)
        await _run_verification(interaction, self.reddit_username.value, self.bot)


class VerifyView(View):
    def __init__(self, bot: "VerifierClient") -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Verify with Reddit",
        style=discord.ButtonStyle.danger,
        emoji="🔐",
        custom_id="reddit_verify_persistent",
    )
    async def verify_button(self, interaction: discord.Interaction, button: Button) -> None:
        user_id = str(interaction.user.id)
        if user_id in verified_db:
            await interaction.response.send_message(
                embed=_already_verified_embed(verified_db[user_id]),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(VerifyModal(self.bot))


class VerifierClient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._http_session: aiohttp.ClientSession | None = None

    async def setup_hook(self) -> None:
        self._http_session = aiohttp.ClientSession()
        self.add_view(VerifyView(self))
        if GUILD_ID:
            guild_obj = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
            print(f"[Setup] Commands synced to guild {GUILD_ID} (instant).")
        else:
            await self.tree.sync()
            print("[Setup] Commands synced globally (may take up to 1 hour).")

        self.loop.create_task(self._ensure_verification_panel())

    async def _ensure_verification_panel(self) -> None:
        await self.wait_until_ready()
        for guild in self.guilds:
            channel = None
            if VERIFICATION_CHANNEL_ID:
                channel = guild.get_channel(VERIFICATION_CHANNEL_ID)
            if not channel:
                channel = discord.utils.get(guild.text_channels, name="verify-yourself")
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                panel_found = False
                async for msg in channel.history(limit=50):
                    if msg.author == self.user and msg.embeds and msg.embeds[0].title == PANEL_TITLE:
                        panel_found = True
                        break
                if not panel_found:
                    await channel.send(embed=_verification_panel_embed(), view=VerifyView(self))
                    print(f"[Panel] Re-posted missing verification panel in #{channel.name} ({guild.name})")
            except discord.HTTPException:
                pass

    async def close(self) -> None:
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        await super().close()

    @property
    def http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession()
        return self._http_session


client = VerifierClient()


@client.event
async def on_member_join(member: discord.Member) -> None:
    pass


@client.event
async def on_message_delete(message: discord.Message) -> None:
    if message.author != client.user or not message.embeds:
        return
    if message.embeds[0].title != PANEL_TITLE:
        return
    if not isinstance(message.channel, discord.TextChannel):
        return
    if message.guild is None:
        return
    try:
        await message.channel.send(embed=_verification_panel_embed(), view=VerifyView(client))
        print(f"[Panel] Reposted deleted panel in #{message.channel.name} ({message.guild.name})")
    except discord.HTTPException:
        pass


@client.event
async def on_member_update(before: discord.Member, after: discord.Member) -> None:
    user_id = str(after.id)
    if user_id not in verified_db:
        return

    locked_nick = verified_db[user_id]
    guild = after.guild

    role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    if role and role in before.roles and role not in after.roles:
        try:
            await after.add_roles(role, reason="Verification lock: role removal blocked")
            print(f"[Lock] Re-applied verified role to {after} (ID: {user_id}).")
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"[Lock] Could not re-apply role to {after}: {exc}")

    if after.nick != locked_nick:
        try:
            await after.edit(nick=locked_nick, reason="Nickname lock: reverted to verified Reddit username")
            print(f"[Lock] Reverted nickname for {after} (ID: {user_id}) → '{locked_nick}'.")
        except discord.Forbidden:
            pass
        except discord.HTTPException as exc:
            print(f"[Lock] Could not revert nickname for {after}: {exc}")


@client.event
async def on_ready() -> None:
    print(f"[Bot] Logged in as {client.user} (ID: {client.user.id})")  # type: ignore[union-attr]
    print(f"[Bot] Verified role: '{VERIFIED_ROLE_NAME}'")
    print(f"[Bot] Verification channel ID: {VERIFICATION_CHANNEL_ID or 'not set'}")
    print(f"[Bot] Karma gate: {MIN_KARMA}+ | Age gate: {MIN_ACCOUNT_AGE_DAYS}+ days")
    print(f"[Bot] Loaded {len(verified_db)} existing verification(s) from disk.")
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="new members verify",
        )
    )


@client.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        if not interaction.response.is_done():
            await interaction.response.send_message(
                embed=_error_embed("🔒 Missing Permissions", "You need **Administrator** permission to use this command."),
                ephemeral=True,
            )


# ─── MOD/ADMIN COMMANDS ────────────────────────────────────────────────────────

@client.tree.command(
    name="setup-verification",
    description="[Admin] Post the persistent verification panel in this channel.",
)
@app_commands.checks.has_permissions(administrator=True)
async def setup_verification(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(embed=_verification_panel_embed(), view=VerifyView(client))  # type: ignore[union-attr]
    await interaction.followup.send("✅ Verification panel posted.", ephemeral=True)


@client.tree.command(
    name="test-verify",
    description="[Admin] Open the verification popup on yourself.",
)
@app_commands.checks.has_permissions(administrator=True)
async def test_verify(interaction: discord.Interaction) -> None:
    await interaction.response.send_modal(VerifyModal(client))


@client.tree.command(
    name="reset-user",
    description="[Admin] Clear a user's verification so they can re-verify.",
)
@app_commands.describe(member="The member to reset")
@app_commands.checks.has_permissions(administrator=True)
async def reset_user(interaction: discord.Interaction, member: discord.Member) -> None:
    await interaction.response.defer(ephemeral=True)

    user_id = str(member.id)
    old_username = verified_db.pop(user_id, None)

    if old_username is None:
        await interaction.followup.send(
            embed=_error_embed("⚠️ Not Verified", f"{member.mention} has no verification record."),
            ephemeral=True,
        )
        return

    _save_verified_db(verified_db)
    print(f"[Reset] Cleared verification for {member} (ID: {user_id}), was u/{old_username}.")

    if interaction.guild:
        role = discord.utils.get(interaction.guild.roles, name=VERIFIED_ROLE_NAME)
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Verification reset by {interaction.user}")
            except (discord.Forbidden, discord.HTTPException) as exc:
                print(f"[Reset] Could not remove role from {member}: {exc}")

    try:
        await member.edit(nick=None, reason="Verification reset: nickname cleared")
    except (discord.Forbidden, discord.HTTPException):
        pass

    await interaction.followup.send(
        embed=discord.Embed(
            title="🔄 Verification Reset",
            description=(
                f"Cleared **u/{old_username}** from {member.mention}.\n"
                "They can now verify again from scratch."
            ),
            color=discord.Color.blurple(),
        ),
        ephemeral=True,
    )


@client.tree.command(
    name="whois",
    description="[Mod] Look up a member's linked Reddit account.",
)
@app_commands.describe(member="The member to look up")
@app_commands.checks.has_permissions(manage_messages=True)
async def whois(interaction: discord.Interaction, member: discord.Member) -> None:
    await interaction.response.defer(ephemeral=True)
    user_id = str(member.id)
    reddit_username = verified_db.get(user_id)

    embed = discord.Embed(
        title="🔍 Member Lookup",
        color=discord.Color.blurple(),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Discord", value=f"{member.mention} (`{member.id}`)", inline=False)
    embed.add_field(
        name="Reddit Account",
        value=f"[u/{reddit_username}](https://reddit.com/u/{reddit_username})" if reddit_username else "❌ Not verified",
        inline=False,
    )
    embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at or datetime.datetime.now(tz=datetime.timezone.utc), "R"), inline=True)
    embed.add_field(name="Account Created", value=discord.utils.format_dt(member.created_at, "R"), inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.command(
    name="verified-list",
    description="[Mod] Show the total number of verified members.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def verified_list(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    total = len(verified_db)
    embed = discord.Embed(
        title="📋 Verified Members",
        description=f"There are currently **{total}** verified member(s) in the database.",
        color=discord.Color.blurple(),
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.command(
    name="serverinfo",
    description="[Mod] Display a summary of the server's verification stats.",
)
@app_commands.checks.has_permissions(manage_messages=True)
async def serverinfo(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    if guild is None:
        await interaction.followup.send(embed=_error_embed("Error", "Must be used in a server."), ephemeral=True)
        return

    role = discord.utils.get(guild.roles, name=VERIFIED_ROLE_NAME)
    verified_count = len(role.members) if role else 0
    total_members = guild.member_count or 0
    unverified = total_members - verified_count

    embed = discord.Embed(
        title=f"📊 {guild.name} — Server Stats",
        color=discord.Color.from_rgb(255, 69, 0),
    )
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Total Members", value=str(total_members), inline=True)
    embed.add_field(name="✅ Verified", value=str(verified_count), inline=True)
    embed.add_field(name="⏳ Unverified", value=str(unverified), inline=True)
    embed.add_field(name="Karma Gate", value=f"{MIN_KARMA}+", inline=True)
    embed.add_field(name="Age Gate", value=f"{MIN_ACCOUNT_AGE_DAYS}+ days", inline=True)
    embed.add_field(name="Verified Role", value=role.mention if role else "❌ Not found", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


@client.tree.command(
    name="check-reddit",
    description="[Mod] Manually look up a Reddit account's karma and age.",
)
@app_commands.describe(username="The Reddit username to check (without u/)")
@app_commands.checks.has_permissions(manage_messages=True)
async def check_reddit(interaction: discord.Interaction, username: str) -> None:
    await interaction.response.defer(ephemeral=True)
    clean = _sanitize_username(username)
    try:
        async with client.http_session.get(REDDIT_API_BASE.format(clean), headers=REDDIT_HEADERS) as resp:
            if resp.status == 404:
                await interaction.followup.send(embed=_error_embed("❌ Not Found", f"u/{clean} does not exist."), ephemeral=True)
                return
            if resp.status != 200:
                await interaction.followup.send(embed=_error_embed("⚠️ API Error", f"Status `{resp.status}`."), ephemeral=True)
                return
            payload = await resp.json()
    except Exception as exc:
        await interaction.followup.send(embed=_error_embed("🔌 Error", str(exc)), ephemeral=True)
        return

    data = payload.get("data", {})
    if not data.get("name"):
        await interaction.followup.send(embed=_error_embed("❌ No Data", "Reddit returned an empty profile."), ephemeral=True)
        return

    name = str(data["name"])
    karma = int(data.get("total_karma", 0))
    created = float(data.get("created_utc", 0.0))
    age_str = _format_account_age(created) if created else "Unknown"
    age_days = _account_age_days(created) if created else 0

    karma_pass = karma >= MIN_KARMA
    age_pass = age_days >= MIN_ACCOUNT_AGE_DAYS

    embed = discord.Embed(
        title=f"🔎 Reddit Account: u/{name}",
        url=f"https://reddit.com/u/{name}",
        color=discord.Color.green() if (karma_pass and age_pass) else discord.Color.red(),
    )
    embed.add_field(name="📈 Karma", value=f"{karma:,} {'✅' if karma_pass else '❌'}", inline=True)
    embed.add_field(name="🎂 Account Age", value=f"{age_str} {'✅' if age_pass else '❌'}", inline=True)
    embed.add_field(
        name="Verdict",
        value="✅ **Eligible to verify**" if (karma_pass and age_pass) else "❌ **Does not meet requirements**",
        inline=False,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill in your token.")
    client.run(DISCORD_TOKEN)
