
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
