# 🧠 AI Weekly Digest

<div align="center">
  <p><strong>Curate today's top AI news stories and generate a LinkedIn-ready post in seconds.</strong></p>
  <p><em>100% free. No credit card. No server.</em></p>
</div>

<div align="center">
  <img src="https://img.shields.io/badge/Groq-Llama_3.3_70B-00d4ff?style=for-the-badge&logo=ai" alt="Groq" />
  <img src="https://img.shields.io/badge/Images-Pexels_/_Pollinations.ai-6366f1?style=for-the-badge" alt="Images" />
  <img src="https://img.shields.io/badge/Vanilla_JS-no_frameworks-22d3a5?style=for-the-badge&logo=javascript" alt="JS" />
</div>

---

## ✨ Features

- **📡 Live RSS Aggregation**: Fetches the latest stories from top publishers (The Hacker News, The Algorithm, TechCrunch, AI News) via a robust **dual-proxy fallback system** (`rss2json` → `feed2json`).
- **🧮 Smart Ranking**: Ranks articles based on 25+ AI keyword boosts and a 7-day recency decay, presenting you with the definitive **Top 3 Stories**.
- **🔄 Interactive UI**: Click any of the Top 3 stories in the Chrome Extension to instantly swap the focus, re-generate the post, and fetch new images for that specific topic.
- **🤖 Llama 3.3 Post Generation**: Uses Groq's lightning-fast API to write a 150-200 word, student-toned, engaging LinkedIn draft.
- **🖼 Dynamic Images**: Pulls high-quality real photography via Pexels, with an automatic fallback to AI-generated images via Pollinations.ai.
- **⚡ 1-Click LinkedIn Fill**: The Chrome extension automatically injects your draft into the LinkedIn composer. **You retain full control and click 'Post' yourself.**

---

## 📁 Project Structure

```text
ai-weekly-digest/
├── index.html            ← Standalone web app (open in any browser)
├── build.py              ← Python script to auto-generate the Chrome Extension bundle
├── .gitignore            ← Security first: prevents API keys from leaking
├── README.md             ← You are here
└── extension/            ← Generated Chrome Extension (Manifest V3)
    ├── manifest.json
    ├── popup.html
    ├── popup.css
    ├── popup.js
    ├── content.js         ← LinkedIn composer integration script
    ├── background.js      ← Service worker
    └── icons/
```

---

## 🚀 Quick Start

### Option A — Web App (Fastest)
1. Open `index.html` in Chrome, Edge, Safari, or Firefox — no local server needed!
2. Click the **⚙️ Settings** icon and enter your **Groq key** (`gsk_...`). Get one free at [console.groq.com](https://console.groq.com).
3. Optionally add a **Pexels key** for real photos. Get one free at [pexels.com/api](https://www.pexels.com/api/).
4. Click **Save & Load**! 
5. Select a story, copy the post, and download your favorite image.

### Option B — Chrome Extension (Best Experience)
1. Open Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select the `extension/` folder from this repository.
4. Pin the 🧠 icon to your toolbar.
5. Click it, enter your keys, and let the app curate your news.
6. When you find a story you love, go to LinkedIn, click **⚡ Fill LinkedIn Draft**, and watch the magic happen!

---

## 🔒 Security & Privacy First

We take your API keys seriously:
- **No Cloud Storage**: Keys are stored exclusively in your browser's local storage (`localStorage` / `chrome.storage.local`).
- **No Tracking**: There is absolutely zero telemetry, tracking, or external server routing. Keys go directly from your browser to Groq/Pexels.
- **Bulletproof `.gitignore`**: For developers utilizing a local `config.js` or `extension/config.js` to hardcode keys during testing, the `.gitignore` explicitly blocks these files. **Your keys will never accidentally leak to GitHub.**

---

## 🛠 For Developers

To modify the extension's behavior or UI, you only ever need to edit the root files (`index.html` or `build.py`). 

Once you make changes, run the build script to automatically regenerate the `extension/` directory and all required icons:

```bash
python3 build.py
```
*(Requires Python 3.6+. Uses standard library only—no pip installs required).*

---

## ⚠️ LinkedIn Safety Note

The Chrome extension uses DOM injection to **fill** your post draft, but it **never auto-posts**. You always review the text and click the "Post" button yourself. This complies with standard safe-automation practices, protecting your LinkedIn account from being flagged.

---

## 📄 License

MIT — Use freely, modify, learn, and share!
