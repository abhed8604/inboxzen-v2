/**
 * InboxZen — Desktop Controller
 */

let toastTimeout = null;

document.addEventListener("DOMContentLoaded", () => {
  // Theme initialization
  const cookieMatch = document.cookie.match(/(^|;)\s*iz-theme=([^;]+)/);
  const savedTheme = localStorage.getItem("iz-theme") || (cookieMatch ? cookieMatch[2] : null);
  if (savedTheme) {
    setTheme(savedTheme, false);
  } else {
    const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    setTheme(prefersDark ? "dark" : "light", false);
  }

  // Engine status monitoring
  pollEngineStatus();
  setInterval(pollEngineStatus, 15000);

  // Keyboard shortcut: Escape to close modal
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSettingsModal();
  });

  // Auto-sync reader pane when feed list updates
  document.body.addEventListener("htmx:afterSwap", (evt) => {
    if (evt.detail.target && evt.detail.target.id === "list" && evt.detail.elt && evt.detail.elt.id === "list") {
      const activeItem = document.querySelector("#list .item.on") || document.querySelector("#list .item");
      if (activeItem && activeItem.dataset.id) {
        if (!activeItem.classList.contains("on")) {
          document.querySelectorAll("#list .item").forEach((el) => el.classList.remove("on"));
          activeItem.classList.add("on");
        }
        const currentReaderId = document.getElementById("rhead")?.dataset.emailId;
        if (currentReaderId !== activeItem.dataset.id) {
          htmx.ajax("GET", `/emails/${activeItem.dataset.id}`, {
            target: "#reader",
            swap: "innerHTML",
          });
        }
      } else if (!activeItem) {
        const reader = document.getElementById("reader");
        if (reader) {
          reader.innerHTML = `
            <div class="none" style="padding: 100px 20px;">
              <p style="font: 400 24px var(--serif); color: var(--ink2); margin-bottom: 6px;">No emails in this view</p>
              <p style="font-size: 12.5px; color: var(--ink3);">Try switching account filter or tabs</p>
            </div>`;
        }
      }
    } else if (evt.detail.target && evt.detail.target.id === "reader") {
      syncIframeTheme();
    }
  });

  // Ensure active selector class remains stable after HTMX settle
  document.body.addEventListener("htmx:afterSettle", (evt) => {
    if (evt.detail.target && evt.detail.target.id === "list") {
      const activeItem = document.querySelector("#list .item.on") || document.querySelector("#list .item");
      if (activeItem && !activeItem.classList.contains("on")) {
        activeItem.classList.add("on");
      }
    }
  });
});

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
}

/* Tabs & Filter Controls */
function setFilterTab(tab, btnEl) {
  const hiddenInput = document.getElementById("filter-tab");
  if (hiddenInput) hiddenInput.value = tab;

  document.querySelectorAll("#tabs button").forEach((btn) => btn.classList.remove("on"));
  if (btnEl) btnEl.classList.add("on");

  const navInbox = document.getElementById("nav-inbox-btn");
  if (navInbox) {
    navInbox.classList.add("on");
  }
}

function selectNavInbox() {
  const importantChip = document.querySelector('#tabs button[data-t="important"]');
  setFilterTab("important", importantChip);
  const unreadVal = document.getElementById("filter-unread")?.value || "0";
  const qVal = document.getElementById("filter-query")?.value || "";
  const acctVal = document.getElementById("filter-account")?.value || "";
  htmx.ajax("GET", `/emails?tab=important&q=${encodeURIComponent(qVal)}&unread=${unreadVal}&account=${encodeURIComponent(acctVal)}`, {
    target: "#list",
    swap: "innerHTML",
  });
}

function toggleUnreadFilter() {
  const unreadInput = document.getElementById("filter-unread");
  const unreadTg = document.getElementById("unread-tg");
  if (!unreadInput) return;

  const willBeActive = unreadInput.value !== "1";
  unreadInput.value = willBeActive ? "1" : "0";

  if (unreadTg) {
    unreadTg.classList.toggle("on", willBeActive);
  }

  const tab = document.getElementById("filter-tab")?.value || "important";
  const q = document.getElementById("filter-query")?.value || "";
  const acct = document.getElementById("filter-account")?.value || "";

  htmx.ajax("GET", `/emails?tab=${encodeURIComponent(tab)}&q=${encodeURIComponent(q)}&unread=${willBeActive ? 1 : 0}&account=${encodeURIComponent(acct)}`, {
    target: "#list",
    swap: "innerHTML",
  });
}

function toggleAccountFilter(accountEmail, chipEl) {
  const accountInput = document.getElementById("filter-account");
  if (!accountInput) return;

  const currentAccount = accountInput.value;
  // If user clicked the same account that is currently selected, toggle it off to show all
  const targetAccount = (currentAccount === accountEmail && accountEmail) ? "" : accountEmail;
  accountInput.value = targetAccount;

  // Update UI active states
  document.querySelectorAll(".acct-chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.account === targetAccount);
  });

  const tab = document.getElementById("filter-tab")?.value || "important";
  const q = document.getElementById("filter-query")?.value || "";
  const unreadVal = document.getElementById("filter-unread")?.value || "0";

  htmx.ajax("GET", `/emails?tab=${encodeURIComponent(tab)}&q=${encodeURIComponent(q)}&unread=${unreadVal}&account=${encodeURIComponent(targetAccount)}`, {
    target: "#list",
    swap: "innerHTML",
  });
}

function selectFeedItem(btnEl) {
  if (!btnEl) return;
  document.querySelectorAll(".item").forEach((el) => el.classList.remove("on"));
  btnEl.classList.add("on");
  btnEl.classList.remove("unread");
  btnEl.classList.add("read");

  const dot = btnEl.querySelector(".udot");
  if (dot) dot.remove();
}

/* In-App Reader HTML / Plain Text Toggle */
function setReaderMode(mode) {
  const iframe = document.getElementById("reader-iframe");
  const pre = document.getElementById("reader-pre");
  const htmlBtn = document.getElementById("mode-html-btn");
  const textBtn = document.getElementById("mode-text-btn");

  if (mode === "html") {
    if (iframe) iframe.style.display = "block";
    if (pre) pre.style.display = "none";
    if (htmlBtn) htmlBtn.classList.add("on");
    if (textBtn) textBtn.classList.remove("on");
  } else {
    if (iframe) iframe.style.display = "none";
    if (pre) pre.style.display = "block";
    if (htmlBtn) htmlBtn.classList.remove("on");
    if (textBtn) textBtn.classList.add("on");
  }
}

/* Toast HUD */
function showToast(message) {
  const toast = document.getElementById("app-toast");
  const toastText = document.getElementById("toast-text");
  if (!toast || !toastText) return;

  toastText.textContent = message;
  toast.classList.add("show");

  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => {
    toast.classList.remove("show");
  }, 2800);
}

function spinButton(btnEl) {
  if (!btnEl) return;
  btnEl.classList.remove("spin");
  void btnEl.offsetWidth; // Force DOM reflow
  btnEl.classList.add("spin");
}

/* Settings Modal */
function openSettingsModal(pane = "rules") {
  const scrim = document.getElementById("scrim");
  if (!scrim) return;
  scrim.classList.add("on");
  switchSettingsPane(pane);
  hideAccountsInstructions();
  const currentMode = document.documentElement.dataset.theme || "dark";
  const lightBtn = document.getElementById("th-light");
  const darkBtn = document.getElementById("th-dark");
  if (lightBtn) lightBtn.classList.toggle("on", currentMode === "light");
  if (darkBtn) darkBtn.classList.toggle("on", currentMode === "dark");
  const textarea = document.getElementById("triage-markdown-input");
  const gutter = document.getElementById("prompt-gutter");
  if (textarea) textarea.scrollTop = 0;
  if (gutter) gutter.scrollTop = 0;
  setTimeout(updatePromptLineNumbers, 40);
}

function closeSettingsModal() {
  const scrim = document.getElementById("scrim");
  if (scrim) scrim.classList.remove("on");
}

function handleScrimClick(event) {
  if (event.target.id === "scrim") {
    closeSettingsModal();
  }
}

function switchSettingsPane(paneKey) {
  document.querySelectorAll(".mside .nav").forEach((btn) => {
    btn.classList.toggle("on", btn.dataset.s === paneKey);
  });
  document.querySelectorAll(".settings-pane").forEach((pane) => {
    pane.style.display = pane.id === `pane-${paneKey}` ? "block" : "none";
  });
  hideAccountsInstructions();
  if (paneKey === "rules") {
    const textarea = document.getElementById("triage-markdown-input");
    const gutter = document.getElementById("prompt-gutter");
    if (textarea) textarea.scrollTop = 0;
    if (gutter) gutter.scrollTop = 0;
    setTimeout(updatePromptLineNumbers, 30);
  }
}

/* Prompt Line Numbers & Synchronized Scrolling */
function updatePromptLineNumbers() {
  const textarea = document.getElementById("triage-markdown-input");
  const gutter = document.getElementById("prompt-gutter");
  if (!textarea || !gutter) return;

  const count = (textarea.value.match(/\n/g) || []).length + 1;
  let html = "";
  for (let i = 1; i <= count; i++) {
    html += `<div>${i}</div>`;
  }
  gutter.innerHTML = html;
  gutter.scrollTop = textarea.scrollTop;
}

function syncPromptScroll() {
  const textarea = document.getElementById("triage-markdown-input");
  const gutter = document.getElementById("prompt-gutter");
  if (textarea && gutter) {
    gutter.scrollTop = textarea.scrollTop;
  }
}

/* Accounts Tab - Overlapping Setup Instructions */
function showAccountsInstructions() {
  const mainView = document.getElementById("accounts-main-view");
  const instView = document.getElementById("accounts-instructions-view");
  if (mainView && instView) {
    mainView.style.display = "none";
    instView.style.display = "block";
  }
}

function hideAccountsInstructions() {
  const mainView = document.getElementById("accounts-main-view");
  const instView = document.getElementById("accounts-instructions-view");
  if (mainView && instView) {
    instView.style.display = "none";
    mainView.style.display = "block";
  }
}

/* Theme Switcher */
function setTheme(mode, showNotification = true) {
  document.documentElement.dataset.theme = mode;
  document.documentElement.setAttribute("data-theme", mode);
  try {
    localStorage.setItem("iz-theme", mode);
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

function handlePromptSaved() {
  const btn = document.getElementById("save-prompt-btn");
  if (btn) btn.textContent = "Saved ✓";
  showToast("Classification instructions saved");
  setTimeout(() => {
    if (btn) btn.textContent = "Save instructions";
    closeSettingsModal();
  }, 600);
}

/* Engine Health Poller */
async function pollEngineStatus() {
  try {
    const res = await fetch("/api/engine/status");
    if (!res.ok) return;
    const data = await res.json();
    const dot = document.getElementById("vram-dot");
    const indicator = document.querySelector(".engine-indicator");
    const tag = document.querySelector(".engine-tag");

    if (data.healthy) {
      if (dot) dot.style.background = "var(--ok)";
      if (tag) tag.textContent = "VRAM";
      if (indicator) indicator.title = "Engine status: Online in VRAM";
    } else {
      if (dot) dot.style.background = "var(--ink3)";
      if (tag) tag.textContent = "Off";
      if (indicator) indicator.title = "Engine status: Engine Paused";
    }
  } catch (err) {
    // Silent fail
  }
}
