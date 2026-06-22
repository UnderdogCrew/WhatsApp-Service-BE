import os
import argparse
from pathlib import Path
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from openai import OpenAI
import sys
import django

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

Your job is to find and summarize the most important recent developments
in the medical field worldwide, with a special emphasis on dermatology/skin.

Use current, credible sources only:
- Peer-reviewed journals: NEJM, JAMA, The Lancet, BMJ, Nature Medicine, JAAD, JAMA Dermatology, British Journal of Dermatology, etc.
- Major medical institutions: WHO, CDC, NIH, NHS, Mayo Clinic, Cleveland Clinic, major universities/hospitals.
- Regulatory bodies: FDA, EMA, MHRA, Health Canada, TGA, etc.
- Reputable medical news outlets: MedPage Today, STAT, Reuters Health, Dermatology Times, Healio, etc.

Rules:
- Prioritize news from the last 30 days.
- Clearly note the date of each item.
- Flag anything preliminary, trial-stage, preclinical, company-reported, or not yet peer-reviewed.
- Avoid hype. Be clinically practical.
- Do not present trial-stage drugs as approved.
- Include source links.
- Use plain language suitable for clinicians, health writers, and non-specialist readers.
- Do not give personal medical advice.
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


def generate_medical_news_report(
    days: int = 7,
    model: str = DEFAULT_MODEL,
    output_file: str = "medical_news_report.md",
) -> str:
    if not os.getenv("OPEN_AI_KEY"):
        raise RuntimeError(
            "OPEN_AI_KEY is missing. Add it to your .env file or export it in your terminal."
        )

    client = OpenAI(api_key=os.getenv("OPEN_AI_KEY"))

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

    report = response.output_text

    output_path = Path(output_file)
    output_path.write_text(report, encoding="utf-8")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Generate recent global medical news report with dermatology focus."
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of recent days to prioritize. Default: 30",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=DEFAULT_MODEL,
        help=f"OpenAI model to use. Default: {DEFAULT_MODEL}",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="medical_news_report.md",
        help="Output markdown file name. Default: medical_news_report.md",
    )

    args = parser.parse_args()

    report = generate_medical_news_report(
        days=args.days,
        model=args.model,
        output_file=args.output,
    )

    print(report)
    print(f"\n\nSaved report to: {args.output}")


if __name__ == "__main__":
    main()