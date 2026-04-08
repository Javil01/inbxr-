// InbXr Chrome Extension — Background service worker
// Adds a right-click context menu item so users can check any page's
// domain or any selected email address without opening the popup.

chrome.runtime.onInstalled.addListener(function () {
  chrome.contextMenus.create({
    id: "inbxr-check-page",
    title: "Check this site's Signal Score",
    contexts: ["page"],
  });
  chrome.contextMenus.create({
    id: "inbxr-check-selection",
    title: "Check selected domain with InbXr",
    contexts: ["selection"],
  });
  chrome.contextMenus.create({
    id: "inbxr-check-link",
    title: "Check this link's domain with InbXr",
    contexts: ["link"],
  });
});

chrome.contextMenus.onClicked.addListener(function (info, tab) {
  var domain = "";

  if (info.menuItemId === "inbxr-check-page" && tab && tab.url) {
    try {
      var u = new URL(tab.url);
      domain = u.hostname.replace(/^www\./, "");
    } catch (e) {}
  } else if (info.menuItemId === "inbxr-check-selection" && info.selectionText) {
    domain = extractDomain(info.selectionText);
  } else if (info.menuItemId === "inbxr-check-link" && info.linkUrl) {
    try {
      var lu = new URL(info.linkUrl);
      domain = lu.hostname.replace(/^www\./, "");
    } catch (e) {}
  }

  if (domain && domain.indexOf(".") !== -1) {
    chrome.tabs.create({
      url: "https://inbxr.us/?domain=" + encodeURIComponent(domain),
    });
  }
});

function extractDomain(text) {
  if (!text) return "";
  text = String(text).trim().toLowerCase();

  // If it looks like an email, grab the domain part
  if (text.indexOf("@") !== -1) {
    return text.split("@")[1].split(/\s/)[0];
  }

  // Strip protocol + path
  text = text.replace(/^https?:\/\//, "");
  text = text.split("/")[0];
  text = text.split("?")[0];
  text = text.split(":")[0];
  text = text.replace(/^www\./, "");

  // Must contain a dot
  if (text.indexOf(".") === -1) return "";
  return text;
}
