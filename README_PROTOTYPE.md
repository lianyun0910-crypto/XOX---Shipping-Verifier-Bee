# Shipping Verifier Bee

AI-powered shipping email and document verification for Gmail and Web.

## Live Demo

**Web App**  
https://xox-shipping-verifier-lncl8ga7n-xox8.vercel.app/

**Backend API**  
https://xox-shipping-verifier-bee-api.onrender.com/

**GitHub**  
https://github.com/lianyun0910-crypto/XOX---Shipping-Verifier-Bee

---

## What It Does

Shipping Verifier Bee helps automate shipping-document verification directly from email or the web.

It can:

- Classify shipping emails
- Extract shipping information from documents
- Compare Shipping Instructions (SI) with Bills of Lading (BL)
- Detect field-level mismatches
- Escalate uncertain cases for human review
- Run verification through the Gmail Bee Chrome extension
- Keep historical verification results
- Generate Excel reports
- Store application data and document archives through Supabase

### Email Categories

`BL_COMPARISON` · `SI_REQUEST` · `INVOICE_QUERY` · `GENERAL` · `SPAM`

### Verification Results

`OK` · `MISMATCH` · `NEEDS_REVIEW`

### Verified Fields

- Shipper
- Consignee
- Notify Party
- Port of Loading
- Port of Discharge
- Container Count
- Gross Weight

---

## Architecture

```text
Gmail
   ↓
Gmail Bee Chrome Extension
   ↓
Render FastAPI Backend
   ↓
Agnes AI
   ↓
Classification
   ↓
Document Extraction
   ↓
Normalization
   ↓
SI / BL Comparison
   ↓
OK / MISMATCH / NEEDS_REVIEW
   ↓
Vercel Web App / Gmail Bee
```

### Technology Stack

| Component | Technology |
|---|---|
| Frontend | Vercel |
| Backend | FastAPI on Render |
| AI | Agnes AI (`agnes-2.5-flash`) |
| Database / Storage | Supabase |
| Email Integration | Gmail API |
| Authentication | Google OAuth |
| Browser Integration | Chrome Extension |

---

## Verification Pipeline

For `BL_COMPARISON` emails:

```text
Email
  ↓
Classify email
  ↓
Find SI + BL documents
  ↓
Extract 7 shipping fields
  ↓
Normalize values
  ↓
Compare SI vs BL
  ↓
Return verification result
```

### Result Types

**OK**  
The required information is sufficiently consistent.

**MISMATCH**  
One or more verified fields differ between the SI and BL.

**NEEDS_REVIEW**  
The system cannot safely complete the verification and requires human review.

---

## Gmail Bee

The Gmail Bee Chrome extension allows users to start verification directly from Gmail.

### Gmail Flow

```text
Gmail Email
   ↓
Bee detects selected email
   ↓
Gmail API message lookup
   ↓
Download shipping attachments
   ↓
Render FastAPI backend
   ↓
Existing analyzer pipeline
   ↓
AI extraction + comparison
   ↓
Result returned to Bee
```

The same core verification pipeline is reused for Gmail and Web uploads.

The Bee can display:

- Verification status
- Confidence
- Email category
- Explanation / reason
- Next action
- SI filename
- BL filename
- Field-by-field comparison
- Evidence
- Review reason

---

## Gmail Authorization

Before using Gmail Bee, the Google account must be authorized for the project's Google OAuth application.

Open the Google authorization endpoint:

https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/start

Complete Google OAuth using the authorized testing account.

The application uses Gmail API access to retrieve the selected email and its attachments for verification.

---

## Chrome Extension Setup

1. Open Chrome.
2. Go to:

```text
chrome://extensions/
```

3. Enable **Developer mode**.
4. Select **Load unpacked**.
5. Select the `gmail-extension/` folder from this repository.
6. Reload the extension.
7. Open Gmail and use the Shipping Verifier Bee.

The production extension communicates with the deployed Render backend and Vercel web application.

---

## Web App

Open the deployed Vercel application:

https://xox-shipping-verifier-lncl8ga7n-xox8.vercel.app/

The Web App provides:

- Shipping email/document verification
- Verification results
- SI / BL comparison
- Review Queue
- Historical verification dashboard
- Excel report generation

---

## History

The History section stores previous verification runs.

Users can inspect individual historical cases and review:

- Verification status
- AI explanation
- Documents
- Extracted information
- SI / BL comparison
- Review information

---

## Supabase

Supabase is used for application data and shipping-document storage.

Required environment variables:

```env
SUPABASE_URL=YOUR_SUPABASE_URL
SUPABASE_SECRET_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=shipping-verifier
CLOUD_LINK_EXPIRES_SECONDS=86400
CLOUD_ARCHIVE_FILES=true
```

Never expose or commit the Supabase service-role key.

---

## Environment Variables

The production backend uses environment variables for AI, Supabase, and Google OAuth configuration.

```env
AI_API_KEY=YOUR_AGNES_API_KEY
AI_BASE_URL=https://apihub.agnes-ai.com/v1
AI_MODEL=agnes-2.5-flash

AI_MAX_RETRIES=2
AI_RETRY_DELAY=5
AI_MIN_REQUEST_INTERVAL=2

SUPABASE_URL=YOUR_SUPABASE_URL
SUPABASE_SECRET_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=shipping-verifier
CLOUD_LINK_EXPIRES_SECONDS=86400
CLOUD_ARCHIVE_FILES=true

GOOGLE_CLIENT_ID=YOUR_GOOGLE_OAUTH_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_OAUTH_CLIENT_SECRET
GMAIL_REDIRECT_URI=https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/callback

FRONTEND_URL=https://xox-shipping-verifier-lncl8ga7n-xox8.vercel.app/
```

Never commit:

- `.env`
- API keys
- Google OAuth secrets
- Gmail tokens
- Supabase service-role keys

---

## Project Structure

```text
XOX---Shipping-Verifier-Bee/
├── backend/
├── frontend/
├── gmail-extension/
├── data/
└── README.md
```

### Main Backend Modules

```text
classifier.py       → Email classification
extractor.py        → Shipping field extraction
normalizer.py       → Data normalization
comparator.py       → SI / BL comparison
document_reader.py  → Document processing
email_reader.py     → Email processing
analyzer.py         → Verification pipeline
main.py             → FastAPI API
```

---

## Production Deployment

The public prototype uses:

```text
Vercel
   ↓
Frontend

Render
   ↓
FastAPI Backend

Supabase
   ↓
Application Data / Document Storage

Agnes AI
   ↓
AI Classification / Extraction / Verification

Gmail API + Google OAuth
   ↓
Gmail Bee Integration
```

The production demo uses the deployed Vercel and Render services. No local server is required for the public demo.

---

## Quick Demo

### Web Demo

1. Open the Vercel Web App.
2. Upload or analyze a shipping email/document.
3. Review the extracted shipping information.
4. Review the SI / BL comparison.
5. Check the final verification result.
6. Open History to inspect previous verification runs.

### Gmail Demo

1. Use an authorized Google testing account.
2. Complete Google OAuth.
3. Install the Gmail Bee Chrome extension.
4. Open Gmail.
5. Open a shipping email.
6. Activate Shipping Verifier Bee.
7. Review the verification result directly from the Gmail workflow.

---

## Security Notes

Do not commit or expose:

- API keys
- Google OAuth client secrets
- Gmail refresh tokens
- Supabase service-role keys
- Other private credentials

Use environment variables for production secrets.

---

## Hackathon Demo

Shipping Verifier Bee demonstrates an end-to-end workflow:

```text
Email
  ↓
AI Classification
  ↓
Document Extraction
  ↓
Field Normalization
  ↓
SI / BL Verification
  ↓
Human Review when necessary
  ↓
Historical Record / Report
```

The system is designed to reduce manual checking of shipping documents while keeping uncertain cases available for human review.

---

## Links

**Web App**  
https://xox-shipping-verifier-lncl8ga7n-xox8.vercel.app/

**Backend API**  
https://xox-shipping-verifier-bee-api.onrender.com/

**Google Gmail Authorization**  
https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/start

**GitHub Repository**  
https://github.com/lianyun0910-crypto/XOX---Shipping-Verifier-Bee
