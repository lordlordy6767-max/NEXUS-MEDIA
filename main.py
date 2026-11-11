import discord, json, os, asyncio, requests, feedparser, re
from discord.ext import commands, tasks
from datetime import datetime
from flask import Flask
from threading import Thread

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = 1545810202232885258
DATA_FILE = "media_data.json"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- FLASK KEEP ALIVE ----------
app = Flask('')

@app.route('/')
def home():
    return "NEXUS MEDIA is online 👑"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

# ---------- DATA ----------
def load():
    if not os.path.exists(DATA_FILE):
        return {"feeds": [], "premium": []}
    with open(DATA_FILE) as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ---------- YOUTUBE ----------
def get_channel_id(handle):
    url = f"https://www.youtube.com/{handle}"
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}).text
    m = re.search(r'"channelId":"(UC[\w-]+)"', html)
    if m:
        return m.group(1)
    return None

def get_latest_youtube(creator):
    handle = creator if creator.startswith("@") else f"@{creator}"
    cid = get_channel_id(handle)
    if not cid:
        return None
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    if not feed.entries:
        return None
    e = feed.entries[0]
    return {
        "id": e.yt_videoid,
        "title": e.title,
        "link": e.link,
        "thumb": e.media_thumbnail[0]["url"] if hasattr(e, "media_thumbnail") else "",
        "author": e.author,
    }

# ---------- BOT EVENTS ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_feeds.start()

# ---------- MEDIA GROUP ----------
@bot.group(name="media", invoke_without_command=True)
async def media(ctx):
    await ctx.send("Use `!media help` for all commands")

@media.command(name="help")
async def media_help(ctx):
    embed = discord.Embed(title="👑 NEXUS MEDIA", description="All Socials, One Bot", color=0x8B5CF6)
    embed.add_field(name="Setup", value="`!media add youtube @handle #channel`\n`!media list`\n`!media remove <number>`", inline=False)
    embed.add_field(name="Filter", value="`!media filter youtube shorts` - Only Shorts\n`!media filter youtube videos` - Only Long Videos\n`!media filter youtube all` - Both", inline=False)
    embed.add_field(name="Premium", value="`!media premium`\n`!media unlock @user` (Owner Only)\n`!media lock @user` (Owner Only)", inline=False)
    embed.add_field(name="Other", value="`!media check` - Check now\n`!media test #channel`\n`!media instant`\n`!media clips`\n`!media schedule 18:00`", inline=False)
    await ctx.send(embed=embed)

@media.command(name="add")
async def media_add(ctx, platform: str, creator: str, channel: discord.TextChannel):
    data = load()
    is_premium = ctx.author.id in data.get("premium", []) or ctx.author.id == OWNER_ID
    user_feeds = [f for f in data["feeds"] if f["user"] == ctx.author.id]
    if not is_premium and len(user_feeds) >= 1:
        await ctx.send("❌ FREE limit: 1 feed only! Get PREMIUM for unlimited.")
        return
    data["feeds"].append({
        "user": ctx.author.id,
        "platform": platform.lower(),
        "creator": creator,
        "channel": channel.id,
        "last_id": None,
        "filter": "all"
    })
    save(data)
    await ctx.send(f"✅ Added **{platform} {creator}** -> {channel.mention}")

@media.command(name="list")
async def media_list(ctx):
    data = load()
    if not data["feeds"]:
        await ctx.send("No feeds yet.")
        return
    msg = "**Your Feeds:**\n"
    for i, f in enumerate(data["feeds"], 1):
        msg += f"{i}. {f['platform'].upper()} `{f['creator']}` -> <#{f['channel']}> | Filter: `{f.get('filter','all')}`\n"
    await ctx.send(msg)

@media.command(name="remove")
async def media_remove(ctx, num: int):
    data = load()
    if 1 <= num <= len(data["feeds"]):
        removed = data["feeds"].pop(num-1)
        save(data)
        await ctx.send(f"✅ Removed {removed['creator']}")
    else:
        await ctx.send("❌ Invalid number")

@media.command(name="filter")
async def media_filter(ctx, platform: str, mode: str):
    mode = mode.lower()
    if mode not in ["shorts", "videos", "all"]:
        await ctx.send("❌ Use `shorts`, `videos`, or `all`")
        return
    data = load()
    updated = 0
    for f in data["feeds"]:
        if f["user"] == ctx.author.id and f["platform"] == platform.lower():
            f["filter"] = mode
            updated += 1
    save(data)
    await ctx.send(f"✅ Filter set to **{mode}** for {updated} {platform} feed(s)")

@media.command(name="unlock")
async def media_unlock(ctx, user: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Owner only!")
        return
    data = load()
    if user.id not in data["premium"]:
        data["premium"].append(user.id)
        save(data)
    await ctx.send(f"👑 {user.mention} is now PREMIUM!")

@media.command(name="lock")
async def media_lock(ctx, user: discord.Member):
    if ctx.author.id != OWNER_ID:
        await ctx.send("❌ Owner only!")
        return
    data = load()
    if user.id in data["premium"]:
        data["premium"].remove(user.id)
        save(data)
    await ctx.send(f"🔒 {user.mention} PREMIUM removed.")

@media.command(name="premium")
async def media_premium(ctx):
    data = load()
    if not data["premium"]:
        await ctx.send("No premium users yet.")
        return
    msg = "**👑 PREMIUM Users:**\n"
    for uid in data["premium"]:
        msg += f"<@{uid}>\n"
    await ctx.send(msg)

@media.command(name="test")
async def media_test(ctx, channel: discord.TextChannel = None):
    ch = channel or ctx.channel
    await ch.send("✅ MEDIA test - Bot can post here!")

# ---------- CHECK - FILTER FIX INSIDE ----------
async def send_post(feed, data):
    ch = bot.get_channel(feed["channel"])
    if not ch:
        return
    embed = discord.Embed(title=data["title"], url=data["link"], color=0x8B5CF6)
    embed.set_image(url=data["thumb"])
    embed.set_footer(text=f"{data['author']} just uploaded!")
    await ch.send(embed=embed)

@tasks.loop(minutes=15)
async def check_feeds():
    data = load()
    for f in data["feeds"]:
        try:
            if f["platform"] != "youtube":
                continue
            latest = get_latest_youtube(f["creator"])
            if not latest:
                continue
            if latest["id"] == f.get("last_id"):
                continue

            # ===== FILTER CHECK - NEW FIX =====
            is_short = "/shorts/" in latest["link"]
            filt = f.get("filter", "all")
            if filt == "shorts" and not is_short:
                f["last_id"] = latest["id"]
                continue
            if filt == "videos" and is_short:
                f["last_id"] = latest["id"]
                continue
            # ===== END FILTER CHECK =====

            await send_post(f, latest)
            f["last_id"] = latest["id"]
        except Exception as e:
            print(f"Error checking {f.get('creator')}: {e}")
    save(data)

@media.command(name="check")
async def media_check(ctx):
    await ctx.send("🔍 Checking feeds...")
    await check_feeds()
    await ctx.send("✅ Check done!")

keep_alive()
bot.run(DISCORD_TOKEN)

