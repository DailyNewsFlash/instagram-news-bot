import os
import requests
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime
import random
import base64
import time

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"]

# ── Topics that Indian audiences love ─────────────────────────────────────────
TRENDING_TOPICS = [
    "cricket",
    "bollywood",
    "politics",
    "technology",
    "business",
    "crime",
    "entertainment",
    "sports",
    "world",
    "science",
]

# ── 1. Fetch trending news from multiple hot topics ───────────────────────────
def fetch_news():
    print("Fetching trending news...")

    # Try multiple topics and collect articles from each
    all_articles = []

    # Pick 3 random topics to fetch from
    selected_topics = random.sample(TRENDING_TOPICS, 3)
    print(f"Fetching from topics: {selected_topics}")

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
                a["_topic"] = topic  # tag which topic it came from
            all_articles.extend(articles)
            print(f"  Got {len(articles)} articles for topic: {topic}")
        except Exception as e:
            print(f"  Error fetching topic {topic}: {e}")

    if not all_articles:
        # Fallback to top headlines
        print("Falling back to top headlines...")
        url = "https://gnews.io/api/v4/top-headlines"
        params = {
            "token": GNEWS_API_KEY,
            "lang": "en",
            "country": "in",
            "max": 10
        }
        response = requests.get(url, params=params)
        data = response.json()
        all_articles = data.get("articles", [])

    if not all_articles:
        print("No articles found.")
        return None

    # Use Gemini to pick the most engaging article
    print(f"Total articles collected: {len(all_articles)}")
    best = pick_most_engaging_article(all_articles)
    print(f"Selected article: {best['title']}")
    return best

# ── 2. Use Gemini to pick the most engaging article ───────────────────────────
def pick_most_engaging_article(articles):
    print("Asking Gemini to pick the most engaging article...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    # Build a numbered list of titles
    titles = "\n".join([f"{i+1}. {a['title']}" for i, a in enumerate(articles[:15])])

    prompt = f"""You are a social media expert for an Indian news Instagram page.

Here are news article titles:
{titles}

Which ONE article will get the most likes, comments and shares from Indian Instagram users aged 18-35?
Consider: cricket, Bollywood, politics, viral stories, shocking news, celebrity gossip, tech news all perform well.

Reply with ONLY the number of the best article. Nothing else."""

    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    try:
        response = requests.post(url, json=payload, timeout=15)
        data = response.json()
        answer = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # Extract just the number
        number = int(''.join(filter(str.isdigit, answer.split()[0])))
        if 1 <= number <= len(articles):
            print(f"Gemini picked article #{number}")
            return articles[number - 1]
    except Exception as e:
        print(f"Gemini pick failed: {e}, using random")

    return random.choice(articles[:10])

# ── 3. Generate caption using Google Gemini ───────────────────────────────────
def generate_caption(article):
    print("Generating caption with Gemini...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
You are an expert Instagram news content creator for @dailynewsflash_in — a professional Indian news page with young Indian followers aged 18-35.

Write a highly engaging Instagram post caption for this news article:

Title: {article['title']}
Description: {article.get('description', '')}
Source: {article['source']['name']}
Published: {article['publishedAt']}

Follow this EXACT structure:

1. Start with a punchy emoji + ONE powerful hook sentence that makes people stop scrolling. Make it shocking, surprising or exciting.

2. Write 4-5 sentences explaining the full story in simple conversational language:
   - What happened?
   - Who is involved?
   - Why does it matter to common Indians?
   - What happens next?

3. Write one line with an interesting angle, surprising fact or strong opinion about this news

4. 📌 Source: {article['source']['name']}

5. Call to action — make it feel natural and conversational:
💬 What's your take on this? Comment below!
👉 Follow @dailynewsflash_in for breaking news every day — don't miss out!

6. Add 20 highly relevant hashtags — mix popular Indian news hashtags, topic-specific tags and trending tags

Important rules:
- Write like you are talking to a young Indian friend, not like a formal newspaper
- Use Hindi words occasionally like "yaar", "desh", "sach mein" to connect with Indian audience
- Use emojis throughout to make it visually engaging
- Keep total length between 1500-2000 characters
- Do NOT make up any facts — only use what is in the title and description above
- Make it feel exciting and worth sharing
"""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    data = response.json()
    try:
        caption = data["candidates"][0]["content"]["parts"][0]["text"]
        print("Caption generated successfully.")
        return caption
    except Exception as e:
        print(f"Caption generation error: {e}")
        return f"📰 {article['title']}\n\n{article.get('description', '')}\n\n📌 Source: {article['source']['name']}\n\n💬 What do you think? Comment below!\n👉 Follow @dailynewsflash_in for daily news!\n\n#news #breakingnews #india #dailynews #newsupdates"

# ── 4. Get smart image keyword using Gemini ───────────────────────────────────
def get_image_keyword(article):
    print("Getting smart image keyword...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
Given this news headline: "{article['title']}"

Give me ONE short generic search keyword (2-3 words max) that would find a relevant,
visually appealing stock photo on Unsplash for this news story.

Rules:
- Use generic visual concepts, NOT specific names of people or events
- Examples: "chess game board", "supreme court building", "ambulance emergency",
  "parliament building india", "cricket stadium crowd", "stock market graph",
  "protest crowd street", "military soldiers", "election voting booth",
  "bollywood cinema", "technology smartphone", "football stadium"
- Return ONLY the keyword, nothing else, no quotes, no explanation

Keyword:"""
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload)
    data = response.json()
    try:
        keyword = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print(f"Smart keyword: {keyword}")
        return keyword
    except:
        return "india news"

# ── 5. Fetch a relevant image from Unsplash ───────────────────────────────────
def fetch_image(keyword):
    print(f"Fetching image for keyword: {keyword}")
    url = "https://api.unsplash.com/search/photos"
    params = {
        "query": keyword,
        "per_page": 10,
        "orientation": "squarish",
        "client_id": UNSPLASH_ACCESS_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    results = data.get("results", [])
    if not results:
        print("No image found, trying fallback: india news")
        params["query"] = "india news"
        response = requests.get(url, params=params)
        data = response.json()
        results = data.get("results", [])
    if not results:
        print("No image found at all.")
        return None
    photo = random.choice(results[:5])
    image_url = photo["urls"]["regular"]
    img_response = requests.get(image_url, stream=True)
    image_path = "/tmp/news_image.jpg"
    with open(image_path, "wb") as f:
        for chunk in img_response.iter_content(1024):
            f.write(chunk)
    print("Image downloaded successfully.")
    return image_path

# ── 6. Design the Instagram post image ────────────────────────────────────────
def create_post_image(image_path, headline, source_name):
    print("Designing the post image...")
    img_size = (1080, 1080)
    if image_path:
        img = Image.open(image_path).convert("RGB")
        img = img.resize(img_size, Image.LANCZOS)
    else:
        img = Image.new("RGB", img_size, color=(20, 20, 40))
    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([(0, 580), (1080, 1080)], fill=(0, 0, 0, 185))
    overlay_draw.rectangle([(0, 0), (1080, 85)], fill=(0, 0, 0, 160))
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
    wrapped = textwrap.wrap(headline, width=30)
    y = 668
    for line in wrapped[:4]:
        draw.text((40, y), line, font=font_large, fill=(255, 255, 255))
        y += 62
    draw.rectangle([(0, 1020), (1080, 1080)], fill=(15, 15, 15))
    draw.text((40, 1034), "Follow @dailynewsflash_in for daily updates", font=font_small, fill=(180, 180, 180))
    output_path = "/tmp/final_post.jpg"
    img.save(output_path, "JPEG", quality=95)
    print("Post image created successfully.")
    return output_path

# ── 7. Upload image to Imgur ──────────────────────────────────────────────────
def upload_image_to_imgur(image_path):
    print("Uploading image to Imgur...")
    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode("utf-8")
    response = requests.post(
        "https://api.imgur.com/3/image",
        headers={"Authorization": "Client-ID 546c25a59c58ad7"},
        data={"image": image_data, "type": "base64"}
    )
    data = response.json()
    if data.get("success"):
        url = data["data"]["link"]
        print(f"Image uploaded: {url}")
        return url
    else:
        print(f"Imgur upload failed: {data}")
        return None

# ── 8. Post to Instagram using official API ───────────────────────────────────
def post_to_instagram(image_url, caption):
    print("Posting to Instagram via official API...")
    container_url = f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media"
    container_params = {
        "image_url": image_url,
        "caption": caption,
        "access_token": FB_ACCESS_TOKEN
    }
    container_response = requests.post(container_url, data=container_params)
    container_data = container_response.json()
    print(f"Container response: {container_data}")
    creation_id = container_data.get("id")
    if not creation_id:
        raise Exception(f"Media container creation failed: {container_data}")
    print(f"Media container created: {creation_id}")
    time.sleep(5)
    publish_url = f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish"
    publish_params = {
        "creation_id": creation_id,
        "access_token": FB_ACCESS_TOKEN
    }
    publish_response = requests.post(publish_url, data=publish_params)
    publish_data = publish_response.json()
    print(f"Publish response: {publish_data}")
    if "id" in publish_data:
        print("Post published successfully!")
    else:
        raise Exception(f"Publishing failed: {publish_data}")

# ── Main flow ─────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Instagram News Bot started at {datetime.now()} ===\n")

    article = fetch_news()
    if not article:
        print("No article found. Exiting.")
        return

    caption     = generate_caption(article)
    keyword     = get_image_keyword(article)
    image_path  = fetch_image(keyword)
    final_image = create_post_image(image_path, article["title"], article["source"]["name"])
    image_url   = upload_image_to_imgur(final_image)

    if not image_url:
        print("Image upload failed. Exiting.")
        return

    post_to_instagram(image_url, caption)

    print(f"\n=== Bot finished successfully at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
