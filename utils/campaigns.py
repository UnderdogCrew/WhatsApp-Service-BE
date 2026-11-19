import datetime

import pytz
from bson import ObjectId
from pymongo import ReturnDocument


def template_category_from_payload(payload, template_name):
    items = (payload or {}).get("data") or []
    match = next((item for item in items if item.get("name") == template_name), None)
    if match is None and items:
        match = items[0]
    return (match or {}).get("category") or ""


def next_campaign_code(db):
    result = db.get_collection("counters").find_one_and_update(
        {"_id": "campaign"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return f"CMP-{1000 + int(result['seq'])}"


def create_campaign(
    db,
    user_id,
    campaign_name,
    template_name,
    template_category,
    recipients,
    status,
    schedule_type,
    scheduled_at=None,
    scheduled_at_utc=None,
    schedule_timezone="UTC",
    sent_at=None,
):
    now = datetime.datetime.now(datetime.timezone.utc)
    document = {
        "user_id": str(user_id),
        "campaign_name": campaign_name or template_name or "Campaign",
        "campaign_code": next_campaign_code(db),
        "template_name": template_name or "",
        "template_category": template_category or "",
        "status": status,
        "recipients": int(recipients or 0),
        "schedule_type": schedule_type,
        "scheduled_at": scheduled_at,
        "scheduled_at_utc": scheduled_at_utc,
        "schedule_timezone": schedule_timezone or "UTC",
        "schedule_id": None,
        "sent_at": sent_at,
        "send_finished": False,
        "created_at": now,
        "updated_at": now,
    }
    campaign_id = db.create_document("campaigns", document)
    return campaign_id, document["campaign_code"]


def mark_campaign_sending(campaign_id):
    if not campaign_id:
        return
    try:
        from utils.database import MongoDB

        MongoDB().update_document(
            "campaigns",
            {"_id": ObjectId(campaign_id)},
            {
                "status": "running",
                "sent_at": datetime.datetime.now(datetime.timezone.utc),
            },
        )
    except Exception as exc:
        print(f"Failed to mark campaign sending: {exc}")


def mark_campaign_send_finished(campaign_id):
    if not campaign_id:
        return
    try:
        from utils.database import MongoDB

        MongoDB().update_document(
            "campaigns",
            {"_id": ObjectId(campaign_id)},
            {"send_finished": True},
        )
    except Exception as exc:
        print(f"Failed to mark campaign send finished: {exc}")


def campaign_delivery_stats(db, user_id, campaign_ids):
    if not campaign_ids:
        return {}
    rows = db.aggregate(
        "whatsapp_message_logs",
        [
            {
                "$match": {
                    "user_id": str(user_id),
                    "campaign_id": {"$in": list(campaign_ids)},
                }
            },
            {
                "$group": {
                    "_id": "$campaign_id",
                    "delivered": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$message_status", ["delivered", "read"]]},
                                1,
                                0,
                            ]
                        }
                    },
                    "read": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$message_status", "read"]},
                                1,
                                0,
                            ]
                        }
                    },
                    "failed": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$message_status", ["failed", "error"]]},
                                1,
                                0,
                            ]
                        }
                    },
                    "logged": {"$sum": 1},
                }
            },
        ],
    )
    return {row["_id"]: row for row in rows}


def _as_utc(value):
    if value is None or value == "":
        return None
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            value = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    if not isinstance(value, datetime.datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def format_campaign_datetime(value, tz_name="Asia/Kolkata"):
    moment = _as_utc(value)
    if moment is None:
        return ""
    try:
        tz = pytz.timezone(tz_name or "Asia/Kolkata")
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Kolkata")
    local = moment.astimezone(tz)
    hour = local.strftime("%I")
    return f"{local.day} {local.strftime('%b')}, {hour}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def category_label(category):
    if not category:
        return ""
    labels = {
        "MARKETING": "Marketing",
        "UTILITY": "Utility",
        "AUTHENTICATION": "Authentication",
    }
    return labels.get(str(category).upper(), str(category).title())


def _percent(count, total):
    if not total:
        return 0
    value = round((count * 100) / total, 1)
    if value == int(value):
        return int(value)
    return value


def build_campaign_row(campaign, stats):
    stats = stats or {}
    recipients = int(campaign.get("recipients") or 0)
    logged = int(stats.get("logged") or 0)
    delivered = int(stats.get("delivered") or 0)
    read = int(stats.get("read") or 0)
    failed = int(stats.get("failed") or 0)
    pending = max(0, logged - delivered - failed)
    is_scheduled = campaign.get("status") == "scheduled"

    if is_scheduled:
        status = "Scheduled"
        when = campaign.get("scheduled_at_utc") or campaign.get("created_at")
        activity_label = "Scheduled · " + format_campaign_datetime(
            when,
            campaign.get("schedule_timezone") or "Asia/Kolkata",
        )
        return {
            "id": str(campaign["_id"]),
            "campaign_name": campaign.get("campaign_name") or "",
            "campaign_code": campaign.get("campaign_code") or "",
            "activity_label": activity_label,
            "template_name": campaign.get("template_name") or "",
            "template_category": category_label(campaign.get("template_category")),
            "status": status,
            "recipients": recipients,
            "delivered_count": None,
            "delivered_percentage": None,
            "read_count": None,
            "read_percentage": None,
            "failed_count": None,
            "show_logs": False,
            "logs_label": "Not sent yet",
        }

    if campaign.get("send_finished"):
        failed += max(0, recipients - logged)

    if not campaign.get("send_finished") or pending > 0:
        status = "Running"
    else:
        status = "Completed"

    when = campaign.get("sent_at") or campaign.get("created_at")
    return {
        "id": str(campaign["_id"]),
        "campaign_name": campaign.get("campaign_name") or "",
        "campaign_code": campaign.get("campaign_code") or "",
        "activity_label": format_campaign_datetime(when, "Asia/Kolkata"),
        "template_name": campaign.get("template_name") or "",
        "template_category": category_label(campaign.get("template_category")),
        "status": status,
        "recipients": recipients,
        "delivered_count": delivered,
        "delivered_percentage": _percent(delivered, recipients),
        "read_count": read,
        "read_percentage": _percent(read, recipients),
        "failed_count": failed,
        "show_logs": True,
        "logs_label": "View logs",
    }
