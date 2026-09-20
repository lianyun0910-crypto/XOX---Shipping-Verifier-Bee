const API_URL = "http://127.0.0.1:8000";

const analyzeCurrent = document.getElementById("analyzeCurrent");
const connectGmail = document.getElementById("connectGmail");
const openWebApp = document.getElementById("openWebApp");
const openHistory = document.getElementById("openHistory");
const openReview = document.getElementById("openReview");
const connectionStatus = document.getElementById("connectionStatus");
const progressSection = document.getElementById("progressSection");
const progressText = document.getElementById("progressText");
const progressPercent = document.getElementById("progressPercent");
const progressFill = document.getElementById("progressFill");
const resultSection = document.getElementById("resultSection");
const summaryCards = document.getElementById("summaryCards");
const resultsList = document.getElementById("resultsList");
const loadingSection = document.getElementById("loadingSection");
const errorSection = document.getElementById("errorSection");

loadAccount();
loadSaved();

connectGmail.addEventListener("click", () => {
  chrome.tabs.create({ url: `${API_URL}/api/gmail/oauth/start` });
});

analyzeCurrent.addEventListener("click", () => {
  hideError();
  showLoading();
  chrome.runtime.sendMessage({ type: "ANALYZE_CURRENT_EMAIL" }, (response) => {
    if (chrome.runtime.lastError || !response?.ok) {
      hideLoading();
      showError(response?.error || "Open a Gmail email first.");
    }
  });
});

openWebApp.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "OPEN_WEB_APP" }, () => void chrome.runtime.lastError);
});

openHistory.addEventListener("click", () => {
  chrome.tabs.create({ url: "http://localhost:5173/#history" });
});

openReview.addEventListener("click", () => {
  chrome.tabs.create({ url: "http://localhost:5173/#review" });
});

async function loadAccount() {
  try {
    const response = await fetch(`${API_URL}/api/gmail/account`);
    const data = await response.json();
    if (data.connected) {
      connectionStatus.textContent = `Connected · ${data.email || "Gmail"}`;
      connectionStatus.classList.add("connected");
      connectGmail.textContent = "Gmail Connected";
    } else if (data.configured) {
      connectionStatus.textContent = "Gmail not connected";
      connectGmail.textContent = "Connect Gmail";
    } else {
      connectionStatus.textContent = "OAuth not configured";
      connectGmail.textContent = "Set up Gmail OAuth";
    }
  } catch (_) {
    connectionStatus.textContent = "Backend unavailable";
  }
}

chrome.runtime.onMessage.addListener((message) => {
  if (message?.type === "GMAIL_ANALYSIS_STARTED") {
    showLoading();
    updateProgress(0, message.total || 0);
    return;
  }
  if (message?.type === "GMAIL_ANALYSIS_PROGRESS") {
    hideLoading();
    updateProgress(message.data?.processed || 0, message.data?.total || 0);
    renderBatch(message.data || {});
    return;
  }
  if (message?.type === "GMAIL_ANALYSIS_COMPLETED" || message?.type === "GMAIL_ANALYSIS_RESULT") {
    hideLoading();
    updateProgress(message.data?.processed || message.data?.total || 0, message.data?.total || 0);
    renderBatch(message.data || {});
    loadAccount();
    return;
  }
  if (message?.type === "GMAIL_ANALYSIS_ERROR") {
    hideLoading();
    showError(message.data?.error || "Analysis failed.");
    loadAccount();
  }
});

async function loadSaved() {
  const data = await chrome.storage.session.get(["latestGmailAnalysis"]);
  if (!data.latestGmailAnalysis) return;
  const saved = data.latestGmailAnalysis;
  if (saved.status === "ANALYZING" || saved.status === "PROCESSING") {
    updateProgress(saved.processed || 0, saved.total || 0);
    renderBatch(saved);
  } else if (saved.status === "COMPLETED") {
    updateProgress(saved.processed || saved.total || 0, saved.total || 0);
    renderBatch(saved);
  } else if (saved.status === "ERROR") {
    showError(saved.error || "Analysis failed.");
  }
}

function updateProgress(processed, total) {
  progressSection.classList.remove("hidden");
  const percent = total ? Math.round((processed / total) * 100) : 0;
  progressText.textContent = `${processed} / ${total}`;
  progressPercent.textContent = `${percent}%`;
  progressFill.style.width = `${percent}%`;
}

function renderBatch(data) {
  const results = Array.isArray(data.results) ? data.results : [];
  resultSection.classList.remove("hidden");

  const summary = data.summary || {};
  const ok = summary.ok ?? results.filter((r) => r.status === "OK").length;
  const mismatch = summary.mismatch ?? results.filter((r) => r.status === "MISMATCH").length;
  const review = summary.needs_review ?? results.filter((r) => r.status === "NEEDS_REVIEW").length;

  summaryCards.innerHTML = `
    <div class="summary-card"><span>TOTAL</span><strong>${data.total || results.length}</strong></div>
    <div class="summary-card"><span>OK</span><strong>${ok}</strong></div>
    <div class="summary-card"><span>MISMATCH</span><strong>${mismatch}</strong></div>
    <div class="summary-card"><span>REVIEW</span><strong>${review}</strong></div>
  `;

  resultsList.innerHTML = results
    .map((result) => {
      const raw = Number(result.decision_confidence ?? result.confidence ?? 0);
      const confidence = Math.round(raw > 1 ? raw : raw * 100);
      const explanation = result.explanation || result.reason || result.review_reason || "No explanation returned.";
      const attachments = Array.isArray(result.attachment_details) ? result.attachment_details : [];
      return `
        <div class="result-item">
          <div class="result-subject">${escapeHtml(result.subject || result.filename || "Email")}</div>
          <div class="result-meta">
            <span class="pill">${escapeHtml(result.category || result.email_category || "UNKNOWN")}</span>
            <span class="pill ${result.status === "OK" ? "ok" : result.status === "MISMATCH" ? "bad" : "review"}">${escapeHtml(result.status || "UNKNOWN")}</span>
            <span class="pill confidence">AI ${confidence}%</span>
          </div>
          <div class="result-reason">${escapeHtml(explanation)}</div>
          ${result.next_action ? `<div class="result-reason"><strong>Next:</strong> ${escapeHtml(result.next_action)}</div>` : ""}
          ${renderComparisonMini(result)}
          ${attachments.length ? `<div class="attachment-mini">${attachments.length} real attachment${attachments.length === 1 ? "" : "s"} fetched from Gmail</div>` : ""}
        </div>
      `;
    })
    .join("");
}


function renderComparisonMini(result) {
  const fields = result?.comparison?.fields || {};
  const entries = Object.entries(fields);
  if (!entries.length) return "";
  return `<div class="comparison-mini">${entries.slice(0, 7).map(([field, value]) => {
    const status = String(value?.status || "UNRESOLVED").toUpperCase();
    return `<div><span>${escapeHtml(field.replace(/_/g, " "))}</span><strong class="${status === "MATCH" ? "ok" : status === "MISMATCH" ? "bad" : "review"}">${escapeHtml(status)}</strong></div>`;
  }).join("")}</div>`;
}

function showLoading() {
  loadingSection.classList.remove("hidden");
  hideError();
}

function hideLoading() {
  loadingSection.classList.add("hidden");
}

function showError(message) {
  errorSection.textContent = message;
  errorSection.classList.remove("hidden");
}

function hideError() {
  errorSection.classList.add("hidden");
}

function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
