import os
import requests
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime
import random
import base64
import time
import sys
import re
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

# ── Gemini Options ────────────────────────────────────────────────────────────
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]

_GEMINI_KEYS = [k.strip() for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GEMINI_API_KEY_2", ""),
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
                    print(f"Gemini OK ({model}, {keys_info}, call #{_call_count.get(key,1)} this run)")
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

                err_msg  = data.get("error", {}).get("message", "")
                err_code = data.get("error", {}).get("code", 0)

                if err_code == 429 or "quota" in err_msg.lower() or "rate" in err_msg.lower():
                    print(f"Rate limit ({model}), trying next option...")
                    time.sleep(5)
                    continue
                else:
                    print(f"Gemini error ({model}): {err_msg}")
                    break  

            except Exception as e:
                print(f"Gemini exception ({model}): {e}")
                time.sleep(2)

    print("All Gemini options exhausted — using rule-based fallback")
    return None


# ── Rule-based fallbacks ──────────────────────────────────────────────────────
def _rule_keyword(article):
    t = article["title"].lower()
    d = article.get("description", "").lower()
    combined = t + " " + d
    if any(w in combined for w in ["murder","kill","dead","body","crime","arrest","rape","attack"]):
        return "police investigation crime scene tape"
    if any(w in combined for w in ["cricket","ipl","match","wicket","bat","bowl","rohit","kohli"]):
        return "cricket stadium match floodlights"
    if any(w in combined for w in ["court","verdict","judge","bail","law"]):
        return "supreme court building exterior pillars"
    if any(w in combined for w in ["bollywood","film","movie","actor","actress","cinema"]):
        return "film camera crew set dramatic lights"
    if any(w in combined for w in ["isro","rocket","satellite","space","moon"]):
        return "rocket launch fire smoke night sky"
    if any(w in combined for w in ["flood","earthquake","cyclone","disaster","rain"]):
        return "flood disaster water submerged village"
    if any(w in combined for w in ["protest","strike","rally","agitation","crowd"]):
        return "protest crowd street demonstration"
    if any(w in combined for w in ["war","military","army","border","soldier"]):
        return "military soldiers equipment dynamic sky"
    if any(w in combined for w in ["economy","inflation","rupee","market","stock","gdp"]):
        return "stock market trading screen finance"
    return "india city skyline dramatic dusk"


def _rule_ai_prompt(article):
    t = article["title"].lower()
    d = article.get("description", "").lower()
    combined = t + " " + d
    if any(w in combined for w in ["murder","kill","crime","arrest"]):
        return "dark crime scene yellow police tape rain dramatic cinematic no people"
    if any(w in combined for w in ["cricket","ipl","match"]):
        return "empty cricket stadium at night floodlights dramatic wide angle cinematic"
    return "dramatic india city skyline dusk golden hour cinematic wide angle"


def _rule_summary(article):
    desc = article.get("description", "").strip()
    if desc and len(desc) > 30:
        words = desc.split()
        return " ".join(words[:30]) + "..."
    return article["title"]


def _rule_caption(article):
    title = article["title"]
    desc  = article.get("description", "")
    src   = article["source"]["name"]
    return (f"⚡ {title}\n\n"
            f"{desc}\n\n"
            f"📌 Source: {src}\n\n"
            f"💬 What do YOU think? Comment below 👇\n"
            f"👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡\n\n"
            f"#india #breakingnews #indianews #dailynewsflash #news #trending #viral")


# ── Combined Parser ───────────────────────────────────────────────────────────
def analyse_article(article, post_type="single"):
    title = article["title"]
    desc  = article.get("description", "")[:300]
    src   = article["source"]["name"]
    topic = article.get("_topic", "general")

    if post_type == "carousel":
        caption_instruction = f"Write 2-3 punchy sentences summarising this story for a carousel slide. End with: 📌 {src}"
    else:
        caption_instruction = f"Create a full single-post viral Instagram caption with hooks, breakdown, slang, source: {src}, engagement call, and 25 hashtags."

    prompt = f"""You are an expert Indian news Instagram editor.
Analyse this news article and return EXACTLY four sections labelled as shown.

Article title: {title}
Description: {desc}
Source: {src}
Topic category: {topic}

Format:
PHOTO_KEYWORD: <3-5 words stock search phrase matching the setting, NO people, NO flags>
AI_IMAGE_PROMPT: <short cinematic photorealistic scene description prompt, max 18 words>
SUMMARY: <2 plain factual summary sentences for image card text overlay>
CAPTION:
<instagram caption body content>"""

    result = call_gemini(prompt)
    if not result:
        return _rule_keyword(article), _rule_ai_prompt(article), _rule_summary(article), _rule_caption(article)

    try:
        keyword, ai_prompt, summary, caption = None, None, None, None
        lines = result.split("\n")
        caption_lines = []
        in_caption = False
        for line in lines:
            if line.startswith("PHOTO_KEYWORD:"):
                keyword = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("AI_IMAGE_PROMPT:"):
                ai_prompt = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("SUMMARY:"):
                summary = line.split(":", 1)[1].strip()
            elif line.startswith("CAPTION:"):
                in_caption = True
            elif in_caption:
                caption_lines.append(line)
        return (keyword or "breaking news press", ai_prompt or "dark dramatic scene cinematic", summary or "", "\n".join(caption_lines).strip())
    except Exception:
        return _rule_keyword(article), _rule_ai_prompt(article), _rule_summary(article), _rule_caption(article)


# ── RSS Reader ────────────────────────────────────────────────────────────────
def _fetch_rss(url, source_name):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": "Mozilla/5.0 NewsBot/1.0"})
        if r.status_code != 200: return []
        articles = []
        items = r.text.split("<item>")[1:]
        for item in items[:15]:
            def tag(t):
                s = item.find(f"<{t}>")
                e = item.find(f"</{t}>")
                if s == -1 or e == -1: return ""
                return item[s+len(t)+2:e].strip().replace("<![CDATA[","").replace("]]>","").strip()
            title = tag("title")
            if title and len(title) > 10:
                articles.append({"title": title, "description": tag("description")[:300], "url": tag("link"), "source": {"name": source_name}, "_topic": "general"})
        return articles
    except Exception:
        return []


# ── Fetching & Filtering ──────────────────────────────────────────────────────
def fetch_articles(count=5):
    all_articles = []
    try:
        r = requests.get("https://gnews.io/api/v4/top-headlines", params={"token": GNEWS_API_KEY, "lang": "en", "country": "in", "max": 10}, timeout=10)
        for a in r.json().get("articles", []):
            a["_topic"] = "top-headlines"
            all_articles.append(a)
    except Exception as e:
        print(f"GNews error: {e}")

    for feed_url, feed_name in random.sample(RSS_FEEDS if 'RSS_FEEDS' in globals() else [("https://feeds.feedburner.com/ndtvnews-top-stories", "NDTV"), ("https://timesofindia.indiatimes.com/rssfeedstopstories.cms","Times of India")], 2):
        all_articles.extend(_fetch_rss(feed_url, feed_name))

    INDIA_BOOST = ["india", "indian", "modi", "delhi", "mumbai", "bjp", "congress", "cricket", "ipl", "sc", "supreme court", "bengaluru"]
    seen, unique = set(), []
    for a in all_articles:
        t = a["title"].strip().lower()
        if t in seen or len(t) < 10: continue
        seen.add(t)
        unique.append(a)

    unique.sort(key=lambda x: sum(3 if k in x["title"].lower() else 0 for k in INDIA_BOOST), reverse=True)
    return unique[:count]


# ── Fixed Keyword Safeguard ───────────────────────────────────────────────────
def _clean_image_query(query, article_title):
    """Intercepts homonyms with absolute word boundaries to prevent false match triggers."""
    q = query.lower()
    t = article_title.lower()
    
    # Exact word boundary matching regex structures
    if re.search(r'\b(cricket|ipl|t20|wicket|batsman|bowler|dhoni|kohli|rohit)\b', q) or re.search(r'\b(cricket|ipl|t20|wicket|batsman|bowler|dhoni|kohli|rohit)\b', t):
        return "cricket sport stadium match pitch"
        
    if re.search(r'\b(apple|iphone|ipad|macbook|steve jobs)\b', q) or re.search(r'\b(apple|iphone|ipad|macbook)\b', t):
        return "apple company technology mobile phone electronics"
        
    return query


# ── Image Retrieval Pipeline ──────────────────────────────────────────────────
def fetch_image(keyword, ai_prompt, article, save_path="/tmp/img.jpg"):
    clean_keyword = _clean_image_query(keyword, article["title"])
    print(f"Original image query: '{keyword}' -> Cleaned query: '{clean_keyword}'")

    # Unsplash search loop
    try:
        params = {"query": clean_keyword, "per_page": 10, "client_id": UNSPLASH_ACCESS_KEY}
        r = requests.get("https://api.unsplash.com/search/photos", params=params, timeout=10)
        res = r.json().get("results", [])
        if res:
            p = random.choice(res)
            r_img = requests.get(p["urls"]["regular"], stream=True, timeout=15)
            if r_img.status_code == 200:
                with open(save_path, "wb") as f:
                    for chunk in r_img.iter_content(4096): f.write(chunk)
                return save_path, "Unsplash"
    except Exception as e:
        print(f"Photo download error: {e}")

    # Fallback to AI Generation
    print("Generating fallback via Pollinations AI Engine...")
    try:
        clean_ai = ai_prompt
        if re.search(r'\b(cricket|ipl|t20)\b', article["title"].lower()):
            clean_ai += " --no insect, bug, grasshopper"
        encoded = quote(f"{clean_ai}, photo, realistic, cinematic")
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&model=flux&nologo=true"
        r = requests.get(url, timeout=45, stream=True)
        if r.status_code == 200:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(4096): f.write(chunk)
            return save_path, "AI Generated"
    except Exception as e:
        print(f"AI generation failed: {e}")

    return None, "none"


# ── Graphics Generation ───────────────────────────────────────────────────────
def _load_fonts():
    base = "/usr/share/fonts/truetype/dejavu/"
    try:
        return {
            "brand":  ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 36),
            "source": ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 26),
            "head":   ImageFont.truetype(base + "DejaVuSans-Bold.ttf", 52),
            "small":  ImageFont.truetype(base + "DejaVuSans.ttf", 28),
            "badge":  ImageFont.truetype(base + "DejaVuSans.ttf", 22),
        }
    except:
        d = ImageFont.load_default()
        return {k: d for k in ["brand", "source", "head", "small", "badge"]}

def _get_topic_tag(headline):
    h = headline.lower()
    if any(w in h for w in ["murder","crime","rape","arrest"]): return "CRIME"
    if any(w in h for w in ["cricket","ipl","match"]): return "CRICKET"
    if any(w in h for w in ["court","verdict","judge","sc"]): return "JUSTICE"
    return "INDIA"

def create_single_image(image_path, image_source, headline, source_name, summary="", output_path="/tmp/final_post.jpg"):
    sz = (1080, 1080)
    img = Image.open(image_path).convert("RGB").resize(sz, Image.LANCZOS) if image_path else Image.new("RGB", sz, (20, 20, 40))
    ov = Image.new("RGBA", sz, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for i in range(22):
        od.rectangle([(0, 520 + i*26), (1080, 520 + (i+1)*26)], fill=(0, 0, 0, min(170 + i*4, 235)))
    od.rectangle([(0, 0), (1080, 98)], fill=(0, 0, 0, 185))
    od.rectangle([(0, 520), (9, 1080)], fill=(220, 30, 30, 255))
    img = Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
    
    draw = ImageDraw.Draw(img)
    f = _load_fonts()
    draw.text((28, 26), "⚡ DAILY NEWS FLASH", font=f["brand"], fill=(255, 200, 50))
    draw.text((920, 26), "IN", font=f["brand"], fill=(220, 30, 30))

    topic_tag = _get_topic_tag(headline)
    tag_w = len(topic_tag) * 14 + 20
    draw.rectangle([(1080-tag_w-10, 60), (1070, 88)], fill=(220, 30, 30))
    draw.text((1080-tag_w, 63), topic_tag, font=f["badge"], fill=(255, 255, 255))

    draw.text((25, 558), f"📌 {source_name.upper()}", font=f["source"], fill=(100, 190, 255))

    y = 608
    for line in textwrap.wrap(headline, width=27)[:3]:
        draw.text((22, y), line, font=f["head"], fill=(255, 255, 255))
        y += 64

    if summary:
        y += 15
        for line in textwrap.wrap(summary, width=42)[:2]:
            draw.text((22, y), line, font=f["small"], fill=(210, 210, 210))
            y += 36

    img.save(output_path, "JPEG", quality=95)
    return output_path


# ── Meta Publishing Endpoint ──────────────────────────────────────────────────
def upload_image_to_ig(image_path, token):
    print("Uploading target media asset card to ImgBB CDN hosting infrastructure...")
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        r = requests.post("https://api.imgbb.com/1/upload", data={"key": "6af8ba4c11438a2e128527a29487c53d", "image": b64}, timeout=30)
        res = r.json()
        if res.get("success"):
            url = res["data"]["url"]
            print(f"Asset hosted live on CDN URL: {url}")
            return url
        print(f"ImgBB platform error log: {res}")
    except Exception as e:
        print(f"Hosting asset pipeline error: {e}")
    return None


def publish_single_post(img_url, caption, token):
    print(f"Calling Meta Graph API to build standard single image container media item...")
    try:
        url = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media"
        p = {"image_url": img_url, "caption": caption, "access_token": token}
        r = requests.post(url, json=p, timeout=20)
        res_data = r.json()
        print(f"Meta Media Container raw response: {res_data}")
        
        c_id = res_data.get("id")
        if not c_id:
            print(f"CRITICAL: Failed to create Meta Container. Response details: {res_data}")
            return False
            
        print(f"Container successfully verified. ID: {c_id}. Broadcasting publish execution sequence...")
        purl = f"https://graph.facebook.com/v18.0/{IG_ACCOUNT_ID}/media_publish"
        r = requests.post(purl, json={"creation_id": c_id, "access_token": token}, timeout=20)
        pub_res = r.json()
        print(f"Meta Publish raw response: {pub_res}")
        
        if "id" in pub_res:
            print("SUCCESS: Post is officially live on your Instagram timeline feed!")
            return True
    except Exception as e:
        print(f"Meta execution pipeline error encountered: {e}")
    return False


# ── Main Function ─────────────────────────────────────────────────────────────
def main():
    print(f"=== Startup Check: Time: {datetime.now().isoformat()} ===")
    articles = fetch_articles(count=1)
    if not articles:
        print("Scraper returned zero items. Stopping script execution.")
        sys.exit(0)
        
    article = articles[0]
    print(f"Targeting Article: {article['title']}")
    
    kw, ai_p, summary, caption = analyse_article(article, post_type="single")
    img_path, img_src = fetch_image(kw, ai_p, article)
    
    if not img_path:
        print("Visual engine returned empty tracking asset path array values. Aborting post.")
        sys.exit(0)
        
    final_render = create_single_image(img_path, img_src, article["title"], article["source"]["name"], summary)
    
    live_web_url = upload_image_to_ig(final_render, FB_ACCESS_TOKEN)
    if live_web_url:
        success = publish_single_post(live_web_url, caption, FB_ACCESS_TOKEN)
        if not success:
            print("Workflow completed generating local data frames, but Meta returned a delivery rejection code.")
    else:
        print("Image upload failed. Post process aborted.")

if __name__ == "__main__":
    main()
