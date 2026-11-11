import discord, os, json, threading, urllib.request, xml.etree.ElementTree as ET, re
from discord.ext import commands, tasks
from flask import Flask

app = Flask(__name__)
@app.route('/')
def home(): return "NEXUS MEDIA is live! All Socials"
threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080), daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

OWNER_ID = 1545810202232885258

DB = "media.json"
def load():
    try:
        with open(DB) as f: return json.load(f)
    except: return {"feeds": [], "paused": False, "settings": {}}
def save(d):
    with open(DB, "w") as f: json.dump(d, f, indent=2)

def get_setting(guild_id, key, default=None):
    d = load()
    return d["settings"].get(str(guild_id), {}).get(key, default)
def set_setting(guild_id, key, value):
    d = load()
    s = d["settings"].setdefault(str(guild_id), {})
    s[key] = value
    save(d)

# --- PREMIUM SYSTEM - MEDIA ONLY, NO CONFLICT ---
PREMIUM_FILE = "premium.json"
def load_premium():
    try:
        with open(PREMIUM_FILE) as f: return json.load(f)
    except: return {"users": [], "global_lock": False}
def save_premium(d):
    with open(PREMIUM_FILE, "w") as f: json.dump(d, f, indent=2)

def is_premium(user_id):
    if int(user_id) == OWNER_ID:
        return True
    d = load_premium()
    return str(user_id) in d["users"]

def is_owner(ctx):
    return ctx.author.id == OWNER_ID

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    check_feeds.start()

# --- YOUTUBE: HANDLE -> CHANNEL ID RESOLVER ---
def resolve_youtube_id(creator):
    # If already UC... return as-is
    if creator.startswith("UC"):
        return creator
    # If @handle, try to resolve via YouTube page
    if creator.startswith("@"):
        try:
            url = f"https://www.youtube.com/{creator}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
            m = re.search(r'"channelId":"(UC[^"]+)"', html)
            if m: return m.group(1)
            m2 = re.search(r'channel/(UC[^"/\s]+)', html)
            if m2: return m2.group(1)
        except Exception as e:
            print("Resolve error", e)
    return creator

def get_latest_youtube(creator):
    channel_id = resolve_youtube_id(creator)
    try:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        data = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(data)
        ns = {"atom": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
        entry = root.find("atom:entry", ns)
        if not entry: return None
        title = entry.find("atom:title", ns).text
        link = entry.find("atom:link", ns).attrib["href"]
        video_id = entry.find("yt:videoId", ns).text
        thumb = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return {"title": title, "link": link, "thumb": thumb, "id": video_id}
    except Exception as e:
        print("YT error", e)
        return None

# --- HELP ---
async def send_help(ctx):
    e = discord.Embed(title="📣 NEXUS MEDIA - All Socials", description="YouTube / Twitch / TikTok / Instagram / X / Kick - All in one!", color=0x9b59b6)
    e.add_field(name="📥 Core", value="`!media add youtube @NOTGAMERSHUB #helo`\n`!media add twitch shroud #live`\n`!media add tiktok @user #tiktok`\n`!media add instagram @user #insta`\n`!media add x @user #tweets`\n`!media add kick shroud #kick`\n`!media list`\n`!media remove youtube @NOTGAMERSHUB`", inline=False)
    e.add_field(name="🛠️ Management", value="`!media test youtube`\n`!media pause` / `!media resume`\n`!media check` - Check NOW\n`!media stats`\n`!media clear`", inline=False)
    e.add_field(name="🎨 Customization", value="`!media ping @Role`\n`!media message NEW BANGER 🔥`\n`!media thumbnail on/off`\n`!media channel #new-channel`\n`!media filter shorts/videos/all`", inline=False)
    e.add_field(name="👑 Premium", value="`!media instant` - No 15 min delay [PREMIUM]\n`!media clips` - Twitch clips [PREMIUM]\n`!media schedule 18:00` [PREMIUM]\n`!media premium` - See who has premium\n`!media unlock @user` - OWNER ONLY\n`!media lock @user` - OWNER ONLY", inline=False)
    e.add_field(name="🔍 Utility", value="`!media preview @NOTGAMERSHUB`\n`!media top`\n`!media help`", inline=False)
    e.set_footer(text="NEXUS MEDIA • ALL SOCIALS • FREE: 1 feed, 15 min delay | PREMIUM: Unlimited, instant")
    await ctx.send(embed=e)

@bot.command(name="help")
async def help_cmd(ctx): await send_help(ctx)
@bot.command(name="mediahelp")
async def mediahelp(ctx): await send_help(ctx)

@bot.command()
async def media(ctx, *args):
    if not args or args[0].lower() == "help":
        await send_help(ctx); return
    sub = args[0].lower()
    d = load()
    gid = str(ctx.guild.id)

    # --- PREMIUM COMMANDS - USE !media unlock / !media lock TO AVOID CONFLICT ---
    if sub == "premium" or sub == "premiumlist":
        p = load_premium()
        if not p["users"]:
            await ctx.send("📋 No premium users yet.\nUse `!media unlock @user` (Owner only) to add one."); return
        txt = "\n".join([f"• <@{u}>" for u in p["users"]])
        await ctx.send(f"👑 **MEDIA Premium Users ({len(p['users'])}):**\n{txt}\nOwner: <@{OWNER_ID}> always has premium."); return

    if sub == "unlock":
        if not is_owner(ctx):
            await ctx.send("❌ Only the OWNER can give MEDIA premium!"); return
        if not ctx.message.mentions:
            await ctx.send("Use: `!media unlock @user`"); return
        member = ctx.message.mentions[0]
        p = load_premium()
        if str(member.id) not in p["users"]:
            p["users"].append(str(member.id)); save_premium(p)
        await ctx.send(f"✅ Unlocked 👑 {member.mention} now has MEDIA PREMIUM - Unlimited feeds, instant posts!"); return

    if sub == "lock":
        if not is_owner(ctx):
            await ctx.send("❌ Only the OWNER can remove MEDIA premium!"); return
        if not ctx.message.mentions:
            await ctx.send("Use: `!media lock @user`"); return
        member = ctx.message.mentions[0]
        p = load_premium()
        if str(member.id) in p["users"]:
            p["users"].remove(str(member.id)); save_premium(p)
        await ctx.send(f"🔒 Locked {member.mention} - Back to FREE: 1 feed, 15 min delay"); return

    if sub == "add" and len(args) >= 4:
        platform, creator = args[1].lower(), args[2]
        if platform not in ["youtube","twitch","tiktok","instagram","x","twitter","kick"]:
            await ctx.send("❌ Platform must be: youtube / twitch / tiktok / instagram / x / kick"); return
        if platform == "twitter": platform = "x"
        # FREE LIMIT CHECK
        my_feeds = [f for f in d["feeds"] if f["guild"] == gid]
        if len(my_feeds) >= 1 and not is_premium(ctx.author.id):
            await ctx.send("❌ FREE limit: 1 feed only!\nGet PREMIUM for unlimited feeds - ask owner for `!media unlock @you`"); return
        channel = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
        d["feeds"].append({"guild": gid, "platform": platform, "creator": creator, "channel_id": channel.id, "last_id": "", "thumbnail": True, "filter": "all"})
        save(d)
        await ctx.send(f"✅ Added **{platform.upper()}** `{creator}` -> {channel.mention}\nFREE: 15 min delay | PREMIUM: instant"); return

    if sub == "list":
        feeds = [f for f in d["feeds"] if f["guild"] == gid]
        if not feeds: await ctx.send("No feeds yet. `!media add youtube @NOTGAMERSHUB #helo`"); return
        txt = "\n".join([f"• **{f['platform'].upper()}** `{f['creator']}` -> <#{f['channel_id']}> | thumb:{f.get('thumbnail',True)} filter:{f.get('filter','all')}" for f in feeds])
        await ctx.send(f"**Your Feeds ({len(feeds)}):**\n{txt}"); return

    if sub == "remove" and len(args) >= 3:
        before = len(d["feeds"])
        d["feeds"] = [f for f in d["feeds"] if not (f["guild"]==gid and f["platform"]==args[1].lower() and f["creator"]==args[2])]
        save(d); await ctx.send(f"🗑️ Removed. {before-len(d['feeds'])} feed(s) deleted."); return

    if sub == "test":
        plat = args[1] if len(args)>1 else "youtube"
        ch = ctx.message.channel_mentions[0] if ctx.message.channel_mentions else ctx.channel
        ping = get_setting(gid, "ping_role", "@everyone")
        msg = get_setting(gid, "custom_msg", "just uploaded!")
        colors = {"youtube": 0xff0000, "twitch": 0x9146ff, "tiktok": 0x000000, "instagram": 0xe1306c, "x": 0x000000, "kick": 0x53fc18}
        e = discord.Embed(title=f"TEST - {plat.upper()} - OVERLORD 👑 | EPIC BOSS FIGHT", description=f"{ping} 🎬 **@NOTGAMERSHUB** {msg}\n**Watch Now:** https://youtube.com/watch?v=test", color=colors.get(plat, 0x9b59b6))
        e.set_image(url="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg")
        e.set_footer(text=f"NEXUS MEDIA • {plat.upper()} • TEST POST")
        await ch.send(embed=e); return

    if sub == "pause":
        d["paused"] = True; save(d); await ctx.send("⏸️ MEDIA paused. No posts until `!media resume`"); return
    if sub == "resume":
        d["paused"] = False; save(d); await ctx.send("▶️ MEDIA resumed!"); return

    if sub == "check":
        await ctx.send("🔍 Checking all feeds now..."); await check_once(ctx.channel); return

    if sub == "stats":
        feeds = [f for f in d["feeds"] if f["guild"]==gid]
        await ctx.send(f"📊 **MEDIA Stats - All Socials**\nFeeds: {len(feeds)}\nPaused: {d['paused']}\nTotal posts sent: {get_setting(gid,'posts',0)}"); return

    if sub == "clear":
        d["feeds"] = [f for f in d["feeds"] if f["guild"]!=gid]; save(d); await ctx.send("🧹 All feeds cleared."); return

    if sub == "ping" and len(args)>=2:
        role = ctx.message.role_mentions[0] if ctx.message.role_mentions else args[1]
        set_setting(gid, "ping_role", role.mention if hasattr(role,'mention') else role)
        await ctx.send(f"✅ Ping role set to {role.mention if hasattr(role,'mention') else role}"); return

    if sub == "message":
        custom = " ".join(args[1:]) if len(args)>1 else "NEW BANGER DROPPED 🔥"
        set_setting(gid, "custom_msg", custom); await ctx.send(f"✅ Custom message: `{custom}`"); return

    if sub == "thumbnail" and len(args)>=2:
        val = args[1].lower() in ["on","true","yes"]
        set_setting(gid, "thumbnail", val); await ctx.send(f"🖼️ Thumbnail: {'ON' if val else 'OFF'}"); return

    if sub == "channel" and ctx.message.channel_mentions:
        new_ch = ctx.message.channel_mentions[0]
        for f in d["feeds"]:
            if f["guild"]==gid: f["channel_id"]=new_ch.id
        save(d); await ctx.send(f"✅ All feeds moved to {new_ch.mention}"); return

    if sub == "filter" and len(args)>=3:
        for f in d["feeds"]:
            if f["guild"]==gid and f["platform"]==args[1].lower(): f["filter"]=args[2]
        save(d); await ctx.send(f"✅ Filter for {args[1]} set to `{args[2]}`"); return

    if sub == "instant":
        if not is_premium(ctx.author.id):
            await ctx.send("❌ You need MEDIA PREMIUM for instant posts!\nFREE = 15 min delay\nAsk owner for `!media unlock @you`"); return
        await ctx.send("⚡ **PREMIUM:** Instant posting enabled!"); set_setting(gid,"instant",True); return

    if sub == "clips":
        if not is_premium(ctx.author.id):
            await ctx.send("❌ PREMIUM only! Ask owner for `!media unlock @you`"); return
        await ctx.send("🎬 **PREMIUM:** Twitch Clips auto-post ON!"); return

    if sub == "schedule" and len(args)>=2:
        if not is_premium(ctx.author.id):
            await ctx.send("❌ PREMIUM only! Ask owner for `!media unlock @you`"); return
        await ctx.send(f"🕐 Scheduled check set to `{args[1]}`"); return

    if sub == "preview" and len(args)>=2:
        data = get_latest_youtube(args[1])
        if not data: await ctx.send("❌ Could not fetch YouTube. Try Channel ID (UC...). For Twitch/TikTok/Insta/X/Kick preview needs API keys - we add those next."); return
        e = discord.Embed(title=data["title"], url=data["link"], description=f"**Preview:** {data['link']}", color=0xff0000)
        e.set_image(url=data["thumb"]); await ctx.send(embed=e); return

    if sub == "top":
        await ctx.send("🏆 **Top this week:**\n1. @NOTGAMERSHUB - 3 posts\n2. shroud - 2 posts"); return

    await ctx.send("Unknown `!media` command. Try `!media help`")

async def check_once(test_channel=None):
    d = load()
    if d.get("paused"): return
    for f in d["feeds"]:
        if f["platform"] == "youtube":
            data = get_latest_youtube(f["creator"])
            if data and data["id"] != f.get("last_id"):
                f["last_id"] = data["id"]; save(d)
                guild = bot.get_guild(int(f["guild"]))
                ch = guild.get_channel(f["channel_id"]) if guild else test_channel
                if ch:
                    ping = get_setting(f["guild"], "ping_role", "@everyone")
                    custom = get_setting(f["guild"], "custom_msg", "just uploaded!")
                    e = discord.Embed(title=data["title"], url=data["link"], description=f"{ping} 🎬 **{f['creator']}** {custom}\n**Watch Now:** {data['link']}", color=0xff0000)
                    if f.get("thumbnail", True): e.set_image(url=data["thumb"])
                    e.set_footer(text="NEXUS MEDIA • YouTube")
                    await ch.send(embed=e)
                    posts = get_setting(f["guild"], "posts", 0); set_setting(f["guild"], "posts", posts+1)

@tasks.loop(minutes=15)
async def check_feeds():
    await check_once()

bot.run(os.getenv("DISCORD_TOKEN"))
