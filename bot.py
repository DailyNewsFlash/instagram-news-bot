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
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

_GEMINI_KEYS = [k.strip() for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GEMINI_API_KEY_2", ""),   # optional second key
] if k.strip()]

_key_index   = 0      
_last_call   = {}     
_call_count  = {}     

def _next_key():
    global _key_index
    if len(_GEMINI_KEYS) == 0:
        return ""
    key = _GEMINI_KEYS[_key_index % len(_GEMINI_KEYS)]
    _key_index += 1
    return key

def call_gemini(prompt, retries=1):
    if not _GEMINI_KEYS:
        print("No Gemini API key configured")
        return None

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in GEMINI_MODELS:
        for attempt in range(retries):
            key = _next_key()

            now = time.time()
            last = _last_call.get(key, 0)
            gap = now - last
            if gap < 5:
                time.sleep(5 - gap)

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
                    import re as _re
                    retry_match = _re.search(r"retry.{0,10}?([0-9]+)s", err_msg, _re.IGNORECASE)
                    suggested = int(retry_match.group(1)) if retry_match else None
                    wait = min(suggested + 2, 15) if suggested else (8 + attempt * 5)
                    print(f"Rate limit ({model}), waiting {wait}s then trying next option...")
                    time.sleep(wait)
                    continue
                else:
                    print(f"Gemini error ({model}): {err_msg}")
                    break  

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
- NEVER use generic broad words like 'cricket' or 'apple' alone. Always append contextual clues to prevent homonym errors (e.g., if the news is about the sport of cricket, use 'cricket stadium match' or 'cricket batsman pitch', NEVER just the word 'cricket').
- NEVER use: india flag, indian flag, india map, face, person, woman, man, portrait, girl, boy
- Match the SCENE not the person: crime news → "police investigation crime scene tape",
  court → "supreme court building exterior", cricket → "cricket stadium floodlights night match",
  protest → "protest crowd street demonstration", flood → "flood water submerged village",
  space → "rocket launch fire smoke night sky", economy → "stock market trading screen",
  bollywood → "film camera crew set lights", politics → "parliament building dome exterior"
- NEVER generate images of people or faces under any circumstances

---
AI_IMAGE_PROMPT:
Write a SHORT (max 18 words) Pollinations AI image generation prompt.
STRICT RULES — violations will ruin the post:
- If the story is about the sport of cricket, you MUST explicitly focus on 'stadium', 'pitch', or 'floodlights' and include '--no insect, bug, grasshopper'.
- NO human faces, NO people, NO portraits, NO person, NO woman, NO man
- Focus ONLY on: locations, objects, scenes, symbols, architecture, nature, vehicles
- Must be: photorealistic, cinematic, dramatic lighting, no text, no logos
- Crime/murder → "crime scene police tape dark alley dramatic lighting"
- Court → "grand supreme court building stone pillars cinematic"
- Cricket → "empty cricket stadium floodlights night match dramatic wide angle"
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
    print("Fetching articles...")
    all_articles = []

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

    print("Loading RSS feeds...")
    feeds = random.sample(RSS_FEEDS, min(3, len(RSS_FEEDS)))
    for feed_url, feed_name in feeds:
        all_articles.extend(_fetch_rss(feed_url, feed_name))

    if not all_articles:
        print("All sources failed — no articles available.")
        return []

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
        is_foreign_src = any(s in src for s in NON_INDIA_SKIP)
        has_india_angle = any(k in t for k in INDIA_BOOST_KEYWORDS)
        if is_foreign_src and not has_india_angle:
            continue   
        unique.append(a)
    print(f"Total unique India-relevant articles: {len(unique)}")

    if not unique:
        print("No India-relevant articles — using all unfiltered")
        unique = list(seen)  

    if len(unique) <= count:
        return unique

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


# ── Context safeguard to strip out literal insect traps ───────────────────────
def _clean_image_query(query, article_title):
    """Intercepts homonyms to avoid literal image search mismatches."""
    q = query.lower()
    t = article_title.lower()
    
    # Force Cricket Sport instead of Cricket Insect
    if "cricket" in q or "cricket" in t or "ipl" in t or "t20" in t or "wicket" in t:
        return "cricket sport stadium match stadium pitch"
        
    # Force Apple Tech instead of Apple Fruit
    if "apple" in q or "iphone" in t or "ipad" in t:
        return "apple company technology electronics"
        
    # Force Stock Market instead of Food Market
    if "market" in q and ("economy" in t or "stock" in t or "rupee" in t or "nifty" in t):
        return "stock market trading floor finance graphics"
        
    return query


# ── Image: try 3 real sources then AI fallback ────────────────────────────────
def fetch_image(keyword, ai_prompt, article, save_path="/tmp/img.jpg"):
    candidates = []

    # Clean the search term query based on real context
    clean_keyword = _clean_image_query(keyword, article["title"])
    print(f"Original image query: '{keyword}' -> Cleaned query: '{clean_keyword}'")

    # Unsplash
    try:
        params = {"query": clean_keyword, "per_page": 15,
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
            params = {"query": clean_keyword, "per_page": 15,
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
            params = {"key": PIXABAY_API_KEY, "q": clean_keyword, "image_type": "photo",
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
                if w >= 500 and h >= 500 and 0.5 <= w/h <= 2.0:
                    print(f"Real photo from {src_name} ({w}x{h})")
                    return save_path, src_name
                else:
                    print(f"Rejected image: too small or wrong ratio ({w}x{h})")
        except Exception as e:
            print(f"Photo download error: {e}")

    # AI fallback — Pollinations (free, no key)
    print("Generating AI image via Pollinations...")
    
    # Intercept AI prompts to force avoid insect images dynamically
    t_lower = article["title"].lower()
    clean_ai_prompt = ai_prompt
    if "cricket" in t_lower or "ipl" in t_lower or "t20" in t_lower:
        if "insect" not in clean_ai_prompt.lower() and "bug" not in clean_ai_prompt.lower():
            clean_ai_prompt += " --no insect, bug, grasshopper, close up grass"

    full_prompt = f"{clean_ai_prompt}, high quality, 4k, photorealistic, no text, no watermark"
    encoded = quote(full_prompt)
    seed = random.randint(1, 99999)
    
    for ai_attempt in range(2):   
        try:
            attempt_seed = seed + ai_attempt * 1000
            attempt_url = (f"https://image.pollinations.ai/prompt/{encoded}"
                          f"?width=1080&height=1080&seed={attempt_seed}&model=flux&nologo=true")
            print(f"AI image attempt {ai_attempt+1}/2...")
            r = requests.get(attempt_url, timeout=90, stream=True)
            if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
                ai_path = save_path.replace(".jpg", f"_ai{ai_attempt}.jpg")
                with open(ai_path, "wb") as f:
                    for chunk in r.iter_content(4096):
                        f.write(chunk)
                try:
                    test = Image.open(ai_path)
                    w, h = test.size
                    if w > 100 and h > 100:
                        print(f"AI image generated OK ({w}x{h})")
                        return ai_path, "AI Generated"
                except Exception:
                    pass
        except Exception as e:
            print(f"AI image attempt {ai_attempt+1} error: {e}")
        time.sleep(3)

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

    topic_tag = _get_topic_tag(headline, source_name)
    tag_w = len(topic_tag) * 14 + 20
    draw.rectangle([(1080-tag_w-10, 60), (1070, 88)], fill=(220, 30, 30))
    draw.text((1080-tag_w, 63), topic_tag, font=f["badge"], fill=(255, 255, 255))

    if image_source == "AI Generated":
        draw.rectangle([(28, 522), (210, 548)], fill=(80, 0, 150))
        draw.text((34, 525), "✨ AI ILLUSTRATED", font=f["badge"], fill=(220, 180, 255))

    draw.text((25, 558), f"📌 {source_name.upper()}", font=f["source"], fill=(100, 190, 255))

    y = 608
    for line in textwrap.wrap(headline, width=27)[:3]:
        draw.text((22, y), line, font=f["head"], fill=(255, 255, 255))
        y += 64

    if summary:
        y += 8
        draw.rectangle([(0, y-4), (1080, y-2)], fill=(220, 30, 30))  
        y += 10
        for line in textwrap.wrap(summary, width=42)[:3]:
            draw.text((22, y), line, font=f["small"], fill=(210, 210, 210))
            y += 36

    draw.rectangle([(0, 1022), (1080, 1080)], fill=(12, 12, 12))
    draw.text((22, 1036), "👉 Follow @dailynewsflash_in for daily updates", font=f["small"], fill=(170, 170, 170))
    
    img.save(output_path, "JPEG", quality=95)
    return output_path


def create_carousel_slides(articles_data, output_dir="/tmp/carousel"):
    os.makedirs(output_dir, exist_ok=True)
    f = _load_fonts()
    sz = (1080, 1080)
    paths = []
    
    # Slide 1: Cover Title Slide
    cover = Image.new("RGB", sz, (15, 15, 25))
    cdraw = ImageDraw.Draw(cover)
    cdraw.rectangle([(0, 0), (1080, 130)], fill=(220, 30, 30))
    cdraw.text((40, 40), "⚡ DAILY NEWS FLASH", font=f["large"], fill=(255, 255, 255))
    
    now_str = datetime.now().strftime("%d %B %Y").upper()
    cdraw.text((40, 240), f"🔥 TOP STORIES TODAY • {now_str}", font=f["brand"], fill=(255, 200, 50))
    
    y = 360
    for idx, (art, _, _, _) in enumerate(articles_data[:5]):
        bullet = f"🔴  {art['title']}"
        lines = textwrap.wrap(bullet, width=36)[:2]
        for line in lines:
            cdraw.text((40, y), line, font=f["body"], fill=(240, 240, 240))
            y += 40
        y += 25
        
    cdraw.rectangle([(0, 960), (1080, 1080)], fill=(25, 25, 35))
    cdraw.text((40, 990), "👉 SWIPE LEFT TO READ FULL STORIES", font=f["brand"], fill=(255, 255, 255))
    
    cover_path = os.path.join(output_dir, "slide_0.jpg")
    cover.save(cover_path, "JPEG", quality=95)
    paths.append(cover_path)
    
    # Story Content Slides
    for idx, (art, img_path, img_src, summary) in enumerate(articles_data):
        slide = (Image.open(img_path).convert("RGB").resize(sz, Image.LANCZOS) 
                 if img_path else Image.new("RGB", sz, (20, 20, 35)))
                 
        sov = Image.new("RGBA", sz, (0, 0, 0, 0))
        sod = ImageDraw.Draw(sov)
        for i in range(24):
            sod.rectangle([(0, 480 + i*25), (1080, 480 + (i+1)*25)], fill=(0, 0, 0, min(170 + i*4, 240)))
        sod.rectangle([(0, 0), (1080, 90)], fill=(0, 0, 0, 190))
        sod.rectangle([(0, 480), (12, 1080)], fill=(220, 30, 30, 255))
        slide = Image.alpha_composite(slide.convert("RGBA"), sov).convert("RGB")
        
        draw = ImageDraw.Draw(slide)
        draw.text((30, 25), f"⚡ STORY #{idx+1}", font=f["brand"], fill=(255, 200, 50))
        
        # Slide number bubble top-right
        draw.rectangle([(960, 20), (1050, 75)], fill=(220, 30, 30))
        draw.text((982, 26), f"{idx+1}/5", font=f["badge"], fill=(255, 255, 255))
        
        draw.text((30, 515), f"📌 {art['source']['name'].upper()}", font=f["source"], fill=(100, 190, 255))
        
        y = 565
        for line in textwrap.wrap(art["title"], width=28)[:3]:
            draw.text((30, y), line, font=f["head"], fill=(255, 255, 255))
            y += 62
            
        if summary:
            y += 12
            draw.rectangle([(0, y-4), (1080, y-2)], fill=(220, 30, 30))
            y += 15
            for line in textwrap.wrap(summary, width=42)[:4]:
                draw.text((30, y), line, font=f["body"], fill=(220, 220, 220))
                y += 38
                
        draw.rectangle([(0, 1025), (1080, 1080)], fill=(15, 15, 15))
        draw.text((30, 1038), "👉 Follow @dailynewsflash_in for zero fluff news", font=f["small"], fill=(150, 150, 150))
        
        spath = os.path.join(output_dir, f"slide_{idx+1}.jpg")
        slide.save(spath, "JPEG", quality=95)
        paths.append(spath)
        
    return paths


# ── Facebook / Instagram API Publishing ───────────────────────────────────────
def refresh_fb_token_if_needed():
    fb_app_id = os.environ.get("FB_APP_ID", "").strip()
    fb_app_secret = os.environ.get("FB_APP_SECRET", "").strip()
    if not fb_app_id or not fb_app_secret:
        print("FB_APP_ID/SECRET not configured. Token auto-refresh skipped.")
        return FB_ACCESS_TOKEN
        
    print("Attempting automatic Facebook access token refresh...")
    try:
        url = "https://graph.facebook.com/v18.0/oauth/access_token"
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": fb_app_id,
            "client_secret": fb_app_secret,
            "fb_exchange_token": FB_ACCESS_TOKEN
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if "access_token" in data:
            print("Token successfully refreshed automatically!")
            return data["access_token"]
        print(f"Token refresh payload warning: {data}")
    except Exception as e:
        print(f"Token refresh failed error: {e}")
    return FB_ACCESS_TOKEN


def upload_image_to_ig(image_path, token):
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        
        # Free public image host endpoint fallback pipeline
        r = requests.post("https://api.imgbb.com/1/upload", 
                          data={"key": "6af8ba4c11438a2e128527a29487c53d", "image": b64}, 
                          timeout=30)
        res = r.json()
        if res.get("success"):
            url = res["data"]["url"]
            print(f"Hosted asset live URL link: {url}")
            return url
        print(f"ImgBB platform error: {res}")
    except Exception as e:
        print(f"Hosting structural engine failure: {e}")
    return None


def publish_single_post(img_url, caption, token):
    print("Publishing Single Image Feed Media item post to Instagram...")
    try:
        url = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media"
        p = {"image_url": img_url, "caption": caption, "access_token": token}
        r = requests.post(url, json=p, timeout=20)
        c_id = r.json().get("id")
        if not c_id:
            print(f"Media Container Creation endpoint Error message: {r.text}")
            return False
            
        # Broadcast media item live publish trigger
        purl = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media_publish"
        r = requests.post(purl, json={"creation_id": c_id, "access_token": token}, timeout=20)
        if "id" in r.json():
            print("Successfully published Single Post straight to IG timeline feed!")
            return True
        print(f"Publish stage error outcome logs: {r.text}")
    except Exception as e:
        print(f"Publish post operation crashed: {e}")
    return False


def publish_carousel_post(slides_urls, caption, token):
    print(f"Publishing multi-card Carousel Post consisting of ({len(slides_urls)} slides)...")
    try:
        child_ids = []
        for index, surl in enumerate(slides_urls):
            url = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media"
            p = {"image_url": surl, "is_carousel_item": True, "access_token": token}
            r = requests.post(url, json=p, timeout=20)
            cid = r.json().get("id")
            if cid:
                child_ids.append(cid)
                print(f"Slide container index #{index+1} created ID string: {cid}")
            else:
                print(f"Failed to push slide item container asset index #{index+1}: {r.text}")
                
        if len(child_ids) < 2:
            print("Aborting carousel pipeline — inadequate amount of clean children items generated.")
            return False
            
        # Parent container grouping orchestration hook block
        url = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media"
        p = {
            "media_type": "CAROUSEL",
            "children": child_ids,
            "caption": caption,
            "access_token": token
        }
        r = requests.post(url, json=p, timeout=25)
        parent_id = r.json().get("id")
        if not parent_id:
            print(f"Carousel Parent Root Bundle Creation Error output: {r.text}")
            return False
            
        purl = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media_publish"
        r = requests.post(purl, json={"creation_id": parent_id, "access_token": token}, timeout=25)
        if "id" in r.json():
            print("Successfully published Carousel Stack to Instagram dashboard!")
            return True
        print(f"Final carousel compilation broadcast release trigger error: {r.text}")
    except Exception as e:
        print(f"Carousel generation operation failure logs: {e}")
    return False


# ── Main Orchestrator Loop ───────────────────────────────────────────────────
def main():
    print(f"=== Startup Check: Time: {datetime.now().isoformat()} | Mode: {POST_TYPE.upper()} ===")
    
    active_token = refresh_fb_token_if_needed()
    
    # Process and target target payload volumes count arrays
    fetch_count = 5 if POST_TYPE == "carousel" else 1
    articles = fetch_articles(count=fetch_count)
    if not articles:
        print("Exit early: No valid automated targets scraped this round.")
        sys.exit(0)
        
    compiled_dataset = []
    
    for idx, article in enumerate(articles):
        print(f"\n--- Processing Entry item index #{idx+1} Title string: {article['title']} ---")
        kw, ai_p, summary, caption = analyse_article(article, post_type=POST_TYPE)
        
        path_flag = f"/tmp/processed_asset_{idx}.jpg"
        img_path, img_src = fetch_image(kw, ai_p, article, save_path=path_flag)
        
        if not img_path:
            print("Critical step skipped: Failed fetching/generating visuals background asset layout structure.")
            continue
            
        compiled_dataset.append((article, img_path, img_src, summary, caption))
        
    if not compiled_dataset:
        print("Halt sequence execution workflow: Process queue containing zero completely rendered payloads.")
        sys.exit(0)
        
    # ROUTE A: Run single isolated immediate timeline drop post
    if POST_TYPE != "carousel":
        article, img_path, img_src, summary, caption = compiled_dataset[0]
        final_render = create_single_image(img_path, img_src, article["title"], article["source"]["name"], summary)
        
        live_web_url = upload_image_to_ig(final_render, active_token)
        if live_web_url:
            publish_single_post(live_web_url, caption, active_token)
            
    # ROUTE B: Run dynamic horizontal multi-carousel slide item drop bundle
    else:
        carousel_input_bundle = []
        global_caption_blocks = []
        
        for idx, (article, img_path, img_src, summary, caption) in enumerate(compiled_dataset):
            carousel_input_bundle.append((article, img_path, img_src, summary))
            
            # Formulate structured description block array item entry details strings
            hook = f"Story #{idx+1}: {article['title']}"
            global_caption_blocks.append(f"🚨 {hook}\n{caption}\n")
            
        # Compile global parent wrapper string data properties block
        head_title_bar = f"⚡ DAILY NEWS FLASH BRIEFING • {datetime.now().strftime('%d %B %Y')}\n\n"
        footer_hash_tags = (
            "\n💬 Which story shocked you the most today? Drop your opinions below! 👇\n"
            "👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡\n\n"
            "#india #breakingnews #indianews #dailynewsflash #news #indiatoday #trending #viral"
        )
        unified_caption = head_title_bar + "\n".join(global_caption_blocks) + footer_hash_tags
        
        slide_disk_paths = create_carousel_slides(carousel_input_bundle)
        
        cloud_hosted_links = []
        for idx, path in enumerate(slide_disk_paths):
            h_url = upload_image_to_ig(path, active_token)
            if h_url:
                cloud_hosted_links.append(h_url)
                
        if len(cloud_hosted_links) >= 2:
            publish_carousel_post(cloud_hosted_links, unified_caption, active_token)
        else:
            print("Pipeline aborted: Insufficient number of images successfully hosted online.")
            
    print("\n=== Automation Cycle Complete: Ending Process Cleanly ===")
    sys.exit(0)

if __name__ == "__main__":
    main()
