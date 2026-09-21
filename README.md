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

Shipping Verifier Bee:

- Classifies shipping emails
- Extracts shipping information
- Compares Shipping Instructions (SI) with Bills of Lading (BL)
- Detects mismatched fields
- Sends uncertain cases to human review

### Email Categories

`BL_COMPARISON` · `SI_REQUEST` · `INVOICE_QUERY` · `GENERAL` · `SPAM`

### Results

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
Classification → Extraction → Normalization → Comparison
  ↓
OK / MISMATCH / NEEDS_REVIEW
```

**Frontend:** Vercel  
**Backend:** Render  
**Database / Storage:** Supabase  
**AI:** Agnes AI (`agnes-2.5-flash`)  
**Email:** Gmail API + Google OAuth

---

## Supabase

Supabase is used for application data and shipping-document storage.

```env
SUPABASE_URL=YOUR_SUPABASE_URL
SUPABASE_SECRET_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=shipping-verifier
CLOUD_LINK_EXPIRES_SECONDS=86400
CLOUD_ARCHIVE_FILES=true
```

Never expose or commit the Supabase service-role key.

---

## Gmail Bee Setup

### 1. Request Access

**Before using Gmail Bee, contact the project team and provide the Google account email you want to use for testing.**

Your Google account must be added as an authorized **Testing User** for the project's Google OAuth application.

> Gmail authorization will not work until your Google account has been granted access.

### 2. Authorize Google

After your account has been granted access, open:

**Google Gmail Authorization**  
https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/start

Sign in with the authorized Google account and complete the OAuth process.

### 3. Install the Chrome Extension

Open:

```text
chrome://extensions/
```

Enable **Developer mode** → **Load unpacked** → select:

```text
gmail-extension/
```

Refresh Gmail.

### 4. Test

Open a shipping email and click **Shipping Verifier Bee**.

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
comparator.py       → SI/BL comparison
document_reader.py  → Document processing
email_reader.py     → Email processing
analyzer.py         → Verification pipeline
main.py             → FastAPI API
```

---

## Environment Variables

```env
AI_API_KEY=YOUR_AGNES_API_KEY
AI_BASE_URL=https://apihub.agnes-ai.com/v1
AI_MODEL=agnes-2.5-flash

SUPABASE_URL=YOUR_SUPABASE_URL
SUPABASE_SECRET_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
SUPABASE_BUCKET=shipping-verifier

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

## Production

The deployed demo uses:

```text
Vercel
+
Render
+
Supabase
+
Agnes AI
+
Gmail API
```

No localhost server is required for the production/demo workflow.

---

## Quick Demo

### Web

1. Open the Vercel Web App.
2. Upload/analyze a shipping email or document.
3. Review the extracted fields.
4. Review the SI/BL comparison.
5. Check the final result.

### Gmail

1. Request Google testing access.
2. Complete Google OAuth.
3. Install Gmail Bee.
4. Open Gmail.
5. Open a shipping email.
6. Click the Bee.
7. Review the verification result.

---

## Links

**Web App**  
https://xox-shipping-verifier-lncl8ga7n-xox8.vercel.app/

**Backend**  
https://xox-shipping-verifier-bee-api.onrender.com/

**Google Authorization**  
https://xox-shipping-verifier-bee-api.onrender.com/api/gmail/oauth/start

**GitHub**  
https://github.com/lianyun0910-crypto/XOX---Shipping-Verifier-Bee
