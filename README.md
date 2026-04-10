#  Email Agent

Run once, get a beautiful email digest of the latest AI advancements across:
-  **LLM / Model Releases**
-  **AI Tools & Frameworks**
-  **Research Papers**
-  **Industry News**

---

## Setup (5 minutes)

### 1. Project Structure

```text
Email-Agent/
├── main.py
├── email_sender.py
├── requirements.txt
├── .env.example
├── credentials.json
└── README.md
```

### 2. Create a virtual environment

```bash
# Mac / Linux
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## API Keys

### Gemini API Key (free tier available)

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Sign in with your Google account
3. Click **Get API Key** → Create with a new project
4. Copy the key

### Gmail OAuth Credentials

This lets the agent send email *from* your Gmail without storing your password.

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Go to **APIs & Services → Library** → enable **Gmail API**
4. Go to **APIs & Services → Credentials**
5. Click **Create Credentials → OAuth client ID**
6. Choose **Desktop app**, give it a name, click **Create**
7. Download the JSON file and rename it `credentials.json`
8. Place `credentials.json` in the `Email-Agent/` folder

> **First run only:** A browser window will open asking you to authorise
> Gmail access. After that, a `token.json` is saved and future runs are silent.

---

## Configure

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
GEMINI_API_KEY="your key here"
RECIPIENT_EMAIL="your mail here"
```

---

## Run

```bash

# Windows
python main.py
```

That's it! The agent will:
1. Search for the most recent and significant AI advancements
2. Extract and summarise the most interesting recent items using Gemini
3. Send a formatted HTML digest to your Gmail inbox

---
