# Shipping Verifier — Gmail + Web Prototype

This is a clean integrated prototype for the Shipping Document Verification hackathon workflow.

## What is included

- Existing Web verification flow and compact UI preserved.
- Existing Agnes AI model/configuration preserved.
- Gmail OAuth + Gmail API integration.
- Gmail Bee can detect an email and trigger analysis from Gmail.
- Gmail uses the real Gmail message and downloads the real attachments.
- SI / BL attachments are passed into the same existing `analyze_email()` pipeline used by Web uploads.
- Existing AI document classification, extraction, normalization, and semantic comparison are reused.
- Verification results return to the Gmail Bee with status, confidence, reasons, next action, evidence, documents, and field-by-field SI / BL comparison.
- History page keeps the existing design and opens each run in a modal with expandable per-case details.
- Review Queue remains available.
- Excel report generation remains available.
- Supabase/cloud archive remains available.
- Duplicate detection has been removed from backend, frontend, Gmail extension, and Excel output.

## Gmail flow

```text
Gmail email
  -> Chrome Bee
  -> FastAPI /api/gmail/classify-batch
  -> Gmail API message/thread lookup
  -> real attachment download
  -> existing analyze_email()
  -> existing extractor + normalizer + comparator
  -> OK / MISMATCH / NEEDS_REVIEW
  -> detailed result returned to Bee
```

## Environment

Create this file locally:

```text
backend/.env
```

Copy your real values from your current project. The ZIP intentionally does NOT include real secrets, API keys, OAuth secrets, refresh tokens, or service credentials.

Use `backend/.env.example` as the template.

Expected keys include:

```env
AI_API_KEY=YOUR_AGNES_API_KEY
AI_BASE_URL=https://apihub.agnes-ai.com/v1
AI_MODEL=agnes-2.5-flash
AI_MAX_RETRIES=2
AI_RETRY_DELAY=5
AI_MIN_REQUEST_INTERVAL=2

SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SECRET_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=shipping-verifier
CLOUD_LINK_EXPIRES_SECONDS=86400
CLOUD_ARCHIVE_FILES=true

GOOGLE_CLIENT_ID=YOUR_GOOGLE_OAUTH_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_OAUTH_CLIENT_SECRET
GMAIL_REDIRECT_URI=https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/callback
FRONTEND_URL=https://xox-shipping-verifier-bee-mu.vercel.app/
```

Do not commit `backend/.env` or Gmail token files.

## Start everything

The easiest option on Windows is:

```text
START_ALL.cmd
```

It opens the backend and frontend in separate command windows. On the first run it automatically creates the Python virtual environment, installs Python dependencies, installs frontend npm dependencies, and starts the servers.

### Manual backend

```powershell
cd C:\Users\USER\Documents\shipping-verifier-final-prototype
.\START_BACKEND.cmd
```

Backend:

```text
http://127.0.0.1:8000
```

### Manual frontend

```powershell
cd C:\Users\USER\Documents\shipping-verifier-final-prototype
.\START_FRONTEND.cmd
```

Frontend:

```text
http://localhost:5173
```

## Gmail authorization

After the backend is running, authorize Gmail once in the browser:

```text
https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/start
```

The OAuth token is stored locally under `data/records/` and is intentionally not included in the ZIP. After authorization, the backend can reuse the saved token across restarts while it remains refreshable.

## Chrome extension

Open:

```text
chrome://extensions/
```

Turn on **Developer mode** -> **Load unpacked** -> select:

```text
C:\Users\USER\Documents\shipping-verifier-final-prototype\gmail-extension
```

Then reload the extension and refresh Gmail.

## What should happen in Gmail

When an email with shipping documents is analyzed:

```text
Gmail
  -> Bee detects selected email
  -> real Gmail API message lookup
  -> SI / BL attachments downloaded
  -> existing AI analyzer runs
  -> AI semantic comparison runs
  -> Bee displays the result
```

The Bee result can include:

- Verification status
- Confidence
- Category
- Explanation / reason
- Next action
- SI filename
- BL filename
- Field-by-field comparison for 7 fields
- Evidence
- Review reason when manual review is required

## 7 comparison fields

- shipper
- consignee
- notify_party
- port_of_loading
- port_of_discharge
- container_count
- gross_weight_kg

The comparison keeps the existing semantic behavior, including company-name normalization, port aliases, numeric container counts, and kg/metric-ton conversion. Missing or unreadable values are escalated to `NEEDS_REVIEW` rather than being treated as mismatches.

## History

Open **History** in the Web app. Each historical run opens in a detail modal. Each email/case inside the run is expandable, so you can inspect the AI explanation, documents, and SI / BL comparison without leaving the History page.

## Notes

This ZIP is a local prototype package. A real Gmail run still requires one-time Google OAuth authorization in your own browser because refresh tokens are user-specific and cannot be bundled safely.
