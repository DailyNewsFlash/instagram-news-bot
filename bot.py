import os, requests, random, base64, time, sys, re, textwrap
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
from urllib.parse import quote

# ── Secrets ───────────────────────────────────────────────────────────────────
GNEWS_API_KEY       = os.environ["GNEWS_API_KEY"].strip()
UNSPLASH_ACCESS_KEY = os.environ["UNSPLASH_ACCESS_KEY"].strip()
GEMINI_API_KEY      = os.environ["GEMINI_API_KEY"].strip()
FB_ACCESS_TOKEN     = os.environ["FB_ACCESS_TOKEN"].strip()
IG_ACCOUNT_ID       = os.environ["IG_ACCOUNT_ID"].strip()
PEXELS_API_KEY      = os.environ.get("PEXELS_API_KEY","").strip()
PIXABAY_API_KEY     = os.environ.get("PIXABAY_API_KEY","").strip()

# ── Gemini setup ──────────────────────────────────────────────────────────────
GEMINI_MODELS = ["gemini-2.0-flash-lite","gemini-2.0-flash","gemini-1.5-flash-8b","gemini-1.5-flash"]
_GEMINI_KEYS  = [k.strip() for k in [
    os.environ.get("GEMINI_API_KEY",""),
    os.environ.get("GEMINI_API_KEY_2",""),
] if k.strip()]
_key_idx = 0
_last_call: dict = {}

def _next_key():
    global _key_idx
    if not _GEMINI_KEYS: return ""
    k = _GEMINI_KEYS[_key_idx % len(_GEMINI_KEYS)]
    _key_idx += 1
    return k

def call_gemini(prompt):
    if not _GEMINI_KEYS:
        return None
    payload = {"contents":[{"parts":[{"text":prompt}]}]}
    for model in GEMINI_MODELS:
        for attempt in range(2):
            key = _next_key()
            gap = time.time() - _last_call.get(key, 0)
            if gap < 5: time.sleep(5 - gap)
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
                _last_call[key] = time.time()
                r = requests.post(url, json=payload, timeout=30)
                d = r.json()
                if "candidates" in d:
                    print(f"Gemini OK ({model})")
                    return d["candidates"][0]["content"]["parts"][0]["text"].strip()
                err = d.get("error",{})
                if err.get("code") == 429 or "quota" in err.get("message","").lower():
                    wait = min(20 + attempt*10, 30)
                    print(f"Rate limit ({model}), waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"Gemini error ({model}): {err.get('message','')}")
                    break
            except Exception as e:
                print(f"Gemini exception: {e}")
                time.sleep(3)
    print("All Gemini options failed — using rule-based fallback")
    return None

# ── RSS feeds ─────────────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("https://feeds.feedburner.com/ndtvnews-top-stories",               "NDTV"),
    ("https://timesofindia.indiatimes.com/rssfeedstopstories.cms",      "Times of India"),
    ("https://www.thehindu.com/news/feeder/default.rss",                "The Hindu"),
    ("https://indianexpress.com/feed/",                                 "Indian Express"),
    ("https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "Hindustan Times"),
    ("https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",         "BBC India"),
    ("https://timesofindia.indiatimes.com/rssfeeds/4719148.cms",        "TOI Sports"),
    ("https://economictimes.indiatimes.com/rssfeedstopstories.cms",     "Economic Times"),
    ("https://feeds.feedburner.com/gadgets360-latest",                  "Gadgets360"),
]

def _clean(text):
    t = re.sub(r"<[^>]+>", "", text)
    for a,b in [("&lt;","<"),("&gt;",">"),("&amp;","&"),("&nbsp;"," "),("&#39;","'"),("&quot;",'"')]:
        t = t.replace(a, b)
    return " ".join(t.split())

def _fetch_rss(url, source):
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent":"NewsBot/1.0"})
        if r.status_code != 200: return []
        arts = []
        for item in r.text.split("<item>")[1:15]:
            def tag(t):
                s,e = item.find(f"<{t}>"), item.find(f"</{t}>")
                return _clean(item[s+len(t)+2:e]) if s!=-1 and e!=-1 else ""
            title = tag("title")
            desc  = _clean(tag("description"))[:300]
            if title and len(title)>10:
                arts.append({"title":title,"description":desc,"url":tag("link"),
                             "source":{"name":source},"_topic":"general"})
        return arts
    except Exception as e:
        print(f"RSS {source}: {e}")
        return []

# ── Fetch articles ─────────────────────────────────────────────────────────────
SKIP_SOURCES = ["guardian","washington post","new york times","fox news","bloomberg"]
INDIA_KEYS   = ["india","indian","modi","bjp","congress","delhi","mumbai","rupee",
                "isro","ipl","cricket","bollywood","supreme court","pakistan"]

def fetch_articles():
    print("Fetching articles...")
    all_arts = []

    # GNews (max 2 calls)
    for params in [
        {"token":GNEWS_API_KEY,"lang":"en","country":"in","max":10},
        {"token":GNEWS_API_KEY,"lang":"en","country":"in","max":10,
         "q":random.choice(["India crime","cricket India","India politics",
                            "India economy","bollywood","India scam","ISRO"]),
         "sortby":"publishedAt"},
    ]:
        try:
            endpoint = "top-headlines" if "q" not in params else "search"
            r = requests.get(f"https://gnews.io/api/v4/{endpoint}",
                             params=params, timeout=10)
            arts = r.json().get("articles",[])
            for a in arts: a["_topic"] = params.get("q","top")
            all_arts.extend(arts)
            print(f"GNews: {len(arts)} articles")
        except Exception as e:
            print(f"GNews error: {e}")

    # RSS feeds
    for feed_url, feed_name in random.sample(RSS_FEEDS, min(5, len(RSS_FEEDS))):
        all_arts.extend(_fetch_rss(feed_url, feed_name))

    # Deduplicate + filter
    seen, unique = set(), []
    for a in all_arts:
        t = a["title"].strip().lower()
        src = a["source"]["name"].lower()
        if t in seen or len(t)<10: continue
        seen.add(t)
        if any(s in src for s in SKIP_SOURCES) and not any(k in t for k in INDIA_KEYS):
            continue
        unique.append(a)
    print(f"Unique India-relevant: {len(unique)}")
    if not unique: return None

    # Gemini picks best
    if len(unique) > 1:
        titles = "\n".join([f"{i+1}. {a['title']}" for i,a in enumerate(unique[:25])])
        ans = call_gemini(
            f"You are a viral Indian Instagram news editor.\n"
            f"Pick the SINGLE BEST article for maximum engagement from young Indians (18-35).\n"
            f"Prioritise: crime, court verdicts, cricket, ISRO, scandal, protest, govt decisions.\n"
            f"Avoid: PR fluff, celebrity meetups, dry reports.\n\n{titles}\n\n"
            f"Reply with ONLY one number. Example: 7"
        )
        if ans:
            try:
                n = int(re.search(r'\d+', ans).group())
                if 1 <= n <= len(unique):
                    print(f"Gemini picked article #{n}: {unique[n-1]['title'][:60]}")
                    return unique[n-1]
            except: pass

    # Score-based fallback
    HIGH = ["murder","rape","arrest","scam","fraud","verdict","protest",
            "cricket","ipl","isro","explosion","flood","crash","war"]
    def score(a):
        t = a["title"].lower()
        s = sum(3 for k in INDIA_KEYS if k in t)
        s += sum(5 for k in HIGH if k in t)
        return s
    unique.sort(key=score, reverse=True)
    print(f"Rule-based pick: {unique[0]['title'][:60]}")
    return unique[0]

# ── Analyse article (ONE Gemini call for everything) ──────────────────────────
def analyse(article):
    title = article["title"]
    desc  = article.get("description","")[:300]
    src   = article["source"]["name"]
    t     = title.lower()

    # Rule-based keyword
    def rule_kw():
        if any(w in t for w in ["murder","kill","rape","crime","arrest","dead"]):
            return "crime scene police tape dark investigation"
        if any(w in t for w in ["cricket","ipl","t20","odi","bcci"]):
            return "cricket stadium floodlights night match"
        if any(w in t for w in ["court","verdict","sc","cbi","ed","judge"]):
            return "supreme court building exterior stone pillars"
        if any(w in t for w in ["isro","rocket","space","satellite","chandrayaan"]):
            return "rocket launch fire smoke night sky"
        if any(w in t for w in ["flood","earthquake","cyclone","disaster"]):
            return "flood disaster rescue boat water"
        if any(w in t for w in ["protest","strike","rally","agitation"]):
            return "protest crowd street demonstration"
        if any(w in t for w in ["scam","fraud","crypto","ponzi","hack"]):
            return "handcuffs police arrest investigation"
        if any(w in t for w in ["modi","bjp","congress","parliament","election"]):
            return "parliament building dome architecture"
        if any(w in t for w in ["bollywood","film","actor","actress","movie"]):
            return "film camera crew set dramatic lights"
        if any(w in t for w in ["economy","inflation","rupee","market","gdp","rbi"]):
            return "stock market trading screen finance"
        return "india city skyline dramatic dusk"

    # Rule-based AI image prompt
    def rule_ai():
        if any(w in t for w in ["murder","kill","rape","crime","arrest"]):
            return "dark crime scene yellow police tape rain dramatic cinematic no people"
        if any(w in t for w in ["cricket","ipl","t20"]):
            return "empty cricket stadium floodlights night dramatic wide angle cinematic"
        if any(w in t for w in ["court","verdict","judge"]):
            return "grand supreme court building stone exterior dramatic storm clouds cinematic"
        if any(w in t for w in ["isro","rocket","space"]):
            return "rocket on launchpad night fire smoke dramatic sky cinematic"
        if any(w in t for w in ["flood","disaster","cyclone"]):
            return "flooded village rescue boat dramatic storm clouds cinematic"
        if any(w in t for w in ["protest","strike","rally"]):
            return "empty city street night dramatic lights cinematic wide angle"
        if any(w in t for w in ["scam","fraud","crypto"]):
            return "dark office computer screen data dramatic cinematic no people"
        if any(w in t for w in ["parliament","modi","election"]):
            return "parliament building dome night dramatic lighting cinematic"
        return "dramatic india city skyline dusk golden hour cinematic"

    # Rule-based caption
    def rule_caption():
        if any(w in t for w in ["murder","kill","rape","crime","arrest","dead"]):
            hook = f"🚨 SHOCKING: {title}"
            why  = "This case raises serious questions about law enforcement and public safety in India."
            cta  = "💬 Should the punishment be stricter? Comment 👇"
            tags = "#india #crime #indianews #justice #breakingnews #viral #law #ndtv #shocking #IndiaNews #dailynewsflash #currentaffairs #trending #indiatoday #safetyIndia #crimeindia #news #policeindia #justiceforall #indianpolice #criminaljustice #outrage #crimewatch #latestnews #indiaalert"
        elif any(w in t for w in ["cricket","ipl","t20","odi","bcci"]):
            hook = f"🏏 BIG NEWS: {title}"
            why  = "Indian cricket fans across the country are reacting — opinions are divided!"
            cta  = "💬 What do you think? Comment below 👇"
            tags = "#cricket #india #ipl #t20 #teamIndia #bcci #breakingnews #cricketlovers #indiancricket #viratkohli #rohitsharma #ipl2026 #t20worldcup #dailynewsflash #cricketfans #indiacricket #cricketindia #cricketnews #sports #trending #viral #sportsnews #indianews #news #cricketworld"
        elif any(w in t for w in ["court","verdict","sc","cbi","ed","judge"]):
            hook = f"⚖️ VERDICT: {title}"
            why  = "This ruling sets a major precedent for how similar cases are handled across India."
            cta  = "💬 Do you agree with this verdict? 👇"
            tags = "#india #supremecourt #verdict #law #justice #breakingnews #indianews #cbi #highcourt #legalindia #dailynewsflash #trending #viral #news #currentaffairs #judiciary #indianlaw #lawandorder #courtverdict #indialegal #ndtv #indiatoday #legal #supremecourtofindia #justiceindia"
        elif any(w in t for w in ["isro","rocket","space","satellite","chandrayaan"]):
            hook = f"🚀 INDIA IN SPACE: {title}"
            why  = "ISRO continues to make every Indian proud on the global stage!"
            cta  = "💬 Proud of ISRO? 🇮🇳 Comment below!"
            tags = "#isro #india #space #rocket #chandrayaan #gaganyaan #science #technology #breakingnews #indianews #proudlyindian #spaceindia #isroindia #dailynewsflash #trending #viral #news #spaceexploration #indianscience #techindia #sciencenews #isronews #indiaspace #moonmission #currentaffairs"
        elif any(w in t for w in ["modi","bjp","congress","parliament","election"]):
            hook = f"🔴 POLITICAL BOMBSHELL: {title}"
            why  = "This political development could impact millions of citizens across India."
            cta  = "💬 What's your take? No filter — comment below! 👇"
            tags = "#india #politics #modi #bjp #congress #breakingnews #indianews #parliament #election #government #dailynewsflash #trending #viral #news #currentaffairs #indianpolitics #politicsnews #indiaelection #ndtv #indiatoday #politicalindia #bjpindia #congressindia #rahulgandhi #narendramodi"
        elif any(w in t for w in ["bollywood","film","actor","actress","movie","ott"]):
            hook = f"🎬 BOLLYWOOD BUZZ: {title}"
            why  = "The entire film industry and fans are talking about this right now!"
            cta  = "💬 Your reaction? Comment below 👇"
            tags = "#bollywood #india #entertainment #film #movies #breakingnews #celebrity #indianews #dailynewsflash #trending #viral #news #bollywoodgossip #filmyindia #ott #bollywoodfans #starnews #actornews #actressnews #hindimovies #filmfare #bollywoodnews #entertainment #indiaentertainment #celebnews"
        elif any(w in t for w in ["flood","earthquake","cyclone","disaster","rain"]):
            hook = f"⚠️ DISASTER: {title}"
            why  = "Millions of Indians are affected. Our thoughts are with those impacted."
            cta  = "💬 Stay safe. Share to spread awareness 👇"
            tags = "#india #disaster #flood #earthquake #breakingnews #indianews #naturaldisaster #disasterrelief #dailynewsflash #trending #viral #news #currentaffairs #ndrf #indiadisaster #climatechange #weatherindia #floodindia #cycloneindia #staysafe #emergencyindia #rescueoperation #disasternews #helpindia #ndtv"
        elif any(w in t for w in ["economy","inflation","rupee","rbi","budget","gdp","market"]):
            hook = f"📉 ECONOMY ALERT: {title}"
            why  = "This directly affects your wallet and the daily life of every Indian household."
            cta  = "💬 Are you feeling the impact? Tell us below 👇"
            tags = "#india #economy #inflation #rupee #rbi #budget #breakingnews #indianews #dailynewsflash #trending #viral #news #currentaffairs #stockmarket #finance #moneyindia #indianeconomy #financenews #businessindia #rupeefall #sensex #nifty #economynews #indianfinance #businessnews"
        else:
            hook = f"⚡ BREAKING: {title}"
            why  = "This is one of the most talked-about stories in India right now."
            cta  = "💬 What's your take? Comment below 👇"
            tags = "#india #breakingnews #indianews #dailynewsflash #news #indiatoday #ndtv #trending #viral #currentaffairs #latestnews #indiaupdates #newsindia #todaynews #flashnews #dailynews #newsupdate #topnews #indianmedia #newsflash #latestindia #indiaalert #breakingnewsindia #urgentindia #newsnow"

        # Build key facts from description
        facts = ""
        if desc and len(desc) > 50:
            sents = [s.strip() for s in re.split(r'[.!?]', desc) if len(s.strip()) > 20]
            if sents:
                facts = f"\n\n🔍 KEY DETAILS:\n• {sents[0]}."
                if len(sents) > 1:
                    facts += f"\n• {sents[1]}."

        return (f"{hook}\n\n"
                f"📖 WHAT HAPPENED:\n{desc}\n"
                f"{facts}\n\n"
                f"{why}\n\n"
                f"{cta}\n"
                f"👉 Follow @dailynewsflash_in — Flash news. Zero fluff. ⚡\n\n"
                f"📌 Source: {src}\n\n{tags}")

    # Try Gemini first
    prompt = f"""You are an expert Indian news Instagram editor.
Analyse this article and return EXACTLY these four sections:

Title: {title}
Description: {desc}
Source: {src}

PHOTO_KEYWORD: [3-5 word stock photo search — scene/object, NEVER person/face/flag]
AI_IMAGE_PROMPT: [max 15 words, photorealistic, cinematic, NO people, NO faces, NO text]
SUMMARY: [2 sentences, max 40 words, specific facts — names/places/numbers from article]
CAPTION:
[Full Instagram caption with:
1. Punchy hook 🚨/⚡/🔴
2. 📖 WHAT HAPPENED — 5-6 sentences with WHO (full name+age), WHERE (exact place), WHEN, HOW, current status
3. 🔍 KEY FACTS — 2-3 bullet points with specific details
4. 🤔 WHY IT MATTERS TO INDIA — 2 sentences
5. 🔥 THE CONTROVERSY — what are people arguing about?
6. Hot take in Indian slang
7. 📌 Source: {src}
8. 💬 Comment CTA + 👉 Follow CTA
9. 25 topic-specific hashtags]

Format EXACTLY:
PHOTO_KEYWORD: ...
AI_IMAGE_PROMPT: ...
SUMMARY: ...
CAPTION:
..."""

    result = call_gemini(prompt)
    if result:
        try:
            kw, ai, summ, cap = None, None, None, None
            lines = result.split("\n")
            cap_lines = []
            in_cap = False
            for line in lines:
                if line.startswith("PHOTO_KEYWORD:"):
                    kw = line.split(":",1)[1].strip().strip('"')
                elif line.startswith("AI_IMAGE_PROMPT:"):
                    ai = line.split(":",1)[1].strip().strip('"')
                elif line.startswith("SUMMARY:"):
                    summ = line.split(":",1)[1].strip()
                elif line.startswith("CAPTION:"):
                    in_cap = True
                elif in_cap:
                    cap_lines.append(line)
            cap = "\n".join(cap_lines).strip()
            if kw and cap:
                return kw, ai or rule_ai(), summ or desc[:100], cap
        except Exception as e:
            print(f"Gemini parse error: {e}")

    # Full rule-based fallback
    return rule_kw(), rule_ai(), desc[:150], rule_caption()

# ── Image fetching ─────────────────────────────────────────────────────────────
def fetch_image(keyword, ai_prompt, save_path="/tmp/img.jpg"):
    candidates = []

    # Unsplash
    try:
        r = requests.get("https://api.unsplash.com/search/photos",
                         params={"query":keyword,"per_page":15,
                                 "page":random.randint(1,3),"orientation":"squarish",
                                 "client_id":UNSPLASH_ACCESS_KEY}, timeout=10)
        results = r.json().get("results",[])
        if results:
            p = random.choice(results[:10])
            candidates.append(("Unsplash", p["urls"]["regular"], p.get("likes",0)))
            print(f"Unsplash: {len(results)} results")
    except Exception as e: print(f"Unsplash: {e}")

    # Pexels
    if PEXELS_API_KEY:
        try:
            r = requests.get("https://api.pexels.com/v1/search",
                             headers={"Authorization":PEXELS_API_KEY},
                             params={"query":keyword,"per_page":15,
                                     "page":random.randint(1,3)}, timeout=10)
            photos = r.json().get("photos",[])
            if photos:
                p = random.choice(photos[:10])
                candidates.append(("Pexels", p["src"]["large2x"], 1000))
                print(f"Pexels: {len(photos)} results")
        except Exception as e: print(f"Pexels: {e}")

    # Pixabay
    if PIXABAY_API_KEY:
        try:
            r = requests.get("https://pixabay.com/api/",
                             params={"key":PIXABAY_API_KEY,"q":keyword,
                                     "image_type":"photo","per_page":15,
                                     "page":random.randint(1,3),
                                     "safesearch":"true","min_width":800}, timeout=10)
            hits = r.json().get("hits",[])
            if hits:
                p = random.choice(hits[:10])
                candidates.append(("Pixabay", p["webformatURL"], p.get("likes",0)))
                print(f"Pixabay: {len(hits)} results")
        except Exception as e: print(f"Pixabay: {e}")

    # Download best real photo
    if candidates:
        pexels = [c for c in candidates if c[0]=="Pexels"]
        src, url, _ = pexels[0] if pexels else max(candidates, key=lambda x:x[2])
        try:
            r = requests.get(url, stream=True, timeout=20)
            if r.status_code == 200:
                with open(save_path,"wb") as f:
                    for chunk in r.iter_content(4096): f.write(chunk)
                img = Image.open(save_path)
                w,h = img.size
                if w>=500 and h>=500 and 0.5<=w/h<=2.0:
                    print(f"Photo from {src} ({w}x{h})")
                    return save_path, src
        except Exception as e: print(f"Photo download: {e}")

    # AI fallback — Pollinations
    print("Generating AI image...")
    for seed in [random.randint(1,99999), random.randint(1,99999)]:
        try:
            full = f"{ai_prompt}, photorealistic, 4k, cinematic, no text, no watermark"
            url  = (f"https://image.pollinations.ai/prompt/{quote(full)}"
                    f"?width=1080&height=1080&seed={seed}&model=flux&nologo=true")
            r = requests.get(url, timeout=90, stream=True)
            if r.status_code==200 and "image" in r.headers.get("content-type",""):
                p = save_path.replace(".jpg",f"_ai{seed}.jpg")
                with open(p,"wb") as f:
                    for chunk in r.iter_content(4096): f.write(chunk)
                img = Image.open(p)
                if img.size[0]>100:
                    print(f"AI image OK ({img.size})")
                    return p, "AI Generated"
        except Exception as e: print(f"AI image: {e}")
        time.sleep(2)

    return None, "none"

# ── Image design ───────────────────────────────────────────────────────────────
def _fonts():
    base = "/usr/share/fonts/truetype/dejavu/"
    try:
        return {
            "brand":  ImageFont.truetype(base+"DejaVuSans-Bold.ttf", 36),
            "tag":    ImageFont.truetype(base+"DejaVuSans-Bold.ttf", 22),
            "source": ImageFont.truetype(base+"DejaVuSans-Bold.ttf", 26),
            "head":   ImageFont.truetype(base+"DejaVuSans-Bold.ttf", 52),
            "body":   ImageFont.truetype(base+"DejaVuSans.ttf", 28),
            "small":  ImageFont.truetype(base+"DejaVuSans.ttf", 26),
        }
    except:
        d = ImageFont.load_default()
        return {k:d for k in ["brand","tag","source","head","body","small"]}

def _topic_tag(title):
    t = title.lower()
    if any(w in t for w in ["murder","crime","rape","arrest","fraud","scam"]): return "CRIME"
    if any(w in t for w in ["cricket","ipl","match","t20","odi","bcci"]):      return "CRICKET"
    if any(w in t for w in ["court","verdict","cbi","ed","judge","bail"]):     return "JUSTICE"
    if any(w in t for w in ["isro","space","rocket","satellite","moon"]):      return "SPACE"
    if any(w in t for w in ["bollywood","film","actor","actress","ott"]):      return "BOLLYWOOD"
    if any(w in t for w in ["inflation","rupee","rbi","gdp","budget","market"]):"ECONOMY"
    if any(w in t for w in ["protest","strike","rally","agitation"]):          return "PROTEST"
    if any(w in t for w in ["pakistan","china","border","military","army"]):   return "WORLD"
    if any(w in t for w in ["modi","bjp","congress","parliament","election"]): return "POLITICS"
    if any(w in t for w in ["flood","earthquake","cyclone","disaster"]):       return "DISASTER"
    return "INDIA"

def create_image(image_path, image_src, headline, source, summary,
                 out="/tmp/post.jpg"):
    sz = (1080,1080)
    img = (Image.open(image_path).convert("RGB").resize(sz, Image.LANCZOS)
           if image_path else Image.new("RGB", sz, (18,18,35)))

    ov = Image.new("RGBA", sz, (0,0,0,0))
    od = ImageDraw.Draw(ov)
    # Gradient from mid to bottom
    for i in range(24):
        od.rectangle([(0, 510+i*24),(1080,510+(i+1)*24)],
                     fill=(0,0,0, min(160+i*4, 240)))
    od.rectangle([(0,0),(1080,95)],  fill=(0,0,0,185))   # top bar
    od.rectangle([(0,510),(8,1080)], fill=(220,30,30,255)) # red accent
    img = Image.alpha_composite(img.convert("RGBA"),ov).convert("RGB")
    draw = ImageDraw.Draw(img)
    f = _fonts()

    # Brand
    draw.text((28,26), "⚡ DAILY NEWS FLASH", font=f["brand"], fill=(255,200,50))
    draw.text((920,26), "IN", font=f["brand"], fill=(220,30,30))

    # Topic tag
    tag = _topic_tag(headline)
    tw  = len(tag)*13+20
    draw.rectangle([(1070-tw,58),(1068,84)], fill=(220,30,30))
    draw.text((1072-tw, 61), tag, font=f["tag"], fill=(255,255,255))

    # AI badge
    if image_src == "AI Generated":
        draw.rectangle([(28,520),(215,545)], fill=(80,0,150))
        draw.text((34,523), "✨ AI ILLUSTRATED", font=f["tag"], fill=(220,180,255))

    # Source
    draw.text((25,560), f"📌 {source.upper()}", font=f["source"], fill=(100,190,255))

    # Headline (max 3 lines)
    y = 610
    for line in textwrap.wrap(headline, width=28)[:3]:
        draw.text((22,y), line, font=f["head"], fill=(255,255,255))
        y += 62

    # Summary on card
    if summary:
        clean = _clean(summary)
        if clean:
            y += 6
            draw.rectangle([(0,y-3),(1080,y-1)], fill=(220,30,30))
            y += 8
            for line in textwrap.wrap(clean, width=44)[:3]:
                draw.text((22,y), line, font=f["body"], fill=(210,210,210))
                y += 36

    # Footer
    draw.rectangle([(0,1022),(1080,1080)], fill=(10,10,10))
    draw.text((22,1036), "👉 Follow @dailynewsflash_in for daily updates",
              font=f["small"], fill=(185,185,185))

    img.save(out, "JPEG", quality=95)
    print("Image created.")
    return out

# ── Upload to Imgur ────────────────────────────────────────────────────────────
def upload_imgur(path):
    with open(path,"rb") as f:
        data = base64.b64encode(f.read()).decode()
    try:
        r = requests.post("https://api.imgur.com/3/image",
                          headers={"Authorization":"Client-ID 546c25a59c58ad7"},
                          data={"image":data,"type":"base64"}, timeout=30)
        d = r.json()
        if d.get("success"):
            print(f"Imgur: {d['data']['link']}")
            return d["data"]["link"]
        print(f"Imgur failed: {d}")
    except Exception as e: print(f"Imgur: {e}")
    return None

# ── Post to Instagram ──────────────────────────────────────────────────────────
def post_to_instagram(image_url, caption):
    token = FB_ACCESS_TOKEN
    print("Creating media container...")
    r = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media",
        data={"image_url":image_url,"caption":caption,"access_token":token},
        timeout=30)
    result = r.json()
    cid = result.get("id")
    if not cid:
        err = result.get("error",{})
        code = err.get("code","?")
        msg  = err.get("message", str(result))
        if code in [190,463] or "expired" in msg.lower():
            print("❌ FB TOKEN EXPIRED")
            print("   Go to: developers.facebook.com/tools/explorer")
            print("   Generate token → me/accounts → copy → update FB_ACCESS_TOKEN secret")
        else:
            print(f"❌ Container error ({code}): {msg}")
        sys.exit(0)

    print(f"Container created: {cid} — waiting 8s...")
    time.sleep(8)

    r2 = requests.post(
        f"https://graph.facebook.com/v25.0/{IG_ACCOUNT_ID}/media_publish",
        data={"creation_id":cid,"access_token":token}, timeout=30)
    result2 = r2.json()
    if "id" in result2:
        print(f"✅ POSTED! Instagram post ID: {result2['id']}")
    else:
        print(f"❌ Publish failed: {result2}")
        sys.exit(0)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"Bot started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    keys_status = (f"GNews={'✅' if GNEWS_API_KEY else '❌'} | "
                   f"Gemini={'✅' if GEMINI_API_KEY else '❌'} | "
                   f"Gemini2={'✅' if os.environ.get('GEMINI_API_KEY_2') else '⚠️'} | "
                   f"Unsplash={'✅' if UNSPLASH_ACCESS_KEY else '❌'} | "
                   f"Pexels={'✅' if PEXELS_API_KEY else '⚠️'} | "
                   f"Pixabay={'✅' if PIXABAY_API_KEY else '⚠️'}")
    print(f"Keys: {keys_status}")
    print('='*50 + '\n')

    # Fetch best article
    article = fetch_articles()
    if not article:
        print("⚠️ No articles found — skipping this run")
        sys.exit(0)
    print(f"\n📰 Selected: {article['title']}\n")

    # Analyse (Gemini or rule-based)
    keyword, ai_prompt, summary, caption = analyse(article)
    print(f"Keyword: {keyword}")
    print(f"Summary: {summary[:80]}...")

    # Fetch image
    img_path, img_src = fetch_image(keyword, ai_prompt)

    # Create designed image
    post_img = create_image(img_path, img_src, article["title"],
                            article["source"]["name"], summary)

    # Upload
    img_url = upload_imgur(post_img)
    if not img_url:
        print("⚠️ Upload failed — skipping")
        sys.exit(0)

    # Post
    post_to_instagram(img_url, caption)

    print(f"\n{'='*50}")
    print(f"✅ Done: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*50 + '\n')

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback; traceback.print_exc()
        sys.exit(0)  # Exit 0 = don't mark as failed, next run tries again
