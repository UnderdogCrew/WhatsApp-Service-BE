import os
import re
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from openai import OpenAI
import sys
import django
import requests

current_path = os.path.abspath(os.getcwd())
base_path = os.path.dirname(current_path)  # This will give you /opt/whatsapp_service/WhatsApp-Service-BE
print(f"base_path: {base_path}")

# Set up Django environment
sys.path.append(base_path)  # Adjust this path accordingly
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'UnderdogCrew.settings')
django.setup()

load_dotenv()

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5")


SYSTEM_PROMPT = """
You are a medical news researcher.

Generate ONLY the medical news content.

Meta WhatsApp Business template rules (mandatory):
- Output must be ONE single continuous line of plain text.
- Do NOT use newline, carriage-return, or tab characters anywhere.
- Do NOT use the characters backslash-n (\\n) or backslash-r (\\r) as line breaks.
- Do NOT use more than 4 consecutive spaces anywhere.
- Put " || " before every section header, subsection header, and each numbered news item.
- Use " · " to separate fields within one news item (Summary, Why it matters, Status, Source).

Important output rules:
- Do not write any intro like "Here is the report".
- Do not write any explanation about how you searched.
- Do not write any disclaimer.
- Do not write closing text like "Hope this helps".
- Do not include code, notes, or instructions.
- Output only the final news message.
- Keep the content ready to send directly as a Meta Business template body parameter.
- Use short, clean, plain-language formatting.
- Include dates and sources.
- Flag preliminary, preclinical, trial-stage, company-reported, or not-yet-peer-reviewed items clearly.

Use current, credible sources only:
- Peer-reviewed journals
- WHO, CDC, NIH, FDA, EMA, MHRA, Health Canada, TGA
- Major hospitals and medical institutions
- Reputable medical news outlets

Focus especially on dermatology and skin health.
"""


def build_user_prompt(days: int) -> str:
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days)

    return f"""
Generate a WhatsApp-ready medical news update for a Meta Business template body parameter.

Date window: {start_date.isoformat()} to {today.isoformat()}

Output only the news content. No intro, no explanation, no disclaimer, no extra text.

Meta template formatting (mandatory):
- Return ONE single line only. No line breaks. No tabs. No \\n or \\r sequences.
- Never use more than 4 consecutive spaces.
- Put " || " before every section header, subsection header, and numbered news item.
- Use " · " between fields inside one news item.
- Use WhatsApp formatting with *bold* text only. No ### or ## headings.

Use this exact single-line structure:

*Top Global Medical News* || 1. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Approved / Peer-reviewed / Trial-stage / Preliminary / Preclinical / Company-reported] · Source: [Source name] - [URL] || 2. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Approved / Peer-reviewed / Trial-stage / Preliminary / Preclinical / Company-reported] · Source: [Source name] - [URL] || *Dermatology / Skin Focus* || *Research & Studies* || 1. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Peer-reviewed / Preliminary / Not yet peer-reviewed] · Source: [Source name] - [URL] || *New Treatments & Medicines* || 1. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Approved / Trial-stage / Preclinical / Company-reported] · Source: [Source name] - [URL] || *Technology & Procedures* || 1. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Peer-reviewed / Trial-stage / Preliminary / Preclinical] · Source: [Source name] - [URL] || *Clinical & Practice Updates* || 1. *[Headline] – [Date]* · Summary: [2 short sentences] · Why it matters: [1 sentence] · Status: [Guideline / Regulatory update / Practice update] · Source: [Source name] - [URL]

Rules:
- Prioritize the last {days} days.
- Include only important and credible medical news.
- Dermatology/skin should have the strongest focus.
- Do not include "What to watch next".
- Do not include greetings.
- Do not include thank you.
- Do not include medical advice disclaimer.
- Before finishing, verify the output is one line with no newlines, tabs, \\n, \\r, or 5+ consecutive spaces.
"""


def get_report_period_label(days: int) -> str:
    today = datetime.now(timezone.utc).date()

    # Example: Last 30 Days – June 2026
    return f"Last {days} Days – {today.strftime('%B')} {today.year}"


def sanitize_for_meta_template_param(text: str) -> str:
    """Strip characters forbidden by Meta WhatsApp template body parameters."""
    text = text.replace("\\n", " || ")
    text = text.replace("\\r", " ")
    text = text.replace("\\t", " ")
    text = text.replace("\t", " ")
    text = text.replace("\r\n", " || ")
    text = text.replace("\r", " || ")
    text = text.replace("\n", " || ")
    text = text.replace("\v", " ")
    text = text.replace("\f", " ")
    text = text.replace("\u2028", " || ")
    text = text.replace("\u2029", " || ")
    text = re.sub(r" {5,}", "    ", text)
    text = re.sub(r"( \|\| ){2,}", " || ", text)
    return text.strip()


def validate_meta_template_param(text: str, param_name: str = "param") -> None:
    """Raise if text still contains Meta-forbidden characters."""
    if re.search(r"[\n\r\t]", text):
        raise ValueError(f"{param_name} contains newline or tab characters after sanitization.")
    if re.search(r" {5,}", text):
        raise ValueError(f"{param_name} contains more than 4 consecutive spaces after sanitization.")


def generate_medical_news_report(
    days: int = 30,
    model: str = DEFAULT_MODEL,
    output_file: str = "medical_news_report.md",
) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing.")

    client = OpenAI()

    response = client.responses.create(
        model=model,
        tools=[
            {
                "type": "web_search"
            }
        ],
        tool_choice="required",
        input=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": build_user_prompt(days),
            },
        ],
    )

    report = sanitize_for_meta_template_param(response.output_text.strip())

    Path(output_file).write_text(report, encoding="utf-8")

    return report


def send_wapnexus_message(
    generated_report: str,
    days: int = 30,
    numbers: list[str] | None = None,
) -> dict:
    token = os.getenv("WAPNEXUS_TOKEN")
    if not token:
        raise RuntimeError("WAPNEXUS_TOKEN is missing.")

    template_name = os.getenv("WAPNEXUS_TEMPLATE_NAME", "medical_news_full_report")

    if numbers is None:
        numbers_env = os.getenv("WAPNEXUS_NUMBERS", "")
        numbers = [num.strip() for num in numbers_env.split(",") if num.strip()]

    if not numbers:
        raise RuntimeError("No WhatsApp numbers found. Add WAPNEXUS_NUMBERS in .env")

    report_period = sanitize_for_meta_template_param(get_report_period_label(days))
    generated_report = sanitize_for_meta_template_param(generated_report)
    validate_meta_template_param(report_period, "metadata[1]")
    validate_meta_template_param(generated_report, "metadata[2]")

    url = "https://api.wapnexus.com/send/message"

    headers = {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://app.wapnexus.com",
        "referer": "https://app.wapnexus.com/",
    }

    payload = {
        "text": "",
        "template_name": template_name,
        "message_type": 2,
        "is_select_all": False,
        "numbers": numbers,
        "metadata": {
            "1": report_period,
            "2": generated_report,
        },
        "paramsFallbackValue": {
            "1": report_period,
            "2": "N/A",
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)

    try:
        response_data = response.json()
    except ValueError:
        response_data = {"raw_response": response.text}

    if response.status_code >= 400:
        raise RuntimeError(
            f"WapNexus API failed. Status: {response.status_code}, Response: {response_data}"
        )

    return response_data


def main():
    parser = argparse.ArgumentParser(
        description="Generate medical news report and send it on WhatsApp Business."
    )

    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--output", type=str, default="medical_news_report.md")
    parser.add_argument("--send", action="store_true", help="Send report to WhatsApp after generation.")

    args = parser.parse_args()

    report = generate_medical_news_report(
        days=args.days,
        model=args.model,
        output_file=args.output,
    )

    print(report)
    print(f"\nSaved report to: {args.output}")

    # if args.send:
    send_wapnexus_message(
        generated_report=report,
        days=args.days,
        numbers=["+916353426351", "+917405444368"]
    )

    print("\nWhatsApp message sent successfully.")


if __name__ == "__main__":
    main()