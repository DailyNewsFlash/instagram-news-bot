import os
import requests
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime
import random
import base64
import time
import sys
from urllib.parse import quote

# ── API keys ──────────────────────────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"].strip()
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"].strip()
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"].strip()
FB_PAGE_ID          = os.environ["FB_PAGE_ID"].strip()
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"].strip()
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"].strip()
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY     = os.environ.get("PIXABAY_API_KEY", "").strip()
POST_TYPE           = os.environ.get("POST_TYPE", "single").strip()

# ── Topics ────────────────────────────────────────────────────────────────────
TRENDING_TOPICS = [
    "India government policy controversy",
    "India Supreme Court verdict",
    "cricket India match result",
    "India economy inflation prices",
    "India crime shocking",
    "bollywood controversy scandal",
    "India politics BJP Congress clash",
    "India protest strike",
    "India scam fraud exposed",
    "India vs Pakistan news",
    "Narendra Modi government decision",
    "India unemployment jobs",
    "India army military",
    "ISRO space India",
    "India startup unicorn",
    "India flood disaster",
    "world war conflict",
    "India education system",
]

# ── Gemini: dual-key rotation + model fallbacks ───────────────────────────────
# Free tier: 15 req/min per key. Two keys = 30 req/min effective limit.
# We rotate keys + models to avoid hitting any single limit.
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

# Primary key always set. Secondary key optional — doubles capacity if set.
_GEMINI_KEYS = [k.strip() for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GEMINI_API_KEY_2", ""),   # optional second key
] if k.strip()]

_key_index   = 0      # which key to use next
_last_call   = {}     # per-key last call timestamp
_call_count  = {}     # per-key call count this run

def _next_key():
    """Round-robin between available keys."""
    global _key_index
    if len(_GEMINI_KEYS) == 0:
        return ""
    key = _GEMINI_KEYS[_key_index % len(_GEMINI_KEYS)]
    _key_index += 1
    return key

def call_gemini(prompt, retries=2):
    """
    Call Gemini with:
    - Key rotation (if 2 keys configured, alternates between them)
    - Model fallback (2.0-flash → 1.5-flash → 1.5-flash-8b)
    - Smart rate-limit backoff (waits then retries, doesn't just give up)
    - Minimum 6s gap between calls to stay under 15 req/min
    """
    if not _GEMINI_KEYS:
        print("No Gemini API key configured")
        return None

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in GEMINI_MODELS:
        for attempt in range(retries):
            key = _next_key()

            # Enforce minimum gap per key — 8s gives 7.5 req/min, safe under 15 limit
            now = time.time()
            last = _last_call.get(key, 0)
            gap = now - last
            if gap < 8:
                time.sleep(8 - gap)

            try:
                url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                       f"{model}:generateContent?key={key}")
                _last_call[key] = time.time()
                _call_count[key] = _call_count.get(key, 0) + 1

                resp = requests.post(url, json=payload, timeout=35)
                data = resp.json()

                if "candidates" in data:
                    keys_info = f"key{'1' if key == _GEMINI_KEYS[0] else '2'}"
                    print(f"Gemini OK ({model}, {keys_info}, "
                          f"call #{_call_count.get(key,1)} this run)")
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

                err_msg  = data.get("error", {}).get("message", "")
                err_code = data.get("error", {}).get("code", 0)

                if err_code == 429 or "quota" in err_msg.lower() or "rate" in err_msg.lower():
                    # Try to read retry-after from error message
                    import re as _re
                    retry_match = _re.search(r"retry.{0,10}?([0-9]+)\s*s", err_msg, _re.IGNORECASE)
                    suggested = int(retry_match.group(1)) + 5 if retry_match else None
                    wait = suggested if suggested else (25 + attempt * 15)
                    print(f"Rate limit ({model}), waiting {wait}s then retrying...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"Gemini error ({model}): {err_msg}")
                    break  # non-rate error — try next model

            except Exception as e:
                print(f"Gemini exception ({model}): {e}")
                time.sleep(4)

    print("All Gemini options exhausted — using rule-based fallback")
    return None


# ── Rule-based fallbacks (used when Gemini is rate-limited) ─────────────────
def _rule_keyword(article):
    t = article["title"].lower()
    d = article.get("description", "").lower()
    combined = t + " " + d
    if any(w in combined for w in ["murder","kill","dead","body","crime","arrest","rape","attack"]):
        return "crime scene police tape investigation dark"
    if any(w in combined for w in ["cricket","ipl","match","wicket","bat","bowl","rohit","kohli","virat"]):
        return "cricket stadium floodlights night match"
    if any(w in combined for w in ["court","verdict","judge","bail","cbi","ed","fir","law"]):
        return "supreme court building exterior stone pillars"
    if any(w in combined for w in ["bollywood","film","movie","actor","actress","cinema","ott","star"]):
        return "film camera crew set dramatic lights"
    if any(w in combined for w in ["isro","rocket","satellite","space","moon","mars","chandrayaan"]):
        return "rocket launch fire smoke night sky"
    if any(w in combined for w in ["flood","earthquake","cyclone","disaster","rain","landslide"]):
        return "flood disaster rescue boat water submerged"
    if any(w in combined for w in ["protest","strike","rally","agitation","crowd","demonstration"]):
        return "protest crowd street demonstration banners"
    if any(w in combined for w in ["war","military","army","border","soldier","pakistan","china"]):
        return "military soldiers equipment dramatic sky"
    if any(w in combined for w in ["economy","inflation","rupee","market","stock","gdp","budget","rbi"]):
        return "stock market trading screen finance"
    if any(w in combined for w in ["scam","fraud","ponzi","crypto","hack","cheat","fake"]):
        return "handcuffs police arrest investigation"
    if any(w in combined for w in ["fire","blast","explosion","building"]):
        return "fire explosion building dramatic night"
    if any(w in combined for w in ["hospital","health","doctor","disease","medicine","drug"]):
        return "hospital interior medical equipment"
    if any(w in combined for w in ["school","college","university","student","education","exam"]):
        return "university campus students studying"
    if any(w in combined for w in ["modi","bjp","congress","parliament","minister","election","government"]):
        return "parliament building dome architecture exterior"
    return "india city skyline dramatic dusk"


def _rule_ai_prompt(article):
    t = article["title"].lower()
    d = article.get("description", "").lower()
    combined = t + " " + d
    if any(w in combined for w in ["murder","kill","crime","arrest","rape","attack"]):
        return "dark crime scene yellow police tape rain dramatic cinematic no people"
    if any(w in combined for w in ["cricket","ipl","match"]):
        return "empty cricket stadium at night floodlights dramatic wide angle cinematic"
    if any(w in combined for w in ["court","verdict","judge","law"]):
        return "grand supreme court building stone exterior dramatic storm clouds cinematic"
    if any(w in combined for w in ["isro","rocket","space","satellite"]):
        return "rocket on launchpad night dramatic fire smoke sky cinematic"
    if any(w in combined for w in ["flood","disaster","cyclone"]):
        return "flooded village road dramatic storm clouds rescue boat cinematic"
    if any(w in combined for w in ["protest","strike","rally"]):
        return "empty city street night dramatic lights fog cinematic wide angle"
    if any(w in combined for w in ["scam","fraud","crypto","hack"]):
        return "dark office computer screen data dramatic cinematic no people"
    if any(w in combined for w in ["parliament","modi","election","government"]):
        return "parliament building dome night dramatic lighting cinematic wide angle"
    if any(w in combined for w in ["economy","inflation","market","rupee"]):
        return "stock market trading floor screens dramatic lighting cinematic"
    if any(w in combined for w in ["bollywood","film","cinema"]):
        return "empty film set camera equipment dramatic studio lighting cinematic"
    return "dramatic india city skyline dusk golden hour cinematic wide angle"


def _rule_summary(article):
    title = article["title"]
    desc  = article.get("description", "").strip()
    if desc and len(desc) > 30:
        # Trim to ~40 words
        words = desc.split()
        short = " ".join(words[:40])
        if len(words) > 40:
            short += "..."
        return short
    return title + " — Read the full story in the caption below."


def _rule_caption(article):
    title = article["title"]
    desc  = article.get("description", "")
    src   = article["source"]["name"]
    return (f"⚡ {title}\n\n"
            f"{desc}\n\n"
            f"📌 Source: {src}\n\n"
            f"💬 What do YOU think? Comment below 👇\n"
            f"👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡\n\n"
            f"#india #breakingnews #indianews #dailynewsflash #news "
            f"#indiatoday #ndtv #trending #viral #currentaffairs")


# ── ONE combined Gemini call per article (saves quota) ────────────────────────
def analyse_article(article, post_type="single"):
    """
    Single Gemini call that returns:
      - photo_keyword   : best stock-photo search term
      - ai_image_prompt : Pollinations AI image prompt
      - caption         : full Instagram caption
    All in one call to minimise quota usage.
    """
    title = article["title"]
    desc  = article.get("description", "")[:300]
    src   = article["source"]["name"]
    topic = article.get("_topic", "general")

    if post_type == "carousel":
        caption_instruction = f"""CAPTION (carousel slide summary):
Write 2-3 punchy sentences summarising this story for a carousel slide.
End with: 📌 {src}"""
    else:
        caption_instruction = f"""CAPTION (full single-post caption):
Structure:
1. ONE punchy hook — 🔴 or 🚨 or ⚡ — the most shocking/controversial angle
2. 📖 WHAT HAPPENED — 3-4 clear sentences: what, who, where, when, consequence
3. 🤔 WHY IT MATTERS — 2 sentences why every Indian should care
4. 🔥 THE CONTROVERSY — 1-2 sentences on what people argue about
5. One hot-take line using Indian slang: "Yaar", "bhai", "sach mein"
6. 📌 Source: {src}
7. 💬 What's YOUR take? Drop your opinion below 👇 Don't hold back!
8. 👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡
9. 25 relevant hashtags (English + Hindi)
Rules: facts only, conversational, emojis throughout, 1800-2200 chars, make people WANT to comment."""

    prompt = f"""You are an expert Indian news Instagram editor.
Analyse this news article and return EXACTLY four sections labelled as shown.

Article title: {title}
Description: {desc}
Source: {src}
Topic category: {topic}

---
PHOTO_KEYWORD:
Give ONE specific 3-5 word stock photo search term that visually matches this story.
Rules:
- NEVER use: india flag, indian flag, india map, face, person, woman, man, portrait, girl, boy
- Match the SCENE not the person: crime news → "police investigation crime scene tape",
  court → "supreme court building exterior", cricket → "cricket stadium floodlights night",
  protest → "protest crowd street demonstration", flood → "flood water submerged village",
  space → "rocket launch fire smoke night sky", economy → "stock market trading screen",
  bollywood → "film camera crew set lights", politics → "parliament building dome exterior"
- NEVER generate images of people or faces under any circumstances

---
AI_IMAGE_PROMPT:
Write a SHORT (max 18 words) Pollinations AI image generation prompt.
STRICT RULES — violations will ruin the post:
- NO human faces, NO people, NO portraits, NO person, NO woman, NO man
- Focus ONLY on: locations, objects, scenes, symbols, architecture, nature, vehicles
- Must be: photorealistic, cinematic, dramatic lighting, no text, no logos
- Crime/murder → "crime scene police tape dark alley dramatic lighting"
- Court → "supreme court building stone pillars dramatic sky cinematic"
- Cricket → "empty cricket stadium floodlights night dramatic wide angle"
- Economy → "stock market graphs screens trading floor dramatic"
- Space → "rocket on launchpad night dramatic sky cinematic"
- Politics → "parliament building dome dramatic storm clouds cinematic"
Good example: "dark crime scene investigation tape rain dramatic lighting photorealistic"
BAD example: "woman looking at camera" — NEVER do this

---
SUMMARY:
Write exactly 2 punchy sentences (max 40 words total) summarising what happened.
Plain language. Facts only. No emojis. This appears ON the image card.

---
{caption_instruction}

Respond in EXACTLY this format — nothing else before or after:
PHOTO_KEYWORD: <keyword here>
AI_IMAGE_PROMPT: <prompt here>
SUMMARY: <2 sentences here>
CAPTION:
<full caption here>"""

    result = call_gemini(prompt)
    if not result:
        # Rule-based fallback so post still looks decent without Gemini
        kw = _rule_keyword(article)
        ai_p = _rule_ai_prompt(article)
        summ = _rule_summary(article)
        cap  = _rule_caption(article)
        return kw, ai_p, summ, cap

    try:
        keyword, ai_prompt, summary, caption = None, None, None, None
        lines = result.split("\n")
        caption_lines = []
        in_caption = False
        for line in lines:
            if line.startswith("PHOTO_KEYWORD:"):
                keyword = line.split(":", 1)[1].strip().strip('"').strip("'")
                in_caption = False
            elif line.startswith("AI_IMAGE_PROMPT:"):
                ai_prompt = line.split(":", 1)[1].strip().strip('"').strip("'")
                in_caption = False
            elif line.startswith("SUMMARY:"):
                summary = line.split(":", 1)[1].strip()
                in_caption = False
            elif line.startswith("CAPTION:"):
                in_caption = True
            elif in_caption:
                caption_lines.append(line)
        caption = "\n".join(caption_lines).strip()
        return (keyword or "breaking news press",
                ai_prompt or "dark dramatic scene cinematic",
                summary or "",
                caption or "")
    except Exception as e:
        print(f"Parse failed: {e}")
        return "breaking news press", "dark dramatic scene cinematic", "", ""


# ── Free RSS feeds — unlimited, no API key ────────────────────────────────────
RSS_FEEDS = [
    ("https://feeds.feedburner.com/ndtvnews-top-stories",         "NDTV"),
    ("https://timesofindia.indiatimes.com/rssfeedstopstories.cms","Times of India"),
    ("https://www.thehindu.com/news/feeder/default.rss",          "The Hindu"),
    ("https://indianexpress.com/feed/",                           "Indian Express"),
    ("https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml","Hindustan Times"),
    ("https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",    "BBC India"),
]

def _fetch_rss(url, source_name):
    try:
        r = requests.get(url, timeout=12,
                         headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0"})
        if r.status_code != 200:
            return []
        xml = r.text
        articles = []
        items = xml.split("<item>")[1:]
        for item in items[:15]:
            def tag(t, block=item):
                s = block.find(f"<{t}>")
                e = block.find(f"</{t}>")
                if s == -1 or e == -1:
                    return ""
                return block[s+len(t)+2:e].strip().replace("<![CDATA[","").replace("]]>","").strip()
            title = tag("title")
            desc  = tag("description")[:300]
            link  = tag("link")
            if title and len(title) > 10:
                articles.append({
                    "title":       title,
                    "description": desc,
                    "url":         link,
                    "source":      {"name": source_name},
                    "_topic":      "general",
                })
        print(f"RSS {source_name}: {len(articles)} articles")
        return articles
    except Exception as e:
        print(f"RSS {source_name} error: {e}")
        return []


# ── fetch_articles: 2 GNews calls max + RSS backup ────────────────────────────
def fetch_articles(count=5):
    """
    GNews free = 100 req/day. We use max 2 calls per run (10/day for 5 posts).
    RSS feeds are free, unlimited, no key needed — always used as supplement.
    """
    print("Fetching articles...")
    all_articles = []

    # Call 1: GNews top headlines (1 request)
    try:
        r = requests.get(
            "https://gnews.io/api/v4/top-headlines",
            params={"token": GNEWS_API_KEY, "lang": "en",
                    "country": "in", "max": 10},
            timeout=10)
        data = r.json()
        arts = data.get("articles", [])
        for a in arts:
            a["_topic"] = "top-headlines"
        all_articles.extend(arts)
        print(f"GNews headlines: {len(arts)} articles")
    except Exception as e:
        print(f"GNews headlines error: {e}")

    # Call 2: GNews search — ONE topic (1 request)
    topic = random.choice([
        "India controversy", "India crime", "cricket India",
        "India politics", "India economy", "bollywood scandal",
        "India Supreme Court", "India scam",
    ])
    try:
        r = requests.get(
            "https://gnews.io/api/v4/search",
            params={"token": GNEWS_API_KEY, "lang": "en", "country": "in",
                    "max": 10, "q": topic, "sortby": "publishedAt"},
            timeout=10)
        arts = r.json().get("articles", [])
        for a in arts:
            a["_topic"] = topic
        all_articles.extend(arts)
        print(f"GNews search '{topic}': {len(arts)} articles")
    except Exception as e:
        print(f"GNews search error: {e}")

    # RSS supplement — always run, free, no quota
    print("Loading RSS feeds...")
    feeds = random.sample(RSS_FEEDS, min(3, len(RSS_FEEDS)))
    for feed_url, feed_name in feeds:
        all_articles.extend(_fetch_rss(feed_url, feed_name))

    if not all_articles:
        print("All sources failed — no articles available.")
        return []

    # Deduplicate + filter non-India irrelevant articles
    NON_INDIA_SKIP = [
        "guardian", "washington post", "new york times", "fox news",
        "bbc world", "reuters world", "bloomberg", "cnn world",
    ]
    INDIA_BOOST_KEYWORDS = [
        "india", "indian", "modi", "bjp", "congress", "delhi", "mumbai",
        "rupee", "isro", "ipl", "cricket", "bollywood", "sc ", "supreme court",
        "pakistan", "china border", "gujarat", "kerala", "bengal", "punjab",
        "tamil", "telangana", "andhra", "karnataka", "maharashtra", "rahul",
    ]

    seen, unique = set(), []
    for a in all_articles:
        t = a["title"].strip().lower()
        src = a["source"]["name"].lower()
        if t in seen or len(t) < 10:
            continue
        seen.add(t)
        # Downrank clearly non-India foreign stories from non-Indian sources
        is_foreign_src = any(s in src for s in NON_INDIA_SKIP)
        has_india_angle = any(k in t for k in INDIA_BOOST_KEYWORDS)
        if is_foreign_src and not has_india_angle:
            continue   # skip e.g. Guardian crypto article with no India angle
        unique.append(a)
    print(f"Total unique India-relevant articles: {len(unique)}")

    if not unique:
        print("No India-relevant articles — using all unfiltered")
        unique = list(seen)  # shouldn't happen but safety net

    if len(unique) <= count:
        return unique

    # ONE Gemini call to pick best — with rule-based fallback
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(unique[:25])])
    prompt = (
        "You are a viral Indian Instagram news editor.\n"
        f"Pick TOP {count} articles for max engagement from young Indians (18-35).\n"
        "Prioritise: scandals, Supreme Court, cricket, ISRO, crime, protest, govt decisions.\n"
        "Avoid: celebrity meetups, PR fluff, dry reports, repeated stories, foreign news with no India angle.\n\n"
        f"{titles}\n\n"
        "Reply with ONLY comma-separated numbers. Example: 3,7,1,12,5\nNothing else."
    )
    answer = call_gemini(prompt)
    if answer:
        try:
            nums = [int(n.strip()) for n in answer.split(",") if n.strip().isdigit()]
            nums = [n for n in nums if 1 <= n <= len(unique)][:count]
            if len(nums) >= min(count, len(unique)):
                print(f"Gemini picked: {nums}")
                return [unique[n-1] for n in nums]
        except Exception as e:
            print(f"Pick parse error: {e}")

    # Smart rule-based fallback — score articles by India relevance
    def score(a):
        t = a["title"].lower()
        d = a.get("description","").lower()
        s = 0
        for k in INDIA_BOOST_KEYWORDS:
            if k in t: s += 3
            if k in d: s += 1
        high_engage = ["murder","scam","rape","arrest","court","verdict","protest",
                       "cricket","ipl","bollywood","isro","explosion","flood","crash"]
        for k in high_engage:
            if k in t: s += 5
        return s
    unique.sort(key=score, reverse=True)
    print("Using rule-based article ranking (Gemini unavailable)")
    return unique[:count]


# ── Image: try 3 real sources then AI fallback ────────────────────────────────
def fetch_image(keyword, ai_prompt, article, save_path="/tmp/img.jpg"):
    candidates = []

    # Unsplash
    try:
        params = {"query": keyword, "per_page": 15,
                  "page": random.randint(1, 3), "orientation": "squarish",
                  "client_id": UNSPLASH_ACCESS_KEY}
        r = requests.get("https://api.unsplash.com/search/photos", params=params, timeout=10)
        results = r.json().get("results", [])
        if results:
            p = random.choice(results[:10])
            candidates.append(("Unsplash", p["urls"]["regular"], p.get("likes", 0)))
            print(f"Unsplash: {len(results)} results")
    except Exception as e:
        print(f"Unsplash error: {e}")

    # Pexels
    if PEXELS_API_KEY:
        try:
            params = {"query": keyword, "per_page": 15,
                      "page": random.randint(1, 3), "orientation": "square"}
            r = requests.get("https://api.pexels.com/v1/search",
                             headers={"Authorization": PEXELS_API_KEY},
                             params=params, timeout=10)
            photos = r.json().get("photos", [])
            if photos:
                p = random.choice(photos[:10])
                candidates.append(("Pexels", p["src"]["large2x"], 1000))
                print(f"Pexels: {len(photos)} results")
        except Exception as e:
            print(f"Pexels error: {e}")

    # Pixabay
    if PIXABAY_API_KEY:
        try:
            params = {"key": PIXABAY_API_KEY, "q": keyword, "image_type": "photo",
                      "per_page": 15, "page": random.randint(1, 3),
                      "orientation": "horizontal", "safesearch": "true", "min_width": 800}
            r = requests.get("https://pixabay.com/api/", params=params, timeout=10)
            hits = r.json().get("hits", [])
            if hits:
                p = random.choice(hits[:10])
                candidates.append(("Pixabay", p["webformatURL"], p.get("likes", 0)))
                print(f"Pixabay: {len(hits)} results")
        except Exception as e:
            print(f"Pixabay error: {e}")

    # Try downloading best real photo
    if candidates:
        pexels = [c for c in candidates if c[0] == "Pexels"]
        src_name, img_url, _ = pexels[0] if pexels else max(candidates, key=lambda x: x[2])
        try:
            r = requests.get(img_url, stream=True, timeout=20)
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(4096):
                        f.write(chunk)
                img = Image.open(save_path)
                w, h = img.size
                # Reject tiny images or extreme aspect ratios
                if w >= 500 and h >= 500 and 0.5 <= w/h <= 2.0:
                    print(f"Real photo from {src_name} ({w}x{h})")
                    return save_path, src_name
                else:
                    print(f"Rejected image: too small or wrong ratio ({w}x{h})")
        except Exception as e:
            print(f"Photo download error: {e}")

    # AI fallback — Pollinations (free, no key)
    print("Generating AI image via Pollinations...")
    full_prompt = f"{ai_prompt}, high quality, 4k, photorealistic, no text, no watermark"
    encoded = quote(full_prompt)
    seed = random.randint(1, 99999)
    ai_url = (f"https://image.pollinations.ai/prompt/{encoded}"
              f"?width=1080&height=1080&seed={seed}&model=flux&nologo=true")
    try:
        r = requests.get(ai_url, timeout=90, stream=True)
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            ai_path = save_path.replace(".jpg", "_ai.jpg")
            with open(ai_path, "wb") as f:
                for chunk in r.iter_content(4096):
                    f.write(chunk)
            Image.open(ai_path).verify()
            print("AI image generated OK")
            return ai_path, "AI Generated"
    except Exception as e:
        print(f"AI image error: {e}")

    return None, "none"


# ── Image design helpers ──────────────────────────────────────────────────────
def _load_fonts():
    base = "/usr/share/fonts/truetype/dejavu/"
    try:
        return {
            "huge":   ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 88),
            "large":  ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 54),
            "head":   ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 54),
            "brand":  ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 36),
            "source": ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 26),
            "body":   ImageFont.truetype(base + "DejaVuSans.ttf", 30),
            "small":  ImageFont.truetype(base + "DejaVuSans.ttf", 28),
            "badge":  ImageFont.truetype(base + "DejaVuSans.ttf", 22),
            "num":    ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 105),
        }
    except:
        d = ImageFont.load_default()
        return {k: d for k in ["huge","large","head","brand","source","body","small","badge","num"]}


def _get_topic_tag(headline, source):
    """Return a short uppercase category label for the post."""
    h = headline.lower()
    if any(w in h for w in ["murder","crime","rape","arrest","theft","fraud","scam","stolen"]):
        return "CRIME"
    if any(w in h for w in ["cricket","ipl","match","wicket","run","batting","bowling","rohit","kohli","virat"]):
        return "CRICKET"
    if any(w in h for w in ["court","verdict","judge","sc","high court","cbi","ed","bail"]):
        return "JUSTICE"
    if any(w in h for w in ["bollywood","film","movie","actor","actress","cinema","ott"]):
        return "BOLLYWOOD"
    if any(w in h for w in ["isro","space","rocket","satellite","moon","mars","chandrayaan"]):
        return "SPACE"
    if any(w in h for w in ["inflation","gdp","economy","rupee","rbi","stock","market","budget"]):
        return "ECONOMY"
    if any(w in h for w in ["protest","strike","rally","agitation","farmer","worker"]):
        return "PROTEST"
    if any(w in h for w in ["pakistan","china","border","military","army","war","ceasefire"]):
        return "WORLD"
    if any(w in h for w in ["modi","bjp","congress","government","minister","parliament","election"]):
        return "POLITICS"
    if any(w in h for w in ["flood","earthquake","cyclone","disaster","rain","storm"]):
        return "DISASTER"
    return "INDIA"


def create_single_image(image_path, image_source, headline, source_name,
                        summary="", output_path="/tmp/final_post.jpg"):
    sz = (1080, 1080)
    img = (Image.open(image_path).convert("RGB").resize(sz, Image.LANCZOS)
           if image_path else Image.new("RGB", sz, (20, 20, 40)))
    ov = Image.new("RGBA", sz, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(22):
        od.rectangle([(0, 520 + i*26), (1080, 520 + (i+1)*26)],
                     fill=(0, 0, 0, min(170 + i*4, 235)))
    od.rectangle([(0, 0), (1080, 98)],  fill=(0, 0, 0, 185))
    od.rectangle([(0, 520), (9, 1080)], fill=(220, 30, 30, 255))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)
    f = _load_fonts()

    draw.text((28, 26), "⚡ DAILY NEWS FLASH", font=f["brand"], fill=(255, 200, 50))
    draw.text((920, 26), "IN", font=f["brand"], fill=(220, 30, 30))

    # Topic tag (top-right area)
    topic_tag = _get_topic_tag(headline, source_name)
    tag_w = len(topic_tag) * 14 + 20
    draw.rectangle([(1080-tag_w-10, 60), (1070, 88)], fill=(220, 30, 30))
    draw.text((1080-tag_w, 63), topic_tag, font=f["badge"], fill=(255, 255, 255))

    if image_source == "AI Generated":
        draw.rectangle([(28, 522), (210, 548)], fill=(80, 0, 150))
        draw.text((34, 525), "✨ AI ILLUSTRATED", font=f["badge"], fill=(220, 180, 255))

    # Source label
    draw.text((25, 558), f"📌 {source_name.upper()}", font=f["source"], fill=(100, 190, 255))

    # Headline
    y = 608
    for line in textwrap.wrap(headline, width=27)[:3]:
        draw.text((22, y), line, font=f["head"], fill=(255, 255, 255))
        y += 64

    # Brief summary on card — the key fix
    if summary:
        y += 8
        draw.rectangle([(0, y-4), (1080, y-2)], fill=(220, 30, 30))  # thin red divider
        y += 10
        for line in textwrap.wrap(summary, width=42)[:3]:
            draw.text((22, y), line, font=f["small"], fill=(210, 210, 210))
            y += 36

    draw.rectangle([(0, 1022), (1080, 1080)], fill=(12, 12, 12))
    draw.text((22, 1036), "👉 Follow @dailynewsflash_in for daily updates",
              font=f["small"], fill=(190, 190, 190))
    img.save(output_path, "JPEG", quality=95)
    print("Single image created.")
    return output_path


def create_cover_slide(output_path="/tmp/slide_0.jpg"):
    img = Image.new("RGB", (1080, 1080), (8, 8, 25))
    draw = ImageDraw.Draw(img)
    f = _load_fonts()
    for i in range(30):
        draw.rectangle([(0, i*36), (1080, (i+1)*36)], fill=(10+i*2, 8+i, 30+i*3))
    draw.rectangle([(55, 195), (1025, 207)], fill=(220, 30, 30))
    draw.rectangle([(55, 830), (1025, 842)], fill=(220, 30, 30))
    draw.text((540, 135), "⚡ @dailynewsflash_in", font=f["small"],  fill=(255, 200, 50), anchor="mm")
    draw.text((540, 390), "TODAY'S",    font=f["huge"],  fill=(255, 255, 255), anchor="mm")
    draw.text((540, 490), "TOP 5 NEWS", font=f["huge"],  fill=(220, 30, 30),   anchor="mm")
    draw.text((540, 640), datetime.now().strftime("%d %B %Y"),
              font=f["large"], fill=(195, 195, 195), anchor="mm")
    draw.text((540, 895), "👉 Swipe to read all 5 stories",
              font=f["small"], fill=(150, 150, 220), anchor="mm")
    draw.text((540, 955), "Follow for India & World news daily",
              font=f["small"], fill=(110, 110, 180), anchor="mm")
    img.save(output_path, "JPEG", quality=95)
    return output_path


def create_news_slide(image_path, image_source, number, headline,
                      description, source, output_path):
    sz = (1080, 1080)
    img = (Image.open(image_path).convert("RGB").resize(sz, Image.LANCZOS)
           if image_path else Image.new("RGB", sz, (12, 12, 35)))
    ov = Image.new("RGBA", sz, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rectangle([(0,   0), (1080, 1080)], fill=(0, 0, 0, 148))
    od.rectangle([(0,   0), (1080,   98)], fill=(0, 0, 0, 215))
    od.rectangle([(0, 885), (1080, 1080)], fill=(0, 0, 0, 230))
    od.rectangle([(0,   0), (9,   1080)],  fill=(220, 30, 30, 255))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    draw = ImageDraw.Draw(img)
    f = _load_fonts()

    draw.text((28, 28), "⚡ DAILY NEWS FLASH", font=f["brand"], fill=(255, 200, 50))
    draw.text((860, 155), f"#{number}", font=f["num"], fill=(220, 30, 30))
    if image_source == "AI Generated":
        draw.rectangle([(28, 95), (200, 120)], fill=(80, 0, 150))
        draw.text((34, 98), "✨ AI ILLUSTRATED", font=f["badge"], fill=(220, 180, 255))
    y = 290
    for line in textwrap.wrap(headline, width=25)[:4]:
        draw.text((28, y), line, font=f["head"], fill=(255, 255, 255))
        y += 64
    if description:
        short = description[:220] + "..." if len(description) > 220 else description
        y += 18
        for line in textwrap.wrap(short, width=44)[:4]:
            draw.text((28, y), line, font=f["body"], fill=(215, 215, 215))
            y += 40
    draw.text((28, 900),  f"📌 {source}",           font=f["small"], fill=(100, 190, 255))
    draw.text((28, 945),  "Swipe for more →",         font=f["small"], fill=(155, 155, 210))
    draw.text((28, 993),  "👉 Follow @dailynewsflash_in", font=f["small"], fill=(255, 200, 50))
    img.save(output_path, "JPEG", quality=95)
    return output_path


# ── Upload to Imgur ───────────────────────────────────────────────────────────
def upload_to_imgur(image_path):
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    try:
        r = requests.post("https://api.imgur.com/3/image",
                          headers={"Authorization": "Client-ID 546c25a59c58ad7"},
                          data={"image": data, "type": "base64"}, timeout=30)
        d = r.json()
        if d.get("success"):
            print(f"Imgur OK: {d['data']['link']}")
            return d["data"]["link"]
        print(f"Imgur failed: {d}")
    except Exception as e:
        print(f"Imgur error: {e}")
    return None


# ── Token auto-refresh ────────────────────────────────────────────────────────
def _get_page_token(user_token, app_id, app_secret):
    """Exchange user token for a Page access token (never expires)."""
    try:
        # Step 1: Get long-lived user token (60 days)
        r = requests.get(
            "https://graph.facebook.com/v25.0/oauth/access_token",
            params={"grant_type": "fb_exchange_token",
                    "client_id": app_id, "client_secret": app_secret,
                    "fb_exchange_token": user_token},
            timeout=15)
        d = r.json()
        ll_token = d.get("access_token", "")
        if not ll_token:
            print(f"Long-lived token exchange failed: {d}")
            return None
        print(f"Long-lived token obtained (expires ~60 days)")

        # Step 2: Get Page access token (never expires for verified apps)
        r2 = requests.get(
            f"https://graph.facebook.com/v25.0/{os.environ.get('FB_PAGE_ID','')}/",
            params={"fields": "access_token", "access_token": ll_token},
            timeout=15)
        d2 = r2.json()
        page_token = d2.get("access_token", "")
        if page_token:
            print("Page token obtained (never expires)")
            return page_token
        print(f"Page token failed: {d2}")
        return ll_token   # fall back to 60-day token
    except Exception as e:
        print(f"Page token error: {e}")
        return None


def refresh_fb_token():
    """
    Full token refresh chain:
    1. If FB_APP_ID + FB_APP_SECRET present: get a never-expiring Page token
    2. If only those missing: use existing FB_ACCESS_TOKEN as-is
    Logs clearly so you know the status every run.
    """
    app_id     = os.environ.get("FB_APP_ID", "").strip()
    app_secret = os.environ.get("FB_APP_SECRET", "").strip()

    if not app_id or not app_secret:
        print("⚠️  FB_APP_ID / FB_APP_SECRET not set in GitHub Secrets.")
        print("    Token will expire every few hours — see setup instructions.")
        print(f"    Using current token (may be expired).")
        return FB_ACCESS_TOKEN

    print("Refreshing FB token...")
    new_token = _get_page_token(FB_ACCESS_TOKEN, app_id, app_secret)
    if new_token:
        return new_token

    print("Token refresh failed — using existing token")
    return FB_ACCESS_TOKEN


# ── Post to Instagram ─────────────────────────────────────────────────────────
def post_single(image_url, caption, token):
    print("Posting single...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30)
    result = r.json()
    cid = result.get("id")
    if not cid:
        err = result.get("error", {})
        code = err.get("code", "?")
        msg  = err.get("message", str(result))
        # Token expired — give clear instructions
        if code in [190, 463] or "expired" in msg.lower() or "session" in msg.lower():
            print("❌ FB TOKEN EXPIRED. Fix: Go to developers.facebook.com/tools/explorer")
            print("   → Generate Access Token → me/accounts → copy access_token")
            print("   → Update FB_ACCESS_TOKEN secret in GitHub")
        raise Exception(f"Container failed (code {code}): {msg}")
    time.sleep(8)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": cid, "access_token": token}, timeout=30)
    if "id" in r2.json():
        print(f"✅ Single post live! ID: {r2.json()['id']}")
    else:
        raise Exception(f"Publish failed: {r2.json()}")


def post_carousel(image_urls, caption, token):
    print(f"Posting carousel ({len(image_urls)} slides)...")
    child_ids = []
    for i, url in enumerate(image_urls):
        r = requests.post(
            f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
            data={"image_url": url, "is_carousel_item": "true", "access_token": token},
            timeout=30)
        cid = r.json().get("id")
        if cid:
            child_ids.append(cid)
        else:
            print(f"Slide {i+1} failed: {r.json()}")
        time.sleep(3)
    if len(child_ids) < 2:
        raise Exception(f"Not enough slides ({len(child_ids)})")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
              "caption": caption, "access_token": token}, timeout=30)
    carid = r.json().get("id")
    if not carid:
        raise Exception(f"Carousel container failed: {r.json()}")
    time.sleep(8)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": carid, "access_token": token}, timeout=30)
    if "id" in r2.json():
        print(f"✅ Carousel live! ID: {r2.json()['id']}")
    else:
        raise Exception(f"Carousel publish failed: {r2.json()}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Bot started {datetime.now()} | Type: {POST_TYPE} ===\n")

    # Refresh FB token first (prevents the "session expired" error)
    token = refresh_fb_token()

    if POST_TYPE == "carousel":
        articles = fetch_articles(count=5)
        if not articles:
            print("No articles found.")
            sys.exit(1)

        slide_paths = [create_cover_slide("/tmp/slide_0.jpg")]
        carousel_captions = []

        for i, article in enumerate(articles):
            print(f"\n--- Slide {i+1}/5: {article['title'][:65]}...")
            # ONE Gemini call covers keyword + AI prompt + slide caption
            keyword, ai_prompt, summary, slide_cap = analyse_article(article, "carousel")
            carousel_captions.append(slide_cap)
            time.sleep(2)   # small pause between Gemini calls

            img_path, img_src = fetch_image(keyword, ai_prompt, article,
                                             f"/tmp/slide_img_{i}.jpg")
            slide = create_news_slide(img_path, img_src, i+1,
                                      article["title"],
                                      article.get("description", ""),
                                      article["source"]["name"],
                                      f"/tmp/slide_{i+1}.jpg")
            slide_paths.append(slide)

        # ONE more Gemini call for the main carousel caption
        time.sleep(5)
        headlines = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles)])
        cap_prompt = (
            f"Write an Instagram carousel caption for @dailynewsflash_in (young Indians 18-35).\n"
            f"Stories:\n{headlines}\n\n"
            f"Structure:\n"
            f"1. 🗞️ Hook: '5 stories India is ARGUING about right now 👇'\n"
            f"2. One spicy teaser per story (1️⃣ to 5️⃣)\n"
            f"3. 'Tell us which story made your blood boil 👇 Comment the number!'\n"
            f"4. 👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡\n"
            f"5. 25 trending hashtags\nUnder 2200 chars."
        )
        main_caption = call_gemini(cap_prompt) or "🗞️ Today's Top 5!\n\n👉 Follow @dailynewsflash_in\n\n#news #india"

        print("\nUploading slides...")
        urls = []
        for path in slide_paths:
            u = upload_to_imgur(path)
            if u:
                urls.append(u)
            time.sleep(2)
        if len(urls) < 2:
            print("Not enough uploads.")
            sys.exit(1)
        post_carousel(urls, main_caption, token)

    else:
        articles = fetch_articles(count=1)
        if not articles:
            print("No articles found.")
            sys.exit(1)
        article = articles[0]
        print(f"\nArticle: {article['title']}")

        # ONE Gemini call for everything
        keyword, ai_prompt, summary, caption = analyse_article(article, "single")
        img_path, img_src = fetch_image(keyword, ai_prompt, article)
        final = create_single_image(img_path, img_src, article["title"],
                                    article["source"]["name"], summary)
        img_url = upload_to_imgur(final)
        if not img_url:
            print("Upload failed.")
            sys.exit(1)
        post_single(img_url, caption, token)

    print(f"\n=== ✅ Done at {datetime.now()} ===\n")


if __name__ == "__main__":
    main()
