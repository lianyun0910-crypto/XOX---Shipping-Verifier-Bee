import React, {
  useEffect,
  useMemo,
  useState,
} from "react";

import "./App.css";


 const API =
  "https://xox-shipping-verifier-bee-api.onrender.com";


type Result = {
  filename?: string;
  email_id?: string;
  subject?: string;
  from?: string;

  status?: string;

  category?: string;
  email_category?: string;

  classification?: {
    category?: string;
    confidence?: number;
    confidence_level?: string;
    confidence_explanation?: string;
    reason?: string;
    explanation?: string;
    evidence?: any;
    next_action?: string;
  };

  email_classification?: {
    category?: string;
    confidence?: number;
    confidence_level?: string;
    confidence_explanation?: string;
    reason?: string;
    explanation?: string;
    evidence?: any;
    next_action?: string;
  };

  document_classification?: {
    document_type?: string;
    confidence?: number;
  };

  language?: string;

  // AI decision metadata
  confidence?: number;
  confidence_level?: string;
  confidence_explanation?: string;
  explanation?: string;
  evidence?: any;
  next_action?: string;

  reason?: string;

  review_reason?: string;

  details?: string;

  documents?: any[];

  si_filename?: string;
  bl_filename?: string;

  comparison?: {
    status?: string;
    reason?: string;

    fields?: Record<
      string,
      {
        si?: any;
        bl?: any;
        status?: string;
        confidence?: number;
        reason?: string;
        explanation?: string;
        evidence?: any;
        next_action?: string;
      }
    >;

    mismatch_fields?: string[];
    unresolved_fields?: string[];

    confidence?: number;
    overall_confidence?: number;
    confidence_level?: string;
    confidence_explanation?: string;
    explanation?: string;
    evidence?: any;
    next_action?: string;
  };
};


type Job = {
  job_id?: string;

  status?: string;

  phase?: string;

  progress?: number;

  current_filename?: string;

  total_files?: number;

  total_cases?: number;

  processed_cases?: number;

  ok?: number;

  mismatch?: number;

  needs_review?: number;

  results?: Result[];

  summary?: {
    total?: number;
    ok?: number;
    mismatch?: number;
    needs_review?: number;
  };

  excel?: {
    filename?: string;
    cloud_url?: string;
    uploaded?: boolean;
    cloud_status?: string;
  };

  cloud_archive?: any;

  error?: string;
};


type HistoryEntry = {
  run_id: string;

  timestamp_utc?: string;

  timestamp_display?: string;

  source?: string;

  summary?: {
    total?: number;
    ok?: number;
    mismatch?: number;
    needs_review?: number;
    documents_processed?: number;
    fields_compared?: number;
  };

  results?: Result[];
};


function cleanFilename(
  value?: string
) {

  return String(
    value || ""
  ).replace(
    /^[a-f0-9]{32}_/i,
    ""
  );
}


function statusClass(
  status?: string
) {

  const value =
    String(
      status ||
      "NEEDS_REVIEW"
    ).toUpperCase();


  if (
    value === "OK" ||
    value === "MATCH"
  ) {

    return "ok";
  }


  if (
    value ===
    "MISMATCH"
  ) {

    return "mismatch";
  }


  return "review";
}


function displayStatus(
  status?: string
) {

  const value =
    String(
      status ||
      "NEEDS_REVIEW"
    ).toUpperCase();


  return value ===
    "NEEDS_REVIEW"
    ? "NEEDS REVIEW"
    : value;
}


function category(
  result: Result
) {

  const candidates = [
    result.email_category,
    result.email_classification?.category,
    result.classification?.category,
    result.category,
  ];

  const validCategories = new Set([
    "BL_COMPARISON",
    "SI_REQUEST",
    "INVOICE_QUERY",
    "GENERAL",
    "SPAM",
  ]);

  const matched = candidates.find(
    (value) =>
      value &&
      validCategories.has(
        String(value).toUpperCase()
      )
  );

  if (matched) {
    return String(matched).toUpperCase();
  }

  const fallback = candidates.find(Boolean);

  if (fallback) {
    const normalized = String(fallback).toUpperCase();

    if (normalized === "DOCUMENT_UPLOAD") {
      return "DOCUMENT";
    }

    return normalized;
  }

  return "UNKNOWN";
}


function fieldLabel(
  field: string
) {

  return field
    .replace(
      /_/g,
      " "
    )
    .replace(
      /\b\w/g,
      (
        char
      ) =>
        char.toUpperCase()
    );
}


function getDocumentType(
  document: any
) {

  return (
    document?.document_type ||
    document?.type ||
    document?.result?.document_type ||
    document?.classification?.document_type ||
    document?.document_classification?.document_type ||
    "OTHER"
  ).toString().toUpperCase();
}


function formatTime(
  entry: HistoryEntry
) {

  if (
    entry.timestamp_display
  ) {

    return entry.timestamp_display;
  }


  if (
    entry.timestamp_utc
  ) {

    const date =
      new Date(
        entry.timestamp_utc
      );


    if (
      !Number.isNaN(
        date.getTime()
      )
    ) {

      return new Intl.DateTimeFormat(
        "en-GB",
        {
          day:
            "2-digit",

          month:
            "short",

          year:
            "numeric",

          hour:
            "numeric",

          minute:
            "2-digit",

          hour12:
            true,
        }
      ).format(
        date
      );
    }
  }


  return "";
}


function App() {

  const [
    page,
    setPage,
  ] = useState<
    "verify" | "history"
  >(
    window.location.hash ===
      "#history"
      ? "history"
      : "verify"
  );


  const [
    files,
    setFiles,
  ] = useState<File[]>(
    []
  );


  const [
    job,
    setJob,
  ] = useState<Job | null>(
    null
  );


  const [
    error,
    setError,
  ] = useState(
    ""
  );


  const [
    openResults,
    setOpenResults,
  ] = useState<
    Record<number, boolean>
  >({});


  const [
    history,
    setHistory,
  ] = useState<
    HistoryEntry[]
  >([]);


  const [
    historyLoading,
    setHistoryLoading,
  ] = useState(
    false
  );


  const [
    selectedHistory,
    setSelectedHistory,
  ] = useState<
    HistoryEntry | null
  >(null);


  const results =
    job?.results ||
    [];


  const summary =
    useMemo(
      () => {

        return {

          total:
            job?.summary?.total ??
            results.length,

          ok:
            job?.summary?.ok ??
            job?.ok ??
            0,

          mismatch:
            job?.summary?.mismatch ??
            job?.mismatch ??
            0,

          needsReview:
            job?.summary?.needs_review ??
            job?.needs_review ??
            0,

        };
      },
      [job, results]
    );


  const isRunning =
    job?.status ===
      "QUEUED"
    ||
    job?.status ===
      "PROCESSING";


  const progress =
    Math.max(
      0,
      Math.min(
        100,
        Number(
          job?.progress ||
          0
        )
      )
    );


  // ==========================================================
  // NAV
  // ==========================================================

  useEffect(
    () => {

      const onHashChange =
        () => {

          setPage(
            window.location.hash ===
              "#history"
              ? "history"
              : "verify"
          );

        };


      window.addEventListener(
        "hashchange",
        onHashChange
      );

      if (window.location.hash === "#history") {
        loadHistory();
      }


      return () => {

        window.removeEventListener(
          "hashchange",
          onHashChange
        );

      };

    },
    []
  );


  function navigate(
    nextPage:
      "verify" |
      "history"
  ) {

    window.location.hash =
      nextPage ===
      "history"
        ? "history"
        : "";

    setPage(
      nextPage
    );

    if (
      nextPage ===
      "history"
    ) {

      loadHistory();

    }

  }


  // ==========================================================
  // FILES
  // ==========================================================

  function addFiles(
    event:
      React.ChangeEvent<HTMLInputElement>
  ) {

    const selected: File[] = event.target.files
      ? Array.from(event.target.files)
      : [];


    setFiles(
      (current) => {

        const keys =
          new Set(
            current.map(
              (
                file
              ) =>
                `${file.name}-${file.size}-${file.lastModified}`
            )
          );


        const merged =
          [
            ...current
          ];


        for (
          const file of selected
        ) {

          const key =
            `${file.name}-${file.size}-${file.lastModified}`;


          if (
            !keys.has(
              key
            )
          ) {

            keys.add(
              key
            );

            merged.push(
              file
            );

          }

        }


        return merged;

      }
    );


    event.target.value =
      "";

  }


  function removeFile(
    index: number
  ) {

    if (
      isRunning
    ) {

      return;
    }


    setFiles(
      current =>
        current.filter(
          (
            _,
            currentIndex
          ) =>
            currentIndex !==
            index
        )
    );

  }


  function clearFiles() {

    if (
      isRunning
    ) {

      return;
    }


    setFiles(
      []
    );

  }


  // ==========================================================
  // ANALYZE
  // ==========================================================

  async function analyze() {

    if (
      files.length ===
      0
    ) {

      setError(
        "Please select at least one file."
      );

      return;
    }


    setError(
      ""
    );

    setJob(
      null
    );

    setOpenResults(
      {}
    );


    try {

      const form =
        new FormData();


      for (
        const file of files
      ) {

        form.append(
          "files",
          file
        );

      }


      const response =
        await fetch(
          `${API}/api/analyze/upload-batch`,
          {
            method:
              "POST",

            body:
              form,
          }
        );


      const data =
        await response.json();


      if (
        !response.ok
      ) {

        throw new Error(
          data.detail ||
          "Unable to start analysis."
        );

      }


      const newJob:
        Job = {
          job_id:
            data.job_id,

          status:
            data.status ||
            "QUEUED",

          progress:
            0,

          total_files:
            data.total_files ||
            files.length,

          total_cases:
            0,

          processed_cases:
            0,

          ok:
            0,

          mismatch:
            0,

          needs_review:
            0,

          results:
            [],
        };


      setJob(
        newJob
      );


      pollJob(
        data.job_id
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to start analysis."
      );

    }

  }


  async function pollJob(
    jobId: string
  ) {

    try {

      const response =
        await fetch(
          `${API}/api/analyze/status/${jobId}`
        );


      const data =
        await response.json();


      if (
        !response.ok
      ) {

        throw new Error(
          data.detail ||
          "Unable to read job."
        );

      }


      setJob(
        data
      );


      if (
        data.status ===
        "COMPLETED"
      ) {

        setOpenResults(
          {}
        );

        loadHistory();

        return;
      }


      if (
        data.status ===
        "ERROR"
      ) {

        setError(
          data.error ||
          "Analysis failed."
        );

        return;
      }


      window.setTimeout(
        () => {

          pollJob(
            jobId
          );

        },
        1200
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to read progress."
      );

    }

  }


  // ==========================================================
  // DOWNLOAD
  // ==========================================================

  async function downloadExcel() {

    try {

      const response =
        await fetch(
          `${API}/api/excel`
        );


      if (
        !response.ok
      ) {

        throw new Error(
          "Excel report is not available."
        );

      }


      const blob =
        await response.blob();


      const url =
        window.URL.createObjectURL(
          blob
        );


      const link =
        document.createElement(
          "a"
        );


      link.href =
        url;


      link.download =
        "shipping_verification_audit.xlsx";


      document.body.appendChild(
        link
      );


      link.click();


      link.remove();


      window.URL.revokeObjectURL(
        url
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to download Excel."
      );

    }

  }


  async function openCloudExcel() {

    try {

      const response =
        await fetch(
          `${API}/api/excel/cloud-url`
        );


      const data =
        await response.json();


      const cloudUrl =
        data.cloud_url ||
        data.url;

      if (
        !response.ok ||
        !cloudUrl
      ) {

        throw new Error(
          data.message ||
          "Cloud Excel is not available."
        );

      }


      window.open(
        cloudUrl,
        "_blank",
        "noopener,noreferrer"
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to open cloud Excel."
      );

    }

  }


  // ==========================================================
  // HISTORY
  // ==========================================================

  async function loadHistory() {

    setHistoryLoading(
      true
    );


    try {

      const response =
        await fetch(
          `${API}/api/history?limit=100`
        );


      const data =
        await response.json();


      if (
        !response.ok
      ) {

        throw new Error(
          data.detail ||
          "Unable to load history."
        );

      }


      setHistory(
        data.items ||
        []
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to load history."
      );

    } finally {

      setHistoryLoading(
        false
      );

    }

  }


  async function openHistoryDetail(
    runId: string
  ) {

    try {

      const response =
        await fetch(
          `${API}/api/history/${runId}`
        );


      const data =
        await response.json();


      if (
        !response.ok
      ) {

        throw new Error(
          data.detail ||
          "Unable to load history detail."
        );

      }


      setSelectedHistory(
        data.item || data
      );

    } catch (
      error
    ) {

      setError(
        error instanceof
        Error
          ? error.message
          : "Unable to load history detail."
      );

    }

  }


  // ==========================================================
  // RESULT TOGGLE
  // ==========================================================

  function toggleResult(
    index: number
  ) {

    setOpenResults(
      current => ({
        ...current,

        [index]:
          !current[
            index
          ],

      })
    );

  }



  // ==========================================================
  // AI EXPLANATION / DECISION DETAILS
  // ==========================================================

  function formatConfidence(
    value: any
  ) {
    if (
      value === undefined ||
      value === null ||
      value === ""
    ) {
      return "";
    }

    const numeric = Number(value);

    if (!Number.isNaN(numeric)) {
      const percentage =
        numeric <= 1
          ? numeric * 100
          : numeric;

      return `${percentage.toFixed(0)}%`;
    }

    return String(value);
  }


  function renderEvidence(
    evidence: any
  ) {

    if (
      evidence === undefined ||
      evidence === null ||
      evidence === ""
    ) {
      return null;
    }

    if (Array.isArray(evidence)) {
      return (
        <ul className="aiEvidenceList">
          {evidence.map(
            (
              item,
              index
            ) => (
              <li
                key={index}
              >
                {
                  typeof item ===
                  "string"
                    ? item
                    : JSON.stringify(
                        item
                      )
                }
              </li>
            )
          )}
        </ul>
      );
    }

    if (
      typeof evidence ===
      "object"
    ) {
      return (
        <pre className="aiEvidenceObject">
          {
            JSON.stringify(
              evidence,
              null,
              2
            )
          }
        </pre>
      );
    }

    return (
      <div className="aiEvidenceText">
        {String(evidence)}
      </div>
    );
  }


  function renderAIExplanation(
    result: Result
  ) {

    const classifier =
      result.email_classification ||
      result.classification ||
      {};

    const comparison =
      result.comparison ||
      {};

    const confidence =
      result.confidence ??
      classifier.confidence ??
      comparison.overall_confidence ??
      comparison.confidence;

    const confidenceLevel =
      result.confidence_level ??
      classifier.confidence_level ??
      comparison.confidence_level;

    const confidenceExplanation =
      result.confidence_explanation ??
      classifier.confidence_explanation ??
      comparison.confidence_explanation;

    const reason =
      result.reason ??
      classifier.reason ??
      comparison.reason;

    const explanation =
      result.explanation ??
      classifier.explanation ??
      comparison.explanation;

    const evidence =
      result.evidence ??
      classifier.evidence ??
      comparison.evidence;

    const nextAction =
      result.next_action ??
      classifier.next_action ??
      comparison.next_action;

    const hasAny =
      confidence !== undefined ||
      confidenceLevel ||
      confidenceExplanation ||
      reason ||
      explanation ||
      evidence !== undefined ||
      nextAction;

    if (!hasAny) {
      return null;
    }

    return (
      <div className="aiExplanation">
        <div className="detailTitle">
          AI Decision Details
        </div>

        <div className="aiDecisionGrid">

          {
            (
              confidence !== undefined ||
              confidenceLevel
            ) && (
              <div className="aiDecisionCard">
                <span>
                  Confidence
                </span>

                <strong>
                  {
                    formatConfidence(
                      confidence
                    )
                  }

                  {
                    confidenceLevel && (
                      <small>
                        {" "}
                        ·{" "}
                        {
                          String(
                            confidenceLevel
                          )
                        }
                      </small>
                    )
                  }
                </strong>
              </div>
            )
          }

          {
            reason && (
              <div className="aiDecisionCard">
                <span>
                  Reason
                </span>

                <p>
                  {String(reason)}
                </p>
              </div>
            )
          }

          {
            explanation && (
              <div className="aiDecisionCard">
                <span>
                  Explanation
                </span>

                <p>
                  {String(explanation)}
                </p>
              </div>
            )
          }

          {
            confidenceExplanation && (
              <div className="aiDecisionCard">
                <span>
                  Confidence explanation
                </span>

                <p>
                  {
                    String(
                      confidenceExplanation
                    )
                  }
                </p>
              </div>
            )
          }

          {
            nextAction && (
              <div className="aiDecisionCard">
                <span>
                  Next Action
                </span>

                <p>
                  {String(nextAction)}
                </p>
              </div>
            )
          }

        </div>

        {
          evidence !== undefined &&
          evidence !== null &&
          evidence !== "" && (
            <div className="aiDecisionCard aiEvidenceCard">
              <span>
                Evidence
              </span>

              {
                renderEvidence(
                  evidence
                )
              }
            </div>
          )
        }
      </div>
    );
  }


  // ==========================================================
  // DOCUMENT RESULTS
  // ==========================================================

  function renderDocuments(
    result: Result
  ) {

    const documents =
      result.documents ||
      [];


    if (
      documents.length ===
      0
    ) {

      return null;
    }


    return (

      <div className="detailBlock">

        <div className="detailTitle">
          Documents
        </div>


        <div className="documentList">

          {documents.map(
            (
              document,
              index
            ) => {

              const filename =
                cleanFilename(
                  document.filename ||
                  document.name ||
                  "Document"
                );


              const type =
                getDocumentType(
                  document
                );


              return (

                <div
                  className="documentRow"
                  key={`${filename}-${index}`}
                >

                  <div>

                    <strong>
                      {filename}
                    </strong>

                    <small>
                      {type.replace(
                        /_/g,
                        " "
                      )}
                    </small>

                  </div>


                  <span>
                    {type}
                  </span>

                </div>

              );

            }
          )}

        </div>

      </div>

    );

  }


  // ==========================================================
  // COMPARISON
  // ==========================================================

  function renderComparison(
    result: Result
  ) {

    const comparison =
      result.comparison;


    const fields =
      comparison?.fields ||
      {};


    if (
      Object.keys(
        fields
      ).length ===
      0
    ) {

      return null;
    }


    return (

      <div className="detailBlock">

        <div className="detailTitle">
          SI / BL Comparison
        </div>


        {comparison?.reason && (

          <div className="comparisonReason">
            {comparison.reason}
          </div>

        )}


        <div className="tableWrap">

          <table className="compareTable">

            <thead>

              <tr>

                <th>
                  Field
                </th>

                <th>
                  SI
                </th>

                <th>
                  BL
                </th>

                <th>
                  Status
                </th>

              </tr>

            </thead>


            <tbody>

              {Object.entries(
                fields
              ).map(
                (
                  [
                    field,
                    value,
                  ]
                ) => {

                  const fieldStatus =
                    value?.status ||
                    "UNRESOLVED";


                  return (

                    <tr
                      key={field}
                    >

                      <td>
                        {
                          fieldLabel(
                            field
                          )
                        }
                      </td>

                      <td>
                        {
                          value?.si ===
                            null ||
                          value?.si ===
                            undefined ||
                          value?.si ===
                            ""
                            ? "—"
                            : String(
                                value.si
                              )
                        }
                      </td>

                      <td>
                        {
                          value?.bl ===
                            null ||
                          value?.bl ===
                            undefined ||
                          value?.bl ===
                            ""
                            ? "—"
                            : String(
                                value.bl
                              )
                        }
                      </td>

                      <td>

                        <span
                          className={`fieldStatus ${statusClass(
                            fieldStatus
                          )}`}
                        >
                          {
                            displayStatus(
                              fieldStatus
                            )
                          }
                        </span>

                      </td>

                    </tr>

                  );

                }
              )}

            </tbody>

          </table>

        </div>

      </div>

    );

  }


  // ==========================================================
  // VERIFY PAGE
  // ==========================================================

  function renderVerifyPage() {

    return (

      <>

        <section className="hero">

          <div className="eyebrow">
            DOCUMENT INTELLIGENCE
          </div>

          <h1>
            Verify shipping documents
            <br />
            
          </h1>

          <p>
            Upload emails and shipping documents together.
            AI classifies the request, identifies document
            types, extracts shipment fields, and compares
            SI and BL data.
          </p>

        </section>


        <section className="uploadCard">

          <div className="sectionHead">

            <div>

              <h2>
                Upload files
              </h2>

              <p>
                Multiple files can be processed in one batch.
              </p>

            </div>


            {files.length > 0 && (

              <button
                className="textBtn"
                onClick={
                  clearFiles
                }
                disabled={
                  isRunning
                }
              >
                Clear all
              </button>

            )}

          </div>


          <label className="dropzone">

            <input
              type="file"
              multiple
              onChange={
                addFiles
              }
              disabled={
                isRunning
              }

              accept="
                .json,
                .eml,
                .msg,
                .pdf,
                .txt,
                .docx,
                .xlsx,
                .xlsm,
                .csv,
                .pptx,
                .png,
                .jpg,
                .jpeg,
                .webp,
                .bmp,
                .tiff
              "
            />


            <div className="uploadIcon">
              ↑
            </div>

            <div className="dropTitle">
              Click to select files
            </div>

            <div className="dropText">
              JSON, EML, MSG, PDF, XLSX, DOCX, TXT and more
            </div>

          </label>


          {files.length > 0 && (

            <div className="selectedFiles">

              <div className="selectedHeader">

                <span>
                  Selected files
                </span>

                <span>
                  {files.length}
                </span>

              </div>


              <div className="selectedRows">

                {files.map(
                  (
                    file,
                    index
                  ) => (

                    <div
                      className="selectedRow"
                      key={`${file.name}-${index}`}
                    >

                      <div className="selectedInfo">

                        <div className="fileIcon">
                          DOC
                        </div>

                        <div className="fileName">
                          {file.name}
                        </div>

                        <div className="fileSize">
                          {
                            (
                              file.size
                              /
                              1024
                            ).toFixed(
                              1
                            )
                          } KB
                        </div>

                      </div>


                      <button
                        className="removeBtn"
                        onClick={() =>
                          removeFile(
                            index
                          )
                        }
                        disabled={
                          isRunning
                        }
                      >
                        ×
                      </button>

                    </div>

                  )
                )}

              </div>

            </div>

          )}


          <div className="uploadActions">

            <button
              className="primaryBtn"
              onClick={
                analyze
              }
              disabled={
                isRunning ||
                files.length ===
                  0
              }
            >

              {
                isRunning
                  ? "Processing..."
                  : "Analyze Files"
              }

            </button>


            <span>
              Batch-safe sequential AI processing
            </span>

          </div>

        </section>


        {error && (

          <div className="errorBox">

            <strong>
              Error
            </strong>

            <span>
              {error}
            </span>

          </div>

        )}


        {job && (

          <section className="progressCard">

            <div className="progressHead">

              <div>

                <div className="eyebrow">
                  BATCH PROCESSING
                </div>

                <h2>
                  {
                    job.status ===
                    "COMPLETED"
                      ? "Analysis completed"
                      : job.status ===
                        "ERROR"
                      ? "Analysis stopped"
                      : "Processing files"
                  }
                </h2>

                <p>
                  {
                    job.phase ===
                    "cloud_archive"
                      ? "Saving verification archive to cloud..."
                      : job.phase ===
                        "generating_report"
                      ? "Generating Excel audit report..."
                      : job.current_filename
                      ? `Processing ${cleanFilename(
                          job.current_filename
                        )}`
                      : "Preparing verification cases..."
                  }
                </p>

              </div>


              <div className="progressPercent">
                {progress}%
              </div>

            </div>


            <div className="progressBar">

              <div
                style={{
                  width:
                    `${progress}%`,
                }}
              />

            </div>


            <div className="progressStats">

              <div>
                <span>
                  Files
                </span>

                <strong>
                  {
                    job.total_files ||
                    files.length
                  }
                </strong>
              </div>


              <div>
                <span>
                  Cases
                </span>

                <strong>
                  {
                    job.processed_cases ??
                    (job.status === "COMPLETED"
                      ? summary.total
                      : 0)
                  }
                  {" / "}
                  {
                    job.total_cases ??
                    (job.status === "COMPLETED"
                      ? summary.total
                      : "—")
                  }
                </strong>
              </div>


              <div>
                <span>
                  OK
                </span>

                <strong className="okText">
                  {summary.ok}
                </strong>
              </div>


              <div>
                <span>
                  Mismatch
                </span>

                <strong className="mismatchText">
                  {
                    summary.mismatch
                  }
                </strong>
              </div>


              <div>
                <span>
                  Review
                </span>

                <strong className="reviewText">
                  {
                    summary.needsReview
                  }
                </strong>
              </div>

            </div>

          </section>

        )}


        {job &&
          results.length >
          0 && (

          <section className="resultsSection">

            <div className="resultsHead">

              <div>

                <div className="eyebrow">
                  VERIFICATION RESULT
                </div>

                <h2>
                  Verification records
                </h2>

                <p>
                  Click any record to view the full result.
                </p>

              </div>


              {job.status ===
                "COMPLETED" && (

                <div className="resultActions">

                  <button
                    className="primaryBtn"
                    onClick={
                      downloadExcel
                    }
                  >
                    Download Excel
                  </button>


                  <button
                    className="secondaryBtn"
                    onClick={
                      openCloudExcel
                    }
                  >
                    Open Cloud File
                  </button>

                </div>

              )}

            </div>


            <div className="summaryGrid">

              <div className="summaryCard">
                <span>
                  TOTAL
                </span>
                <strong>
                  {summary.total}
                </strong>
              </div>

              <div className="summaryCard">
                <span>
                  OK
                </span>
                <strong className="okText">
                  {summary.ok}
                </strong>
              </div>

              <div className="summaryCard">
                <span>
                  MISMATCH
                </span>
                <strong className="mismatchText">
                  {summary.mismatch}
                </strong>
              </div>

              <div className="summaryCard">
                <span>
                  NEEDS REVIEW
                </span>
                <strong className="reviewText">
                  {summary.needsReview}
                </strong>
              </div>

            </div>


            <div className="resultList">

              {results.map(
                (
                  result,
                  index
                ) => {

                  const open =
                    !!openResults[
                      index
                    ];


                  return (

                    <article
                      className="resultCard"
                      key={`${result.filename}-${index}`}
                    >

                      <button
                        className="resultHeader"
                        onClick={() =>
                          toggleResult(
                            index
                          )
                        }
                      >

                        <div>

                          <div className="resultTitle">
                            {
                              cleanFilename(
                                result.filename ||
                                result.subject ||
                                "Record"
                              )
                            }
                          </div>


                          <div className="meta">

                            <span className="catPill">
                              {
                                category(
                                  result
                                )
                              }
                            </span>


                            <span
                              className={`statusPill ${statusClass(
                                result.status
                              )}`}
                            >
                              {
                                displayStatus(
                                  result.status
                                )
                              }
                            </span>

                          </div>

                        </div>


                        <span>
                          {
                            open
                              ? "Hide details ↑"
                              : "View details ↓"
                          }
                        </span>

                      </button>


                      {open && (

                        <div className="resultDetail">

                          {
                            renderAIExplanation(
                              result
                            )
                          }

                          {result.reason && (

                            <div className="reason">
                              {result.reason}
                            </div>

                          )}


                          {result.review_reason && (

                            <div className="reviewReason">
                              NEEDS REVIEW:{" "}
                              {
                                result.review_reason
                              }
                            </div>

                          )}


                          {
                            renderDocuments(
                              result
                            )
                          }


                          {
                            renderComparison(
                              result
                            )
                          }


                          <div className="overall">

                            <div>
                              <span>
                                Verification status
                              </span>

                              <strong
                                className={
                                  statusClass(
                                    result.status
                                  )
                                }
                              >
                                {
                                  displayStatus(
                                    result.status
                                  )
                                }
                              </strong>
                            </div>


                            <div>

                              {
                                result.status ===
                                "OK"
                                  ? "All required fields matched."
                                  : result.status ===
                                    "MISMATCH"
                                  ? "One or more fields do not match."
                                  : "Manual review is required."
                              }

                            </div>

                          </div>

                        </div>

                      )}

                    </article>

                  );

                }
              )}

            </div>


            {job.cloud_archive && (

              <div className="cloudNotice">

                <span>
                  Cloud archive:
                </span>

                <strong>
                  {
                    job.cloud_archive.uploaded
                      ? "Uploaded"
                      : "Local only"
                  }
                </strong>

                {job.cloud_archive.cloud_prefix && (

                  <span>
                    {job.cloud_archive.cloud_prefix}
                  </span>

                )}

              </div>

            )}

          </section>

        )}

      </>

    );

  }


  // ==========================================================
  // HISTORY PAGE
  // ==========================================================

  function renderHistoryPage() {

    return (

      <section className="historyPage">

        <div className="historyHero">

          <div className="eyebrow">
            VERIFICATION HISTORY
          </div>

          <h2>
            Previous verification runs
          </h2>

          <p>
            Every completed upload and Gmail batch is
            recorded here.
          </p>

        </div>


        {historyLoading ? (

          <div className="emptyHistory">
            Loading history...
          </div>

        ) : history.length === 0 ? (

          <div className="emptyHistory">
            No verification history yet.
          </div>

        ) : (

          <div className="historyList">

            {history.map(
              (
                item
              ) => {

                const summary =
                  item.summary ||
                  {};


                return (

                  <button
                    className="historyRow"
                    key={
                      item.run_id
                    }
                    onClick={() =>
                      openHistoryDetail(
                        item.run_id
                      )
                    }
                  >

                    <div>

                      <strong>
                        {
                          item.source ===
                          "gmail"
                            ? "Gmail batch"
                            : "Web upload"
                        }
                      </strong>

                      <span>
                        {
                          formatTime(
                            item
                          )
                        }
                      </span>

                    </div>


                    <div className="historyStats">

                      <span>
                        {
                          summary.total ||
                          0
                        } cases
                      </span>

                      <span className="okText">
                        {
                          summary.ok ||
                          0
                        } OK
                      </span>

                      <span className="mismatchText">
                        {
                          summary.mismatch ||
                          0
                        } Mismatch
                      </span>

                      <span className="reviewText">
                        {
                          summary.needs_review ||
                          0
                        } Review
                      </span>

                    </div>

                  </button>

                );

              }
            )}

          </div>

        )}

      </section>

    );

  }


  // ==========================================================
  // HISTORY MODAL
  // ==========================================================

  function renderHistoryModal() {

    if (!selectedHistory) {
      return null;
    }

    const summary = selectedHistory.summary || {};

    return (
      <div
        className="modalBackdrop"
        onClick={() => setSelectedHistory(null)}
      >
        <div
          className="modal"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="modalHead">
            <div>
              <h2>
                {selectedHistory.source === "gmail" ? "Gmail batch" : "Web upload"}
              </h2>
              <p>{formatTime(selectedHistory)}</p>
            </div>

            <button
              className="textBtn"
              onClick={() => setSelectedHistory(null)}
            >
              Close
            </button>
          </div>

          <div className="summaryGrid">
            <div className="summaryCard">
              <span>TOTAL</span>
              <strong>{summary.total || 0}</strong>
            </div>
            <div className="summaryCard">
              <span>OK</span>
              <strong className="okText">{summary.ok || 0}</strong>
            </div>
            <div className="summaryCard">
              <span>MISMATCH</span>
              <strong className="mismatchText">{summary.mismatch || 0}</strong>
            </div>
            <div className="summaryCard">
              <span>REVIEW</span>
              <strong className="reviewText">{summary.needs_review || 0}</strong>
            </div>
          </div>

          <div className="historyDetailList">
            {(selectedHistory.results || []).map((result, index) => (
              <details
                className="historyCase"
                key={`${result.email_id}-${index}`}
                open={index === 0}
              >
                <summary className="historyCaseSummary">
                  <div>
                    <strong>
                      {cleanFilename(result.filename || result.subject || "Record")}
                    </strong>
                    <small>{category(result)}</small>
                  </div>

                  <div className="historyCaseRight">
                    <span
                      className={`statusPill ${statusClass(result.status)}`}
                    >
                      {displayStatus(result.status)}
                    </span>
                    <span className="historyCaseChevron">+</span>
                  </div>
                </summary>

                <div className="historyCaseBody">
                  {renderAIExplanation(result)}

                  {result.review_reason && (
                    <div className="reviewReason">
                      NEEDS REVIEW: {result.review_reason}
                    </div>
                  )}

                  {renderDocuments(result)}
                  {renderComparison(result)}

                  <div className="overall">
                    <div>
                      <span>Verification status</span>
                      <strong className={statusClass(result.status)}>
                        {displayStatus(result.status)}
                      </strong>
                    </div>
                    <div>
                      {result.status === "OK"
                        ? "All required fields matched."
                        : result.status === "MISMATCH"
                        ? "One or more fields do not match."
                        : "Manual review is required."}
                    </div>
                  </div>
                </div>
              </details>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (

    <div className="app">

      <header className="topbar">

        <div className="brand">

          <div className="brandMark">
            SV
          </div>

          <div>

            <div className="brandName">
              Shipping Verifier
            </div>

            <div className="brandSub">
              AI-powered shipping document verification
            </div>

          </div>

        </div>


        <nav className="nav">

          <button
            className={`navBtn ${
              page ===
              "verify"
                ? "active"
                : ""
            }`}
            onClick={() =>
              navigate(
                "verify"
              )
            }
          >
            Verify
          </button>


          <button
            className={`navBtn ${
              page ===
              "history"
                ? "active"
                : ""
            }`}
            onClick={() =>
              navigate(
                "history"
              )
            }
          >
            Verification History
          </button>

        </nav>

      </header>


      <main className="main">

        {
          page ===
          "verify"
            ? renderVerifyPage()
            : renderHistoryPage()
        }

      </main>


      <footer className="footer">

        <span>
          Shipping Verifier
        </span>

        <span>
          AI + Document Verification
        </span>

      </footer>


      {
        renderHistoryModal()
      }

    </div>

  );

}


export default App;