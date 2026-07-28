import os
import sys
import time
import traceback

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "UnderdogCrew.settings")
django.setup()

from utils.send_message_data import TokenBucketLimiter
from utils.scheduled_message_redis import claim_due_scheduled_messages
from utils.whatsapp_message_data import send_message_data

POLL_INTERVAL_SECONDS = 60


def send_scheduled_whatsapp_message(payload):
    numbers = payload.get("numbers") or []
    limiter = TokenBucketLimiter(rate_per_sec=60)
    for number in numbers:
        limiter.acquire()
        send_message_data(
            number=number,
            template_name=payload.get("template_name"),
            text=payload.get("text") or "",
            image_url=payload.get("image_url") or "",
            user_id=payload.get("user_id"),
            metadata=payload.get("metadata"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            location_name=payload.get("location_name"),
            address=payload.get("address"),
            params_fallback_value=payload.get("params_fallback_value"),
            button_value=payload.get("button_value"),
        )


def process_due_messages():
    due_messages = claim_due_scheduled_messages()
    if not due_messages:
        return 0

    for payload in due_messages:
        schedule_id = payload.get("schedule_id")
        try:
            print(
                f"Sending scheduled message {schedule_id} "
                f"to {len(payload.get('numbers') or [])} numbers"
            )
            send_scheduled_whatsapp_message(payload)
            print(f"Scheduled message {schedule_id} sent successfully")
        except Exception as exc:
            line_number = sys.exc_info()[-1].tb_lineno
            print(
                f"Error sending scheduled message {schedule_id} "
                f"on line {line_number}: {type(exc).__name__} {exc}"
            )
            traceback.print_exc()

    return len(due_messages)


def run_worker():
    print("Redis scheduled message worker started")
    while True:
        try:
            processed = process_due_messages()
            if processed:
                print(f"Processed {processed} due scheduled message(s)")
        except Exception as exc:
            line_number = sys.exc_info()[-1].tb_lineno
            print(
                f"Worker loop error on line {line_number}: "
                f"{type(exc).__name__} {exc}"
            )
            traceback.print_exc()
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker()
