# Palestine & Gaza News AI Bot — Zero-Cost Humanitarian Reporting

An automated, 100% free-tier AI news collection, verification, and editorial drafting system focusing on **Palestine and Gaza**.

The bot continuously aggregates verified reports from official UN agencies and top international humanitarian correspondents, synthesizes objective source-grounded post drafts, renders dignified 16:9 editorial illustrations, and automatically organizes publishing packages directly in **Google Drive** for manual review and 1-click sharing on X (Twitter).

---

## 🏗️ Architecture

```text
GitHub Actions (Hourly RSS / Twice-Daily Batch)
  │
  ├── 1. RSS Ingestion (feedparser) from UN OCHA, Al Jazeera, BBC, MEE, Democracy Now!
  │
  ├── 2. Qualification & Clustering (Deduplication, Title Similarity, Multi-Agency Corroboration)
  │
  ├── 3. Gemini 2.5 Flash (Factual extraction, character-limit validation, dignified visual prompts)
  │
  ├── 4. Pollinations FLUX / Turbo (Renders 1280×720 editorial illustrations at $0.00 cost)
  │
  ├── 5. Google Drive Archival (posts.csv, posts.jsonl, batch_summary.md, images/)
  │
  └── 6. Operator Review & Publishing to X with 1 click
```

---

## ✨ Key Principles & Editorial Ethics

* **Zero Paid APIs:** Operates 100% on free tiers — Google Gemini 2.5 Flash free tier (1,500 requests/day), Pollinations FLUX ($0.00, no key required), and GitHub Actions free runner minutes.
* **No Twitter API Paywall:** By uploading ready-to-post CSVs, formatted drafts, and illustrations directly to Google Drive, it sidesteps X's \$100/mo API paywall while preserving vital human-in-the-loop oversight.
* **Strict Factual Grounding:** Quotes and figures are directly attributed to official agencies (UN OCHA, WHO, PRCS, UNICEF). The bot never fabricates casualty counts or unverified claims.
* **Humanitarian Dignity:** Strictly prohibits graphic gore, severed bodies, or deceptive photorealistic deepfakes. Instead, it generates solemn, dignified fine-art watercolor and vector editorial illustrations highlighting civilian resilience, aid convoys, and makeshift schools.

---

## 🚀 Quick Start (Local Setup)

### 1. Clone & Install Dependencies

```bash
git clone https://github.com/Zaryab-dev/palestine-news-ai-bot.git
cd palestine-news-ai-bot

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

Copy the example environment file:
```bash
cp .env.example .env
```

Open `.env` and add your **Gemini API Key**:
* Get a free key in 30 seconds from [Google AI Studio](https://aistudio.google.com/app/apikey).
* (Images work out-of-the-box via Pollinations without any API key!)

### 3. Run Automated Tests

Verify that everything is configured and passing:
```bash
pytest -v
```

---

## 📡 CLI Commands & Modes

```bash
# Test connectivity and relevance across all configured RSS feeds
python -m src.pipeline --mode test-feeds

# Run hourly news collection into local pending queue
python -m src.pipeline --mode collect

# Execute a full batch run (generate posts, render images, sync to Drive)
python -m src.pipeline --mode batch --batch-size 5

# Run a safe dry-run (processes real feeds without altering permanent state)
python -m src.pipeline --mode dry-run --batch-size 2
```

---

## ☁️ Google Drive Setup (One-Time)

To allow the bot to automatically upload batch folders into your Google Drive:

1. Visit [Google Cloud Console](https://console.cloud.google.com).
2. Create a project and enable the **Google Drive API**.
3. Under **OAuth consent screen**:
   * User Type: **External**
   * Publishing status: **Testing**
   * Add your Google account email under **Test Users**.
4. Under **Credentials**:
   * Click **Create Credentials** → **OAuth client ID**.
   * Application type: **Desktop app**.
   * Copy your `Client ID` and `Client secret`.
5. Run the guided interactive setup helper:
   ```bash
   python scripts/setup_google_drive.py
   ```
   This will open your browser for 1-click authorization, obtain the persistent `GOOGLE_REFRESH_TOKEN`, provision your `Gaza-Palestine-News-AI-Bot` Drive folder, and write the keys to `.env`.

---

## 🤖 GitHub Actions Automation

The repository includes `.github/workflows/scheduled-bot.yml` which handles:
* **Hourly Collection:** Fetches and deduplicates incoming news every hour (`15 * * * *`).
* **Twice-Daily Batch Release:** Synthesizes posts and generates graphics at 05:00 and 17:00 UTC (`0 5,17 * * *`), corresponding to 10:00 & 22:00 PKT / 07:00 & 19:00 Gaza time.
* **Manual Trigger (`workflow_dispatch`):** Run on demand anytime from GitHub's Actions tab.

### Required GitHub Secrets

In your GitHub repository, go to **Settings → Secrets and variables → Actions** and add:

| Secret Name | Description | Where to get it |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Free Gemini API Key | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GOOGLE_CLIENT_ID` | OAuth Client ID | Google Cloud Console |
| `GOOGLE_CLIENT_SECRET` | OAuth Client Secret | Google Cloud Console |
| `GOOGLE_REFRESH_TOKEN` | OAuth Refresh Token | Generated by `setup_google_drive.py` |
| `GOOGLE_DRIVE_FOLDER_ID` | Root Drive Folder ID | Generated by `setup_google_drive.py` |

---

## 📂 Google Drive Output Format

Each batch creates a clean directory in your Google Drive:

```text
Gaza-Palestine-News-AI-Bot/
└── 2026-11-09/
    └── batch_0500_utc/
        ├── posts.csv           # Ready-to-copy spreadsheet with headlines, drafts, and hashtags
        ├── posts.jsonl         # Complete machine-readable data contract
        ├── batch_summary.md    # Markdown briefing with full text of all drafts
        └── images/
            ├── <story_id_1>.png # 1280x720 16:9 dignified editorial illustration
            └── <story_id_2>.png
```

---

## 📜 License & Sourcing

This project is open-source under the MIT License. All news summaries strictly link to the original reporting publishers (UN OCHA, WHO, Al Jazeera, BBC, etc.).
