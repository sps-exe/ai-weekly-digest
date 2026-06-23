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
