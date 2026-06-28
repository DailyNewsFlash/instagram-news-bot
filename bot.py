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

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"]
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY", "")
PIXABAY_API_KEY     = os.environ.get("PIXABAY_API_KEY", "")
POST_TYPE           = os.environ.get("POST_TYPE", "single")

# ── High-engagement, controversy-driving topics ───────────────────────────────
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
    "India rape crime justice",
    "India farmer protest",
    "India army military",
    "ISRO space India",
    "India startup unicorn",
    "India flood disaster",
    "world war conflict",
    "India education system",
]

# ── Gemini API call with retry ────────────────────────────────────────────────
def call_gemini(prompt, retries=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=25)
            data = response.json()
            if "candidates" in data:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"Gemini attempt {attempt+1} failed: {data.get('error', {}).get('message', data)}")
        except Exception as e:
            print(f"Gemini attempt {attempt+1} error: {e}")
        time.sleep(3)
    return None

# ── Fetch articles ─────────────────────────────────────────────────────────────
def fetch_articles(count=5):
    print(f"Fetching articles for {count} posts...")
    all_articles = []
    selected_topics = random.sample(TRENDING_TOPICS, min(8, len(TRENDING_TOPICS)))
    for topic in selected_topics:
        url = "https://gnews.io/api/v4/search"
        params = {
            "token": GNEWS_API_KEY,
            "lang": "en",
            "country": "in",
            "max": 5,
            "q": topic,
            "sortby": "publishedAt"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            articles = data.get("articles", [])
            for a in articles:
                a["_topic"] = topic
            all_articles.extend(articles)
        except Exception as e:
            print(f"Error fetching '{topic}': {e}")

    if not all_articles:
        print("Falling back to top headlines...")
        url = "https://gnews.io/api/v4/top-headlines"
        params = {"token": GNEWS_API_KEY, "lang": "en", "country": "in", "max": 10}
        try:
            response = requests.get(url, params=params, timeout=10)
            all_articles = response.json().get("articles", [])
        except Exception as e:
            print(f"Fallback failed: {e}")

    if not all_articles:
        return []

    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    print(f"Total unique articles: {len(unique)}")
    return pick_top_articles(unique, count)

# ── Gemini picks most controversial/engaging articles ─────────────────────────
def pick_top_articles(articles, count=5):
    print(f"Asking Gemini to pick top {count} high-engagement articles...")
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:25])])
    prompt = f"""You are a viral social media editor for an Indian news Instagram page targeting 18-35 year olds.

Here are news article titles:
{titles}

Pick the TOP {count} articles that will generate the MOST engagement — likes, comments, shares, arguments, reactions.

Prioritise articles about:
- Controversies and scandals (government, celebrities, corporate)
- Shocking crimes, injustice, corruption exposed
- Things that make people ANGRY or EMOTIONAL
- Major decisions that affect common Indians (prices, jobs, taxes, laws)
- India vs Pakistan, cricket matches, major sports results
- Viral moments people are already talking about
- ISRO, major tech or science breakthroughs
- Natural disasters, major accidents

AVOID:
- Celebrity meetups, photo ops, PR fluff (like "X meets Y at event")
- Minor local municipal news
- Repetitive political speeches without substance
- Old recycled stories

Reply with ONLY the numbers separated by commas. Example: 3,7,1,12,5
Nothing else."""

    answer = call_gemini(prompt)
    if answer:
        try:
            numbers = [int(n.strip()) for n in answer.split(",") if n.strip().isdigit()]
            numbers = [n for n in numbers if 1 <= n <= len(articles)][:count]
            if len(numbers) >= 1:
                print(f"Gemini picked: {numbers}")
                return [articles[n-1] for n in numbers]
        except Exception as e:
            print(f"Gemini parse failed: {e}")
    print("Using fallback articles")
    return articles[:count]

# ── Get photo search keyword ───────────────────────────────────────────────────
def get_image_keyword(article):
    prompt = f"""News headline: "{article['title']}"
News description: "{article.get('description', '')[:200]}"

Give ONE highly specific photo search keyword (3-5 words) for a stock photo that matches this news VISUALLY.

CRITICAL RULES:
- Match the actual visual scene, not the abstract topic
- Good examples:
  * "India inflation food prices" → "indian market vegetable stall"
  * "Supreme Court verdict" → "supreme court building pillars"
  * "IPL cricket match" → "cricket bat stadium night lights"
  * "India Pakistan border" → "military soldiers border patrol"
  * "ISRO rocket launch" → "rocket launch fire exhaust"
  * "Farmer protest Delhi" → "protest crowd demonstration street"
  * "Bollywood actress controversy" → "film set camera crew lights"
  * "India flood disaster" → "flood water submerged village"
  * "Startup funding" → "startup office whiteboard meeting"
  * "Parliament session" → "parliament building dome architecture"
- NEVER return: india flag, indian flag, india map, indian people generic, crowd generic
- Be specific to the exact event in the headline

Return ONLY the 3-5 word keyword. Nothing else."""

    keyword = call_gemini(prompt)
    if keyword:
        keyword = keyword.strip().strip('"').strip("'")
        blocked = ["india flag", "indian flag", "india map", "indian crowd",
                   "people of india", "indian people", "india news", "breaking news generic"]
        if any(b in keyword.lower() for b in blocked):
            return _topic_fallback(article)
        print(f"Photo keyword: '{keyword}'")
        return keyword
    return _topic_fallback(article)

# ── Get AI image generation prompt ────────────────────────────────────────────
def get_ai_image_prompt(article):
    prompt = f"""News headline: "{article['title']}"
News description: "{article.get('description', '')[:200]}"

Write a SHORT image generation prompt (max 20 words) for an AI to create a photorealistic, dramatic news-style image for this story.

Rules:
- Photorealistic, cinematic, dramatic lighting
- No text, no words, no logos in the image
- No real people's faces or identifiable politicians
- Focus on the SCENE or SYMBOL of the story
- Examples:
  * Cricket news → "dramatic cricket stadium at night, floodlights, packed crowd, photorealistic"
  * Court verdict → "grand supreme court building exterior, dramatic sky, cinematic lighting"
  * Protest news → "large peaceful protest crowd, signs, golden hour lighting, aerial view"
  * Flood disaster → "flooded village road, rescue boat, dramatic storm clouds, photorealistic"
  * Economic news → "indian market stalls, colorful vegetables, busy street, golden hour"
  * Space/ISRO → "rocket launching at night, fire and smoke, dramatic sky, photorealistic"
  * Political news → "empty parliament building interior, dramatic lighting, wide angle"

Return ONLY the image prompt. Nothing else."""

    ai_prompt = call_gemini(prompt)
    if ai_prompt:
        ai_prompt = ai_prompt.strip().strip('"').strip("'")
        print(f"AI image prompt: '{ai_prompt}'")
        return ai_prompt
    # Fallback prompt
    return _ai_prompt_fallback(article)

def _ai_prompt_fallback(article):
    title = article["title"].lower()
    if "cricket" in title or "ipl" in title: return "cricket stadium night floodlights crowd dramatic cinematic"
    if "court" in title or "verdict" in title: return "grand courthouse building dramatic sky cinematic"
    if "protest" in title: return "peaceful protest crowd city street aerial view golden hour"
    if "flood" in title: return "flooded village rescue boat storm clouds dramatic photorealistic"
    if "rocket" in title or "isro" in title: return "rocket launch night fire smoke dramatic sky"
    if "war" in title or "military" in title: return "military equipment dramatic sky cinematic wide angle"
    if "economy" in title or "inflation" in title: return "busy indian market colorful stalls golden hour photorealistic"
    if "bollywood" in title: return "film set camera lights dramatic cinema atmosphere"
    return "dramatic news studio broadcast lights cinematic dark background"

def _topic_fallback(article):
    title = article["title"].lower()
    if "cricket" in title or "ipl" in title: return "cricket stadium match crowd"
    if "football" in title or "fifa" in title: return "football stadium match crowd"
    if "bollywood" in title or "actor" in title: return "cinema stage lights performance"
    if "court" in title or "verdict" in title: return "court justice law building"
    if "protest" in title or "strike" in title: return "protest crowd demonstration street"
    if "flood" in title or "disaster" in title: return "flood disaster rescue emergency"
    if "rocket" in title or "isro" in title: return "rocket launch space fire"
    if "scam" in title or "fraud" in title: return "handcuffs police investigation"
    if "war" in title or "military" in title: return "military soldiers equipment"
    if "economy" in title or "inflation" in title: return "stock market economy finance"
    return "news press conference microphone"

# ── Generate AI image via Pollinations (free, no key needed) ─────────────────
def generate_ai_image(article, save_path):
    """Generate a photorealistic AI image using Pollinations.AI — completely free."""
    ai_prompt = get_ai_image_prompt(article)
    # Add quality boosters
    full_prompt = f"{ai_prompt}, high quality, 4k, photorealistic, professional photography, no text, no watermark"
    encoded = quote(full_prompt)
    # Pollinations.AI — free, no key, copyright-free outputs
    # Using seed for variety, 1080x1080 square format
    seed = random.randint(1, 99999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1080&seed={seed}&model=flux&nologo=true"
    print(f"Generating AI image from Pollinations...")
    try:
        r = requests.get(url, timeout=60, stream=True)
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(1024):
                    f.write(chunk)
            # Verify it's a valid image
            img = Image.open(save_path)
            img.verify()
            print(f"✅ AI image generated successfully ({img.format if hasattr(img, 'format') else 'OK'})")
            return save_path
        else:
            print(f"Pollinations failed: status {r.status_code}")
            return None
    except Exception as e:
        print(f"AI image generation error: {e}")
        return None

# ── Fetch best image from multiple sources then AI fallback ──────────────────
def fetch_image(article, save_path="/tmp/news_image.jpg"):
    """
    Priority order:
    1. Unsplash (real photos, high quality)
    2. Pexels   (real photos, very high quality)
    3. Pixabay  (real photos, good variety)
    4. Pollinations AI (generated, topic-specific, copyright-free)
    """
    keyword = get_image_keyword(article)
    candidates = []

    # ── Source 1: Unsplash ────────────────────────────────────────────────────
    try:
        url = "https://api.unsplash.com/search/photos"
        params = {
            "query": keyword, "per_page": 15,
            "page": random.randint(1, 3),
            "orientation": "squarish",
            "client_id": UNSPLASH_ACCESS_KEY
        }
        r = requests.get(url, params=params, timeout=10)
        results = r.json().get("results", [])
        if results:
            photo = random.choice(results[:10])
            candidates.append(("unsplash", photo["urls"]["regular"], photo.get("likes", 0)))
            print(f"Unsplash: {len(results)} results for '{keyword}'")
        else:
            print(f"Unsplash: no results for '{keyword}'")
    except Exception as e:
        print(f"Unsplash error: {e}")

    # ── Source 2: Pexels ──────────────────────────────────────────────────────
    if PEXELS_API_KEY:
        try:
            url = "https://api.pexels.com/v1/search"
            params = {"query": keyword, "per_page": 15,
                      "page": random.randint(1, 3), "orientation": "square"}
            r = requests.get(url, headers={"Authorization": PEXELS_API_KEY},
                             params=params, timeout=10)
            photos = r.json().get("photos", [])
            if photos:
                photo = random.choice(photos[:10])
                candidates.append(("pexels", photo["src"]["large2x"], 1000))
                print(f"Pexels: {len(photos)} results for '{keyword}'")
            else:
                print(f"Pexels: no results for '{keyword}'")
        except Exception as e:
            print(f"Pexels error: {e}")

    # ── Source 3: Pixabay ─────────────────────────────────────────────────────
    if PIXABAY_API_KEY:
        try:
            url = "https://pixabay.com/api/"
            params = {
                "key": PIXABAY_API_KEY, "q": keyword,
                "image_type": "photo", "per_page": 15,
                "page": random.randint(1, 3),
                "orientation": "horizontal", "safesearch": "true",
                "min_width": 800
            }
            r = requests.get(url, params=params, timeout=10)
            hits = r.json().get("hits", [])
            if hits:
                photo = random.choice(hits[:10])
                candidates.append(("pixabay", photo["webformatURL"], photo.get("likes", 0)))
                print(f"Pixabay: {len(hits)} results for '{keyword}'")
            else:
                print(f"Pixabay: no results for '{keyword}'")
        except Exception as e:
            print(f"Pixabay error: {e}")

    # ── Try to download a real photo ──────────────────────────────────────────
    if candidates:
        # Prefer Pexels for quality, otherwise pick highest likes
        pexels = [c for c in candidates if c[0] == "pexels"]
        chosen = pexels[0] if pexels else max(candidates, key=lambda x: x[2])
        source_name, img_url, _ = chosen
        try:
            print(f"Downloading from {source_name}...")
            r = requests.get(img_url, stream=True, timeout=20)
            if r.status_code == 200:
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(4096):
                        f.write(chunk)
                # Quick sanity check on the image
                test_img = Image.open(save_path)
                w, h = test_img.size
                if w >= 400 and h >= 400:
                    print(f"✅ Real photo from {source_name} ({w}x{h})")
                    return save_path, source_name
                else:
                    print(f"Image too small ({w}x{h}), trying AI generation...")
        except Exception as e:
            print(f"Download failed: {e}")

    # ── Source 4: AI Generation (Pollinations) — always works ────────────────
    print("No suitable real photo found — generating AI image...")
    ai_path = save_path.replace(".jpg", "_ai.jpg")
    result = generate_ai_image(article, ai_path)
    if result:
        return result, "AI Generated"

    print("All image sources failed — using plain background")
    return None, "none"

# ── Design single post image ───────────────────────────────────────────────────
def create_single_image(image_path, image_source, headline, source_name,
                        output_path="/tmp/final_post.jpg"):
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB").resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(20, 20, 40))

    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for i in range(20):
        alpha = int(175 + i * 3)
        od.rectangle([(0, 530 + i*28), (1080, 530 + (i+1)*28)],
                     fill=(0, 0, 0, min(alpha, 235)))
    od.rectangle([(0, 0), (1080, 98)], fill=(0, 0, 0, 185))
    od.rectangle([(0, 530), (9, 1080)], fill=(220, 30, 30, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_headline = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
        font_small    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_brand    = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_source   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
        font_ai_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except:
        font_headline = font_small = font_brand = font_source = font_ai_badge = ImageFont.load_default()

    draw.text((28, 26), "⚡ DAILY NEWS FLASH", font=font_brand, fill=(255, 200, 50))
    draw.text((920, 26), "IN", font=font_brand, fill=(220, 30, 30))

    # AI badge if image was generated
    if image_source == "AI Generated":
        draw.rectangle([(28, 530), (195, 558)], fill=(80, 0, 150))
        draw.text((35, 533), "✨ AI ILLUSTRATED", font=font_ai_badge, fill=(220, 180, 255))

    draw.text((25, 570), f"📌 {source_name.upper()}", font=font_source, fill=(100, 190, 255))

    wrapped = textwrap.wrap(headline, width=27)[:4]
    for i, line in enumerate(wrapped):
        draw.text((22, 625 + i * 68), line, font=font_headline, fill=(255, 255, 255))

    draw.rectangle([(0, 1022), (1080, 1080)], fill=(12, 12, 12))
    draw.text((22, 1036), "👉 Follow @dailynewsflash_in for daily updates",
              font=font_small, fill=(190, 190, 190))

    img.save(output_path, "JPEG", quality=95)
    print("Single image created.")
    return output_path

# ── Carousel cover slide ──────────────────────────────────────────────────────
def create_cover_slide(output_path="/tmp/slide_0.jpg"):
    img = Image.new("RGB", (1080, 1080), color=(8, 8, 25))
    draw = ImageDraw.Draw(img)

    try:
        font_huge  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 88)
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_huge = font_large = font_small = ImageFont.load_default()

    for i in range(30):
        draw.rectangle([(0, i*36), (1080, (i+1)*36)],
                       fill=(10+i*2, 8+i, 30+i*3))
    draw.rectangle([(55, 195), (1025, 207)], fill=(220, 30, 30))
    draw.rectangle([(55, 830), (1025, 842)], fill=(220, 30, 30))
    draw.text((540, 135), "⚡ @dailynewsflash_in", font=font_small, fill=(255, 200, 50), anchor="mm")
    draw.text((540, 390), "TODAY'S", font=font_huge, fill=(255, 255, 255), anchor="mm")
    draw.text((540, 490), "TOP 5 NEWS", font=font_huge, fill=(220, 30, 30), anchor="mm")
    today = datetime.now().strftime("%d %B %Y")
    draw.text((540, 640), today, font=font_large, fill=(195, 195, 195), anchor="mm")
    draw.text((540, 895), "👉 Swipe to read all 5 stories", font=font_small,
              fill=(150, 150, 220), anchor="mm")
    draw.text((540, 955), "Follow for India & World news daily", font=font_small,
              fill=(110, 110, 180), anchor="mm")

    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Carousel news slide ───────────────────────────────────────────────────────
def create_news_slide(image_path, image_source, number, headline,
                      description, source, output_path):
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB").resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(12, 12, 35))

    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (1080, 1080)], fill=(0, 0, 0, 148))
    od.rectangle([(0, 0), (1080, 98)],   fill=(0, 0, 0, 215))
    od.rectangle([(0, 885), (1080, 1080)], fill=(0, 0, 0, 230))
    od.rectangle([(0, 0), (9, 1080)], fill=(220, 30, 30, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_num   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 105)
        font_head  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        font_desc  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
        font_badge = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
    except:
        font_num = font_head = font_desc = font_small = font_brand = font_badge = ImageFont.load_default()

    draw.text((28, 28), "⚡ DAILY NEWS FLASH", font=font_brand, fill=(255, 200, 50))
    draw.text((860, 155), f"#{number}", font=font_num, fill=(220, 30, 30))

    # AI badge
    if image_source == "AI Generated":
        draw.rectangle([(28, 95), (195, 120)], fill=(80, 0, 150))
        draw.text((34, 98), "✨ AI ILLUSTRATED", font=font_badge, fill=(220, 180, 255))

    wrapped_head = textwrap.wrap(headline, width=25)
    y = 290
    for line in wrapped_head[:4]:
        draw.text((28, y), line, font=font_head, fill=(255, 255, 255))
        y += 64

    if description:
        short = description[:220] + "..." if len(description) > 220 else description
        y += 18
        for line in textwrap.wrap(short, width=44)[:4]:
            draw.text((28, y), line, font=font_desc, fill=(215, 215, 215))
            y += 40

    draw.text((28, 900),  f"📌 {source}", font=font_small, fill=(100, 190, 255))
    draw.text((28, 945),  "Swipe for more →", font=font_small, fill=(155, 155, 210))
    draw.text((28, 993),  "👉 Follow @dailynewsflash_in", font=font_small, fill=(255, 200, 50))

    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Single post caption ───────────────────────────────────────────────────────
def generate_single_caption(article):
    print("Generating caption...")
    prompt = f"""You are a viral Instagram news editor for @dailynewsflash_in targeting Indians aged 18-35.

Write a highly engaging, controversial, emotionally charged caption for:
Title: {article['title']}
Description: {article.get('description', '')}
Source: {article['source']['name']}

Caption structure:
1. ONE punchy hook line with the most shocking/controversial angle — use 🔴 or 🚨 or ⚡

2. 📖 WHAT HAPPENED — 3 to 4 clear sentences explaining the story in simple language:
   - What exactly happened?
   - Who is involved (people, organisations, government)?
   - When and where did this happen?
   - What has been the immediate reaction or consequence?
   Write this like you are explaining to a friend who just woke up and knows nothing about it.

3. 🤔 WHY IT MATTERS — 2 sentences on why every Indian should care about this.

4. 🔥 THE CONTROVERSY — 1-2 sentences on what people are arguing about. Who is right? Who is wrong?

5. One sentence hot take using Indian slang: "Yaar", "bhai", "sach mein", "desh ke log"

6. 📌 Source: {article['source']['name']}

7. 💬 What's YOUR take? Drop your opinion below 👇
   Don't hold back — tell us what you really think!

8. 👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡

9. 25 relevant hashtags (mix of English and Hindi hashtags like #India #BreakingNews #ISRO etc.)

Rules: Facts only, no made-up details. Conversational tone. Emojis throughout. 1800-2200 chars total."""

    caption = call_gemini(prompt)
    if caption:
        return caption
    return f"⚡ {article['title']}\n\n📌 Source: {article['source']['name']}\n\n💬 What do you think? Comment!\n👉 Follow @dailynewsflash_in!\n\n#news #india #breakingnews"

# ── Carousel caption ──────────────────────────────────────────────────────────
def generate_carousel_caption(articles):
    print("Generating carousel caption...")
    headlines = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles)])
    prompt = f"""You are a viral Instagram editor for @dailynewsflash_in for Indian 18-35 year olds.

Write a carousel caption for today's top 5 controversial news stories:
{headlines}

Structure:
1. 🗞️ Hook: "5 stories India is ARGUING about right now 👇 Swipe before it's too late!"
2. One spicy one-liner per story (make it controversial/opinionated):
   1️⃣ [story 1 — shocking angle]
   2️⃣ [story 2 — shocking angle]
   3️⃣ [story 3 — shocking angle]
   4️⃣ [story 4 — shocking angle]
   5️⃣ [story 5 — shocking angle]
3. "Tell us which story made your blood boil 👇 Comment the number!"
4. 💬 We want YOUR opinion — no filter!
5. 👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡
6. 25 trending hashtags

Under 2200 chars. Make it impossible NOT to swipe and comment."""

    caption = call_gemini(prompt)
    if caption:
        return caption
    return f"🗞️ Today's Top 5 Stories!\n\nSwipe 👉\n💬 Comment which shocked you!\n👉 Follow @dailynewsflash_in!\n\n#news #india #breakingnews"

# ── Upload to Imgur ───────────────────────────────────────────────────────────
def upload_to_imgur(image_path):
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    try:
        r = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            data={"image": image_data, "type": "base64"},
            timeout=30
        )
        data = r.json()
        if data.get("success"):
            print(f"Imgur: {data['data']['link']}")
            return data["data"]["link"]
        print(f"Imgur failed: {data}")
        return None
    except Exception as e:
        print(f"Imgur error: {e}")
        return None

# ── Post single to Instagram ──────────────────────────────────────────────────
def post_single(image_url, caption):
    print("Posting to Instagram...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    result = r.json()
    creation_id = result.get("id")
    if not creation_id:
        raise Exception(f"Container failed: {result}")
    time.sleep(8)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    if "id" in r2.json():
        print(f"✅ Posted! ID: {r2.json()['id']}")
    else:
        raise Exception(f"Publish failed: {r2.json()}")

# ── Post carousel to Instagram ────────────────────────────────────────────────
def post_carousel(image_urls, caption):
    print(f"Posting carousel with {len(image_urls)} slides...")
    child_ids = []
    for i, img_url in enumerate(image_urls):
        r = requests.post(
            f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
            data={"image_url": img_url, "is_carousel_item": "true",
                  "access_token": FB_ACCESS_TOKEN},
            timeout=30
        )
        child_id = r.json().get("id")
        if child_id:
            child_ids.append(child_id)
        else:
            print(f"  Slide {i+1} failed: {r.json()}")
        time.sleep(3)

    if len(child_ids) < 2:
        raise Exception(f"Not enough slides ({len(child_ids)})")

    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"media_type": "CAROUSEL", "children": ",".join(child_ids),
              "caption": caption, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    carousel_id = r.json().get("id")
    if not carousel_id:
        raise Exception(f"Carousel container failed: {r.json()}")

    time.sleep(8)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": carousel_id, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    if "id" in r2.json():
        print(f"✅ Carousel posted! ID: {r2.json()['id']}")
    else:
        raise Exception(f"Carousel publish failed: {r2.json()}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Bot started {datetime.now()} | Type: {POST_TYPE} ===\n")

    if POST_TYPE == "carousel":
        articles = fetch_articles(count=5)
        if not articles:
            print("No articles. Exiting.")
            sys.exit(1)

        slide_paths = [create_cover_slide("/tmp/slide_0.jpg")]

        for i, article in enumerate(articles):
            print(f"\n--- Article {i+1}/5: {article['title'][:70]}...")
            img_path, img_source = fetch_image(article, f"/tmp/slide_img_{i}.jpg")
            slide_path = create_news_slide(
                img_path, img_source, i+1,
                article["title"],
                article.get("description", ""),
                article["source"]["name"],
                f"/tmp/slide_{i+1}.jpg"
            )
            slide_paths.append(slide_path)
            time.sleep(1)

        print(f"\nUploading {len(slide_paths)} slides...")
        image_urls = []
        for path in slide_paths:
            url = upload_to_imgur(path)
            if url:
                image_urls.append(url)
            time.sleep(2)

        if len(image_urls) < 2:
            print("Not enough uploads. Exiting.")
            sys.exit(1)

        caption = generate_carousel_caption(articles)
        post_carousel(image_urls, caption)

    else:
        articles = fetch_articles(count=1)
        if not articles:
            print("No articles. Exiting.")
            sys.exit(1)
        article = articles[0]
        print(f"\nArticle: {article['title']}")
        image_path, image_source = fetch_image(article)
        final_image = create_single_image(
            image_path, image_source,
            article["title"], article["source"]["name"]
        )
        image_url = upload_to_imgur(final_image)
        if not image_url:
            print("Upload failed. Exiting.")
            sys.exit(1)
        caption = generate_single_caption(article)
        post_single(image_url, caption)

    print(f"\n=== ✅ Done at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
