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
    const label = document.getElementById("vram-footer-label");
    const indicator = document.querySelector(".engine-indicator");

    if (data.healthy) {
      if (dot) {
        dot.style.background = "var(--ok)";
        dot.style.animation = "none";
      }
      if (label) label.textContent = "vllm-d3-lite";
      if (indicator) indicator.title = "Engine status: Online in VRAM";
    } else if (data.status === "downloading") {
      if (dot) {
        dot.style.background = "var(--warn, #e5a93c)";
        dot.style.animation = "pulse 1.5s infinite";
      }
      if (label) label.textContent = "Downloading model…";
      if (indicator) indicator.title = "Engine status: Downloading model (first launch)";
    } else {
      if (dot) {
        dot.style.background = "var(--ink3)";
        dot.style.animation = "none";
      }
      if (label) label.textContent = "vllm-d3-lite";
      if (indicator) indicator.title = "Engine status: Engine Paused";
    }
  } catch (err) {
    // Silent fail
  }
}

/* Onboarding Controller */
let selectedOnboardingCompute = "cpu";
let cudaPollTimer = null;

function selectComputeOption(type) {
  selectedOnboardingCompute = type;
  const cpuCard = document.getElementById("card-compute-cpu");
  const gpuCard = document.getElementById("card-compute-gpu");
  if (cpuCard) cpuCard.classList.toggle("selected", type === "cpu");
  if (gpuCard) gpuCard.classList.toggle("selected", type === "gpu");
}

function goToOnboardingStep(step) {
  const computeStep = document.getElementById("onboarding-step-compute");
  const mailStep = document.getElementById("onboarding-step-mail");
  const computeTab = document.getElementById("onboarding-tab-compute");
  const mailTab = document.getElementById("onboarding-tab-mail");

  if (step === "compute") {
    if (computeStep) computeStep.style.display = "block";
    if (mailStep) mailStep.style.display = "none";
    if (computeTab) computeTab.classList.add("on");
    if (mailTab) mailTab.classList.remove("on");
  } else {
    if (computeStep) computeStep.style.display = "none";
    if (mailStep) mailStep.style.display = "block";
    if (computeTab) computeTab.classList.remove("on");
    if (mailTab) mailTab.classList.add("on");
  }
}

let modelPollTimer = null;

async function startOnboardingSetup() {
  const nextBtn = document.getElementById("onboarding-compute-next-btn");
  const dlSection = document.getElementById("onboarding-download-section");
  const dlTitle = document.getElementById("onboarding-dl-title");
  const dlSub = document.getElementById("onboarding-dl-sub");
  const dlPercent = document.getElementById("onboarding-dl-percent");
  const dlBar = document.getElementById("onboarding-dl-bar");
  const dlStats = document.getElementById("onboarding-dl-stats");
  const dlStatus = document.getElementById("onboarding-dl-status");

  if (nextBtn) {
    nextBtn.disabled = true;
    nextBtn.textContent = "Setting up...";
  }

  // 1. Save compute preference
  const formData = new FormData();
  formData.append("device", selectedOnboardingCompute);
  try {
    await fetch("/api/settings/compute", { method: "POST", body: formData });
  } catch (e) {}

  // 2. If GPU selected, install CUDA if needed
  if (selectedOnboardingCompute === "gpu") {
    try {
      const cudaRes = await fetch("/api/cuda/status");
      const cudaData = await cudaRes.json();
      if (!cudaData.installed) {
        if (dlSection) dlSection.style.display = "block";
        if (dlTitle) dlTitle.textContent = "Downloading CUDA acceleration runtime";
        if (dlSub) dlSub.textContent = "NVIDIA CUDA runtime libraries (~850 MB)";
        if (dlStatus) dlStatus.textContent = "Initializing download…";

        await fetch("/api/cuda/install", { method: "POST" });
        await new Promise((resolve) => {
          const timer = setInterval(async () => {
            try {
              const r = await fetch("/api/cuda/status");
              const d = await r.json();
              if (d.state.status === "downloading") {
                if (dlBar) dlBar.style.width = `${d.state.percent}%`;
                if (dlPercent) dlPercent.textContent = `${d.state.percent}%`;
                if (dlStats) dlStats.textContent = d.state.message || "Downloading...";
                if (dlStatus) dlStatus.textContent = "In progress";
              } else if (d.state.status === "ready" || d.installed) {
                clearInterval(timer);
                resolve();
              } else if (d.state.status === "error") {
                clearInterval(timer);
                resolve();
              }
            } catch (err) {
              clearInterval(timer);
              resolve();
            }
          }, 800);
        });
      }
    } catch (e) {}
  }

  // 3. Check and download classification model
  try {
    const modelRes = await fetch("/api/model/status");
    const modelData = await modelRes.json();

    if (modelData.downloaded) {
      if (dlSection) dlSection.style.display = "block";
      if (dlTitle) dlTitle.textContent = "Classification model ready";
      if (dlSub) dlSub.textContent = "ggml-org/vllm-d3-lite-GGUF:Q8_0";
      if (dlPercent) dlPercent.textContent = "100%";
      if (dlBar) dlBar.style.width = "100%";
      if (dlStats) dlStats.textContent = "Verified on disk ✓";
      if (dlStatus) dlStatus.textContent = "Ready";

      setTimeout(() => {
        goToOnboardingStep("mail");
      }, 500);
      return;
    }

    // Start model download
    if (dlSection) dlSection.style.display = "block";
    if (dlTitle) dlTitle.textContent = "Downloading classification model";
    if (dlSub) dlSub.textContent = "ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)";
    if (dlStatus) dlStatus.textContent = "Connecting to repository…";

    await fetch("/api/model/download", { method: "POST" });

    if (modelPollTimer) clearInterval(modelPollTimer);
    modelPollTimer = setInterval(async () => {
      try {
        const res = await fetch("/api/model/status");
        if (!res.ok) return;
        const data = await res.json();
        const st = data.state;

        if (st.status === "downloading") {
          if (dlBar) dlBar.style.width = `${st.percent}%`;
          if (dlPercent) dlPercent.textContent = `${st.percent}%`;
          if (dlStats) dlStats.textContent = `${st.downloaded_mb || 0} MB / ${st.total_mb || 1082} MB`;
          if (dlStatus) dlStatus.textContent = "Downloading…";
        } else if (st.status === "ready" || data.downloaded) {
          clearInterval(modelPollTimer);
          modelPollTimer = null;
          if (dlBar) dlBar.style.width = "100%";
          if (dlPercent) dlPercent.textContent = "100%";
          if (dlTitle) dlTitle.textContent = "Model downloaded & loaded ✓";
          if (dlStats) dlStats.textContent = `${st.total_mb || 1082} MB / ${st.total_mb || 1082} MB`;
          if (dlStatus) dlStatus.textContent = "Complete";

          setTimeout(() => {
            goToOnboardingStep("mail");
          }, 800);
        } else if (st.status === "error") {
          clearInterval(modelPollTimer);
          modelPollTimer = null;
          if (dlStatus) dlStatus.textContent = `Error: ${st.error || "Download failed"}`;
          if (nextBtn) {
            nextBtn.disabled = false;
            nextBtn.textContent = "Retry Download";
          }
        }
      } catch (err) {}
    }, 500);
  } catch (err) {
    goToOnboardingStep("mail");
  }
}

async function finishOnboarding(openAccounts = false) {
  const scrim = document.getElementById("onboarding-scrim");
  if (scrim) scrim.classList.remove("on");

  // Save selection and mark completed
  const formData = new FormData();
  formData.append("device", selectedOnboardingCompute);
  try {
    await fetch("/api/onboarding/complete", {
      method: "POST",
      body: formData,
    });
  } catch (e) {}

  showToast(`Setup completed (${selectedOnboardingCompute.toUpperCase()} mode active)`);

  if (openAccounts) {
    openSettingsModal("accounts");
    showAccountsInstructions();
  }
}

/* Compute Device Settings & CUDA Installer */
async function switchComputeDevice(device) {
  const cpuCard = document.getElementById("settings-card-cpu");
  const gpuCard = document.getElementById("settings-card-gpu");
  const cudaBox = document.getElementById("settings-cuda-box");
  const activeLabel = document.getElementById("settings-active-compute-label");

  if (cpuCard) cpuCard.classList.toggle("selected", device === "cpu");
  if (gpuCard) gpuCard.classList.toggle("selected", device === "gpu");

  const formData = new FormData();
  formData.append("device", device);
  try {
    const res = await fetch("/api/settings/compute", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (device === "gpu") {
      if (!data.cuda_installed && cudaBox) {
        cudaBox.style.display = "block";
      }
      if (activeLabel) activeLabel.textContent = "NVIDIA GPU (CUDA)";
      showToast("Compute device set to NVIDIA GPU");
    } else {
      if (cudaBox) cudaBox.style.display = "none";
      if (activeLabel) activeLabel.textContent = "CPU Multi-threaded";
      showToast("Compute device set to CPU");
    }
  } catch (e) {}
}

async function startCudaDownload(context = "settings") {
  const btn = document.getElementById(`${context}-cuda-install-btn`);
  const progressBox = document.getElementById(`${context}-cuda-progress`);
  const bar = document.getElementById(`${context}-cuda-bar`);
  const statusText = document.getElementById(`${context}-cuda-status-text`);
  const percentText = document.getElementById(`${context}-cuda-percent-text`);

  if (btn) {
    btn.disabled = true;
    btn.textContent = "Downloading...";
  }
  if (progressBox) progressBox.style.display = "block";

  try {
    await fetch("/api/cuda/install", { method: "POST" });
  } catch (e) {}

  if (cudaPollTimer) clearInterval(cudaPollTimer);
  cudaPollTimer = setInterval(async () => {
    try {
      const res = await fetch("/api/cuda/status");
      if (!res.ok) return;
      const data = await res.json();
      const state = data.state;

      if (state.status === "downloading") {
        if (bar) bar.style.width = `${state.percent}%`;
        if (percentText) percentText.textContent = `${state.percent}%`;
        if (statusText) statusText.textContent = `Downloading CUDA runtime (${state.percent}%)...`;
      } else if (state.status === "extracting") {
        if (bar) bar.style.width = `95%`;
        if (percentText) percentText.textContent = `95%`;
        if (statusText) statusText.textContent = "Extracting runtime libraries...";
      } else if (state.status === "ready") {
        clearInterval(cudaPollTimer);
        cudaPollTimer = null;
        if (bar) bar.style.width = `100%`;
        if (percentText) percentText.textContent = `100%`;
        if (statusText) statusText.textContent = "CUDA runtime installed successfully!";
        if (btn) {
          btn.textContent = "Installed ✓";
          btn.disabled = true;
        }
        const badge = document.getElementById(`${context}-gpu-badge`);
        if (badge) {
          badge.className = "compute-badge ready";
          badge.textContent = "Ready";
        }
        showToast("CUDA runtime installed and active!");
      } else if (state.status === "error") {
        clearInterval(cudaPollTimer);
        cudaPollTimer = null;
        if (statusText) statusText.textContent = `Error: ${state.error || "Download failed"}`;
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Retry Download";
        }
      }
    } catch (e) {}
  }, 1000);
}

