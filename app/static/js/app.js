/**
 * InboxZen — thin client glue.
 *
 * Everything dynamic is server-rendered HTMX fragments; this file only keeps
 * what browsers must do by themselves: theme flipping, keyboard events,
 * the iframe theme sync for the sandboxed reader, and the prompt-editor
 * line-number gutter (which needs live text-layout measurement).
 */

document.addEventListener("DOMContentLoaded", () => {
  // The first URL carries the session token; the cookie has it now, so drop
  // it from the address bar/history without losing any other params.
  const initialUrl = new URL(location.href);
  if (initialUrl.searchParams.has("token")) {
    initialUrl.searchParams.delete("token");
    history.replaceState(null, "", `${initialUrl.pathname}${initialUrl.search}`);
  }

  // Theme initialization (cookie is the single store; server also reads it)
  const cookieMatch = document.cookie.match(/(^|;)\s*iz-theme=([^;]+)/);
  if (cookieMatch) {
    setTheme(cookieMatch[2], false);
  } else {
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(prefersDark ? "dark" : "light", false);
  }

  // Keyboard shortcut: Escape closes whatever modal is on top
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const onboarding = document.getElementById("onboarding-scrim");
    if (onboarding && onboarding.classList.contains("on")) {
      e.preventDefault();
      return;
    }
    const scrim = document.getElementById("scrim");
    if (scrim && scrim.classList.contains("on")) closeSettingsModal();
  });

  const searchInput = document.getElementById("q");
  const searchClear = document.getElementById("search-clear");

  const syncSearchClear = () => {
    if (searchClear && searchInput) searchClear.hidden = !searchInput.value;
  };

  const clearSearch = () => {
    if (!searchInput || !searchInput.value) return;
    searchInput.value = "";
    searchInput.dispatchEvent(new Event("input", { bubbles: true }));
    searchInput.focus();
  };

  if (searchInput) {
    searchInput.addEventListener("input", syncSearchClear);
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && searchInput.value) {
        event.preventDefault();
        clearSearch();
      }
    });
    syncSearchClear();
  }
  if (searchClear) searchClear.addEventListener("click", clearSearch);

  // Re-measure the prompt-editor gutter after any swap brings an editor in
  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (document.getElementById("triage-markdown-input")) updatePromptLineNumbers();
    if (window.matchMedia("(max-width: 960px)").matches &&
        event.detail.target && event.detail.target.id === "reader") {
      event.detail.target.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "start" });
    }
  });

  document.body.addEventListener("htmx:afterSettle", syncFeedUrl);
});

function syncFeedUrl() {
  const input = document.getElementById("q");
  const tab = document.getElementById("filter-tab");
  if (!input || !tab) return;

  const params = new URLSearchParams();
  const query = input.value.trim();
  if (query) params.set("q", query);
  if (tab.value && tab.value !== "important") params.set("tab", tab.value);

  const unread = document.getElementById("filter-unread");
  if (unread && unread.value === "1") params.set("unread", "1");

  const account = document.getElementById("filter-account");
  if (account && account.value) params.set("account", account.value);

  const page = document.getElementById("page-state");
  if (page && page.value && page.value !== "1") params.set("page", page.value);

  const suffix = params.toString();
  const next = location.pathname + (suffix ? `?${suffix}` : "");
  if (next !== location.pathname + location.search) {
    history.replaceState(null, "", next);
  }
}

/* Toast — shows whatever message via a server-rendered OOB fragment */
function showToast(message) {
  htmx.ajax("GET", "/fragments/toast?msg=" + encodeURIComponent(message), { swap: "none" });
}

/* Settings modal — the shells live in #settings-root; closing just empties it */
function closeSettingsModal() {
  const root = document.getElementById("settings-root");
  if (root) root.innerHTML = "";
}

/* First-sync prompt — shown once after connecting a new Gmail account */
function closeFirstSyncPrompt() {
  const root = document.getElementById("first-sync-root");
  if (root) root.innerHTML = "";
}

/* Engine footer opens the settings on its Engine pane */
function openEngineSettings() {
  htmx.ajax("GET", "/fragments/settings?pane=model", { target: "#settings-root" });
}

function handleScrimClick(event) {
  if (event.target.id === "scrim") closeSettingsModal();
}

function readerDoc() {
  const iframe = document.getElementById("reader-iframe");
  if (!iframe) return null;
  try {
    return iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
  } catch (e) {
    return null;
  }
}

/* Scales fixed-width email layouts down to the reader pane. */
function fitReaderContent() {
  const iframe = document.getElementById("reader-iframe");
  const doc = readerDoc();
  if (!iframe || !doc || !doc.documentElement) return;
  const root = doc.documentElement;
  root.style.zoom = "";
  const available = root.clientWidth;
  const content = root.scrollWidth;
  if (available > 0 && content > available + 1) {
    root.style.zoom = Math.max(0.5, available / content);
  }
}

/* In-App Reader HTML / Plain Text Toggle (visibility only — iframe stays mounted) */
function setReaderMode(mode) {
  const iframe = document.getElementById("reader-iframe");
  const pre = document.getElementById("reader-pre");
  const paper = document.getElementById("paper");
  const htmlBtn = document.getElementById("mode-html-btn");
  const textBtn = document.getElementById("mode-text-btn");

  if (mode === "html") {
    if (paper) paper.classList.add("html-mail");
    if (iframe) iframe.style.display = "block";
    if (pre) pre.style.display = "none";
    if (htmlBtn) htmlBtn.classList.add("on");
    if (textBtn) textBtn.classList.remove("on");
    fitReaderContent();
  } else {
    if (paper) paper.classList.remove("html-mail");
    if (iframe) iframe.style.display = "none";
    if (pre) pre.style.display = "block";
    if (htmlBtn) htmlBtn.classList.remove("on");
    if (textBtn) textBtn.classList.add("on");
  }
}

/* Theme Switcher */
function setTheme(mode, showNotification = true) {
  document.documentElement.dataset.theme = mode;
  try {
    document.cookie = `iz-theme=${mode};path=/;max-age=31536000;SameSite=Lax`;
  } catch (e) {}

  const lightBtn = document.getElementById("th-light");
  const darkBtn = document.getElementById("th-dark");
  if (lightBtn) lightBtn.classList.toggle("on", mode === "light");
  if (darkBtn) darkBtn.classList.toggle("on", mode === "dark");

  syncIframeTheme();

  if (showNotification) {
    showToast(`Switched to ${mode} theme`);
  }
}

/* Syncs the sandboxed reader iframe with the active theme */
function syncIframeTheme() {
  const iframe = document.getElementById("reader-iframe");
  if (!iframe) return;
  const isDark = document.documentElement.dataset.theme === "dark";
  try {
    const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
    if (doc && doc.documentElement) {
      doc.documentElement.dataset.theme = isDark ? "dark" : "light";
      doc.documentElement.style.colorScheme = isDark ? "dark" : "light";
      if (doc.body) {
        doc.body.dataset.theme = isDark ? "dark" : "light";
      }
    }
  } catch (e) {}
  fitReaderContent();
  setTimeout(fitReaderContent, 150);
}

let readerResizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(readerResizeTimer);
  readerResizeTimer = setTimeout(fitReaderContent, 120);
});

/* Prompt Line Numbers & Synchronized Scrolling */
let promptMirror = null;

function measurePromptHeights(lines) {
  const textarea = document.getElementById("triage-markdown-input");
  if (!textarea) return [];

  if (!promptMirror || !promptMirror.isConnected) {
    promptMirror = document.createElement("div");
    promptMirror.style.cssText =
      "position:absolute;left:-9999px;top:0;visibility:hidden;white-space:pre-wrap;word-break:break-word;padding:0;margin:0;line-height:20px;";
    document.body.appendChild(promptMirror);
  }
  const ta = getComputedStyle(textarea);
  promptMirror.style.fontSize = ta.fontSize;
  promptMirror.style.fontWeight = ta.fontWeight;
  promptMirror.style.fontFamily = ta.fontFamily;
  promptMirror.style.letterSpacing = ta.letterSpacing;
  promptMirror.style.width = `${textarea.clientWidth - parseFloat(ta.paddingLeft) - parseFloat(ta.paddingRight)}px`;

  promptMirror.replaceChildren(
    ...lines.map((line) => {
      const row = document.createElement("div");
      if (line) row.textContent = line;
      return row;
    })
  );
  return lines.map((_, i) => Math.max(20, promptMirror.children[i].offsetHeight));
}

function updatePromptLineNumbers() {
  const textarea = document.getElementById("triage-markdown-input");
  const gutter = document.getElementById("prompt-gutter");
  if (!textarea || !gutter) return;

  const lines = textarea.value.split("\n");
  const heights = measurePromptHeights(lines);

  gutter.replaceChildren(
    ...lines.map((_, i) => {
      const num = document.createElement("div");
      num.textContent = i + 1;
      num.style.height = `${heights[i]}px`;
      return num;
    })
  );
}

function syncPromptScroll() {
  const textarea = document.getElementById("triage-markdown-input");
  const gutter = document.getElementById("prompt-gutter");
  if (textarea && gutter) {
    gutter.scrollTop = textarea.scrollTop;
  }
}
