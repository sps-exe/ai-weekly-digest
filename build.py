#!/usr/bin/env python3
"""
AI Weekly Digest — Build Script
Generates the Chrome extension files and icons.
Run once:  python3 build.py
"""
import os, struct, zlib, math, json

ROOT  = os.path.dirname(os.path.abspath(__file__))
EXT   = os.path.join(ROOT, 'extension')
ICONS = os.path.join(EXT,  'icons')
os.makedirs(ICONS, exist_ok=True)

def w(rel, content, mode='w'):
    path = os.path.join(EXT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode) as f:
        f.write(content)
    print(f'  ✓  extension/{rel}')

def wr(rel, data):  # binary
    path = os.path.join(EXT, rel)
    with open(path, 'wb') as f:
        f.write(data)
    print(f'  ✓  extension/{rel}')

# ─────────────────────────────────────────────────────────────────────────────
# ICONS  (gradient circle: cyan core → dark navy rim)
# ─────────────────────────────────────────────────────────────────────────────
def make_png(size):
    W = H = size
    cx, cy = W / 2.0, H / 2.0
    R_out  = min(W, H) / 2.0 * 0.88
    R_in   = R_out * 0.42

    rows = []
    for y in range(H):
        row = bytearray([0])          # PNG filter: None
        for x in range(W):
            d = math.hypot(x - cx + .5, y - cy + .5)
            if d > R_out:
                row += bytearray([10, 15, 30])     # background
            elif d <= R_in:
                row += bytearray([0, 212, 255])    # bright cyan core
            else:
                t = (d - R_in) / (R_out - R_in)   # 0=core 1=rim
                r = round(0   + (17  - 0  ) * t)
                g = round(212 + (24  - 212) * t)
                b = round(255 + (39  - 255) * t)
                row += bytearray([r, g, b])
        rows.append(bytes(row))

    raw        = b''.join(rows)
    compressed = zlib.compress(raw, 9)

    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)

    ihdr = struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', ihdr)
            + chunk(b'IDAT', compressed)
            + chunk(b'IEND', b''))

for sz in [16, 48, 128]:
    wr(f'icons/icon{sz}.png', make_png(sz))

# ─────────────────────────────────────────────────────────────────────────────
# manifest.json
# ─────────────────────────────────────────────────────────────────────────────
manifest = {
  "manifest_version": 3,
  "name": "AI Weekly Digest",
  "version": "1.0.0",
  "description": "Curate top AI news & auto-generate a LinkedIn post — powered by Groq (free).",
  "icons": {"16":"icons/icon16.png","48":"icons/icon48.png","128":"icons/icon128.png"},
  "action": {
    "default_popup": "popup.html",
    "default_title": "AI Weekly Digest",
    "default_icon": {"16":"icons/icon16.png","48":"icons/icon48.png"}
  },
  "permissions": ["storage","activeTab","scripting","clipboardWrite"],
  "host_permissions": [
    "https://api.groq.com/*",
    "https://api.rss2json.com/*",
    "https://feed2json.org/*",
    "https://api.pexels.com/*",
    "https://image.pollinations.ai/*",
    "https://www.linkedin.com/*"
  ],
  "content_scripts": [{
    "matches": ["https://www.linkedin.com/*"],
    "js": ["content.js"],
    "run_at": "document_idle"
  }],
  "background": {"service_worker":"background.js"}
}
w('manifest.json', json.dumps(manifest, indent=2))

# ─────────────────────────────────────────────────────────────────────────────
# background.js  (MV3 service worker — minimal)
# ─────────────────────────────────────────────────────────────────────────────
w('background.js', '''\
/* background.js — Service Worker
   Handles lifecycle events; actual logic lives in popup.js + content.js */

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    console.log('[AI Digest] Extension installed.');
  }
});

// Relay messages between popup and content scripts when popup is closed
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'PING') sendResponse({ ok: true });
  return false;
});
''')

# ─────────────────────────────────────────────────────────────────────────────
# content.js  (injected into linkedin.com)
# ─────────────────────────────────────────────────────────────────────────────
w('content.js', r'''
/* content.js — LinkedIn page integration
   Fills the post composer when triggered from the popup. */

'use strict';

// ── Selectors (LinkedIn changes class names often — try multiple) ──────────
const TRIGGER_SELECTORS = [
  '[data-control-name="share.sharebox_feed_create_update"]',
  '.share-box-feed-entry__trigger',
  'button.share-box-feed-entry__trigger',
  '[aria-label="Start a post"]'
];

const EDITOR_SELECTORS = [
  '.ql-editor[contenteditable="true"]',
  '[contenteditable="true"][data-placeholder]',
  '.editor-content [contenteditable="true"]',
  '[role="textbox"][contenteditable="true"]'
];

// ── Fill the LinkedIn composer with text ──────────────────────────────────
async function fillComposer(text) {
  // Step 1: find & click "Start a post"
  let trigger = null;
  for (const sel of TRIGGER_SELECTORS) {
    trigger = document.querySelector(sel);
    if (trigger) break;
  }

  if (!trigger) {
    // Try text-based search as last resort
    const buttons = [...document.querySelectorAll('button')];
    trigger = buttons.find(b => /start a post/i.test(b.textContent));
  }

  if (!trigger) {
    return { ok: false, error: 'Could not find the "Start a post" button. Please navigate to your LinkedIn feed first.' };
  }

  trigger.click();

  // Step 2: wait for composer editor to appear
  const editor = await waitForEditor();
  if (!editor) {
    return { ok: false, error: 'Composer did not open in time. Try clicking "Start a post" manually first.' };
  }

  // Step 3: fill using React-compatible events
  editor.focus();
  await sleep(120);

  // Clear any existing text
  document.execCommand('selectAll', false, null);
  document.execCommand('delete', false, null);

  // Insert text in a way React's synthetic event system recognises
  const insertOk = document.execCommand('insertText', false, text);

  if (!insertOk) {
    // Fallback: set innerHTML and dispatch events manually
    editor.innerHTML = text.split('\n').map(l => `<p>${escHtml(l) || '<br>'}</p>`).join('');
  }

  // Dispatch events so React re-validates (enables the Post button)
  ['input', 'change', 'keyup'].forEach(type => {
    editor.dispatchEvent(new Event(type, { bubbles: true, cancelable: true }));
  });

  showToast('✅ Post draft ready! Review and click Post.');
  return { ok: true };
}

// ── Helpers ───────────────────────────────────────────────────────────────
function waitForEditor(timeout = 6000) {
  return new Promise(resolve => {
    const start = Date.now();
    const obs = new MutationObserver(() => {
      for (const sel of EDITOR_SELECTORS) {
        const el = document.querySelector(sel);
        if (el) { obs.disconnect(); resolve(el); return; }
      }
      if (Date.now() - start > timeout) { obs.disconnect(); resolve(null); }
    });
    obs.observe(document.body, { childList: true, subtree: true });
    // Also check immediately
    for (const sel of EDITOR_SELECTORS) {
      const el = document.querySelector(sel);
      if (el) { obs.disconnect(); resolve(el); return; }
    }
  });
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function showToast(msg) {
  let toast = document.getElementById('__aiDigestToast__');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = '__aiDigestToast__';
    Object.assign(toast.style, {
      position:'fixed', bottom:'28px', right:'24px', zIndex:'99999',
      background:'#161f35', border:'1px solid rgba(0,212,255,0.4)',
      borderRadius:'12px', padding:'12px 20px', color:'#22d3a5',
      fontFamily:'Inter,sans-serif', fontSize:'14px', fontWeight:'600',
      boxShadow:'0 8px 32px rgba(0,0,0,0.6)', maxWidth:'320px',
      transition:'all 0.3s ease', opacity:'0', transform:'translateY(16px)'
    });
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  requestAnimationFrame(() => {
    toast.style.opacity = '1';
    toast.style.transform = 'translateY(0)';
  });
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(16px)';
  }, 4000);
}

// ── Message Listener ──────────────────────────────────────────────────────
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.action === 'FILL_COMPOSER') {
    fillComposer(msg.text).then(sendResponse);
    return true; // async response
  }
});
''')

# ─────────────────────────────────────────────────────────────────────────────
# popup.html
# ─────────────────────────────────────────────────────────────────────────────
w('popup.html', '''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>AI Weekly Digest</title>
  <link rel="preconnect" href="https://fonts.googleapis.com"/>
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet"/>
  <link rel="stylesheet" href="popup.css"/>
</head>
<body>

<!-- ── Header ── -->
<header>
  <div class="logo">
    <img src="icons/icon48.png" alt="logo" class="logo-img"/>
    <div>
      <h1>AI Weekly Digest</h1>
      <p class="tagline">Groq · Pexels · LinkedIn</p>
    </div>
  </div>
  <div class="header-actions">
    <button id="btnRefresh" class="icon-btn" title="Refresh news">↻</button>
    <button id="btnGear"    class="icon-btn" title="Settings">⚙</button>
  </div>
</header>

<!-- ── Settings Panel (collapsible) ── -->
<section id="settingsPanel" class="panel" style="display:none">
  <h2 class="panel-title">API Keys</h2>
  <div class="field-group">
    <label for="inputGroqKey">Groq Key <span class="req">*</span></label>
    <div class="input-wrap">
      <input type="password" id="inputGroqKey" placeholder="gsk_…" autocomplete="off"/>
      <button class="eye-btn" onclick="toggleVis('inputGroqKey',this)">👁</button>
    </div>
    <p class="hint">Free at <a href="https://console.groq.com" target="_blank">console.groq.com</a> — no card needed</p>
  </div>
  <div class="field-group">
    <label for="inputPexelsKey">Pexels Key <span class="opt">(optional)</span></label>
    <div class="input-wrap">
      <input type="password" id="inputPexelsKey" placeholder="Leave blank to use AI images" autocomplete="off"/>
      <button class="eye-btn" onclick="toggleVis('inputPexelsKey',this)">👁</button>
    </div>
    <p class="hint">Free at <a href="https://www.pexels.com/api/" target="_blank">pexels.com/api</a></p>
  </div>
  <button id="btnSaveKeys" class="btn btn-primary">Save &amp; Load</button>
</section>

<!-- ── Loading ── -->
<div id="loadingView" class="loading-view" style="display:none">
  <div class="spinner"></div>
  <p id="loadingLabel">Fetching AI news…</p>
</div>

<!-- ── Error ── -->
<div id="errorView" class="error-view" style="display:none">
  <span class="err-icon">⚠️</span>
  <p id="errorMsg">Something went wrong.</p>
  <button class="btn btn-ghost btn-sm" onclick="initDashboard()">Retry</button>
</div>

<!-- ── Main Content ── -->
<main id="contentView" style="display:none">

  <!-- Top Story -->
  <section class="card top-story" id="topStoryCard">
    <div class="card-meta">
      <span class="source-tag" id="storySource"></span>
      <span class="story-date" id="storyDate"></span>
      <span class="score-badge" id="storyScore"></span>
    </div>
    <h3 class="story-title" id="storyTitle"></h3>
    <p  class="story-summary" id="storySummary"></p>
    <a  class="story-link" id="storyLink" href="#" target="_blank" rel="noopener">Read full story ↗</a>
  </section>

  <!-- Other Stories (collapsed) -->
  <details class="others-details">
    <summary>View more stories</summary>
    <div class="news-list" id="newsList"></div>
  </details>

  <div class="divider"></div>

  <!-- Image Picker -->
  <section class="image-section">
    <div class="section-header">
      <span class="section-label">📸 Cover Image</span>
      <button id="btnNewImg" class="btn btn-ghost btn-xs">New Images</button>
    </div>
    <div id="imageGrid" class="image-grid">
      <div class="img-loading">
        <div class="spinner sm"></div>
      </div>
    </div>
    <div id="selectedImageActions" style="display:none;margin-top:8px">
      <button id="btnDownloadImg" class="btn btn-ghost btn-xs full-w">⬇ Download Selected Image</button>
    </div>
  </section>

  <div class="divider"></div>

  <!-- LinkedIn Post -->
  <section class="post-section">
    <div class="section-header">
      <span class="section-label">💼 LinkedIn Post</span>
      <button id="btnRegen" class="btn btn-ghost btn-xs" disabled>♻ Regen</button>
    </div>
    <div id="postSpinner" class="post-spinner" style="display:none">
      <div class="spinner sm"></div>
      <span>Generating with Llama 3.3 70B…</span>
    </div>
    <div id="postBox" class="post-box placeholder">Post will appear here…</div>
    <div id="postErr" class="post-error" style="display:none"></div>
  </section>

  <!-- Actions -->
  <div class="actions">
    <button id="btnCopy" class="btn btn-success" disabled>📋 Copy Post</button>
    <button id="btnFill" class="btn btn-primary" disabled>⚡ Fill LinkedIn Draft</button>
  </div>

</main>

<!-- ── Toast ── -->
<div id="toast"></div>

<script src="config.js" onerror="console.log('No local config.js found.')"></script>
<script src="popup.js"></script>
</body>
</html>
''')

# ─────────────────────────────────────────────────────────────────────────────
# config.js  (optional local config, ignored by git)
# ─────────────────────────────────────────────────────────────────────────────
import shutil
if os.path.exists(os.path.join(ROOT, 'config.js')):
    shutil.copy2(os.path.join(ROOT, 'config.js'), os.path.join(EXT, 'config.js'))
    print('  ✓  extension/config.js')


# ─────────────────────────────────────────────────────────────────────────────
# popup.css
# ─────────────────────────────────────────────────────────────────────────────
w('popup.css', '''/* popup.css — AI Weekly Digest Chrome Extension */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --bg:        #0a0f1e;
  --surface:   #111827;
  --card:      #161f35;
  --card-h:    #1c2847;
  --accent:    #00d4ff;
  --accent-d:  rgba(0,212,255,.14);
  --accent-g:  rgba(0,212,255,.3);
  --t1:        #f0f6ff;
  --t2:        #8899b4;
  --t3:        #4a5876;
  --border:    rgba(0,212,255,.12);
  --border-s:  rgba(0,212,255,.35);
  --success:   #22d3a5;
  --error:     #ff4d6d;
  --warn:      #f59e0b;
  --r-sm:      8px;
  --r-md:      12px;
  --r-lg:      16px;
  --ease:      all .2s cubic-bezier(.4,0,.2,1);
}

html{font-size:14px}
body{
  width:400px;min-height:200px;max-height:600px;overflow-y:auto;
  font-family:'Inter',sans-serif;background:var(--bg);color:var(--t1);
  line-height:1.55;scrollbar-width:thin;scrollbar-color:var(--accent-d) transparent;
}
body::-webkit-scrollbar{width:4px}
body::-webkit-scrollbar-thumb{background:var(--accent-d);border-radius:99px}

h1,h2,h3,h4{font-family:'Space Grotesk',sans-serif}

/* ── Header ── */
header{
  display:flex;align-items:center;justify-content:space-between;
  padding:12px 14px 10px;border-bottom:1px solid var(--border);
  position:sticky;top:0;z-index:10;
  background:rgba(10,15,30,.9);backdrop-filter:blur(12px);
}
.logo{display:flex;align-items:center;gap:9px}
.logo-img{width:28px;height:28px;border-radius:6px}
.logo h1{font-size:.95rem;background:linear-gradient(90deg,#fff 50%,var(--accent));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.tagline{font-size:.62rem;color:var(--t3);text-transform:uppercase;letter-spacing:.07em;margin-top:1px}

.header-actions{display:flex;gap:6px}
.icon-btn{
  background:rgba(255,255,255,.04);border:1px solid var(--border);
  border-radius:6px;color:var(--t2);cursor:pointer;
  width:30px;height:30px;display:flex;align-items:center;justify-content:center;
  font-size:.95rem;transition:var(--ease);
}
.icon-btn:hover{background:var(--accent-d);color:var(--accent);border-color:var(--border-s)}

/* ── Settings Panel ── */
.panel{background:var(--card);border-bottom:1px solid var(--border);padding:14px}
.panel-title{font-size:.85rem;margin-bottom:12px;color:var(--t2)}
.field-group{margin-bottom:12px}
.field-group label{display:block;font-size:.72rem;font-weight:600;
  color:var(--t2);margin-bottom:5px;text-transform:uppercase;letter-spacing:.05em}
.req{color:var(--error)}
.opt{color:var(--t3);font-weight:400;text-transform:none;letter-spacing:0}
.input-wrap{position:relative}
.input-wrap input{
  width:100%;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r-sm);padding:8px 34px 8px 10px;
  color:var(--t1);font-family:'Inter',sans-serif;font-size:.82rem;outline:none;
  transition:var(--ease);
}
.input-wrap input:focus{border-color:var(--accent);box-shadow:0 0 0 2px var(--accent-d)}
.input-wrap input::placeholder{color:var(--t3)}
.eye-btn{
  position:absolute;right:8px;top:50%;transform:translateY(-50%);
  background:none;border:none;color:var(--t3);cursor:pointer;font-size:.9rem;padding:0;
}
.eye-btn:hover{color:var(--accent)}
.hint{font-size:.68rem;color:var(--t3);margin-top:4px}
.hint a{color:var(--accent);text-decoration:none}

/* ── Buttons ── */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:6px;
  border-radius:var(--r-sm);font-family:'Inter',sans-serif;font-weight:600;
  cursor:pointer;border:none;transition:var(--ease);white-space:nowrap;
}
.btn:disabled{opacity:.4;cursor:not-allowed;transform:none!important;box-shadow:none!important}
.btn-primary{background:linear-gradient(135deg,var(--accent),#0099cc);color:#000;padding:9px 16px;font-size:.82rem}
.btn-primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 0 16px var(--accent-g)}
.btn-success{background:linear-gradient(135deg,var(--success),#16a87f);color:#000;padding:9px 16px;font-size:.82rem}
.btn-success:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 0 14px rgba(34,211,165,.4)}
.btn-ghost{background:rgba(255,255,255,.04);color:var(--t2);border:1px solid var(--border);padding:7px 12px;font-size:.78rem}
.btn-ghost:hover:not(:disabled){background:var(--accent-d);color:var(--accent);border-color:var(--border-s)}
.btn-sm{padding:7px 12px;font-size:.78rem}
.btn-xs{padding:4px 9px;font-size:.7rem}
.full-w{width:100%}

/* ── Loading / Error ── */
.loading-view,.error-view{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:10px;padding:36px 20px;text-align:center;
}
.loading-view p,.error-view p{font-size:.82rem;color:var(--t2)}
.err-icon{font-size:1.8rem}

.spinner{
  width:32px;height:32px;border-radius:50%;
  border:2px solid var(--border);border-top-color:var(--accent);
  animation:spin .7s linear infinite;
}
.spinner.sm{width:18px;height:18px;border-width:2px}
@keyframes spin{to{transform:rotate(360deg)}}

/* ── Main ── */
main{padding:14px 14px 0}

/* ── Top Story Card ── */
.top-story{
  background:var(--card);border:1px solid var(--border-s);
  border-radius:var(--r-md);padding:12px 14px;margin-bottom:10px;
  position:relative;overflow:hidden;
}
.top-story::before{
  content:'#1';position:absolute;top:10px;right:10px;
  background:linear-gradient(135deg,var(--accent),#0099cc);
  color:#000;font-size:.6rem;font-weight:800;padding:2px 7px;border-radius:99px;
}
.card-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:6px}
.source-tag{background:var(--accent-d);color:var(--accent);border-radius:99px;
  padding:1px 8px;font-size:.62rem;font-weight:700;letter-spacing:.04em}
.story-date{font-size:.62rem;color:var(--t3)}
.score-badge{font-size:.62rem;font-weight:700;color:var(--warn);
  background:rgba(245,158,11,.12);padding:1px 6px;border-radius:99px}
.story-title{font-size:.88rem;font-weight:700;margin-bottom:5px;line-height:1.35}
.story-summary{font-size:.75rem;color:var(--t2);line-height:1.5;
  display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;
  margin-bottom:6px}
.story-link{font-size:.7rem;color:var(--accent);font-weight:600;
  text-decoration:none;display:inline-block}
.story-link:hover{text-decoration:underline}

/* ── Others (details) ── */
.others-details{margin-bottom:10px}
.others-details summary{
  font-size:.72rem;color:var(--t2);cursor:pointer;padding:4px 0;
  list-style:none;display:flex;align-items:center;gap:6px;
}
.others-details summary::before{content:'▶';font-size:.6rem;transition:var(--ease)}
.others-details[open] summary::before{transform:rotate(90deg)}
.news-list{display:flex;flex-direction:column;gap:6px;padding-top:8px}
.mini-card{
  background:var(--card);border:1px solid var(--border);border-radius:var(--r-sm);
  padding:9px 11px;display:flex;gap:10px;align-items:flex-start;
  transition:var(--ease);
  cursor:pointer;
}
.mini-card:hover{background:var(--card-h);border-color:rgba(0,212,255,.2)}
.mini-card.selected{border-color:var(--accent);background:rgba(255,255,255,0.05)}
.mini-rank{
  width:24px;height:24px;border-radius:50%;background:rgba(255,255,255,.05);
  border:1px solid var(--border);color:var(--t3);font-size:.7rem;font-weight:700;
  display:flex;align-items:center;justify-content:center;flex-shrink:0;margin-top:1px;
}
.mini-body{flex:1;min-width:0}
.mini-title{font-size:.78rem;font-weight:600;margin-bottom:3px;line-height:1.3;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mini-meta{font-size:.64rem;color:var(--t3)}

/* ── Divider ── */
.divider{height:1px;background:var(--border);margin:10px 0}

/* ── Image Section ── */
.image-section{margin-bottom:10px}
.section-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.section-label{font-size:.72rem;font-weight:700;color:var(--t2);
  text-transform:uppercase;letter-spacing:.06em}
.image-grid{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;
}
.img-loading{grid-column:1/-1;display:flex;justify-content:center;padding:16px}
.img-thumb{
  border-radius:var(--r-sm);overflow:hidden;cursor:pointer;
  border:2px solid transparent;transition:var(--ease);position:relative;
}
.img-thumb img{width:100%;height:90px;object-fit:cover;display:block}
.img-thumb:hover{border-color:rgba(0,212,255,.5)}
.img-thumb.selected{border-color:var(--accent);box-shadow:0 0 12px var(--accent-g)}
.img-thumb.selected::after{
  content:'✓';position:absolute;top:5px;right:5px;
  background:var(--accent);color:#000;width:18px;height:18px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;font-size:.65rem;font-weight:800;
}
.img-credit{font-size:.6rem;color:var(--t3);text-align:center;margin-top:3px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.img-source-label{font-size:.58rem;color:var(--accent);font-weight:600;
  text-transform:uppercase;letter-spacing:.04em;text-align:center}

/* ── Post Section ── */
.post-section{margin-bottom:10px}
.post-spinner{display:flex;align-items:center;gap:8px;padding:12px 0;color:var(--t2);font-size:.78rem}
.post-box{
  background:var(--surface);border:1px solid var(--border);border-radius:var(--r-sm);
  padding:12px 13px;font-size:.8rem;line-height:1.7;white-space:pre-wrap;
  word-break:break-word;min-height:80px;color:var(--t1);max-height:200px;overflow-y:auto;
}
.post-box.placeholder{color:var(--t3);font-style:italic;
  display:flex;align-items:center;justify-content:center}
.post-error{font-size:.72rem;color:#ff8fa0;margin-top:6px;
  background:rgba(255,77,109,.08);border:1px solid rgba(255,77,109,.25);
  border-radius:6px;padding:8px 10px}

/* ── Actions ── */
.actions{
  display:grid;grid-template-columns:1fr 1fr;gap:8px;
  padding:10px 0 14px;
}

/* ── Toast ── */
#toast{
  position:fixed;bottom:14px;left:50%;transform:translateX(-50%) translateY(20px);
  background:var(--card);border:1px solid var(--border-s);border-radius:var(--r-sm);
  padding:8px 16px;font-size:.78rem;font-weight:600;color:var(--success);
  box-shadow:0 4px 20px rgba(0,0,0,.5);opacity:0;
  transition:all .3s cubic-bezier(.34,1.56,.64,1);pointer-events:none;white-space:nowrap;
}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

/* ── Saved badge ── */
.saved-dot{
  width:7px;height:7px;border-radius:50%;background:var(--success);
  box-shadow:0 0 6px rgba(34,211,165,.6);display:inline-block;
}
''')

# ─────────────────────────────────────────────────────────────────────────────
# popup.js
# ─────────────────────────────────────────────────────────────────────────────
w('popup.js', r'''
/* popup.js — AI Weekly Digest Chrome Extension
   Groq (Llama 3.3 70B) + Pexels/Pollinations images */

'use strict';

/* ══════════════════════════════
   CONSTANTS
══════════════════════════════ */
const GROQ_EP    = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODEL = 'llama-3.3-70b-versatile';
const PROXY      = 'https://api.rss2json.com/v1/api.json?rss_url=';
const PROXY2     = 'https://feed2json.org/convert?url=';
const PEXELS_EP  = 'https://api.pexels.com/v1/search';
const POLLIN     = 'https://image.pollinations.ai/prompt/';

const SOURCES = [
  { name:'The Hacker News', url:'https://feeds.feedburner.com/TheHackersNews',                         filterAI:true  },
  { name:'The Algorithm',   url:'https://rss.beehiiv.com/feeds/thealgorithmsubstack.com.xml',          filterAI:false },
  { name:'TechCrunch',      url:'https://techcrunch.com/feed/',                                        filterAI:true  },
  { name:'AI News',         url:'https://www.artificialintelligence-news.com/feed/',                   filterAI:false }
];

const BOOSTS = [
  ['breakthrough',8],['launch',5],['released',5],['open source',6],['open-source',6],
  ['gpt',7],['llm',6],['claude',7],['gemini',7],['research',4],['robot',5],['agent',5],
  ['new model',8],['state-of-the-art',7],['beats',5],['surpasses',6],['human-level',8],
  ['multimodal',5],['reasoning',4],['fine-tuning',4],['openai',6],['anthropic',6],
  ['billion parameters',6],['deepmind',6],['autonomous',5]
];

const AI_KW = [
  'artificial intelligence','machine learning','deep learning','neural network','llm','gpt',
  'claude','gemini','openai','anthropic','language model','chatbot','generative ai','diffusion',
  'transformer','robotics','autonomous','agent','agi','alignment','hugging face','mistral','llama'
];

/* ══════════════════════════════
   STATE
══════════════════════════════ */
const S = {
  groqKey:   '',
  pexelsKey: '',
  stories:   [],
  post:      '',
  images:    [],   // [{url, credit, sourceLabel}]
  selImg:    -1
};

/* ══════════════════════════════
   INIT
══════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  bindButtons();
  const stored = await chrome.storage.local.get(['groq_key','pexels_key']);
  if (stored.groq_key || window.DEFAULT_GROQ_KEY) {
    S.groqKey   = stored.groq_key || window.DEFAULT_GROQ_KEY;
    S.pexelsKey = stored.pexels_key || window.DEFAULT_PEXELS_KEY || '';
    fillKeyInputs();
    showBadge(true);
    await initDashboard();
  } else {
    showSection('settings');
  }
});

function bindButtons() {
  $('btnSaveKeys').addEventListener('click', saveKeys);
  $('btnRefresh').addEventListener('click',  initDashboard);
  $('btnGear').addEventListener('click',     () => togglePanel());
  $('btnCopy').addEventListener('click',     copyPost);
  $('btnFill').addEventListener('click',     fillLinkedIn);
  $('btnNewImg').addEventListener('click',   () => fetchImages(S.stories[0]));
  $('btnRegen').addEventListener('click',    () => generatePost(S.stories[0]));
  $('btnDownloadImg').addEventListener('click', downloadImage);
}

/* ══════════════════════════════
   SETTINGS
══════════════════════════════ */
async function saveKeys() {
  const gk = $('inputGroqKey').value.trim();
  const pk = $('inputPexelsKey').value.trim();
  if (!gk || !gk.startsWith('gsk_')) {
    toast('Invalid Groq key — must start with gsk_', true); return;
  }
  S.groqKey = gk; S.pexelsKey = pk;
  await chrome.storage.local.set({ groq_key: gk, pexels_key: pk });
  showBadge(true);
  $('settingsPanel').style.display = 'none';
  await initDashboard();
}

function fillKeyInputs() {
  $('inputGroqKey').value   = S.groqKey   ? '•'.repeat(24) : '';
  $('inputPexelsKey').value = S.pexelsKey ? '•'.repeat(24) : '';
}

function togglePanel() {
  const p = $('settingsPanel');
  p.style.display = p.style.display === 'none' ? 'block' : 'none';
  // Restore real values for editing
  if (p.style.display === 'block') {
    $('inputGroqKey').value   = S.groqKey;
    $('inputPexelsKey').value = S.pexelsKey;
  }
}

/* ══════════════════════════════
   DASHBOARD
══════════════════════════════ */
async function initDashboard() {
  showSection('loading');
  setLabel('loadingLabel','Fetching AI news from 4 sources…');
  $('btnRefresh').disabled = true;

  try {
    S.stories = await fetchAllStories();
    S.selStoryIdx = 0;
    renderTopStory(S.stories[0]);
    renderOthers();
    showSection('content');
    // Non-blocking parallel: images + post
    fetchImages(S.stories[0]);
    await generatePost(S.stories[0]);
  } catch (e) {
    showSection('error');
    $('errorMsg').textContent = e.message || 'Unknown error. Check your internet connection.';
  } finally {
    $('btnRefresh').disabled = false;
  }
}

/* ══════════════════════════════
   RSS FETCHING + RANKING
══════════════════════════════ */
async function fetchAllStories() {
  const results = await Promise.allSettled(SOURCES.map(fetchRSS));
  let all = [];
  let errs = [];
  results.forEach((r, i) => { 
    if (r.status === 'fulfilled') all = all.concat(r.value); 
    else errs.push(SOURCES[i].name + ': ' + r.reason.message);
  });
  if (!all.length) throw new Error('RSS Error: ' + errs.join(' | '));
  all = dedup(all);
  all.forEach(a => { a._score = score(a); });
  all.sort((a,b) => b._score - a._score);
  return all.slice(0,3);
}

async function fetchRSS(src) {
  let items = [];
  try {
    const res  = await fetch(PROXY + encodeURIComponent(src.url) + '&count=20');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (data.status !== 'ok' || !data.items) throw new Error('Bad response');
    items = data.items.map(it => ({
      title:   strip(it.title  || ''),
      summary: strip(it.description || it.content || '').slice(0,400),
      link:    it.link || it.url || '#',
      source:  src.name,
      pubDate: new Date(it.pubDate || it.published || Date.now()),
      _raw:    (it.title||'') + ' ' + (it.description||'') + ' ' + (it.categories||[]).join(' ')
    }));
  } catch (e) {
    const res = await fetch(PROXY2 + encodeURIComponent(src.url));
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    if (!data.items) throw new Error('Bad response');
    items = data.items.map(it => ({
      title:   strip(it.title  || ''),
      summary: strip(it.summary || it.content_html || '').slice(0,400),
      link:    it.url || it.id || '#',
      source:  src.name,
      pubDate: new Date(it.date_published || Date.now()),
      _raw:    (it.title||'') + ' ' + (it.summary||it.content_html||'')
    }));
  }
  if (src.filterAI) items = items.filter(it => AI_KW.some(kw => it._raw.toLowerCase().includes(kw)));
  return items;
}

function score(a) {
  const t = (a.title + ' ' + a.summary).toLowerCase();
  let s = 0;
  for (const [w, pts] of BOOSTS) if (t.includes(w)) s += pts;
  const ageDays = (Date.now() - (a.pubDate?.getTime()||0)) / 86400000;
  s += Math.max(0, 20 - ageDays * 3);
  return Math.round(s * 10) / 10;
}

function dedup(arr) {
  const seen = [];
  return arr.filter(a => {
    const t = a.title.toLowerCase().replace(/[^a-z0-9\s]/g,'');
    const dup = seen.some(s => jaccard(s,t) > 0.65);
    if (!dup) { seen.push(t); return true; }
    return false;
  });
}

function jaccard(a,b) {
  const sA = new Set(a.split(/\s+/).filter(w=>w.length>3));
  const sB = new Set(b.split(/\s+/).filter(w=>w.length>3));
  if (!sA.size||!sB.size) return 0;
  return [...sA].filter(w=>sB.has(w)).length / new Set([...sA,...sB]).size;
}

/* ══════════════════════════════
   GROQ — POST GENERATION
══════════════════════════════ */
async function generatePost(story) {
  if (!story || !S.groqKey) return;
  $('postSpinner').style.display = 'flex';
  $('postBox').className = 'post-box placeholder';
  $('postBox').textContent = 'Generating with Llama 3.3 70B…';
  $('btnCopy').disabled = $('btnFill').disabled = $('btnRegen').disabled = true;
  $('postErr').style.display = 'none';

  const prompt =
    'Write a LinkedIn post about this AI news for a CS + AI undergraduate student\'s profile.\n\n' +
    'Title: "' + story.title + '"\nSource: ' + story.source + '\nSummary: "' + story.summary + '"\n\n' +
    'Requirements:\n' +
    '- 150–200 words, curious student tone (not corporate)\n' +
    '- Start directly with substance — no "Exciting news!" openers\n' +
    '- 1 clear technical insight or takeaway\n' +
    '- Why this matters to the AI/tech community\n' +
    '- End with a thought-provoking open question\n' +
    '- Exactly 5 hashtags on a new line at the end\n' +
    '- Max 2–3 emojis, placed naturally\n' +
    '- NO filler phrases like "In today\'s fast-paced world"';

  try {
    const res = await fetch(GROQ_EP, {
      method: 'POST',
      headers: { 'Authorization':'Bearer ' + S.groqKey, 'Content-Type':'application/json' },
      body: JSON.stringify({ model:GROQ_MODEL, max_tokens:1024, messages:[{role:'user',content:prompt}] })
    });
    if (!res.ok) {
      const err = await res.json().catch(()=>({}));
      throw new Error(err?.error?.message || 'Groq API error ' + res.status);
    }
    const data = await res.json();
    S.post = data.choices?.[0]?.message?.content || '';
    if (!S.post) throw new Error('Empty response from Groq');
    $('postBox').className = 'post-box';
    $('postBox').textContent = S.post;
    $('btnCopy').disabled = $('btnFill').disabled = $('btnRegen').disabled = false;
  } catch (e) {
    $('postBox').textContent = 'Generation failed.';
    $('postErr').style.display = 'block';
    $('postErr').textContent = '⚠ ' + e.message;
    $('btnRegen').disabled = false;
  } finally {
    $('postSpinner').style.display = 'none';
  }
}

function regeneratePost() {
  if(S.stories[S.selStoryIdx]) generatePost(S.stories[S.selStoryIdx]);
}

/* ══════════════════════════════
   IMAGE FETCHING
══════════════════════════════ */
function keywords(story) {
  const stopWords = new Set(['the','a','an','in','on','at','by','for','with','about','from',
    'to','of','is','are','was','new','its','and','or','but','how','what','why','its','will']);
  const words = (story.title||'').toLowerCase().replace(/[^a-z0-9\s]/g,'').split(/\s+/);
  const kws = words.filter(w=>w.length>3&&!stopWords.has(w)).slice(0,4);
  return kws.join(' ') + ' artificial intelligence technology';
}

function pollinationUrl(story) {
  const prompt = encodeURIComponent(
    'futuristic AI technology concept, ' + story.title.slice(0,60) +
    ', professional editorial, glowing blue cyan, dark background, high quality'
  );
  return POLLIN + prompt + '?width=640&height=360&nologo=true&model=flux&seed=' + Math.floor(Math.random()*9999);
}

async function fetchImages(story) {
  if (!story) return;
  $('imageGrid').innerHTML = '<div class="img-loading"><div class="spinner sm"></div></div>';
  $('selectedImageActions').style.display = 'none';
  S.images = []; S.selImg = -1;

  try {
    if (S.pexelsKey) {
      const q = encodeURIComponent(keywords(story));
      const res = await fetch(PEXELS_EP + '?query=' + q + '&per_page=2&orientation=landscape', {
        headers:{ 'Authorization': S.pexelsKey }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.photos?.length) {
          S.images = data.photos.map(p => ({
            url:         p.src.large,
            credit:      '© ' + p.photographer + ' / Pexels',
            sourceLabel: 'Pexels'
          }));
        }
      }
    }
    // Pad with Pollinations if needed
    while (S.images.length < 2) {
      S.images.push({
        url:         pollinationUrl(story),
        credit:      'AI-generated',
        sourceLabel: 'Pollinations.ai'
      });
    }
    renderImages(S.images);
  } catch (e) {
    // Fallback to Pollinations entirely
    S.images = [pollinationUrl(story), pollinationUrl(story)].map(url => ({
      url, credit:'AI-generated', sourceLabel:'Pollinations.ai'
    }));
    renderImages(S.images);
  }
}

/* ══════════════════════════════
   RENDER
══════════════════════════════ */
function renderTopStory(s) {
  if (!s) return;
  $('storySource').textContent  = s.source;
  $('storyDate').textContent    = fmtDate(s.pubDate);
  $('storyScore').textContent   = 'Score: ' + s._score;
  $('storyTitle').textContent   = s.title;
  $('storySummary').textContent = s.summary || 'No summary.';
  $('storyLink').href           = s.link;
}

function renderOthers() {
  $('newsList').innerHTML = S.stories.map((s,i) =>
    '<div class="mini-card' + (i === S.selStoryIdx ? ' selected' : '') + '" onclick="selectStory('+i+')">' +
      '<div class="mini-rank">' + (i+1) + '</div>' +
      '<div class="mini-body">' +
        '<div class="mini-title">' + esc(s.title) + '</div>' +
        '<div class="mini-meta">' + esc(s.source) + ' · ' + fmtDate(s.pubDate) + '</div>' +
      '</div>' +
    '</div>'
  ).join('');
}

function selectStory(idx) {
  S.selStoryIdx = idx;
  const s = S.stories[idx];
  if (!s) return;
  renderTopStory(s);
  renderOthers();
  generatePost(s);
  fetchImages(s);
}

function renderImages(imgs) {
  $('imageGrid').innerHTML = imgs.map((img,i) =>
    '<div>' +
      '<div class="img-thumb" id="imgThumb'+i+'" onclick="selectImg('+i+')">' +
        '<img src="'+img.url+'" alt="cover" loading="lazy" onerror="this.parentElement.style.display=\'none\'"/>' +
      '</div>' +
      '<div class="img-credit">'+esc(img.credit)+'</div>' +
      '<div class="img-source-label">'+esc(img.sourceLabel)+'</div>' +
    '</div>'
  ).join('');
}

function selectImg(idx) {
  S.selImg = idx;
  document.querySelectorAll('.img-thumb').forEach((el,i) => {
    el.classList.toggle('selected', i === idx);
  });
  $('selectedImageActions').style.display = 'block';
}

/* ══════════════════════════════
   ACTIONS
══════════════════════════════ */
async function copyPost() {
  if (!S.post) return;
  try {
    await navigator.clipboard.writeText(S.post);
  } catch {
    const ta = document.createElement('textarea');
    ta.value = S.post;
    Object.assign(ta.style, {position:'fixed',top:0,left:0,opacity:0});
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
  }
  toast('✅ Post copied to clipboard!');
  const b = $('btnCopy');
  b.textContent = '✓ Copied!';
  setTimeout(() => { b.textContent = '📋 Copy Post'; }, 2000);
}

async function fillLinkedIn() {
  if (!S.post) return;
  $('btnFill').disabled = true;
  $('btnFill').textContent = 'Opening…';
  try {
    const [tab] = await chrome.tabs.query({ active:true, currentWindow:true });
    if (!tab?.url?.includes('linkedin.com')) {
      // Open LinkedIn first
      chrome.tabs.create({ url:'https://www.linkedin.com/feed/' });
      toast('ℹ Opened LinkedIn. Click ⚡ Fill again once the page loads.');
      return;
    }
    const result = await chrome.tabs.sendMessage(tab.id, { action:'FILL_COMPOSER', text:S.post });
    if (result?.ok) {
      toast('✅ Post draft filled! Review & click Post on LinkedIn.');
    } else {
      toast('⚠ ' + (result?.error || 'Could not fill composer. Navigate to your LinkedIn feed first.'), true);
    }
  } catch (e) {
    toast('⚠ Make sure you are on linkedin.com', true);
  } finally {
    $('btnFill').disabled = false;
    $('btnFill').textContent = '⚡ Fill LinkedIn Draft';
  }
}

function downloadImage() {
  if (S.selImg < 0 || !S.images[S.selImg]) return;
  const img = S.images[S.selImg];
  // Open image in new tab (extensions can't trigger native download directly for remote URLs)
  chrome.tabs.create({ url: img.url });
  toast('ℹ Image opened in a new tab — right-click → Save Image As');
}

/* ══════════════════════════════
   UI HELPERS
══════════════════════════════ */
function showSection(name) {
  ['settingsPanel','loadingView','errorView','contentView'].forEach(id => {
    const el = $(id);
    if (el) el.style.display = 'none';
  });
  if (name === 'settings')  { $('settingsPanel').style.display = 'block'; return; }
  if (name === 'loading')   { $('loadingView').style.display   = 'flex';  return; }
  if (name === 'error')     { $('errorView').style.display     = 'flex';  return; }
  if (name === 'content')   { $('contentView').style.display   = 'block'; return; }
}

function showBadge(on) {
  const gear = $('btnGear');
  if (on) {
    if (!$('savedDot')) {
      const dot = document.createElement('span');
      dot.id = 'savedDot';
      dot.className = 'saved-dot';
      Object.assign(dot.style, {position:'absolute',top:'3px',right:'3px'});
      gear.style.position = 'relative';
      gear.appendChild(dot);
    }
  }
}

let _toastTimer;
function toast(msg, isErr=false) {
  const el = $('toast');
  el.textContent = msg;
  el.style.color = isErr ? '#ff8fa0' : '#22d3a5';
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 3200);
}

function togglePanel() {
  const p = $('settingsPanel');
  const isHidden = p.style.display === 'none' || !p.style.display;
  p.style.display = isHidden ? 'block' : 'none';
  if (isHidden) { $('inputGroqKey').value = S.groqKey; $('inputPexelsKey').value = S.pexelsKey; }
}

window.togglePanel = togglePanel;
window.selectImg   = selectImg;

/* ── Tiny helpers ── */
function $(id)        { return document.getElementById(id); }
function setLabel(id,t){ $(id).textContent = t; }
function strip(html)  { const d=document.createElement('div');d.innerHTML=html;return d.textContent||''; }
function esc(s)       { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function fmtDate(d)   {
  if (!d||isNaN(d.getTime())) return '';
  const h = Math.floor((Date.now()-d.getTime())/3600000);
  if (h<1) return 'Just now';
  if (h<24) return h+'h ago';
  const day = Math.floor(h/24);
  return day<7 ? day+'d ago' : d.toLocaleDateString('en-US',{month:'short',day:'numeric'});
}

function toggleVis(inputId, btn) {
  const inp = document.getElementById(inputId);
  inp.type = inp.type === 'password' ? 'text' : 'password';
}
window.toggleVis = toggleVis;
''')

print('\n✅  All extension files written successfully.\n')
print('Directory structure:')
for root, dirs, files in os.walk(EXT):
    level = root.replace(EXT, '').count(os.sep)
    indent = '  ' * level
    print(f'{indent}{os.path.basename(root)}/')
    for f in files:
        print(f'{indent}  {f}')
