import os
import requests
from PIL import Image, ImageDraw, ImageFont
from instagrapi import Client
import textwrap
from datetime import datetime
import random

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
INSTAGRAM_USERNAME  = os.environ["INSTAGRAM_USERNAME"]
INSTAGRAM_PASSWORD  = os.environ["INSTAGRAM_PASSWORD"]

# ── 1. Fetch trending news ─────────────────────────────────────────────────────
def fetch_news():
    print("Fetching trending news...")
    url = "https://gnews.io/api/v4/top-headlines"
    params = {
        "token": GNEWS_API_KEY,
        "lang": "en",
        "country": "in",
        "max": 10,
        "topic": "breaking-news"
    }
    response = requests.get(url, params=params)
    data = response.json()
    articles = data.get("articles", [])
    if not articles:
        print("No articles found.")
        return None
    article = random.choice(articles)
    print(f"Selected article: {article['title']}")
    return article

# ── 2. Generate caption using Google Gemini (free, no credit card) ────────────
def generate_caption(article):
    print("Generating caption with Gemini...")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = f"""
You are a professional Instagram news content creator for the account @dailynewsflash_in.

Write an engaging Instagram post caption for this news article:

Title: {article['title']}
Description: {article.get('description', '')}
Source: {article['source']['name']}
Published: {article['publishedAt']}

Requirements:
- Start with a strong hook (1 sentence that grabs attention)
- Summarize the news clearly in 2-3 sentences
- Mention the source like: Source: {article['source']['name']}
- End with: Comment your thoughts below and follow @dailynewsflash_in for daily news updates!
- Add 15 relevant hashtags at the end
- Keep total length under 2000 characters
- Use line breaks to make it readable
- Add relevant emojis to make it visually engaging
- Do NOT make up any facts - only use what is in the title and description above
"""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    response = requests.post(url, json=payload)
    data = response.json()
    try:
        caption = data["candidates"][0]["content"]["parts"][0]["text"]
        print("Caption generated successfully.")
        return caption
    except Exception as e:
        print(f"Caption generation error: {e}")
        print(f"Response: {data}")
        return f"{article['title']}\n\nSource: {article['source']['name']}\n\nFollow @dailynewsflash_in for more news!\n\n#news #breakingnews #india #dailynews #newsupdates"

# ── 3. Fetch a relevant image from Unsplash ───────────────────────────────────
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
        print("No image found, using fallback.")
        return None, None
    photo = random.choice(results[:5])
    image_url = photo["urls"]["regular"]
    photographer = photo["user"]["name"]
    img_response = requests.get(image_url, stream=True)
    image_path = "/tmp/news_image.jpg"
    with open(image_path, "wb") as f:
        for chunk in img_response.iter_content(1024):
            f.write(chunk)
    print(f"Image downloaded. Photo by: {photographer}")
    return image_path, photographer

# ── 4. Design the Instagram post image ────────────────────────────────────────
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

# ── 5. Post to Instagram ──────────────────────────────────────────────────────
def post_to_instagram(image_path, caption):
    print("Logging into Instagram...")
    cl = Client()
    cl.delay_range = [2, 5]
    cl.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
    print("Uploading post...")
    cl.photo_upload(image_path, caption)
    print("Post uploaded successfully!")

# ── Main flow ─────────────────────────────────────────────────────────────────
def main():
    print(f"\n=== Instagram News Bot started at {datetime.now()} ===\n")

    article = fetch_news()
    if not article:
        print("No article found. Exiting.")
        return

    caption     = generate_caption(article)
    keyword     = " ".join(article["title"].split()[:3])
    image_path, photographer = fetch_image(keyword)
    final_image = create_post_image(image_path, article["title"], article["source"]["name"])
    post_to_instagram(final_image, caption)

    print(f"\n=== Bot finished successfully at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
