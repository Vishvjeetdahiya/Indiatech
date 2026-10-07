# Discord Reddit Verification Bot

A Discord bot that lets server members verify their identity by linking a Reddit account. On success it assigns a configurable role and optionally syncs the server nickname.

---

## Features

- `/verify username:<reddit_username>` slash command
- Validates account existence, suspension status, and karma via Reddit's public API
- Assigns a configurable Discord role on success
- Optional server nickname sync to the verified Reddit handle
- Fully ephemeral responses — only the verifying user ever sees the bot's replies
- Graceful error messages for every failure path (404, suspension, rate limits, missing permissions)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.10+ | Uses `X \| Y` union type hints |
| Discord Bot Token | Create one at the [Discord Developer Portal](https://discord.com/developers/applications) |
| A Discord Server | Where you have admin rights |

---

## Discord Developer Portal Setup

### 1. Create the Application & Bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**.
2. Navigate to **Bot** → **Add Bot**.
3. Under **Token**, click **Reset Token** and copy it — this is your `DISCORD_TOKEN`.

### 2. Enable Required Privileged Intents

Under **Bot → Privileged Gateway Intents**, enable:

- ✅ **Server Members Intent** — required to fetch member objects for role and nickname assignment.

### 3. Invite the Bot to Your Server

Use the **OAuth2 → URL Generator** with the following scopes and permissions:

**Scopes:**
- `bot`
- `applications.commands`

**Bot Permissions:**
- `Manage Roles`
- `Manage Nicknames` *(only if `UPDATE_NICKNAME=true`)*
- `Send Messages`
- `Use Slash Commands`

Copy the generated URL and open it in your browser to invite the bot.

---

## Role Hierarchy (Important)

The bot's own role **must be positioned above** the `Verified Redditor` role (or whatever name you configure) in **Server Settings → Roles**. Discord enforces that bots can only manage roles ranked below their own.

```
[Bot Role]          ← must be here or higher
[Verified Redditor] ← target role
[@everyone]
```

---

## Installation

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd discord-indiatech-bot

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Open .env and fill in your DISCORD_TOKEN
```

---

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_TOKEN` | ✅ Yes | — | Your Discord bot token |
| `VERIFIED_ROLE_NAME` | No | `Verified Redditor` | Exact name of the Discord role to assign |
| `UPDATE_NICKNAME` | No | `false` | Set `true` to sync server nickname with Reddit username |

---

## Running the Bot

```bash
# With virtual environment active
python bot.py
```

You should see:
```
[Setup] Slash commands synced globally.
[Bot] Logged in as YourBot#1234 (ID: ...)
[Bot] Verified role name: 'Verified Redditor'
[Bot] Nickname sync: disabled
```

> **Note:** Global slash command sync can take up to **1 hour** to propagate across all Discord servers. For instant testing during development, use guild-scoped sync instead.

---

## Usage

In any channel where the bot has access, type:

```
/verify username:spez
```

The bot will:
1. Validate the Reddit account exists and is not suspended.
2. Assign the configured role to you.
3. *(Optional)* Update your server nickname.
4. Reply ephemerally with a summary embed showing your karma and account age.

---

## Error Reference

| Error | Cause | Fix |
|---|---|---|
| `Account Not Found` | Misspelled username or deleted account | Double-check the Reddit username |
| `Account Suspended` | Reddit has suspended the account | Cannot verify a suspended account |
| `Role Not Found` | Role name mismatch | Create a role matching `VERIFIED_ROLE_NAME` exactly |
| `Permission Denied` | Bot role is too low in the hierarchy | Move the bot's role above the verified role |
| `Rate Limited` | Too many requests to Reddit | Wait ~60 seconds and retry |

---

## Project Structure

```
discord-indiatech-bot/
├── bot.py            # Bot client, event handlers, /verify command
├── requirements.txt  # Python dependencies
├── .env.example      # Environment variable template
└── README.md         # This file
```
