# InbXr Signal Score — Chrome Extension

Check the deliverability Signal Score of any sending domain in 30 seconds.

## What it does

- **Popup:** Click the InbXr icon in your toolbar to check any domain. Auto-populates with the current tab's domain.
- **Right-click context menu:** Right-click any page, selected email, or link → "Check with InbXr" to score the domain.
- **History:** Keeps your last 5 checks in local storage so you can re-check without retyping.

## How it works

The extension calls `https://inbxr.us/api/badge/<domain>.json` and renders the result in a popup. It returns the 2 domain-derived signals (Authentication Standing + Domain Reputation) that the Signal Engine can compute from public DNS data alone. For the full 7-signal reading, the user clicks through to inbxr.us and connects an ESP or uploads a CSV.

Every scan contributes to the public [Signal Score Leaderboard](https://inbxr.us/leaderboard) (anonymized).

## Loading unpacked (for development)

1. Open Chrome and go to `chrome://extensions`
2. Enable "Developer mode" in the top-right
3. Click "Load unpacked"
4. Select this `chrome-extension/` directory
5. Pin the InbXr icon to your toolbar

## Publishing to the Chrome Web Store

1. Zip the contents of this directory (NOT the directory itself — zip the files inside)
2. Go to the [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
3. Click "New Item" and upload the zip
4. Fill in:
   - **Description:** See `store-description.txt`
   - **Category:** Productivity / Developer Tools
   - **Language:** English
   - **Screenshots:** 1280x800 or 640x400, at least one required
   - **Promotional images:** 440x280 small tile (optional but recommended)
5. Submit for review (typically takes 1-3 business days)

## Store listing description

**Short description (132 chars max):**
> Check the deliverability Signal Score of any sending domain in 30 seconds. Powered by the InbXr Signal Engine.

**Full description:**
> InbXr reads 7 Inbox Signals from any sending domain and gives you a composite Signal Score out of 100. This extension lets you check any domain's score without leaving your browser.
>
> What you can check:
> - Authentication Standing (SPF / DKIM / DMARC vs 2024-2025 ISP mandates)
> - Domain Reputation (blacklist monitoring, DNSBL status)
> - And a preview of the other 5 signals that require a connected ESP
>
> Use it to:
> - Check prospects before cold outreach
> - Validate your own domain setup in one click
> - See why certain senders land in spam
> - Compare domain deliverability across competitors
>
> Right-click any page, link, or selected email address to check its domain. Or click the extension icon and paste a domain directly.
>
> Built by InbXr — the intelligence layer between your ESP and the inbox. Learn more at https://inbxr.us

## File structure

```
chrome-extension/
├── manifest.json       # MV3 manifest with permissions
├── popup.html          # Extension popup UI
├── popup.css           # Popup styling
├── popup.js            # Popup logic + API calls + history
├── background.js       # Service worker for right-click menus
├── icons/              # 16, 32, 48, 128 px icons
└── README.md           # This file
```

## Permissions explained

- `contextMenus` — needed for the right-click menu items
- `activeTab` — needed to auto-populate the popup with the current tab's domain
- `storage` — needed for the recent-checks history in local storage
- `host_permissions: https://inbxr.us/*` — the only external host the extension calls
