import os
import requests
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime
import random

# ── API keys from GitHub Secrets ──────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"]
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"]
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"]
FB_PAGE_ID          = os.environ["FB_PAGE_ID"]
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"]

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

# ── 2. Generate caption using Google Gemini ───────────────────────────────────
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

# ── 5. Get Instagram Business Account ID from Facebook Page ───────────────────
def get_instagram_account_id():
    print("Getting Instagram Business Account ID...")
    url = f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}"
    params = {
        "fields": "instagram_business_account",
        "access_token": FB_ACCESS_TOKEN
    }
    response = requests.get(url, params=params)
    data = response.json()
    print(f"Page data: {data}")
    ig_account = data.get("instagram_business_account", {})
    ig_id = ig_account.get("id")
    if not ig_id:
        # fallback: use page ID directly
        ig_id = FB_PAGE_ID
    print(f"Instagram Account ID: {ig_id}")
    return ig_id

# ── 6. Upload image to a public URL using Imgur (free) ────────────────────────
def upload_image_to_imgur(image_path):
    print("Uploading image to Imgur for public URL...")
    # Use a simple image hosting approach via Unsplash CDN already downloaded
    # Instead we'll use the file directly via base64 with Imgur API
    with open(image_path, "rb") as f:
        import base64
        image_data = base64.b64encode(f.read()).decode("utf-8")
    
    response = requests.post(
        "https://api.imgur.com/3/image",
        headers={"Authorization": "Client-ID 546c25a59c58ad7"},
        data={"image": image_data, "type": "base64"}
    )
    data = response.json()
    print(f"Imgur response: {data.get('success')}")
    if data.get("success"):
        url = data["data"]["link"]
        print(f"Image uploaded: {url}")
        return url
    else:
        print(f"Imgur upload failed: {data}")
        return None

# ── 7. Post to Instagram using official API ───────────────────────────────────
def post_to_instagram(ig_account_id, image_url, caption):
    print("Posting to Instagram via official API...")
    
    # Step 1: Create media container
    container_url = f"https://graph.facebook.com/v25.0/{ig_account_id}/media"
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
        print(f"Failed to create media container: {container_data}")
        raise Exception(f"Media container creation failed: {container_data}")
    
    print(f"Media container created: {creation_id}")
    
    # Step 2: Publish the container
    import time
    time.sleep(5)  # wait a moment before publishing
    
    publish_url = f"https://graph.facebook.com/v25.0/{ig_account_id}/media_publish"
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
    keyword     = " ".join(article["title"].split()[:3])
    image_path  = fetch_image(keyword)
    final_image = create_post_image(image_path, article["title"], article["source"]["name"])
    image_url   = upload_image_to_imgur(final_image)
    
    if not image_url:
        print("Image upload failed. Exiting.")
        return
    
    ig_account_id = get_instagram_account_id()
    post_to_instagram(ig_account_id, image_url, caption)

    print(f"\n=== Bot finished successfully at {datetime.now()} ===\n")

if __name__ == "__main__":
    main()
