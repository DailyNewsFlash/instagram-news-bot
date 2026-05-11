import os
import requests
import anthropic
from PIL import Image, ImageDraw, ImageFont
from instagrapi import Client
import textwrap
import json
from datetime import datetime
import random

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
INSTAGRAM_USERNAME  = os.environ["INSTAGRAM_USERNAME"]
INSTAGRAM_PASSWORD  = os.environ["INSTAGRAM_PASSWORD"]

# ── 1. Fetch trending news ─────────────────────────────────────────────────────
def fetch_news():
    print("Fetching trending news...")
    url = "https://gnews.io/api/v4/top-headlines"
    params = {
        "token": GNEWS_API_KEY,
        "lang": "en",
        "country": "in",   # India news — change to 'us' for world news
        "max": 10,
        "topic": "breaking-news"
    }
    response = requests.get(url, params=params)
    data = response.json()
    articles = data.get("articles", [])
    if not articles:
        print("No articles found.")
        return None
    # Pick a random article from the top 10 so we don't repeat the same one
    article = random.choice(articles)
    print(f"Selected article: {article['title']}")
    return article

# ── 2. Generate Instagram caption using Claude ────────────────────────────────
def generate_caption(article):
    print("Generating caption with Claude...")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
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
- Mention the source like: "Source: {article['source']['name']}"
- End with a call to action: ask followers to comment their thoughts and follow @dailynewsflash_in for more
- Add 15-20 relevant hashtags at the end
- Keep total length under 2000 characters
- Use line breaks to make it readable
- Add relevant emojis to make it visually engaging
- Do NOT make up any facts — only use what is in the title and description above
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    caption = message.content[0].text
    print("Caption generated successfully.")
    return caption

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
    # Download the image
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

    draw = ImageDraw.Draw(img)

    # Dark overlay at bottom for text readability
    overlay = Image.new("RGBA", img_size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.rectangle([(0, 600), (1080, 1080)], fill=(0, 0, 0, 180))
    overlay_draw.rectangle([(0, 0), (1080, 80)], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Try to load a font, fall back to default if not available
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
        font_brand = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    except:
        font_large = ImageFont.load_default()
        font_small = font_large
        font_brand = font_large

    # Brand name at top
    draw.text((40, 22), "@dailynewsflash_in", font=font_brand, fill=(255, 200, 50))

    # Source badge
    source_text = f"Source: {source_name}"
    draw.text((40, 620), source_text, font=font_small, fill=(150, 220, 255))

    # Wrap and draw headline
    wrapped = textwrap.wrap(headline, width=28)
    y = 680
    for line in wrapped[:4]:   # max 4 lines
        draw.text((40, y), line, font=font_large, fill=(255, 255, 255))
        y += 65

    # Bottom bar
    draw.rectangle([(0, 1020), (1080, 1080)], fill=(20, 20, 20))
    draw.text((40, 1032), "Follow for daily news updates", font=font_small, fill=(180, 180, 180))

    output_path = "/tmp/final_post.jpg"
    img.save(output_path, "JPEG", quality=95)
    print("Post image created successfully.")
    return output_path

# ── 5. Post to Instagram ──────────────────────────────────────────────────────
def post_to_instagram(image_path, caption):
    print("Logging into Instagram...")
    cl = Client()
    cl.delay_range = [2, 5]   # polite delay between actions
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

    caption    = generate_caption(article)
    keyword    = article["title"].split()[0:3]
    keyword    = " ".join(keyword)
    image_path, photographer = fetch_image(keyword)
    final_image = create_post_image(image_path, article["title"], article["source"]["name"])
    post_to_instagram(final_image, caption)

    print(f"\n=== Bot finished successfully at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
