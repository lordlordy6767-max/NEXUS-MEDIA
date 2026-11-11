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

# ---------- YOUTUBE - FIXED V2 - NEW ONES ADDED HERE ----------
def get_channel_id(handle):
    h = handle if handle.startswith("@") else f"@{handle}"
    # NEW 1: Lemnos with CORRECT param forHandle (old ?handle= was wrong)
    try:
        r = requests.get(f"https://yt.lemnoslife.com/channels?part=id,snippet&forHandle={h}", timeout=15).json()
        print("Lemnos channels:", str(r)[:500])
        if r.get("items"):
            return r["items"][0]["id"]
    except Exception as e:
        print("Lemnos channel fail:", e)

    # NEW 2: Invidious search - finds channel by handle
    try:
        r = requests.get(f"https://inv.nadeko.net/api/v1/search?q={h}&type=channel", timeout=15).json()
        if r and len(r) > 0:
            return r[0].get("authorId")
    except Exception as e:
        print("Invidious fail:", e)

    # Fallback: old scrape
    try:
        url = f"https://www.youtube.com/{h}"
        html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10).text
        m = re.search(r'"channelId":"(UC[\w-]+)"', html)
        if m:
            return m.group(1)
        # NEW 3: second pattern
        m2 = re.search(r'"externalId":"(UC[\w-]+)"', html)
        if m2:
            return m2.group(1)
    except Exception as e:
        print("Scrape fail:", e)
    return None

def parse_duration_iso(s):
    # PT1M5S -> 65 seconds, PT45S -> 45
    try:
        m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', s or "")
        if not m: return 9999
        h, mi, sec = m.groups()
        return int(h or 0)*3600 + int(mi or 0)*60 + int(sec or 0)
    except:
        return 9999

def is_short_video(video_id):
    # Check real duration via Lemnos, not link. Shorts = <= 60s
    try:
        r = requests.get(f"https://yt.lemnoslife.com/videos?part=contentDetails&id={video_id}", timeout=10).json()
        if r.get("items"):
            dur = r["items"][0].get("contentDetails", {}).get("duration", "")
            secs = parse_duration_iso(dur)
            print(f"Video {video_id} duration {dur} = {secs}s -> short={secs<=60}")
            return secs <= 60
    except Exception as e:
        print("Short check fail:", e)
    return False

def get_latest_youtube(creator):
    handle = creator if creator.startswith("@") else f"@{creator}"
    cid = get_channel_id(handle)
    if not cid:
        print(f"NO CHANNEL ID for {handle}")
        return None
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}")
    if not feed.entries:
        print(f"NO ENTRIES for {cid}")
        return None
    e = feed.entries[0]
    vid = e.yt_videoid
    return {
        "id": vid,
        "title": e.title,
        "link": e.link,
        "thumb": e.media_thumbnail[0]["url"] if hasattr(e, "media_thumbnail") else "",
        "author": e.author,
        "is_short": is_short_video(vid),
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
    embed.add_field(name="Other", value="`!media check` - Check now\n`!media debug @handle` - See what bot finds\n`!media test #channel`", inline=False)
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
        msg += f"{i}. {f['platform'].upper()} `{f['creator']}` -> <#{f['channel']}> | Filter: `{f.get('filter','all')}` | Last: `{f.get('last_id')}`\n"
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

# NEW: Debug with Step 1 / Step 2 - so we know exactly where it fails
@media.command(name="debug")
async def media_debug(ctx, creator: str):
    await ctx.send(f"🔍 Debugging `{creator}`...")
    cid = get_channel_id(creator)
    if not cid:
        await ctx.send("❌ Step 1 FAILED: Could not get Channel ID. Check Render LOGS - it will show Lemnos response.")
        return
    await ctx.send(f"✅ Channel ID found: `{cid}`")
    latest = get_latest_youtube(creator)
    if not latest:
        await ctx.send("❌ Step 2 FAILED: Got ID but no videos in RSS feed.")
        return
    await ctx.send(f"✅ Found: **{latest['title']}**\nLink: {latest['link']}\nID: `{latest['id']}`\nIs Short: `{latest['is_short']}`")

# ---------- CHECK - FIXED ----------
async def send_post(feed, data):
    ch = bot.get_channel(feed["channel"])
    if not ch:
        return
    embed = discord.Embed(title=data["title"], url=data["link"], color=0x8B5CF6)
    embed.set_image(url=data["thumb"])
    embed.set_footer(text=f"{data['author']} just uploaded!")
    await ch.send(embed=embed)

async def check_once():
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
            filt = f.get("filter", "all")
            if filt == "shorts" and not latest.get("is_short"):
                f["last_id"] = latest["id"]
                continue
            if filt == "videos" and latest.get("is_short"):
                f["last_id"] = latest["id"]
                continue
            await send_post(f, latest)
            f["last_id"] = latest["id"]
        except Exception as e:
            print(f"Error checking {f.get('creator')}: {e}")
    save(data)

@tasks.loop(minutes=15)
async def check_feeds():
    await check_once()

@media.command(name="check")
async def media_check(ctx):
    await ctx.send("🔍 Checking feeds...")
    await check_once()
    await ctx.send("✅ Check done! If nothing posted, latest was already seen or filtered out. Use `!media debug @handle` to see it.")

keep_alive()
bot.run(DISCORD_TOKEN)
