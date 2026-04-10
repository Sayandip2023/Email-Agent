"""
email_sender.py — sends the AI digest via Gmail API using OAuth2.
"""

import os
import base64
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

CATEGORY_COLORS = {
    "LLM / Model Releases":   "#4f46e5",
    "AI Tools & Frameworks":  "#0284c7",
    "Research Papers":        "#059669",
    "Industry News":          "#b45309",
}

CATEGORY_ORDER = [
    "LLM / Model Releases",
    "AI Tools & Frameworks",
    "Research Papers",
    "Industry News",
]

# ── Gmail auth ────────────────────────────────────────────────────────────

def get_gmail_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)


# ── URL helpers ───────────────────────────────────────────────────────────

def is_real_url(url: str) -> bool:
    if not url:
        return False
    return "vertexaisearch" not in url and "/grounding-api-redirect" not in url

def domain_of(url: str) -> str:
    if not is_real_url(url):
        return ""
    try:
        return url.split("/")[2].replace("www.", "").lower()
    except IndexError:
        return ""

def best_url(article: dict) -> str:
    url = article.get("url", "")
    if is_real_url(url):
        return url
    for chunk in article.get("sources", []):
        u = chunk.get("url", "")
        if is_real_url(u):
            return u
    return ""


# ── Per-card link ─────────────────────────────────────────────────────────

def read_more_html(article: dict, color: str) -> str:
    url = best_url(article)
    if not url:
        return ""
    label = domain_of(url) or url
    return (
        f'<p style="margin:10px 0 0;padding-top:10px;border-top:1px solid #f1f5f9;">'
        f'<a href="{url}" style="font-size:12px;color:{color};text-decoration:none;'
        f'font-family:monospace,monospace;">{label}&nbsp;&rarr;</a>'
        f'</p>'
    )


# ── All-sources index ─────────────────────────────────────────────────────

def build_sources_index(articles: list[dict]) -> str:
    """
    Numbered list of every article with its resolved URL, grouped by category.
    One entry per article — title as the link text, domain shown alongside.
    """
    rows = ""
    n = 1
    for cat in CATEGORY_ORDER:
        cat_articles = [a for a in articles if a.get("category") == cat]
        if not cat_articles:
            continue
        color = CATEGORY_COLORS.get(cat, "#64748b")
        rows += (
            f'<tr><td colspan="3" style="padding:12px 0 4px;">'
            f'<span style="font-size:10px;font-weight:700;letter-spacing:0.12em;'
            f'text-transform:uppercase;color:{color};">{cat}</span>'
            f'</td></tr>'
        )
        for article in cat_articles:
            title = article.get("title", "Untitled")
            url   = best_url(article)
            dom   = domain_of(url) if url else "—"
            title_cell = (
                f'<a href="{url}" style="color:#0f172a;text-decoration:none;'
                f'font-size:13px;line-height:1.5;">{title}</a>'
                if url else
                f'<span style="color:#374151;font-size:13px;">{title}</span>'
            )
            rows += (
                f'<tr style="border-bottom:1px solid #f1f5f9;">'
                f'<td style="padding:7px 10px 7px 0;width:22px;font-size:11px;'
                f'color:#94a3b8;vertical-align:top;">{n}.</td>'
                f'<td style="padding:7px 12px 7px 0;vertical-align:top;">{title_cell}</td>'
                f'<td style="padding:7px 0;width:130px;vertical-align:top;text-align:right;">'
                f'<span style="font-size:11px;color:#94a3b8;font-family:monospace,monospace;">'
                f'{dom}</span></td>'
                f'</tr>'
            )
            n += 1
    return f'<table width="100%" cellpadding="0" cellspacing="0">{rows}</table>'


# ── HTML template ─────────────────────────────────────────────────────────

def build_html(articles: list[dict]) -> str:
    date_str = datetime.now().strftime("%A, %B %d, %Y")

    grouped: dict[str, list[dict]] = {c: [] for c in CATEGORY_ORDER}
    for a in articles:
        grouped.setdefault(a.get("category", "General"), []).append(a)

    active_cats = [c for c in CATEGORY_ORDER if grouped.get(c)]
    total       = sum(len(v) for v in grouped.values())

    sections_html = ""
    for cat in CATEGORY_ORDER:
        items = grouped.get(cat, [])
        if not items:
            continue
        color      = CATEGORY_COLORS.get(cat, "#64748b")
        cards_html = ""

        for item in items:
            title   = item.get("title", "Untitled")
            summary = item.get("summary", "").replace("```json", "").replace("```", "").strip()
            why     = item.get("why_interesting", "")
            url     = best_url(item)

            title_html = (
                f'<a href="{url}" style="color:#0f172a;text-decoration:none;'
                f'border-bottom:1px solid {color}44;">{title}</a>'
                if url else
                f'<span style="color:#0f172a;">{title}</span>'
            )

            cards_html += f"""
            <div style="background:#ffffff;border:1px solid #e2e8f0;
                        border-left:3px solid {color};border-radius:6px;
                        padding:20px 22px;margin-bottom:12px;">
              <p style="margin:0 0 10px;font-size:15px;font-weight:700;
                        line-height:1.45;font-family:Georgia,serif;">
                {title_html}
              </p>
              <p style="margin:0 0 10px;font-size:13.5px;color:#374151;line-height:1.7;">
                {summary}
              </p>
              <p style="margin:0;font-size:12.5px;color:{color};line-height:1.5;
                        padding-top:10px;border-top:1px solid #f1f5f9;">
                {why}
              </p>
              {read_more_html(item, color)}
            </div>"""

        sections_html += f"""
        <div style="margin-bottom:40px;">
          <table cellpadding="0" cellspacing="0" style="margin-bottom:14px;">
            <tr>
              <td style="width:3px;background:{color};border-radius:2px;">&nbsp;</td>
              <td style="padding-left:12px;">
                <h2 style="margin:0;font-size:10.5px;font-weight:700;
                           letter-spacing:0.12em;text-transform:uppercase;
                           color:{color};">
                  {cat}
                </h2>
              </td>
            </tr>
          </table>
          {cards_html}
        </div>"""

    all_sources = build_sources_index(articles)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>AI Research Digest</title>
</head>
<body style="margin:0;padding:0;background:#f8fafc;
             font-family:'Helvetica Neue',Arial,sans-serif;">

  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f8fafc;padding:40px 0;">
  <tr><td align="center">
  <table width="640" cellpadding="0" cellspacing="0"
         style="max-width:640px;width:100%;background:#ffffff;border-radius:8px;
                overflow:hidden;
                box-shadow:0 1px 3px rgba(0,0,0,0.08),0 8px 32px rgba(0,0,0,0.06);">

    <!-- Header -->
    <tr><td style="background:#0f172a;padding:36px 40px 30px;">
      <p style="margin:0 0 8px;font-size:10px;letter-spacing:0.18em;color:#475569;
                text-transform:uppercase;">
        AI Research Digest
      </p>
      <h1 style="margin:0 0 6px;font-size:26px;font-weight:800;color:#f8fafc;
                 font-family:Georgia,serif;letter-spacing:-0.01em;">
        What happened in AI this week
      </h1>
      <p style="margin:0;font-size:13px;color:#64748b;">
        {date_str}&nbsp;&middot;&nbsp;{total} items across {len(active_cats)} categories
      </p>
    </td></tr>

    <tr><td style="height:2px;background:linear-gradient(90deg,#4f46e5,#0284c7,#059669,#b45309);"></td></tr>

    <!-- Article cards -->
    <tr><td style="padding:36px 40px 28px;">
      {sections_html}
    </td></tr>

    <!-- All sources index -->
    <tr><td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:28px 40px 32px;">
      <p style="margin:0 0 14px;font-size:10px;font-weight:700;letter-spacing:0.14em;
                text-transform:uppercase;color:#64748b;">
        All {total} sources
      </p>
      {all_sources}
    </td></tr>

    <!-- Footer -->
    <tr><td style="background:#f1f5f9;border-top:1px solid #e2e8f0;
                   padding:16px 40px;text-align:center;">
      <p style="margin:0;font-size:11px;color:#94a3b8;line-height:1.6;">
        Generated by your AI News Agent using Gemini 2.5 Flash with Google Search grounding.
      </p>
    </td></tr>

  </table>
  </td></tr>
  </table>

</body>
</html>"""


# ── Send ──────────────────────────────────────────────────────────────────

def send_digest_email(recipient: str, articles: list[dict]):
    service   = get_gmail_service()
    subject   = f"AI Research Digest — {datetime.now().strftime('%b %d, %Y')}"
    html_body = build_html(articles)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = "me"
    msg["To"]      = recipient
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"Digest sent to {recipient}")