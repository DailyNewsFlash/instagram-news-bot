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

TRENDING_TOPICS = [
    "cricket", "bollywood", "politics", "technology",
    "business", "crime", "entertainment", "sports", "world", "science",
]

# ── Fetch multiple articles ────────────────────────────────────────────────────
def fetch_articles(count=5):
    print(f"Fetching {count} trending articles...")
    all_articles = []
    selected_topics = random.sample(TRENDING_TOPICS, min(5, len(TRENDING_TOPICS)))
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
            print(f"Error fetching {topic}: {e}")

    if not all_articles:
        url = "https://gnews.io/api/v4/top-headlines"
        params = {"token": GNEWS_API_KEY, "lang": "en", "country": "in", "max": 10}
        response = requests.get(url, params=params)
        all_articles = response.json().get("articles", [])

    if not all_articles:
        return []

    # Remove duplicates by title
    seen = set()
    unique = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique.append(a)

    # Ask Gemini to rank top articles
    return pick_top_articles(unique, count)

# ── Gemini picks top N articles ───────────────────────────────────────────────
def pick_top_articles(articles, count=5):
    print(f"Asking Gemini to pick top {count} articles...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:20])])
    prompt = f"""You are a social media expert for an Indian news Instagram page targeting 18-35 year olds.

Here are news article titles:
{titles}

Pick the TOP {count} articles that will get the most engagement (likes, comments, shares) from young Indians.
Consider: cricket, Bollywood, politics, viral stories, shocking news, celebrity gossip, tech news perform well.

Reply with ONLY the numbers separated by commas. Example: 3,7,1,12,5
Nothing else."""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=15)
        data = response.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        numbers = [int(n.strip()) for n in answer.split(",") if n.strip().isdigit()]
        numbers = [n for n in numbers if 1 <= n <= len(articles)][:count]
        if len(numbers) >= count:
            print(f"Gemini picked articles: {numbers}")
            return [articles[n-1] for n in numbers]
    except Exception as e:
        print(f"Gemini pick failed: {e}")
    return articles[:count]

# ── Get image keyword ──────────────────────────────────────────────────────────
def get_image_keyword(article):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""News headline: "{article['title']}"
Topic: "{article.get('_topic', 'general')}"

Give ONE specific Unsplash search keyword (2-4 words) for a relevant stock photo.
NEVER use: india flag, indian flag, india map, india news.
Be topic-specific: cricket→"cricket stadium match", bollywood→"cinema actress film", 
politics→"parliament government", tech→"smartphone technology", crime→"police arrest".
Return ONLY the keyword."""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=10)
        data = response.json()
        keyword = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        blocked = ["india flag", "indian flag", "india map", "india news"]
        if any(b in keyword.lower() for b in blocked):
            fallbacks = {"cricket": "cricket stadium", "bollywood": "cinema film",
                        "politics": "parliament building", "technology": "smartphone digital",
                        "business": "stock market", "crime": "police enforcement",
                        "sports": "sports athlete", "world": "world globe",
                        "science": "science laboratory", "entertainment": "stage performance"}
            keyword = fallbacks.get(article.get("_topic", ""), "breaking news")
        return keyword
    except:
        return "breaking news"

# ── Fetch image from Unsplash ──────────────────────────────────────────────────
def fetch_image(keyword, save_path="/tmp/news_image.jpg"):
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": keyword,
        "per_page": 10,
        "page": random.randint(1, 3),
        "orientation": "squarish",
        "client_id": UNSPLASH_ACCESS_KEY
    }
    response = requests.get(url, params=params)
    results = response.json().get("results", [])
    if not results:
        params["query"] = "breaking news"
        params["page"] = 1
        response = requests.get(url, params=params)
        results = response.json().get("results", [])
    if not results:
        return None
    photo = random.choice(results)
    img_response = requests.get(photo["urls"]["regular"], stream=True)
    with open(save_path, "wb") as f:
        for chunk in img_response.iter_content(1024):
            f.write(chunk)
    return save_path

# ── Design single post image ───────────────────────────────────────────────────
def create_single_image(image_path, headline, source_name, output_path="/tmp/final_post.jpg"):
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB").resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(20, 20, 40))
    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, 580), (1080, 1080)], fill=(0, 0, 0, 185))
    od.rectangle([(0, 0), (1080, 85)], fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    except:
        font_large = ImageFont.load_default()
        font_small = font_large
        font_brand = font_large
    draw.text((40, 24), "@dailynewsflash_in", font=font_brand, fill=(255, 200, 50))
    draw.text((40, 610), f"Source: {source_name}", font=font_small, fill=(120, 200, 255))
    for i, line in enumerate(textwrap.wrap(headline, width=30)[:4]):
        draw.text((40, 668 + i*62), line, font=font_large, fill=(255, 255, 255))
    draw.rectangle([(0, 1020), (1080, 1080)], fill=(15, 15, 15))
    draw.text((40, 1034), "Follow @dailynewsflash_in for daily updates", font=font_small, fill=(180, 180, 180))
    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Design carousel cover slide ───────────────────────────────────────────────
def create_cover_slide(output_path="/tmp/slide_0.jpg"):
    img = Image.new("RGB", (1080, 1080), color=(10, 10, 30))
    draw = ImageDraw.Draw(img)
    try:
        font_huge  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
    except:
        font_huge = font_large = font_small = ImageFont.load_default()

    # Background gradient effect using rectangles
    for i in range(20):
        alpha_val = int(255 * i / 20)
        draw.rectangle([(0, i*54), (1080, (i+1)*54)], fill=(20+i*3, 20+i*2, 60+i*2))

    # Decorative lines
    draw.rectangle([(60, 200), (1020, 208)], fill=(255, 200, 50))
    draw.rectangle([(60, 820), (1020, 828)], fill=(255, 200, 50))

    # Brand
    draw.text((540, 140), "@dailynewsflash_in", font=font_small, fill=(255, 200, 50), anchor="mm")

    # Main title
    draw.text((540, 420), "TODAY'S", font=font_huge, fill=(255, 255, 255), anchor="mm")
    draw.text((540, 520), "TOP NEWS", font=font_huge, fill=(255, 200, 50), anchor="mm")

    # Date
    today = datetime.now().strftime("%d %B %Y")
    draw.text((540, 650), today, font=font_large, fill=(200, 200, 200), anchor="mm")

    # Swipe hint
    draw.text((540, 900), "Swipe to read all stories →", font=font_small, fill=(150, 150, 200), anchor="mm")
    draw.text((540, 960), "Follow for daily news updates", font=font_small, fill=(120, 120, 180), anchor="mm")

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
    od.rectangle([(0, 0), (1080, 1080)], fill=(0, 0, 0, 140))
    od.rectangle([(0, 0), (1080, 90)], fill=(0, 0, 0, 200))
    od.rectangle([(0, 900), (1080, 1080)], fill=(0, 0, 0, 220))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font_num   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 90)
        font_head  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
        font_desc  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    except:
        font_num = font_head = font_desc = font_small = font_brand = ImageFont.load_default()

    draw.text((40, 25), "@dailynewsflash_in", font=font_brand, fill=(255, 200, 50))
    draw.text((900, 200), f"#{number}", font=font_num, fill=(255, 200, 50, 180))

    wrapped_head = textwrap.wrap(headline, width=28)
    y = 320
    for line in wrapped_head[:4]:
        draw.text((50, y), line, font=font_head, fill=(255, 255, 255))
        y += 58

    if description:
        short_desc = description[:180] + "..." if len(description) > 180 else description
        wrapped_desc = textwrap.wrap(short_desc, width=42)
        y += 20
        for line in wrapped_desc[:3]:
            draw.text((50, y), line, font=font_desc, fill=(210, 210, 210))
            y += 40

    draw.text((50, 930), f"📌 {source}", font=font_small, fill=(120, 200, 255))
    draw.text((50, 980), "Swipe for more news →", font=font_small, fill=(150, 150, 200))
    draw.text((50, 1030), "Follow @dailynewsflash_in", font=font_small, fill=(255, 200, 50))

    img.save(output_path, "JPEG", quality=95)
    return output_path

# ── Generate single post caption ──────────────────────────────────────────────
def generate_single_caption(article):
    print("Generating single post caption...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""You are an expert Instagram news creator for @dailynewsflash_in targeting young Indians aged 18-35.

Write an engaging caption for:
Title: {article['title']}
Description: {article.get('description', '')}
Source: {article['source']['name']}

Structure:
1. Punchy hook with emoji
2. 4-5 sentences explaining the story simply
3. Why it matters to Indians
4. 📌 Source: {article['source']['name']}
5. 💬 What's your take? Comment below!
   👉 Follow @dailynewsflash_in for breaking news every day!
6. 20 relevant hashtags

Rules: conversational tone, occasional Hindi words, emojis throughout, 1500-2000 chars, facts only."""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return f"📰 {article['title']}\n\n📌 Source: {article['source']['name']}\n\n💬 Comment below!\n👉 Follow @dailynewsflash_in!\n\n#news #india #breakingnews"

# ── Generate carousel caption ──────────────────────────────────────────────────
def generate_carousel_caption(articles):
    print("Generating carousel caption...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    headlines = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles)])
    prompt = f"""You are an Instagram news creator for @dailynewsflash_in.

Write a caption for a carousel post containing today's top 5 news stories:
{headlines}

Structure:
1. 🗞️ Hook: "Today's Top 5 News Stories you NEED to know!"
2. Quick one-line teaser for each story with emoji and number
3. "Swipe through all 5 stories →"
4. 💬 Which story surprised you the most? Comment below!
   👉 Follow @dailynewsflash_in — your daily dose of news!
5. 20 relevant hashtags

Keep it exciting, conversational, under 2000 chars."""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    data = response.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        return f"🗞️ Today's Top 5 News!\n\nSwipe to read all stories →\n\n💬 Comment below!\n👉 Follow @dailynewsflash_in!\n\n#news #india #top5 #breakingnews #dailynews"

# ── Upload image to Imgur ──────────────────────────────────────────────────────
def upload_to_imgur(image_path):
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    response = requests.post(
        "https://api.imgur.com/3/image",
        headers={"Authorization": "Client-ID 546c25a59c58ad7"},
        data={"image": image_data, "type": "base64"}
    )
    data = response.json()
    if data.get("success"):
        return data["data"]["link"]
    print(f"Imgur upload failed: {data}")
    return None

# ── Post single image to Instagram ────────────────────────────────────────────
def post_single(image_url, caption):
    print("Posting single image...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url": image_url, "caption": caption, "access_token": FB_ACCESS_TOKEN}
    )
    creation_id = r.json().get("id")
    if not creation_id:
        raise Exception(f"Container failed: {r.json()}")
    time.sleep(5)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": FB_ACCESS_TOKEN}
    )
    if "id" in r2.json():
        print("Single post published!")
    else:
        raise Exception(f"Publish failed: {r2.json()}")

# ── Post carousel to Instagram ────────────────────────────────────────────────
def post_carousel(image_urls, caption):
    print(f"Creating carousel with {len(image_urls)} slides...")
    child_ids = []
    for i, img_url in enumerate(image_urls):
        print(f"  Creating container for slide {i+1}...")
        r = requests.post(
            f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
            data={
                "image_url": img_url,
                "is_carousel_item": "true",
                "access_token": FB_ACCESS_TOKEN
            }
        )
        child_id = r.json().get("id")
        if not child_id:
            print(f"  Failed to create slide {i+1}: {r.json()}")
            continue
        child_ids.append(child_id)
        time.sleep(2)

    if len(child_ids) < 2:
        raise Exception("Not enough carousel slides created")

    print(f"Creating carousel container with {len(child_ids)} slides...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": FB_ACCESS_TOKEN
        }
    )
    carousel_id = r.json().get("id")
    if not carousel_id:
        raise Exception(f"Carousel container failed: {r.json()}")

    time.sleep(5)
    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": carousel_id, "access_token": FB_ACCESS_TOKEN}
    )
    if "id" in r2.json():
        print("Carousel published successfully!")
    else:
        raise Exception(f"Carousel publish failed: {r2.json()}")

# ── Main flow ─────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Bot started at {datetime.now()} | Type: {POST_TYPE} ===\n")

    if POST_TYPE == "carousel":
        articles = fetch_articles(count=5)
        if not articles:
            print("No articles found.")
            return

        slide_paths = []
        cover_path = create_cover_slide("/tmp/slide_0.jpg")
        slide_paths.append(cover_path)

        for i, article in enumerate(articles):
            print(f"\nProcessing article {i+1}: {article['title']}")
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

        print("\nUploading slides to Imgur...")
        image_urls = []
        for path in slide_paths:
            url = upload_to_imgur(path)
            if url:
                image_urls.append(url)
                time.sleep(1)

        if len(image_urls) < 2:
            print("Not enough images uploaded.")
            return

        caption = generate_carousel_caption(articles)
        post_carousel(image_urls, caption)

    else:
        articles = fetch_articles(count=1)
        if not articles:
            print("No articles found.")
            return
        article = articles[0]
        keyword = get_image_keyword(article)
        image_path = fetch_image(keyword)
        final_image = create_single_image(image_path, article["title"], article["source"]["name"])
        image_url = upload_to_imgur(final_image)
        if not image_url:
            print("Image upload failed.")
            return
        caption = generate_single_caption(article)
        post_single(image_url, caption)

    print(f"\n=== Bot finished at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
