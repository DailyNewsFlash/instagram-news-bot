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
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"]
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY     = os.environ.get("PIXABAY_API_KEY", "")
POST_TYPE           = os.environ.get("POST_TYPE", "single")

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

# ── Gemini: smart rate-limit handling with model fallbacks ────────────────────
# Free tier limits: 15 req/min on 2.0-flash, 15 req/min on 1.5-flash
# We add delays between calls to stay well under the limit
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]
_last_gemini_call = 0   # track time of last call globally

def call_gemini(prompt, retries=2):
    global _last_gemini_call
    # Always wait at least 5 seconds between Gemini calls to avoid rate limits
    elapsed = time.time() - _last_gemini_call
    if elapsed < 5:
        time.sleep(5 - elapsed)

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for model in GEMINI_MODELS:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent?key={GEMINI_API_KEY}")
        for attempt in range(retries):
            try:
                _last_gemini_call = time.time()
                resp = requests.post(url, json=payload, timeout=30)
                data = resp.json()
                if "candidates" in data:
                    print(f"Gemini OK ({model})")
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                err_msg = data.get("error", {}).get("message", "")
                err_code = data.get("error", {}).get("code", 0)
                if err_code == 429 or "quota" in err_msg.lower() or "rate" in err_msg.lower():
                    wait = 35 + (attempt * 30)
                    print(f"Rate limit on {model}, waiting {wait}s...")
                    time.sleep(wait)
                    continue    # retry same model after wait
                else:
                    print(f"Gemini {model} error: {err_msg}")
                    break       # non-rate error → try next model
            except Exception as e:
                print(f"Gemini {model} exception: {e}")
                time.sleep(5)

    print("All Gemini models failed — using rule-based fallback")
    return None


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
Analyse this news article and return EXACTLY three sections labelled as shown.

Article title: {title}
Description: {desc}
Source: {src}
Topic category: {topic}

---
PHOTO_KEYWORD:
Give ONE specific 3-5 word stock photo search term that visually matches this story.
NEVER use: india flag, indian flag, india map, indian crowd generic.
Be literal: "cricket stadium night lights", "supreme court building pillars",
"protest crowd city street", "rocket launch fire smoke", "flooded village rescue boat".

---
AI_IMAGE_PROMPT:
Write a SHORT (max 18 words) Pollinations AI image generation prompt.
Must be: photorealistic, cinematic, dramatic lighting, no text, no real faces.
Example: "rocket launching at night fire smoke dramatic sky photorealistic 4k"

---
{caption_instruction}

Respond in EXACTLY this format — nothing else before or after:
PHOTO_KEYWORD: <keyword here>
AI_IMAGE_PROMPT: <prompt here>
CAPTION:
<full caption here>"""

    result = call_gemini(prompt)
    if not result:
        return None, None, None

    try:
        keyword, ai_prompt, caption = None, None, None
        lines = result.split("\n")
        caption_lines = []
        in_caption = False
        for line in lines:
            if line.startswith("PHOTO_KEYWORD:"):
                keyword = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("AI_IMAGE_PROMPT:"):
                ai_prompt = line.split(":", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("CAPTION:"):
                in_caption = True
            elif in_caption:
                caption_lines.append(line)
        caption = "\n".join(caption_lines).strip()
        return keyword or "breaking news press", ai_prompt or "dramatic news event cinematic", caption or ""
    except Exception as e:
        print(f"Parse failed: {e}")
        return "breaking news press", "dramatic news cinematic", ""


# ── Pick best articles (single Gemini call) ───────────────────────────────────
def fetch_articles(count=5):
    print(f"Fetching articles...")
    all_articles = []
    selected_topics = random.sample(TRENDING_TOPICS, min(7, len(TRENDING_TOPICS)))
    for topic in selected_topics:
        params = {
            "token": GNEWS_API_KEY, "lang": "en", "country": "in",
            "max": 4, "q": topic, "sortby": "publishedAt"
        }
        try:
            r = requests.get("https://gnews.io/api/v4/search", params=params, timeout=10)
            arts = r.json().get("articles", [])
            for a in arts:
                a["_topic"] = topic
            all_articles.extend(arts)
        except Exception as e:
            print(f"Fetch '{topic}' error: {e}")

    if not all_articles:
        try:
            r = requests.get("https://gnews.io/api/v4/top-headlines",
                             params={"token": GNEWS_API_KEY, "lang": "en",
                                     "country": "in", "max": 10}, timeout=10)
            all_articles = r.json().get("articles", [])
        except Exception as e:
            print(f"Headline fallback error: {e}")

    if not all_articles:
        return []

    seen, unique = set(), []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)
    print(f"Found {len(unique)} unique articles")

    # Pick best via ONE Gemini call
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(unique[:25])])
    prompt = (f"You are a viral Indian Instagram news editor.\n"
              f"Pick TOP {count} articles for max engagement from young Indians.\n"
              f"Prioritise: scandals, Supreme Court, cricket, ISRO, crime, protest, viral.\n"
              f"Avoid: celebrity meetups, PR fluff, dry government reports.\n\n"
              f"{titles}\n\n"
              f"Reply with ONLY comma-separated numbers. Example: 3,7,1,12,5")
    answer = call_gemini(prompt)
    if answer:
        try:
            nums = [int(n.strip()) for n in answer.split(",") if n.strip().isdigit()]
            nums = [n for n in nums if 1 <= n <= len(unique)][:count]
            if nums:
                print(f"Picked articles: {nums}")
                return [unique[n-1] for n in nums]
        except Exception as e:
            print(f"Pick parse error: {e}")
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
                if w >= 400 and h >= 400:
                    print(f"Real photo from {src_name} ({w}x{h})")
                    return save_path, src_name
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


def create_single_image(image_path, image_source, headline, source_name,
                        output_path="/tmp/final_post.jpg"):
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
    if image_source == "AI Generated":
        draw.rectangle([(28, 522), (200, 548)], fill=(80, 0, 150))
        draw.text((34, 525), "✨ AI ILLUSTRATED", font=f["badge"], fill=(220, 180, 255))
    draw.text((25, 565), f"📌 {source_name.upper()}", font=f["source"], fill=(100, 190, 255))
    y = 620
    for line in textwrap.wrap(headline, width=27)[:4]:
        draw.text((22, y), line, font=f["head"], fill=(255, 255, 255))
        y += 68
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
def refresh_fb_token():
    """
    Exchange the current token for a new 60-day long-lived token.
    Requires FB_APP_ID and FB_APP_SECRET secrets in GitHub.
    If those secrets are not set, skips silently.
    """
    app_id     = os.environ.get("FB_APP_ID", "")
    app_secret = os.environ.get("FB_APP_SECRET", "")
    if not app_id or not app_secret:
        print("FB_APP_ID / FB_APP_SECRET not set — skipping token refresh")
        return FB_ACCESS_TOKEN
    try:
        url = "https://graph.facebook.com/v25.0/oauth/access_token"
        params = {
            "grant_type":        "fb_exchange_token",
            "client_id":         app_id,
            "client_secret":     app_secret,
            "fb_exchange_token": FB_ACCESS_TOKEN,
        }
        r = requests.get(url, params=params, timeout=15)
        d = r.json()
        new_token = d.get("access_token", "")
        if new_token:
            print(f"Token refreshed OK (expires_in: {d.get('expires_in','?')}s)")
            return new_token
        print(f"Token refresh failed: {d}")
    except Exception as e:
        print(f"Token refresh error: {e}")
    return FB_ACCESS_TOKEN


# ── Post to Instagram ─────────────────────────────────────────────────────────
def post_single(image_url, caption, token):
    print("Posting single...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": token},
        timeout=30)
    cid = r.json().get("id")
    if not cid:
        raise Exception(f"Container failed: {r.json()}")
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
            keyword, ai_prompt, slide_cap = analyse_article(article, "carousel")
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
        keyword, ai_prompt, caption = analyse_article(article, "single")
        img_path, img_src = fetch_image(keyword, ai_prompt, article)
        final = create_single_image(img_path, img_src, article["title"],
                                    article["source"]["name"])
        img_url = upload_to_imgur(final)
        if not img_url:
            print("Upload failed.")
            sys.exit(1)
        post_single(img_url, caption, token)

    print(f"\n=== ✅ Done at {datetime.now()} ===\n")


if __name__ == "__main__":
    main()
