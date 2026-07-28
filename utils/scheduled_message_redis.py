import json
import uuid
from datetime import datetime, timezone

import pytz
from UnderdogCrew.settings import redis_client

SCHEDULED_MESSAGES_ZSET = "whatsapp:scheduled_messages"
SCHEDULED_MESSAGE_KEY = "whatsapp:scheduled_message:{schedule_id}"


def parse_scheduled_at(scheduled_at, schedule_timezone="UTC"):
    """
    Parse scheduled_at into a timezone-aware UTC datetime.
    - ISO strings with Z/offset are treated as absolute times.
    - Naive datetimes are interpreted in schedule_timezone.
    """
    if not scheduled_at:
        raise ValueError("scheduled_at is required")

    value = str(scheduled_at).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid scheduled_at format: {scheduled_at}") from exc

    if dt.tzinfo is None:
        tz_name = schedule_timezone or "UTC"
        try:
            tz = pytz.timezone(tz_name)
        except pytz.UnknownTimeZoneError as exc:
            raise ValueError(f"Invalid schedule_timezone: {tz_name}") from exc
        dt = tz.localize(dt)

    return dt.astimezone(timezone.utc)


def store_scheduled_message(payload, scheduled_at_utc):
    """
    Store a scheduled message in Redis.
    Uses a sorted set (score = unix timestamp) + JSON payload key.
    """
    schedule_id = str(uuid.uuid4())
    score = scheduled_at_utc.timestamp()
    payload_to_store = dict(payload)
    payload_to_store["schedule_id"] = schedule_id
    payload_to_store["scheduled_at_utc"] = scheduled_at_utc.isoformat()

    pipe = redis_client.pipeline()
    pipe.zadd(SCHEDULED_MESSAGES_ZSET, {schedule_id: score})
    pipe.set(SCHEDULED_MESSAGE_KEY.format(schedule_id=schedule_id), json.dumps(payload_to_store))
    pipe.execute()
    return schedule_id


def claim_due_scheduled_messages(now_ts=None, limit=50):
    """
    Atomically claim due scheduled messages (score <= now).
    Returns list of payload dicts.
    """
    if now_ts is None:
        now_ts = datetime.now(timezone.utc).timestamp()

    due_ids = redis_client.zrangebyscore(
        SCHEDULED_MESSAGES_ZSET,
        min=0,
        max=now_ts,
        start=0,
        num=limit,
    )
    claimed = []
    for raw_id in due_ids:
        schedule_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
        removed = redis_client.zrem(SCHEDULED_MESSAGES_ZSET, schedule_id)
        if not removed:
            continue

        key = SCHEDULED_MESSAGE_KEY.format(schedule_id=schedule_id)
        raw_payload = redis_client.get(key)
        redis_client.delete(key)
        if not raw_payload:
            continue

        if isinstance(raw_payload, bytes):
            raw_payload = raw_payload.decode("utf-8")
        try:
            claimed.append(json.loads(raw_payload))
        except json.JSONDecodeError:
            continue

    return claimed
