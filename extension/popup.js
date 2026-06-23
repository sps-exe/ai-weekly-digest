
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
