import os
import requests
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime
import random
import base64
import time
import sys

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"]
POST_TYPE           = os.environ.get("POST_TYPE", "single")  # "single" or "carousel"

# ── India-specific trending topics ────────────────────────────────────────────
TRENDING_TOPICS = [
    "cricket India IPL",
    "bollywood movies",
    "Indian politics BJP Congress",
    "India technology startup",
    "India business economy",
    "India crime",
    "entertainment celebrity",
    "India sports",
    "world news India",
    "science space ISRO",
    "India education",
    "India health",
    "Mumbai Delhi news",
    "viral India",
]

# ── Gemini API call with retry ─────────────────────────────────────────────────
def call_gemini(prompt, retries=3):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    for attempt in range(retries):
        try:
            response = requests.post(url, json=payload, timeout=20)
            data = response.json()
            if "candidates" in data:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            print(f"Gemini attempt {attempt+1} failed: {data.get('error', data)}")
        except Exception as e:
            print(f"Gemini attempt {attempt+1} error: {e}")
        time.sleep(2)
    return None

# ── Fetch multiple articles ────────────────────────────────────────────────────
def fetch_articles(count=5):
    print(f"Fetching {count} trending articles...")
    all_articles = []
    selected_topics = random.sample(TRENDING_TOPICS, min(6, len(TRENDING_TOPICS)))
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

    # Remove duplicates by title
    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    print(f"Total unique articles found: {len(unique)}")
    return pick_top_articles(unique, count)

# ── Gemini picks top N articles ───────────────────────────────────────────────
def pick_top_articles(articles, count=5):
    print(f"Asking Gemini to pick top {count} articles...")
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:20])])
    prompt = f"""You are a social media expert for an Indian news Instagram page targeting 18-35 year olds.

Here are news article titles from India and the world:
{titles}

Pick the TOP {count} articles that will get the most engagement (likes, comments, shares) from young Indians.
Prioritise: cricket, IPL, Bollywood, viral news, politics, ISRO, crime, celebrity gossip, tech.
Avoid: dry government reports, very local municipal news, old repeated stories.

Reply with ONLY the numbers separated by commas. Example: 3,7,1,12,5
Nothing else. No explanation."""

    answer = call_gemini(prompt)
    if answer:
        try:
            numbers = [int(n.strip()) for n in answer.split(",") if n.strip().isdigit()]
            numbers = [n for n in numbers if 1 <= n <= len(articles)][:count]
            if len(numbers) >= count:
                print(f"Gemini picked articles: {numbers}")
                return [articles[n-1] for n in numbers]
        except Exception as e:
            print(f"Gemini parse failed: {e}")
    print("Using first articles as fallback")
    return articles[:count]

# ── Get image keyword ──────────────────────────────────────────────────────────
def get_image_keyword(article):
    topic = article.get("_topic", "general")
    prompt = f"""News headline: "{article['title']}"
Topic category: "{topic}"

Give ONE specific Unsplash search keyword (2-4 words) for a visually stunning, relevant stock photo.

Rules:
- NEVER use: india flag, indian flag, india map, india news, indian people generic
- Be very specific to the actual subject:
  * Cricket/IPL → "cricket match stadium crowd"
  * Bollywood → "bollywood cinema stage lights"  
  * Politics → "parliament building government"
  * Technology/startup → "technology laptop startup office"
  * Business/economy → "stock market trading"
  * Crime → "police investigation"
  * Space/ISRO → "rocket launch space"
  * Health → "hospital doctor medical"
  * Education → "students classroom university"
  * Sports → "sports athlete competition"
  * Viral/entertainment → "crowd celebration event"
  * World news → pick the specific country or event location

Return ONLY the 2-4 word keyword. Nothing else."""

    keyword = call_gemini(prompt)
    if keyword:
        blocked = ["india flag", "indian flag", "india map", "india news", "indian people"]
        if any(b in keyword.lower() for b in blocked):
            fallbacks = {
                "cricket": "cricket stadium match",
                "bollywood": "cinema film stage",
                "politics": "parliament building",
                "technology": "smartphone digital tech",
                "business": "stock market finance",
                "crime": "police investigation crime",
                "sports": "sports athlete competition",
                "world": "cityscape skyline",
                "science": "science laboratory research",
                "entertainment": "stage lights performance",
                "health": "hospital medical doctor",
                "education": "university students campus",
            }
            for key, val in fallbacks.items():
                if key in topic.lower():
                    return val
            return "breaking news newspaper"
        print(f"Image keyword: {keyword}")
        return keyword
    # Fallback based on topic
    fallbacks = {
        "cricket": "cricket stadium match",
        "bollywood": "cinema film stage",
        "politics": "parliament building",
        "technology": "smartphone digital tech",
        "business": "stock market finance",
    }
    for key, val in fallbacks.items():
        if key in topic.lower():
            return val
    return "breaking news"

# ── Fetch image from Unsplash ──────────────────────────────────────────────────
def fetch_image(keyword, save_path="/tmp/news_image.jpg"):
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": keyword,
        "per_page": 15,
        "page": random.randint(1, 4),
        "orientation": "squarish",
        "client_id": UNSPLASH_ACCESS_KEY
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        results = response.json().get("results", [])
    except Exception as e:
        print(f"Unsplash error: {e}")
        results = []

    if not results:
        print(f"No results for '{keyword}', trying 'breaking news'...")
        params["query"] = "breaking news"
        params["page"] = 1
        try:
            response = requests.get(url, params=params, timeout=10)
            results = response.json().get("results", [])
        except:
            return None

    if not results:
        return None

    photo = random.choice(results[:10])
    try:
        img_response = requests.get(photo["urls"]["regular"], stream=True, timeout=15)
        with open(save_path, "wb") as f:
            for chunk in img_response.iter_content(1024):
                f.write(chunk)
        print(f"Image downloaded for keyword: {keyword}")
        return save_path
    except Exception as e:
        print(f"Image download failed: {e}")
        return None

# ── Design single post image ───────────────────────────────────────────────────
def create_single_image(image_path, headline, source_name, output_path="/tmp/final_post.jpg"):
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB").resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(20, 20, 40))

    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 540), (1080, 1080)], fill=(0, 0, 0, 200))
    od.rectangle([(0, 0), (1080, 90)], fill=(0, 0, 0, 170))
    # Accent bar
    od.rectangle([(0, 540), (8, 1080)], fill=(255, 60, 60, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_source = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        font_large = ImageFont.load_default()
        font_small = font_large
        font_brand = font_large
        font_source = font_large

    # Brand bar top
    draw.text((40, 25), "⚡ DAILY NEWS FLASH", font=font_brand, fill=(255, 200, 50))
    draw.text((900, 25), "IN", font=font_brand, fill=(255, 80, 80))

    # Source label
    draw.text((30, 565), f"📌 {source_name}".upper(), font=font_source, fill=(120, 200, 255))

    # Headline — wrapped
    wrapped = textwrap.wrap(headline, width=28)[:4]
    for i, line in enumerate(wrapped):
        draw.text((30, 620 + i * 65), line, font=font_large, fill=(255, 255, 255))

    # Bottom bar
    draw.rectangle([(0, 1020), (1080, 1080)], fill=(15, 15, 15))
    draw.text((30, 1034), "👉 Follow @dailynewsflash_in for daily updates", font=font_small, fill=(200, 200, 200))

    img.save(output_path, "JPEG", quality=95)
    print("Single image created.")
    return output_path

# ── Design carousel cover slide ───────────────────────────────────────────────
def create_cover_slide(output_path="/tmp/slide_0.jpg"):
    img = Image.new("RGB", (1080, 1080), color=(10, 10, 30))
    draw = ImageDraw.Draw(img)

    try:
        font_huge  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 85)
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_huge = font_large = font_small = ImageFont.load_default()

    # Gradient background
    for i in range(30):
        draw.rectangle([(0, i*36), (1080, (i+1)*36)], fill=(15+i*2, 10+i*1, 40+i*3))

    # Decorative accent lines
    draw.rectangle([(60, 195), (1020, 205)], fill=(255, 60, 60))
    draw.rectangle([(60, 830), (1020, 840)], fill=(255, 60, 60))

    # Brand
    draw.text((540, 135), "⚡ @dailynewsflash_in", font=font_small, fill=(255, 200, 50), anchor="mm")

    # Main title
    draw.text((540, 390), "TODAY'S", font=font_huge, fill=(255, 255, 255), anchor="mm")
    draw.text((540, 490), "TOP 5 NEWS", font=font_huge, fill=(255, 60, 60), anchor="mm")

    # Date
    today = datetime.now().strftime("%d %B %Y")
    draw.text((540, 640), today, font=font_large, fill=(200, 200, 200), anchor="mm")

    # Swipe hint
    draw.text((540, 900), "👉 Swipe to read all stories", font=font_small, fill=(150, 150, 220), anchor="mm")
    draw.text((540, 960), "Follow for daily news from India & World", font=font_small, fill=(120, 120, 180), anchor="mm")

    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Design carousel news slide ────────────────────────────────────────────────
def create_news_slide(image_path, number, headline, description, source, output_path):
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB").resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(15, 15, 40))

    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 0), (1080, 1080)], fill=(0, 0, 0, 150))
    od.rectangle([(0, 0), (1080, 95)], fill=(0, 0, 0, 210))
    od.rectangle([(0, 890), (1080, 1080)], fill=(0, 0, 0, 230))
    # Left accent
    od.rectangle([(0, 0), (8, 1080)], fill=(255, 60, 60, 255))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_num   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
        font_head  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
        font_desc  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 27)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
    except:
        font_num = font_head = font_desc = font_small = font_brand = ImageFont.load_default()

    # Brand top
    draw.text((30, 28), "⚡ DAILY NEWS FLASH", font=font_brand, fill=(255, 200, 50))

    # Big number watermark
    draw.text((870, 160), f"#{number}", font=font_num, fill=(255, 60, 60))

    # Headline
    wrapped_head = textwrap.wrap(headline, width=26)
    y = 300
    for line in wrapped_head[:4]:
        draw.text((30, y), line, font=font_head, fill=(255, 255, 255))
        y += 62

    # Description
    if description:
        short_desc = description[:200] + "..." if len(description) > 200 else description
        wrapped_desc = textwrap.wrap(short_desc, width=44)
        y += 18
        for line in wrapped_desc[:4]:
            draw.text((30, y), line, font=font_desc, fill=(215, 215, 215))
            y += 38

    # Bottom
    draw.text((30, 910), f"📌 Source: {source}", font=font_small, fill=(120, 200, 255))
    draw.text((30, 955), "Swipe for more stories →", font=font_small, fill=(160, 160, 210))
    draw.text((30, 1000), "👉 Follow @dailynewsflash_in", font=font_small, fill=(255, 200, 50))

    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Generate single post caption ──────────────────────────────────────────────
def generate_single_caption(article):
    print("Generating single post caption...")
    prompt = f"""You are an expert Instagram news creator for @dailynewsflash_in targeting young Indians aged 18-35.

Write an engaging caption for this news:
Title: {article['title']}
Description: {article.get('description', '')}
Source: {article['source']['name']}

Structure your caption like this:
1. 🔴 BREAKING / 🚨 SHOCKING / ⚡ BIG NEWS — one punchy line hook (make it grab attention)
2. 3-4 sentences explaining the full story simply — what happened, who, where, when, why it matters
3. Why this matters to Indians specifically — connect it to Indian audience
4. Your reaction line — "Yaar, this is huge!" or "Sach mein this changes everything!" etc.
5. 📌 Source: {article['source']['name']}
6. 💬 What do YOU think? Drop your reaction below! 👇
7. 👉 Follow @dailynewsflash_in — Flash news. Zero fluff. 🗞️
8. Blank line then 25 relevant hashtags mixing: #India #BreakingNews #[topic] #DailyNewsFlash etc.

Rules:
- Use emojis naturally throughout
- Occasionally use Hindi words: "yaar", "desh", "bhai", "sach mein", "ekdum"  
- Conversational and exciting tone — like a friend telling you news
- 1500-2000 characters total
- Facts only — no made up details"""

    caption = call_gemini(prompt)
    if caption:
        return caption
    return f"⚡ {article['title']}\n\n📌 Source: {article['source']['name']}\n\n💬 What do you think? Comment below!\n👉 Follow @dailynewsflash_in!\n\n#news #india #breakingnews #dailynewsflash"

# ── Generate carousel caption ──────────────────────────────────────────────────
def generate_carousel_caption(articles):
    print("Generating carousel caption...")
    headlines = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles)])
    prompt = f"""You are an Instagram news creator for @dailynewsflash_in targeting young Indians 18-35.

Write a carousel caption for today's top 5 news stories:
{headlines}

Structure:
1. 🗞️ "Today's TOP 5 News you NEED to know! 👇 Swipe through!" (hook)
2. Quick exciting one-liner for each story with emoji + number:
   1️⃣ [story 1 teaser]
   2️⃣ [story 2 teaser]
   3️⃣ [story 3 teaser]
   4️⃣ [story 4 teaser]
   5️⃣ [story 5 teaser]
3. "Swipe through all 5 stories — don't miss #3! 👉"
4. 💬 Which story surprised you most? Comment the number below! 👇
5. 👉 Follow @dailynewsflash_in — your daily dose of India & World news! ⚡
6. 25 relevant hashtags

Keep it exciting, conversational, under 2200 chars."""

    caption = call_gemini(prompt)
    if caption:
        return caption
    return f"🗞️ Today's Top 5 News!\n\nSwipe to read all stories 👉\n\n💬 Comment which surprised you!\n👉 Follow @dailynewsflash_in!\n\n#news #india #top5 #breakingnews #dailynews"

# ── Upload image to Imgur ──────────────────────────────────────────────────────
def upload_to_imgur(image_path):
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    try:
        response = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": "Client-ID 546c25a59c58ad7"},
            data={"image": image_data, "type": "base64"},
            timeout=30
        )
        data = response.json()
        if data.get("success"):
            print(f"Imgur upload successful: {data['data']['link']}")
            return data["data"]["link"]
        print(f"Imgur upload failed: {data}")
        return None
    except Exception as e:
        print(f"Imgur upload error: {e}")
        return None

# ── Post single image to Instagram ────────────────────────────────────────────
def post_single(image_url, caption):
    print("Posting single image to Instagram...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    result = r.json()
    creation_id = result.get("id")
    if not creation_id:
        raise Exception(f"Container failed: {result}")
    print(f"Media container created: {creation_id}")
    time.sleep(8)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN},
        timeout=30
    )
    result2 = r2.json()
    if "id" in result2:
        print(f"✅ Single post published! Post ID: {result2['id']}")
    else:
        raise Exception(f"Publish failed: {result2}")

# ── Post carousel to Instagram ────────────────────────────────────────────────
def post_carousel(image_urls, caption):
    print(f"Creating carousel with {len(image_urls)} slides...")
    child_ids = []
    for i, img_url in enumerate(image_urls):
        print(f"  Creating container for slide {i+1}/{len(image_urls)}...")
        r = requests.post(
            f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
            data={
                "image_url": img_url,
                "is_carousel_item": "true",
                "access_token": FB_ACCESS_TOKEN
            },
            timeout=30
        )
        child_id = r.json().get("id")
        if not child_id:
            print(f"  ⚠️ Failed slide {i+1}: {r.json()}")
            continue
        child_ids.append(child_id)
        time.sleep(3)

    if len(child_ids) < 2:
        raise Exception(f"Not enough carousel slides created ({len(child_ids)})")

    print(f"Creating carousel container with {len(child_ids)} slides...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": FB_ACCESS_TOKEN
        },
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
        print(f"✅ Carousel published! Post ID: {r2.json()['id']}")
    else:
        raise Exception(f"Carousel publish failed: {r2.json()}")

# ── Main flow ─────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Bot started at {datetime.now()} IST | Type: {POST_TYPE} ===\n")

    if POST_TYPE == "carousel":
        articles = fetch_articles(count=5)
        if not articles:
            print("No articles found. Exiting.")
            sys.exit(1)

        slide_paths = []
        cover_path = create_cover_slide("/tmp/slide_0.jpg")
        slide_paths.append(cover_path)

        for i, article in enumerate(articles):
            print(f"\nProcessing article {i+1}/5: {article['title'][:60]}...")
            keyword = get_image_keyword(article)
            img_path = fetch_image(keyword, f"/tmp/slide_img_{i}.jpg")
            slide_path = create_news_slide(
                img_path, i+1,
                article["title"],
                article.get("description", ""),
                article["source"]["name"],
                f"/tmp/slide_{i+1}.jpg"
            )
            slide_paths.append(slide_path)
            time.sleep(1)

        print(f"\nUploading {len(slide_paths)} slides to Imgur...")
        image_urls = []
        for path in slide_paths:
            url = upload_to_imgur(path)
            if url:
                image_urls.append(url)
            time.sleep(2)

        if len(image_urls) < 2:
            print("Not enough images uploaded. Exiting.")
            sys.exit(1)

        caption = generate_carousel_caption(articles)
        post_carousel(image_urls, caption)

    else:
        articles = fetch_articles(count=1)
        if not articles:
            print("No articles found. Exiting.")
            sys.exit(1)
        article = articles[0]
        print(f"\nSelected article: {article['title']}")
        keyword = get_image_keyword(article)
        image_path = fetch_image(keyword)
        final_image = create_single_image(image_path, article["title"], article["source"]["name"])
        image_url = upload_to_imgur(final_image)
        if not image_url:
            print("Image upload failed. Exiting.")
            sys.exit(1)
        caption = generate_single_caption(article)
        post_single(image_url, caption)

    print(f"\n=== ✅ Bot finished successfully at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
