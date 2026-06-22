import os
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

Important output rules:
- Do not write any intro like "Here is the report".
- Do not write any explanation about how you searched.
- Do not write any disclaimer.
- Do not write closing text like "Hope this helps".
- Do not include code, notes, or instructions.
- Output only the final news message.
- Keep the content ready to send directly on WhatsApp Business.
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
Generate a WhatsApp-ready medical news update.

Date window:
{start_date.isoformat()} to {today.isoformat()}

Output only the news content. No intro, no explanation, no disclaimer, no extra text.

Use this exact structure:

*Top Global Medical News*

1. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Approved / Peer-reviewed / Trial-stage / Preliminary / Preclinical / Company-reported]
Source: [Source name] - [URL]

2. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Approved / Peer-reviewed / Trial-stage / Preliminary / Preclinical / Company-reported]
Source: [Source name] - [URL]

*Dermatology / Skin Focus*

*Research & Studies*

1. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Peer-reviewed / Preliminary / Not yet peer-reviewed]
Source: [Source name] - [URL]

*New Treatments & Medicines*

1. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Approved / Trial-stage / Preclinical / Company-reported]
Source: [Source name] - [URL]

*Technology & Procedures*

1. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Peer-reviewed / Trial-stage / Preliminary / Preclinical]
Source: [Source name] - [URL]

*Clinical & Practice Updates*

1. *[Headline] – [Date]*
Summary: [2 short sentences]
Why it matters: [1 sentence]
Status: [Guideline / Regulatory update / Practice update]
Source: [Source name] - [URL]

Rules:
- Prioritize the last {days} days.
- Include only important and credible medical news.
- Dermatology/skin should have the strongest focus.
- Do not include "What to watch next".
- Do not include greetings.
- Do not include thank you.
- Do not include medical advice disclaimer.
- Do not include markdown headings using ### or ##.
- Use WhatsApp formatting with *bold* text only.
"""


def get_report_period_label(days: int) -> str:
    today = datetime.now(timezone.utc).date()

    # Example: Last 30 Days – June 2026
    return f"Last {days} Days – {month_name[today.month]} {today.year}"


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

    report = response.output_text.strip()

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

    report_period = get_report_period_label(days)

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

    if args.send:
        result = send_wapnexus_message(
            generated_report=report,
            days=args.days,
            numbers=["+916353426351", "+917405444368"]
        )

        print("\nWhatsApp message sent successfully.")
        print(result)


if __name__ == "__main__":
    main()