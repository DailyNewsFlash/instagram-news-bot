"""
Runs BEFORE bot.py every time.
Exchanges FB_ACCESS_TOKEN for a never-expiring Page token
and saves it back to GitHub Secrets automatically.
"""
import os, requests, base64, sys

token      = os.environ.get("FB_ACCESS_TOKEN", "").strip()
app_id     = os.environ.get("FB_APP_ID", "").strip()
app_secret = os.environ.get("FB_APP_SECRET", "").strip()
page_id    = os.environ.get("FB_PAGE_ID", "").strip()
gh_token   = os.environ.get("GH_TOKEN", "").strip()
gh_repo    = os.environ.get("GH_REPO", "").strip()

print("=== FB Token Refresh ===")

if not all([token, app_id, app_secret, page_id]):
    print("❌ Missing FB credentials — cannot refresh")
    sys.exit(0)

# ── Step 1: Validate current token ───────────────────────────────────────────
check = requests.get("https://graph.facebook.com/v25.0/me",
                     params={"access_token": token}, timeout=10)
cd = check.json()
if "error" in cd:
    print(f"⚠️  Current token status: {cd['error'].get('message','unknown')}")
else:
    print(f"✅ Current token valid (user: {cd.get('name','?')})")

# ── Step 2: Exchange for long-lived token (60 days) ───────────────────────────
r = requests.get(
    "https://graph.facebook.com/v25.0/oauth/access_token",
    params={"grant_type": "fb_exchange_token",
            "client_id": app_id, "client_secret": app_secret,
            "fb_exchange_token": token}, timeout=15)
d = r.json()
ll_token = d.get("access_token", "")
if not ll_token:
    print(f"❌ Long-lived exchange failed: {d.get('error',{}).get('message','')}")
    print("Bot will try with existing token...")
    sys.exit(0)
print("✅ Long-lived token obtained (~60 days)")

# ── Step 3: Get Page token (never expires) ────────────────────────────────────
r2 = requests.get(
    f"https://graph.facebook.com/v25.0/{page_id}",
    params={"fields": "access_token", "access_token": ll_token}, timeout=15)
d2 = r2.json()
final_token = d2.get("access_token", ll_token)
if "access_token" in d2:
    print("✅ Page token obtained (never expires)")
else:
    print(f"⚠️  Page token unavailable, using 60-day token")

# ── Step 4: Save back to GitHub Secrets ──────────────────────────────────────
if not gh_token or not gh_repo:
    print("⚠️  PAT_TOKEN not set — cannot save to GitHub Secrets")
    print("    Add PAT_TOKEN secret to GitHub for permanent auto-refresh")
    sys.exit(0)

try:
    # Get repo public key
    key_resp = requests.get(
        f"https://api.github.com/repos/{gh_repo}/actions/secrets/public-key",
        headers={"Authorization": f"Bearer {gh_token}",
                 "Accept": "application/vnd.github+json"}, timeout=10)
    if key_resp.status_code != 200:
        print(f"❌ Cannot get public key: {key_resp.status_code}")
        sys.exit(0)

    key_data = key_resp.json()
    pub_key_b64 = key_data["key"]
    key_id = key_data["key_id"]

    # Encrypt with PyNaCl (already installed in workflow)
    from nacl import public as nacl_public
    pub_key_bytes = base64.b64decode(pub_key_b64)
    box = nacl_public.SealedBox(nacl_public.PublicKey(pub_key_bytes))
    encrypted = base64.b64encode(box.encrypt(final_token.encode())).decode()

    # Save secret
    resp = requests.put(
        f"https://api.github.com/repos/{gh_repo}/actions/secrets/FB_ACCESS_TOKEN",
        headers={"Authorization": f"Bearer {gh_token}",
                 "Accept": "application/vnd.github+json"},
        json={"encrypted_value": encrypted, "key_id": key_id}, timeout=10)

    if resp.status_code in [201, 204]:
        print("✅ FB_ACCESS_TOKEN saved to GitHub Secrets — auto-refresh complete!")
    else:
        print(f"❌ Failed to save secret: {resp.status_code} — {resp.text[:200]}")

except Exception as e:
    print(f"❌ Secret save error: {e}")

print("=== Token Refresh Done ===\n")
