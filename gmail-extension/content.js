let bee = null;
let label = null;
let bubble = null;

let pressedEmail = null;

let trackingPointer = false;
let customDragging = false;
let overBee = false;

let startX = 0;
let startY = 0;

const DRAG_THRESHOLD = 8;


// ============================================================
// INIT
// ============================================================

function init() {

  if (
    document.getElementById(
      "shipping-verifier-bee"
    )
  ) {

    return;
  }


  console.log(
    "[Shipping Verifier] Initializing Bee..."
  );


  createBee();

  attachPointerDrag();

  observeNavigation();


  console.log(
    "[Shipping Verifier] Bee loaded."
  );
}


// ============================================================
// CREATE BEE
// ============================================================

function createBee() {

  bee =
    document.createElement(
      "div"
    );

  bee.id =
    "shipping-verifier-bee";


  const image =
    document.createElement(
      "img"
    );

  image.src =
    chrome.runtime.getURL(
      "bee.svg"
    );

  image.alt =
    "Shipping Verifier Bee";


  label =
    document.createElement(
      "div"
    );

  label.id =
    "shipping-verifier-bee-label";

  label.textContent =
    "Drop email here";


  bee.appendChild(
    image
  );

  bee.appendChild(
    label
  );


  // ----------------------------------------------------------
  // Click opens web app.
  // ----------------------------------------------------------

  bee.addEventListener(
    "click",
    () => {

      chrome.runtime.sendMessage({
        type:
          "OPEN_WEB_APP"
      });

    }
  );


  // ----------------------------------------------------------
  // Native drag fallback.
  // ----------------------------------------------------------

  bee.addEventListener(
    "dragover",
    (event) => {

      event.preventDefault();

      activateBee();

    },
    true
  );


  bee.addEventListener(
    "dragenter",
    (event) => {

      event.preventDefault();

      activateBee();

    },
    true
  );


  bee.addEventListener(
    "dragleave",
    () => {

      deactivateBee();

    },
    true
  );


  bee.addEventListener(
    "drop",
    (event) => {

      event.preventDefault();

      const emails =
        collectSelectedEmails(
          event.target
        );


      if (
        emails.length
      ) {

        analyzeEmails(
          emails
        );

      } else {

        const fallback =
          extractEmailFromElement(
            event.target
          );


        if (fallback) {

          analyzeEmails(
            [
              fallback
            ]
          );

        } else {

          showBubble(
            "I could not read the Gmail email.",
            "error"
          );

        }

      }

    },
    true
  );


  document.body.appendChild(
    bee
  );


  bubble =
    document.createElement(
      "div"
    );

  bubble.id =
    "shipping-verifier-bubble";


  document.body.appendChild(
    bubble
  );
}


// ============================================================
// POINTER DRAG
// ============================================================

function attachPointerDrag() {

  document.addEventListener(
    "pointerdown",
    (event) => {

      if (
        event.button !== 0
      ) {

        return;
      }


      if (
        bee &&
        bee.contains(
          event.target
        )
      ) {

        return;
      }


      const email =
        extractEmailFromElement(
          event.target
        );


      if (!email) {

        return;
      }


      pressedEmail =
        email;

      trackingPointer =
        true;

      customDragging =
        false;

      overBee =
        false;


      startX =
        event.clientX;

      startY =
        event.clientY;


      console.log(
        "[Shipping Verifier] Email pointer down:",
        email.subject
      );

    },
    true
  );


  document.addEventListener(
    "pointermove",
    (event) => {

      if (
        !trackingPointer ||
        !pressedEmail
      ) {

        return;
      }


      const distance =
        Math.sqrt(
          Math.pow(
            event.clientX -
              startX,
            2
          )
          +
          Math.pow(
            event.clientY -
              startY,
            2
          )
        );


      if (
        !customDragging &&
        distance >=
          DRAG_THRESHOLD
      ) {

        customDragging =
          true;

        showDraggingState();

        console.log(
          "[Shipping Verifier] Custom drag started."
        );
      }


      if (
        !customDragging
      ) {

        return;
      }


      const rect =
        bee.getBoundingClientRect();


      const inside =
        event.clientX >=
          rect.left
        &&
        event.clientX <=
          rect.right
        &&
        event.clientY >=
          rect.top
        &&
        event.clientY <=
          rect.bottom;


      if (
        inside &&
        !overBee
      ) {

        overBee =
          true;

        activateBee();

      }


      if (
        !inside &&
        overBee
      ) {

        overBee =
          false;

        deactivateBee();

      }

    },
    true
  );


  document.addEventListener(
    "pointerup",
    (event) => {

      if (
        !trackingPointer
      ) {

        return;
      }


      const wasDragging =
        customDragging;

      const dropped =
        overBee;


      resetPointer();


      if (
        wasDragging &&
        dropped
      ) {

        const emails =
          collectSelectedEmails(
            event.target,
            pressedEmail
          );


        if (
          emails.length
        ) {

          analyzeEmails(
            emails
          );

        } else {

          analyzeEmails(
            [
              pressedEmail
            ]
          );

        }

      }

    },
    true
  );


  document.addEventListener(
    "pointercancel",
    () => {

      resetPointer();

    },
    true
  );
}


// ============================================================
// RESET
// ============================================================

function resetPointer() {

  trackingPointer =
    false;

  customDragging =
    false;

  overBee =
    false;

  pressedEmail =
    null;

  deactivateBee();
}


// ============================================================
// EMAIL ROW
// ============================================================

function findGmailRow(
  element
) {

  if (!element) {
    return null;
  }


  const selectors = [
    "tr.zA",
    "tr[role='row']",
    "[data-legacy-thread-id]",
    "[data-thread-id]",
    "[role='main'] tr"
  ];


  for (
    const selector of
      selectors
  ) {

    try {

      const row =
        element.closest(
          selector
        );


      if (row) {

        return row;
      }

    } catch {
      // Ignore.
    }

  }


  return null;
}


// ============================================================
// EXTRACT EMAIL
// ============================================================

function extractEmailFromElement(
  element
) {

  const row =
    findGmailRow(
      element
    );


  if (!row) {
    return null;
  }


  const text =
    (
      row.innerText ||
      ""
    ).trim();


  if (!text) {
    return null;
  }


  // Sender.
  const senderElement =
    row.querySelector(
      "[email]"
    ) ||
    row.querySelector(
      "[data-hovercard-id]"
    ) ||
    row.querySelector(
      ".yW"
    );


  const sender =
    senderElement?.getAttribute(
      "email"
    )
    ||
    senderElement?.innerText?.trim()
    ||
    "";


  // Subject.
  const subjectElement =
    row.querySelector(
      ".bog"
    )
    ||
    row.querySelector(
      ".y6"
    )
    ||
    row.querySelector(
      "span.bog"
    );


  let subject =
    subjectElement?.innerText?.trim()
    ||
    "";


  // Snippet.
  const snippetElement =
    row.querySelector(
      ".y2"
    )
    ||
    row.querySelector(
      "span.y2"
    );


  const snippet =
    snippetElement?.innerText?.trim()
    ||
    "";


  // Gmail URL.
  let gmailUrl =
    "";


  const links =
    Array.from(
      row.querySelectorAll(
        "a[href]"
      )
    );


  for (
    const link of links
  ) {

    const href =
      link.getAttribute(
        "href"
      );


    if (
      href &&
      href.includes(
        "#"
      )
    ) {

      gmailUrl =
        new URL(
          href,
          window.location.origin
        ).href;

      break;
    }

  }


  // Gmail identifiers. Prefer explicit DOM attributes when Gmail exposes them.
  const gmailThreadId =
    row.getAttribute(
      "data-legacy-thread-id"
    )
    ||
    row.getAttribute(
      "data-thread-id"
    )
    ||
    "";

  const gmailMessageId =
    row.getAttribute(
      "data-legacy-message-id"
    )
    ||
    row.getAttribute(
      "data-message-id"
    )
    ||
    "";

  const emailId =
    gmailThreadId
    ||
    gmailMessageId
    ||
    extractIdFromUrl(
      gmailUrl
    )
    ||
    `gmail-${Date.now()}-${Math.random()}`;


  // Fallback subject.
  if (!subject) {

    const lines =
      text
        .split("\n")
        .map(
          (line) =>
            line.trim()
        )
        .filter(Boolean);


    subject =
      lines
        .slice(
          1,
          4
        )
        .join(
          " "
        )
        .slice(
          0,
          200
        );
  }


  const body =
    [
      subject,
      snippet,
      text
    ]
      .filter(Boolean)
      .join(
        "\n\n"
      )
      .slice(
        0,
        12000
      );


  return {

    email_id:
      emailId,

    gmail_message_id:
      gmailMessageId,

    gmail_thread_id:
      gmailThreadId,

    from:
      sender,

    to:
      "",

    subject:
      subject ||
      "Gmail email",

    body:
      body,

    attachments:
      [],

    source:
      "gmail_drag",

    gmail_url:
      gmailUrl ||
      window.location.href

  };
}


// ============================================================
// MULTIPLE SELECTED EMAILS
// ============================================================

function collectSelectedEmails(
  fallbackTarget,
  fallbackEmail = null
) {

  const results = [];

  const seen =
    new Set();


  // ----------------------------------------------------------
  // Try Gmail's checked checkboxes.
  // ----------------------------------------------------------

  const checkboxSelectors = [
    "input[type='checkbox']:checked",
    "[aria-checked='true']"
  ];


  const candidates = [];


  for (
    const selector of
      checkboxSelectors
  ) {

    const elements =
      Array.from(
        document.querySelectorAll(
          selector
        )
      );


    candidates.push(
      ...elements
    );

  }


  for (
    const element of
      candidates
  ) {

    const email =
      extractEmailFromElement(
        element
      );


    if (!email) {
      continue;
    }


    const key =
      email.email_id ||
      email.gmail_url ||
      email.subject;


    if (
      seen.has(key)
    ) {

      continue;
    }


    seen.add(
      key
    );

    results.push(
      email
    );
  }


  // ----------------------------------------------------------
  // If Gmail selected state was not detectable, use the email
  // that was actually dragged.
  // ----------------------------------------------------------

  if (
    fallbackEmail
  ) {

    const key =
      fallbackEmail.email_id ||
      fallbackEmail.gmail_url ||
      fallbackEmail.subject;


    if (
      !seen.has(key)
    ) {

      results.push(
        fallbackEmail
      );
    }

  }


  // ----------------------------------------------------------
  // Final fallback.
  // ----------------------------------------------------------

  if (
    results.length === 0 &&
    fallbackTarget
  ) {

    const email =
      extractEmailFromElement(
        fallbackTarget
      );


    if (email) {

      results.push(
        email
      );
    }

  }


  return results;
}


// ============================================================
// CURRENT OPEN EMAIL
// ============================================================

function extractCurrentGmailEmail() {

  const subject =
    document.querySelector(
      "h2.hP"
    )?.innerText?.trim()
    ||
    "";


  const senderElement =
    document.querySelector(
      "[role='main'] [email]"
    )
    ||
    document.querySelector(
      "[email]"
    );


  const sender =
    senderElement?.getAttribute(
      "email"
    )
    ||
    senderElement?.innerText
    ||
    "";


  const body =
    document.querySelector(
      "div.a3s.aiL"
    )?.innerText?.trim()
    ||
    document.querySelector(
      "div.a3s"
    )?.innerText?.trim()
    ||
    "";


  if (
    !subject &&
    !body
  ) {

    return null;
  }


  const attachments =
    Array.from(
      document.querySelectorAll(
        ".aQH, .aZo, .aV3"
      )
    )
      .map(
        (element) =>
          (
            element.innerText
            ||
            element.getAttribute(
              "data-tooltip"
            )
            ||
            ""
          ).trim()
      )
      .filter(Boolean);


  const currentUrlId =
    extractIdFromUrl(
      window.location.href
    )
    ||
    "";

  return {

    email_id:
      currentUrlId
      ||
      `gmail-${Date.now()}`,

    gmail_message_id:
      currentUrlId,

    gmail_thread_id:
      currentUrlId,

    from:
      sender,

    to:
      "",

    subject:
      subject ||
      "Gmail email",

    body:
      body.slice(
        0,
        20000
      ),

    attachments:
      attachments,

    source:
      "gmail_current_email",

    gmail_url:
      window.location.href

  };
}


// ============================================================
// URL ID
// ============================================================

function extractIdFromUrl(
  href
) {

  if (!href) {
    return "";
  }


  const match =
    href.match(
      /#(?:.*\/)?([a-zA-Z0-9_-]{8,})$/
    );


  return (
    match
      ? match[1]
      : ""
  );
}


// ============================================================
// UI STATE
// ============================================================

function showDraggingState() {

  if (!bee) {
    return;
  }


  bee.classList.add(
    "drag-active"
  );


  label.textContent =
    "Drag to Bee";
}


function activateBee() {

  if (!bee) {
    return;
  }


  bee.classList.add(
    "drag-active"
  );


  label.textContent =
    "Release to analyze";
}


function deactivateBee() {

  if (!bee) {
    return;
  }


  bee.classList.remove(
    "drag-active"
  );


  if (
    !bee.classList.contains(
      "analyzing"
    )
  ) {

    label.textContent =
      "Drop email here";
  }
}


// ============================================================
// ANALYZE
// ============================================================

function analyzeEmails(
  emails
) {

  if (
    !emails ||
    !emails.length
  ) {

    showBubble(
      "No email detected.",
      "error"
    );

    return;
  }


  showAnalyzing(
    emails.length
  );


  chrome.runtime.sendMessage(
    {
      type:
        "ANALYZE_EMAIL_BATCH",

      emails:
        emails
    },
    () => {

      if (
        chrome.runtime.lastError
      ) {

        showBubble(
          "Could not connect to Shipping Verifier.",
          "error"
        );

      }

    }
  );
}


// ============================================================
// ANALYZING
// ============================================================

function showAnalyzing(
  total
) {

  bee.classList.remove(
    "success",
    "mismatch"
  );


  bee.classList.add(
    "analyzing"
  );


  label.textContent =
    total > 1
      ? `Analyzing ${total} emails...`
      : "Analyzing email...";


  bubble.classList.remove(
    "visible"
  );
}


// ============================================================
// SHOW RESULTS
// ============================================================

function showBatchResult(
  data
) {

  bee.classList.remove("analyzing");

  const results = Array.isArray(data?.results) ? data.results : [];
  const ok = results.filter((item) => String(item?.status || "").toUpperCase() === "OK").length;
  const mismatch = results.filter((item) => String(item?.status || "").toUpperCase() === "MISMATCH").length;
  const review = results.filter((item) => String(item?.status || "").toUpperCase() === "NEEDS_REVIEW").length;

  bee.classList.remove("mismatch", "success");
  bee.classList.add(review || mismatch ? "mismatch" : "success");
  label.textContent = results.length === 1 ? (results[0]?.status || "Analyzed") : `${results.length} analyzed`;

  function safe(value) {
    return escapeHtml(value === null || value === undefined || value === "" ? "—" : String(value));
  }

  function confidenceText(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${Math.round((number <= 1 ? number : number / 100) * 100)}%`;
  }

  function evidence(value) {
    if (Array.isArray(value)) {
      return value.slice(0, 4).map((item) => `<div class="sv-result-reason">• ${safe(typeof item === "object" ? JSON.stringify(item) : item)}</div>`).join("");
    }
    if (value && typeof value === "object") return `<div class="sv-result-reason">${safe(JSON.stringify(value))}</div>`;
    return value ? `<div class="sv-result-reason">${safe(value)}</div>` : "";
  }

  function fields(result) {
    const values = Object.entries(result?.comparison?.fields || {});
    if (!values.length) return "";
    return `
      <div class="sv-compare-title">SI / BL Comparison</div>
      <div class="sv-compare-table-wrap">
        <table class="sv-compare-table">
          <thead><tr><th>Field</th><th>SI</th><th>BL</th><th>Status</th></tr></thead>
          <tbody>
            ${values.map(([field, value]) => {
              const status = String(value?.status || "UNRESOLVED").toUpperCase();
              const className = status === "MATCH" ? "match" : status === "MISMATCH" ? "bad" : "review";
              return `<tr><td>${safe(field.replace(/_/g, " "))}</td><td>${safe(value?.si)}</td><td>${safe(value?.bl)}</td><td><span class="sv-field-status ${className}">${safe(status)}</span></td></tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>`;
  }

  function card(result) {
    const comparison = result?.comparison || {};
    const reason = result?.explanation || comparison?.explanation || result?.reason || result?.review_reason || "";
    const nextAction = result?.next_action || comparison?.next_action || "";
    return `
      <div class="sv-result-card">
        <div class="sv-result-subject">${safe(result?.subject || "Email")}</div>
        <div>
          <span class="sv-result-category">${safe(result?.category || result?.email_category || "UNKNOWN")}</span>
          <span class="sv-result-status ${result?.status === "NEEDS_REVIEW" || result?.status === "MISMATCH" ? "review" : ""}">${safe(result?.status || "UNKNOWN")}</span>
        </div>
        <div class="sv-ai-grid">
          <div><strong>Confidence</strong><span>${confidenceText(result?.confidence ?? result?.decision_confidence)}</span></div>
          <div><strong>Attachments</strong><span>${safe(result?.attachment_count ?? (result?.documents || []).length)}</span></div>
        </div>
        ${result?.si_filename || result?.bl_filename ? `<div class="sv-result-reason">SI: ${safe(result?.si_filename)}<br/>BL: ${safe(result?.bl_filename)}</div>` : ""}
        ${reason ? `<div class="sv-result-reason"><strong>Reason</strong><br/>${safe(reason)}</div>` : ""}
        ${nextAction ? `<div class="sv-result-reason"><strong>Next action</strong><br/>${safe(nextAction)}</div>` : ""}
        ${result?.confidence_explanation ? `<div class="sv-result-reason"><strong>Confidence</strong><br/>${safe(result?.confidence_explanation)}</div>` : ""}
        ${fields(result)}
        ${evidence(result?.evidence || comparison?.evidence)}
      </div>`;
  }

  showBubble(`
    <div class="sv-result-title">AI verification</div>
    <div class="sv-summary">${results.length} total · ${ok} OK · ${mismatch} mismatch · ${review} needs review</div>
    ${results.slice(0, 3).map(card).join("") || `<div class="sv-error">No verification result returned.</div>`}
    ${results.length > 3 ? `<div class="sv-summary">Open the Bee side panel to view all results.</div>` : ""}
  `, "result");
}

// ============================================================
// BUBBLE
// ============================================================

function showBubble(
  content,
  type
) {

  if (!bubble) {
    return;
  }


  if (
    type ===
    "error"
  ) {

    bubble.innerHTML =
      `

        <div class="sv-result-title">
          Bee needs help
        </div>

        <div class="sv-error">
          ${escapeHtml(content)}
        </div>

      `;

  } else {

    bubble.innerHTML =
      content;
  }


  bubble.classList.add(
    "visible"
  );


  setTimeout(
    () => {

      bubble.classList.remove(
        "visible"
      );

    },
    10000
  );
}


// ============================================================
// ESCAPE
// ============================================================

function escapeHtml(
  value
) {

  return String(
    value || ""
  )
    .replace(
      /&/g,
      "&amp;"
    )
    .replace(
      /</g,
      "&lt;"
    )
    .replace(
      />/g,
      "&gt;"
    )
    .replace(
      /"/g,
      "&quot;"
    )
    .replace(
      /'/g,
      "&#039;"
    );
}


// ============================================================
// BACKGROUND EVENTS
// ============================================================

chrome.runtime.onMessage.addListener(
  (
    message
  ) => {

    if (
      message?.type ===
      "GMAIL_ANALYSIS_STARTED"
    ) {

      showAnalyzing(
        message.total ||
        1
      );

      return;
    }


    if (
      message?.type ===
      "GMAIL_ANALYSIS_COMPLETED"
    ) {

      showBatchResult(
        message.data ||
        {}
      );

      return;
    }


    if (
      message?.type ===
      "GMAIL_ANALYSIS_ERROR"
    ) {

      bee.classList.remove(
        "analyzing"
      );

      bee.classList.add(
        "mismatch"
      );

      label.textContent =
        "Analysis failed";


      showBubble(
        message.data?.error
        ||
        "Analysis failed.",
        "error"
      );

    }

  }
);


// ============================================================
// CURRENT EMAIL REQUEST
// ============================================================

chrome.runtime.onMessage.addListener(
  (
    message,
    sender,
    sendResponse
  ) => {

    if (
      message?.type ===
      "GET_CURRENT_GMAIL_EMAIL"
    ) {

      const email =
        extractCurrentGmailEmail();


      if (!email) {

        sendResponse({
          ok: false,

          error:
            "Please open a Gmail email first."
        });

        return;
      }


      sendResponse({
        ok: true,

        email:
          email
      });


      return true;
    }

  }
);


// ============================================================
// NAVIGATION
// ============================================================

function observeNavigation() {

  let lastUrl =
    window.location.href;


  setInterval(
    () => {

      if (
        window.location.href !==
        lastUrl
      ) {

        lastUrl =
          window.location.href;


        if (bee) {

          bee.classList.remove(
            "analyzing",
            "success",
            "mismatch",
            "drag-active"
          );

        }


        if (bubble) {

          bubble.classList.remove(
            "visible"
          );

        }

      }

    },
    700
  );
}


// ============================================================
// START
// ============================================================

if (
  document.readyState ===
  "loading"
) {

  document.addEventListener(
    "DOMContentLoaded",
    init
  );

} else {

  init();
}