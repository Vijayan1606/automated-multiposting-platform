# Automated Multi-Platform Posting System — Credentials Setup Guide

## Quick Setup Checklist

Copy this file and fill in each section. Then save as `.env` in your project root.

---

## 1. TELEGRAM

### Step-by-step:
1. Open Telegram, search for **@BotFather**
2. Send `/newbot` and follow prompts to get your **Bot Token**
3. Create a channel or group and **add your bot as an admin**
4. To get the **Chat ID**:
   - Send a test message to the channel
   - Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Find `"chat": {"id": -1001234567890}` in the response

```
TELEGRAM_BOT_TOKEN=1234567890:ABCDEFghijklmno-pqrstuvwxyz
TELEGRAM_CHAT_ID=-1001234567890
```

---

## 2. BLUESKY

### Step-by-step:
1. Go to **https://bsky.app** and log in
2. Navigate to: **Settings → App Passwords → Add App Password**
3. Name it (e.g. "posting-system") and copy the generated password
4. Your identifier is your handle, e.g. `yourname.bsky.social`

```
BLUESKY_IDENTIFIER=yourname.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

---

## 3. MASTODON

### Step-by-step:
1. Log into your Mastodon instance (e.g. mastodon.social)
2. Go to **Preferences → Development → New Application**
3. Name it, check `write:statuses` scope, click Submit
4. Copy the **Access Token** shown on the next screen

```
MASTODON_INSTANCE_URL=https://mastodon.social
MASTODON_ACCESS_TOKEN=your_access_token_here
```

---

## 4. LINKEDIN

### Step-by-step:
1. Go to **https://www.linkedin.com/developers/apps** → Create App
2. Under **Products**, request: **Share on LinkedIn** and **Sign In with LinkedIn**
3. After approval, use the OAuth 2.0 flow to get a token with scopes:
   - `r_liteprofile`
   - `w_member_social`
4. Get your Person URN:
   ```
   GET https://api.linkedin.com/v2/me
   Authorization: Bearer <your_token>
   ```
   The response `id` field is your Person URN (format: `urn:li:person:XXXXXXXX`)

> ⚠️ LinkedIn tokens expire after **60 days**. You'll need to re-authenticate when it expires.

```
LINKEDIN_ACCESS_TOKEN=AQV...your_token_here
LINKEDIN_PERSON_URN=urn:li:person:XXXXXXXXX
```

---

## 5. REDDIT

### Step-by-step:
1. Go to **https://www.reddit.com/prefs/apps**
2. Click **Create Another App** at the bottom
3. Choose type: **script**
4. Set redirect URI to: `http://localhost:8080`
5. After creation:
   - **Client ID** = shown below the app name (short string)
   - **Client Secret** = the "secret" field
6. Format your user agent as: `python:your-app-name:v1.0 (by /u/yourusername)`
7. Set a subreddit you can post to (e.g. `u_yourusername` for your profile, or `test`)

> ⚠️ Reddit blocks posts to `r/test` from some accounts. Try your own user subreddit: `u_yourusername`

```
REDDIT_CLIENT_ID=AbCdEfGhIjKlMn
REDDIT_CLIENT_SECRET=xXxXxXxXxXxXxXxXxXxXxX
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
REDDIT_USER_AGENT=python:automated-posting:v1.0.0 (by /u/your_reddit_username)
REDDIT_SUBREDDIT=u_your_reddit_username
```

---

## Troubleshooting

| Status | Meaning | Fix |
|--------|---------|-----|
| `unconfigured` | Credentials missing in .env | Add the credentials and restart |
| `failed: auth` | Token/password wrong or expired | Re-generate the credential |
| `failed: rate limit` | Posted too recently | Wait and try again |
| `failed: scope` | Token missing permissions | Re-create token with correct scopes |
| `failed: timeout` | Network/server slow | Check internet, retry |
