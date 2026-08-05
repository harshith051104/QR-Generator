# QR Code Based Certificate Verification System

A lightweight, high-performance Certificate Verification System built with Python, FastAPI, Google Sheets API (`gspread`), `qrcode`, and Jinja2 templates.

---

## 🌟 Key Features

* **Google Sheets as Source of Truth**: Manage certificate records directly in Google Sheets.
* **Automated UUID & QR URL Generation**: Auto-fills missing UUID4 tokens and QR URLs into Google Sheets.
* **Instantaneous Verification ($O(1)$ Memory Cache)**: Loads Google Sheet records into memory for sub-5ms response times.
* **Background Cache Auto-Refresh**: Periodically re-syncs Google Sheets every 5 minutes (plus on-demand `/refresh-cache` endpoint).
* **Permanent QR Codes**: QR codes contain clean, HTTPS-ready verification URLs (`BASE_URL/verify/<token>`).
* **Live Verification Timestamp**: Verified pages display an explicit live scan timestamp to reassure recruiters.
* **Mobile-Responsive UI**: Glassmorphic design, company logo branding, green/red status badges, and search form.
* **Vercel & Render Ready**: Includes `vercel.json` and serverless handler in `api/index.py`.

---

## 📂 Project Structure

```text
c:\Users\sriha\My work\QRcode\
├── api/
│   └── index.py              # Vercel serverless entry point
├── backend/
│   ├── __init__.py
│   ├── google_service.py     # gspread client & Google Sheets sync
│   ├── qr_generator.py       # QR code PNG image generator
│   └── cache.py              # In-memory dictionary lookup cache
├── templates/
│   ├── index.html            # Search portal page
│   ├── verified.html         # ✅ Verified certificate display page
│   └── invalid.html          # ❌ Invalid certificate alert page
├── static/
│   ├── style.css             # Modern CSS stylesheet
│   └── logo.svg              # Company branding logo
├── qr_codes/                 # Generated QR code PNG files
├── credentials/              # Google Cloud Service Account JSON storage
│   └── service_account.json.template
├── main.py                   # FastAPI server entry point
├── generate_qr.py            # CLI script to generate missing tokens & QR codes
├── vercel.json               # Vercel deployment config
├── requirements.txt          # Python dependencies
├── .env.example              # Environment template file
└── README.md                 # Setup & deployment guide
```

---

## 📋 Google Sheet Column Setup

Create a Google Sheet with the following column headers in Row 1:

| Certificate Number | Verification Token | QR URL | Name | Course | Issue Date | Company | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| AI2026-001 | *(Auto-generated)* | *(Auto-generated)* | Harshith Sri | AI Workshop | 2026-08-01 | Tech Academy | Verified |
| AI2026-002 | *(Auto-generated)* | *(Auto-generated)* | Jane Doe | Web Security | 2026-08-02 | Tech Academy | Revoked |

---

## ⚙️ Local Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set up your Google Service Account key in `credentials/service_account.json`.
3. Configure `.env`:
   ```env
   BASE_URL=http://localhost:8000
   GOOGLE_SHEET_ID=your_google_sheet_id_here
   ```
4. Run QR generator:
   ```bash
   python generate_qr.py
   ```
5. Run web server:
   ```bash
   python main.py
   ```

---

## 🚀 How to Deploy on Vercel (Step-by-Step)

Deploying to **Vercel** is 100% supported out of the box!

### Step 1: Push Code to GitHub
Push your repository to GitHub:
```bash
git init
git add .
git commit -m "Initial commit"
git push origin main
```

### Step 2: Import Project into Vercel
1. Go to **[Vercel Dashboard](https://vercel.com/dashboard)** and click **Add New** &rarr; **Project**.
2. Select your GitHub repository.
3. Keep default settings (Vercel automatically detects `vercel.json` and Python runtime).

### Step 3: Add Environment Variables in Vercel
In the Vercel **Environment Variables** section, add:

| Key | Value |
| :--- | :--- |
| `BASE_URL` | `https://your-app-name.vercel.app` *(Your Vercel URL)* |
| `GOOGLE_SHEET_ID` | `1mJRFSLAkEDijqEh4H81bEG84dK_AZG7vyLDlrusqhLE` |
| `GOOGLE_SHEET_NAME` | `QR-Generator` |
| `GOOGLE_CREDENTIALS_JSON` | *(Paste the entire contents of `service_account.json` as a single raw JSON string)* |

### Step 4: Click Deploy!
Click **Deploy**. Vercel will deploy your FastAPI verification server instantly.

### Step 5: Generate QR Codes for your Vercel Domain
Once deployed, update `BASE_URL` in your local `.env` to your new Vercel domain:
```env
BASE_URL=https://your-app-name.vercel.app
```
And re-run:
```bash
python generate_qr.py
```
This updates the QR URLs in Google Sheets to point to your live Vercel domain!
