# 🤖 AI News Agent

Run once, get a beautiful email digest of the latest AI advancements across:
- 🚀 LLM / Model Releases
- 🛠️ AI Tools & Frameworks  
- 📄 Research Papers
- 🗞️ Industry News

---

## Setup (5 minutes)

### 1. Clone / copy the project files
```
ai_news_agent/
├── main.py
├── email_sender.py
├── requirements.txt
├── .env.example
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
8. Place `credentials.json` in the `ai_news_agent/` folder

> **First run only:** A browser window will open asking you to authorise 
> Gmail access. After that, a `token.json` is saved and future runs are silent.

---

## Configure

Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

```env
GEMINI_API_KEY="your_gemini_api_key_here"
RECIPIENT_EMAIL="you@gmail.com"
```

---

## Run

```bash
# Mac / Linux
python3 main.py

# Windows
python main.py
```

That's it! The agent will:
1. Search DuckDuckGo across all 4 categories (~2–3 searches each)
2. Extract and summarise the most interesting recent items
3. Send a formatted HTML digest to your Gmail inbox

---

## Customise

**Change the AI model** — in `main.py`, update:
```python
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")
```
Swap for `"gemini-1.5-pro"` or any other supported model.

**Use OpenAI instead of Gemini:**
```bash
pip install langchain-openai
```
```python
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4o")
```
Add `OPENAI_API_KEY` to your `.env`.

**Change the search depth** — in `main.py`'s system prompt, adjust:
```
"find the MOST RECENT and SIGNIFICANT AI advancements"
```
to target specific topics, time ranges, or sources.

**Schedule it (optional):**
- **Mac/Linux:** add a cron job with `crontab -e`
  ```
  0 8 * * 1  cd /path/to/ai_news_agent && venv/bin/python main.py
  ```
  *(runs every Monday at 8am)*
- **Windows:** use Task Scheduler pointing to `venv\Scripts\python.exe main.py`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ImportError: cannot import name create_tool_calling_agent` | Run `pip install --upgrade langchain langchain-core` |
| `DuckDuckGoSearchRun` rate limit error | Wait a minute and try again; DDG throttles rapid requests |
| Gmail auth browser doesn't open | Run `python -c "from email_sender import get_gmail_service; get_gmail_service()"` separately |
| No articles collected | Check your Gemini API key; try increasing `max_iterations` in AgentExecutor |
