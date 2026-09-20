const API_URL =
  "https://xox-shipping-verifier-bee-api.onrender.com";

const POLL_INTERVAL_MS = 1000;


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
  // Save initial state
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
  // CREATE ASYNC BACKEND JOB
  // ----------------------------------------------------------

  try {

    console.log(
      "[Shipping Verifier] Creating Gmail analysis job..."
    );


    const response =
      await fetch(
        `${API_URL}/api/gmail/analyze-batch`,
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
      "[Shipping Verifier] Gmail analysis job created:",
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


    if (
      !data.job_id
    ) {

      throw new Error(
        "Backend did not return a Gmail analysis job ID."
      );

    }


    // --------------------------------------------------------
    // Save job state
    // --------------------------------------------------------

    await chrome.storage.session.set({

      latestAnalysis: {

        status:
          data.status ||
          "QUEUED",

        job_id:
          data.job_id,

        total:
          data.total ||
          emails.length,

        processed:
          0,

        results:
          []

      }

    });


    // --------------------------------------------------------
    // START POLLING
    // --------------------------------------------------------

    await pollGmailJob(
      data.job_id,
      emails,
      tabId
    );


  } catch (
    error
  ) {

    console.error(
      "[Shipping Verifier] Gmail batch analysis failed:",
      error
    );


    await finishAnalysisError(
      getErrorMessage(
        error
      ),
      emails,
      tabId
    );

  }

}


// ============================================================
// POLL GMAIL ANALYSIS JOB
// ============================================================

async function pollGmailJob(
  jobId,
  emails,
  tabId
) {

  console.log(
    "[Shipping Verifier] Polling Gmail job:",
    jobId
  );


  while (
    true
  ) {

    try {

      const response =
        await fetch(
          `${API_URL}/api/gmail/status/${encodeURIComponent(jobId)}`,
          {
            method:
              "GET",

            cache:
              "no-store"
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
          "Backend returned invalid JSON while checking Gmail job."
        );

      }


      console.log(
        "[Shipping Verifier] Gmail job status:",
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


      const status =
        String(
          data.status ||
          ""
        ).toUpperCase();


      const processed =
        Number(
          data.processed ||
          0
        );


      const total =
        Number(
          data.total ||
          emails.length ||
          0
        );


      const currentResults =
        Array.isArray(
          data.results
        )
          ? data.results
          : [];


      // ------------------------------------------------------
      // SAVE CURRENT PROGRESS
      // ------------------------------------------------------

      await chrome.storage.session.set({

        latestAnalysis: {

          ...data,

          status:

            status ||
            "PROCESSING",

          job_id:
            jobId,

          total:
            total,

          processed:
            processed,

          results:
            currentResults

        }

      });


      // ------------------------------------------------------
      // SEND PROGRESS TO SIDE PANEL
      // ------------------------------------------------------

      notifyExtensionPages({

        type:
          "GMAIL_ANALYSIS_PROGRESS",

        data: {

          ...data,

          status:
            status ||
            "PROCESSING",

          job_id:
            jobId,

          total:
            total,

          processed:
            processed,

          results:
            currentResults

        }

      });


      // ------------------------------------------------------
      // SEND PROGRESS TO GMAIL BEE
      // ------------------------------------------------------

      sendToGmailTab(
        tabId,
        {

          type:
            "GMAIL_ANALYSIS_PROGRESS",

          data: {

            ...data,

            status:
              status ||
              "PROCESSING",

            job_id:
              jobId,

            total:
              total,

            processed:
              processed,

            results:
              currentResults

          }

        }
      );


      // ------------------------------------------------------
      // COMPLETED
      // ------------------------------------------------------

      if (
        status ===
          "COMPLETED" ||

        status ===
          "SUCCESS" ||

        status ===
          "DONE"
      ) {

        console.log(
          "[Shipping Verifier] Gmail job completed."
        );


        const analysis =
          normalizeCompletedAnalysis(
            data,
            emails
          );


        await chrome.storage.session.set({

          latestAnalysis:
            analysis

        });


        // ----------------------------------------------------
        // SIDE PANEL
        // ----------------------------------------------------

        notifyExtensionPages({

          type:
            "GMAIL_ANALYSIS_COMPLETED",

          data:
            analysis

        });


        // ----------------------------------------------------
        // GMAIL BEE
        // ----------------------------------------------------

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
          "[Shipping Verifier] Final Gmail analysis:",
          analysis
        );


        return;
      }


      // ------------------------------------------------------
      // ERROR
      // ------------------------------------------------------

      if (
        status ===
          "ERROR" ||

        status ===
          "FAILED"
      ) {

        throw new Error(
          data.error ||
          data.message ||
          "Gmail analysis job failed."
        );

      }


      // ------------------------------------------------------
      // STILL PROCESSING
      // ------------------------------------------------------

      await sleep(
        POLL_INTERVAL_MS
      );

    } catch (
      error
    ) {

      console.error(
        "[Shipping Verifier] Gmail polling failed:",
        error
      );


      throw error;

    }

  }

}


// ============================================================
// NORMALIZE COMPLETED RESULT
// ============================================================

function normalizeCompletedAnalysis(
  data,
  emails
) {

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


  // ----------------------------------------------------------
  // SUMMARY
  // ----------------------------------------------------------

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


  return {

    ...data,

    status:
      "COMPLETED",

    job_id:
      data.job_id ||
      "",

    run_id:
      data.run_id ||
      "",

    total:
      Number(
        data.total
      ) ||
      results.length,

    processed:
      Number(
        data.processed
      ) ||
      results.length,

    ok:
      data.summary?.ok ??
      data.ok ??
      ok,

    mismatch:
      data.summary?.mismatch ??
      data.mismatch ??
      mismatch,

    needs_review:
      data.summary?.needs_review ??
      data.needs_review ??
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

}


// ============================================================
// ERROR HANDLING
// ============================================================

async function finishAnalysisError(
  errorMessage,
  emails,
  tabId
) {

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


  // ----------------------------------------------------------
  // SIDE PANEL
  // ----------------------------------------------------------

  notifyExtensionPages({

    type:
      "GMAIL_ANALYSIS_ERROR",

    data:
      analysis

  });


  // ----------------------------------------------------------
  // GMAIL BEE
  // ----------------------------------------------------------

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
// SLEEP
// ============================================================

function sleep(
  milliseconds
) {

  return new Promise(
    (resolve) => {

      setTimeout(
        resolve,
        milliseconds
      );

    }
  );

}


// ============================================================
// ERROR MESSAGE
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