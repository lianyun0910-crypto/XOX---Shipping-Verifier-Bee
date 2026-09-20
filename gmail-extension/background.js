const API_URL =
  "https://xox-shipping-verifier-bee-api.onrender.com";


// ============================================================
// SIDE PANEL
// ============================================================

chrome.sidePanel
  .setPanelBehavior({
    openPanelOnActionClick: true
  })
  .catch(
    (error) => {

      console.error(
        "[Shipping Verifier] Side panel setup failed:",
        error
      );

    }
  );


// ============================================================
// MESSAGE LISTENER
// ============================================================

chrome.runtime.onMessage.addListener(
  (
    message,
    sender,
    sendResponse
  ) => {

    if (
      !message ||
      !message.type
    ) {
      return;
    }


    // --------------------------------------------------------
    // SINGLE EMAIL
    // --------------------------------------------------------

    if (
      message.type ===
      "ANALYZE_EMAIL"
    ) {

      const email =
        message.email;

      const tabId =
        sender.tab?.id ||
        null;


      analyzeEmailBatch(
        [email],
        tabId
      );


      sendResponse({
        ok: true,
        total: 1
      });


      return true;
    }


    // --------------------------------------------------------
    // EMAIL BATCH
    // --------------------------------------------------------

    if (
      message.type ===
      "ANALYZE_EMAIL_BATCH"
    ) {

      const emails =
        Array.isArray(
          message.emails
        )
          ? message.emails
          : [];


      const tabId =
        sender.tab?.id ||
        null;


      console.log(
        "[Shipping Verifier] Analyze email batch:",
        emails.length
      );


      if (
        emails.length ===
        0
      ) {

        sendResponse({
          ok: false,

          error:
            "No emails were provided."
        });

        return true;
      }


      sendResponse({
        ok: true,

        total:
          emails.length
      });


      analyzeEmailBatch(
        emails,
        tabId
      );


      return true;
    }


    // --------------------------------------------------------
    // OPEN WEB APP
    // --------------------------------------------------------

    if (
      message.type ===
      "OPEN_WEB_APP"
    ) {

      chrome.tabs.create({
        url:
          "http://localhost:5173"
      });


      sendResponse({
        ok: true
      });


      return true;
    }


    // --------------------------------------------------------
    // CURRENT EMAIL
    // --------------------------------------------------------

    if (
      message.type ===
      "ANALYZE_CURRENT_EMAIL"
    ) {

      getActiveTab()
        .then(
          (tab) => {

            if (
              !tab ||
              !tab.id
            ) {

              sendResponse({
                ok: false,

                error:
                  "No active Gmail tab found."
              });

              return;
            }


            chrome.tabs.sendMessage(
              tab.id,

              {
                type:
                  "GET_CURRENT_GMAIL_EMAIL"
              },

              (response) => {

                if (
                  chrome.runtime.lastError
                ) {

                  console.error(
                    "[Shipping Verifier] Gmail page error:",
                    chrome.runtime.lastError.message
                  );


                  sendResponse({
                    ok: false,

                    error:
                      "Open a Gmail email first."
                  });

                  return;
                }


                sendResponse(
                  response || {
                    ok: false,

                    error:
                      "Unable to read current Gmail email."
                  }
                );

              }
            );

          }
        )
        .catch(
          (error) => {

            console.error(
              "[Shipping Verifier] Active tab error:",
              error
            );


            sendResponse({
              ok: false,

              error:
                "Unable to access Gmail."
            });

          }
        );


      return true;
    }

  }
);


// ============================================================
// ACTIVE TAB
// ============================================================

async function getActiveTab() {

  const tabs =
    await chrome.tabs.query({
      active: true,
      currentWindow: true
    });


  return tabs[0];
}


// ============================================================
// ANALYZE EMAIL BATCH
// ============================================================

async function analyzeEmailBatch(
  emails,
  tabId
) {

  if (
    !emails ||
    emails.length === 0
  ) {

    return;
  }


  console.log(
    "[Shipping Verifier] Starting Gmail batch:",
    emails.length
  );


  // ----------------------------------------------------------
  // Save state
  // ----------------------------------------------------------

  await chrome.storage.session.set({

    pendingEmailBatch:
      emails,

    latestAnalysis: {

      status:
        "ANALYZING",

      total:
        emails.length,

      processed:
        0,

      results:
        []

    }

  });


  // ----------------------------------------------------------
  // START UI
  // ----------------------------------------------------------

  const startMessage = {

    type:
      "GMAIL_ANALYSIS_STARTED",

    total:
      emails.length

  };


  notifyExtensionPages(
    startMessage
  );


  sendToGmailTab(
    tabId,
    startMessage
  );


  // ----------------------------------------------------------
  // BACKEND BATCH REQUEST
  // ----------------------------------------------------------

  try {

    console.log(
      "[Shipping Verifier] Calling Gmail batch endpoint..."
    );


    const response =
      await fetch(
        `${API_URL}/api/gmail/classify-batch`,
        {

          method:
            "POST",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({
              emails:
                emails
            })

        }
      );


    const text =
      await response.text();


    let data = {};


    try {

      data =
        text
          ? JSON.parse(
              text
            )
          : {};

    } catch {

      throw new Error(
        "Backend returned invalid JSON."
      );

    }


    console.log(
      "[Shipping Verifier] Gmail batch response:",
      data
    );


    if (
      !response.ok
    ) {

      throw new Error(
        data.detail ||
        data.message ||
        `Backend returned HTTP ${response.status}.`
      );

    }


    // --------------------------------------------------------
    // Normalize results
    // --------------------------------------------------------

    const rawResults =
      Array.isArray(
        data.results
      )
        ? data.results
        : [];


    const results =
      rawResults.map(
        (
          result,
          index
        ) => {

          const email =
            emails[index] ||
            {};


          return {

            ...result,

            email_id:
              result.email_id ||
              email.email_id ||
              `gmail-${index}`,

            subject:
              result.subject ||
              email.subject ||
              "Gmail email",

            from:
              result.from ||
              email.from ||
              "",

            category:
              result.category ||
              result.email_category ||
              "UNKNOWN",

            email_category:
              result.email_category ||
              result.category ||
              "UNKNOWN",

            status:
              result.status ||
              "NEEDS_REVIEW",

            gmail_url:
              result.gmail_url ||
              email.gmail_url ||
              ""

          };

        }
      );


    // --------------------------------------------------------
    // Calculate summary
    // --------------------------------------------------------

    const ok =
      results.filter(
        (item) =>
          item.status ===
          "OK"
      ).length;


    const mismatch =
      results.filter(
        (item) =>
          item.status ===
          "MISMATCH"
      ).length;


    const needsReview =
      results.filter(
        (item) =>
          item.status ===
          "NEEDS_REVIEW"
      ).length;


    const analysis = {

      status:
        "COMPLETED",

      run_id:
        data.run_id ||
        "",

      total:
        results.length,

      processed:
        results.length,

      ok:
        data.summary?.ok ??
        ok,

      mismatch:
        data.summary?.mismatch ??
        mismatch,

      needs_review:
        data.summary?.needs_review ??
        needsReview,

      summary:
        data.summary ||
        {
          total:
            results.length,

          ok:
            ok,

          mismatch:
            mismatch,

          needs_review:
            needsReview
        },

      results:
        results,

      history:
        data.history ||
        null,

      cloud_archive:
        data.cloud_archive ||
        null

    };


    // --------------------------------------------------------
    // Save final extension state
    // --------------------------------------------------------

    await chrome.storage.session.set({

      latestAnalysis:
        analysis

    });


    // --------------------------------------------------------
    // Notify side panel
    // --------------------------------------------------------

    notifyExtensionPages({

      type:
        "GMAIL_ANALYSIS_COMPLETED",

      data:
        analysis

    });


    // --------------------------------------------------------
    // Notify Gmail Bee
    // --------------------------------------------------------

    sendToGmailTab(
      tabId,
      {
        type:
          "GMAIL_ANALYSIS_COMPLETED",

        data:
          analysis

      }
    );


    console.log(
      "[Shipping Verifier] Gmail analysis completed:",
      analysis
    );


  } catch (
    error
  ) {

    console.error(
      "[Shipping Verifier] Gmail batch analysis failed:",
      error
    );


    const errorMessage =
      getErrorMessage(
        error
      );


    const analysis = {

      status:
        "ERROR",

      total:
        emails.length,

      processed:
        0,

      results:
        [],

      error:
        errorMessage

    };


    await chrome.storage.session.set({

      latestAnalysis:
        analysis

    });


    notifyExtensionPages({

      type:
        "GMAIL_ANALYSIS_ERROR",

      data:
        analysis

    });


    sendToGmailTab(
      tabId,
      {
        type:
          "GMAIL_ANALYSIS_ERROR",

        data:
          analysis

      }
    );

  }

}


// ============================================================
// SEND TO GMAIL TAB
// ============================================================

function sendToGmailTab(
  tabId,
  message
) {

  if (
    tabId === null ||
    tabId === undefined
  ) {

    return;
  }


  chrome.tabs.sendMessage(
    tabId,
    message,
    () => {

      if (
        chrome.runtime.lastError
      ) {

        console.debug(
          "[Shipping Verifier] Gmail notification failed:",
          chrome.runtime.lastError.message
        );

      }

    }
  );

}


// ============================================================
// NOTIFY EXTENSION PAGES
// ============================================================

function notifyExtensionPages(
  message
) {

  chrome.runtime.sendMessage(
    message,
    () => {

      if (
        chrome.runtime.lastError
      ) {

        console.debug(
          "[Shipping Verifier] No extension page listening."
        );

      }

    }
  );

}


// ============================================================
// ERROR
// ============================================================

function getErrorMessage(
  error
) {

  if (
    error &&
    typeof error.message ===
      "string"
  ) {

    return error.message;

  }


  return String(
    error ||
    "Unknown error."
  );

}