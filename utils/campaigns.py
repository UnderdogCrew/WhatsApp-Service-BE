import csv
import datetime
import io
import math
import re

import pytz
from bson import ObjectId
from pymongo import ReturnDocument

CAMPAIGN_LOG_STATUSES = ("all", "running", "completed", "scheduled")
CAMPAIGN_LOG_SORTS = ("newest", "oldest", "name", "recipients", "failed")
_SORT_ALIASES = {
    "newest_first": "newest",
    "oldest_first": "oldest",
    "name_asc": "name",
    "most_failed": "failed",
}
_DISPLAY_STATUS = {
    "running": "Running",
    "completed": "Completed",
    "scheduled": "Scheduled",
}


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


def campaign_activity_moment(campaign):
    if campaign.get("status") == "scheduled":
        when = campaign.get("scheduled_at_utc") or campaign.get("created_at")
    else:
        when = campaign.get("sent_at") or campaign.get("created_at")
    return _as_utc(when)


def _activity_at(campaign):
    moment = campaign_activity_moment(campaign)
    if moment is None:
        return ""
    return moment.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_campaign_row(campaign, stats):
    stats = stats or {}
    recipients = int(campaign.get("recipients") or 0)
    logged = int(stats.get("logged") or 0)
    delivered = int(stats.get("delivered") or 0)
    read = int(stats.get("read") or 0)
    failed = int(stats.get("failed") or 0)
    pending = max(0, logged - delivered - failed)
    is_scheduled = campaign.get("status") == "scheduled"
    activity_at = _activity_at(campaign)

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
            "activity_at": activity_at,
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
        "activity_at": activity_at,
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


def _read_int(params, key):
    raw = params.get(key, None)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _parse_log_dates(start_date, end_date):
    kolkata = pytz.timezone("Asia/Kolkata")
    start_utc = None
    end_utc = None
    if start_date:
        try:
            naive = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            return None, None, "Invalid start_date format. Use YYYY-MM-DD."
        start_utc = kolkata.localize(naive).astimezone(datetime.timezone.utc)
    if end_date:
        try:
            naive = datetime.datetime.strptime(end_date, "%Y-%m-%d") + datetime.timedelta(days=1)
        except ValueError:
            return None, None, "Invalid end_date format. Use YYYY-MM-DD."
        end_utc = kolkata.localize(naive).astimezone(datetime.timezone.utc)
    if start_date and end_date and end_date < start_date:
        return None, None, "end_date must be on or after start_date"
    return start_utc, end_utc, None


def format_range_label(start_date, end_date):
    if not start_date and not end_date:
        return "All time"

    def _day(value):
        return datetime.datetime.strptime(value, "%Y-%m-%d")

    if start_date and end_date:
        start = _day(start_date)
        end = _day(end_date)
        if start.year == end.year and start.month == end.month:
            return f"{start.day}–{end.day} {start.strftime('%b')} {start.year}"
        if start.year == end.year:
            return f"{start.day} {start.strftime('%b')} – {end.day} {end.strftime('%b')} {end.year}"
        return (
            f"{start.day} {start.strftime('%b')} {start.year} – "
            f"{end.day} {end.strftime('%b')} {end.year}"
        )
    if start_date:
        start = _day(start_date)
        return f"From {start.day} {start.strftime('%b')} {start.year}"
    end = _day(end_date)
    return f"Until {end.day} {end.strftime('%b')} {end.year}"


def parse_campaign_log_params(params):
    search = (params.get("search") or "").strip()
    if len(search) > 100:
        return None, "search must be 100 characters or fewer"

    template = (params.get("template") or params.get("template_name") or "").strip()
    if template.lower() in {"all", "all templates"}:
        template = ""

    status_value = (params.get("status") or "all").strip().lower()
    if status_value not in CAMPAIGN_LOG_STATUSES:
        return None, "status must be one of all, running, completed, scheduled"

    sort = (params.get("sort") or "newest").strip().lower().replace(" ", "_")
    sort = _SORT_ALIASES.get(sort, sort)
    if sort not in CAMPAIGN_LOG_SORTS:
        return None, "sort must be one of newest, oldest, name, recipients, failed"

    export_format = (params.get("format") or "json").strip().lower()
    if export_format not in {"json", "csv"}:
        return None, "format must be json or csv"

    start_date = (params.get("start_date") or "").strip()
    end_date = (params.get("end_date") or "").strip()
    start_utc, end_utc, date_error = _parse_log_dates(start_date, end_date)
    if date_error:
        return None, date_error

    try:
        limit_raw = _read_int(params, "limit")
        page = _read_int(params, "page")
        skip = _read_int(params, "skip")
    except ValueError as exc:
        return None, str(exc)

    limit = 20 if limit_raw is None or limit_raw <= 0 else min(limit_raw, 100)
    if page is not None:
        if page < 1:
            return None, "page must be 1 or greater"
        skip = (page - 1) * limit
    else:
        skip = 0 if skip is None else skip
        if skip < 0:
            return None, "skip must be 0 or greater"
        page = (skip // limit) + 1

    return {
        "search": search,
        "template": template,
        "status": status_value,
        "sort": sort,
        "format": export_format,
        "start_date": start_date,
        "end_date": end_date,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "page": page,
        "limit": limit,
        "skip": skip,
    }, None


def _activity_expr():
    return {
        "$cond": [
            {"$eq": ["$status", "scheduled"]},
            {"$ifNull": ["$scheduled_at_utc", "$created_at"]},
            {"$ifNull": ["$sent_at", "$created_at"]},
        ]
    }


def campaign_log_query(user_id, filters):
    clauses = [{"user_id": str(user_id)}]
    if filters["search"]:
        pattern = {"$regex": re.escape(filters["search"]), "$options": "i"}
        clauses.append(
            {
                "$or": [
                    {"campaign_name": pattern},
                    {"template_name": pattern},
                    {"campaign_code": pattern},
                ]
            }
        )
    comparisons = []
    activity = _activity_expr()
    if filters["start_utc"] is not None:
        comparisons.append({"$gte": [activity, filters["start_utc"]]})
    if filters["end_utc"] is not None:
        comparisons.append({"$lt": [activity, filters["end_utc"]]})
    if len(comparisons) == 1:
        clauses.append({"$expr": comparisons[0]})
    elif comparisons:
        clauses.append({"$expr": {"$and": comparisons}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _template_options(campaigns):
    seen = {}
    for campaign in campaigns:
        name = (campaign.get("template_name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen[name.lower()] = {
            "name": name,
            "category": category_label(campaign.get("template_category")),
        }
    return sorted(seen.values(), key=lambda item: item["name"].lower())


def _sort_rows(rows, sort):
    if sort == "oldest":
        return sorted(rows, key=lambda row: row.get("activity_at") or "")
    if sort == "name":
        return sorted(
            rows,
            key=lambda row: (
                (row.get("campaign_name") or "").lower(),
                row.get("activity_at") or "",
            ),
        )
    if sort == "recipients":
        return sorted(
            rows,
            key=lambda row: (-(row.get("recipients") or 0), row.get("activity_at") or ""),
        )
    if sort == "failed":
        return sorted(
            rows,
            key=lambda row: (
                -(row["failed_count"] if row.get("failed_count") is not None else -1),
                row.get("activity_at") or "",
            ),
        )
    return sorted(rows, key=lambda row: row.get("activity_at") or "", reverse=True)


def _paginate(rows, page, limit, skip):
    total = len(rows)
    return rows[skip:skip + limit], {
        "page": page,
        "limit": limit,
        "skip": skip,
        "total": total,
        "total_pages": math.ceil(total / limit) if total else 0,
        "has_next": skip + limit < total,
        "has_previous": skip > 0,
    }


def build_campaign_summary(rows):
    sent_rows = [row for row in rows if row["status"] != "Scheduled"]
    recipients = sum(row["recipients"] for row in sent_rows)
    delivered = sum(row["delivered_count"] or 0 for row in sent_rows)
    read = sum(row["read_count"] or 0 for row in sent_rows)
    failed = sum(row["failed_count"] or 0 for row in sent_rows)
    queued = sum(
        max(0, row["recipients"] - (row["delivered_count"] or 0) - (row["failed_count"] or 0))
        for row in sent_rows
    )
    return {
        "campaigns_sent": len(sent_rows),
        "scheduled": sum(1 for row in rows if row["status"] == "Scheduled"),
        "recipients": recipients,
        "queued": queued,
        "delivered": delivered,
        "delivery_rate": _percent(delivered, recipients),
        "read": read,
        "read_rate": _percent(read, recipients),
        "failed": failed,
        "failed_rate": _percent(failed, recipients),
    }


def campaign_status_counts(rows):
    counts = {"all": len(rows), "running": 0, "completed": 0, "scheduled": 0}
    for row in rows:
        key = (row.get("status") or "").lower()
        if key in counts:
            counts[key] += 1
    return counts


def failure_reasons_by_campaign(db, user_id, campaign_ids):
    if not campaign_ids:
        return {}
    grouped = db.aggregate(
        "whatsapp_message_logs",
        [
            {
                "$match": {
                    "user_id": str(user_id),
                    "campaign_id": {"$in": list(campaign_ids)},
                    "message_status": {"$in": ["failed", "error"]},
                }
            },
            {
                "$group": {
                    "_id": {
                        "campaign_id": "$campaign_id",
                        "reason": {
                            "$trim": {
                                "input": {
                                    "$ifNull": [
                                        "$error_message",
                                        {"$ifNull": ["$title", ""]},
                                    ]
                                }
                            }
                        },
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"count": -1}},
        ],
    )
    reasons = {}
    for row in grouped:
        campaign_id = (row.get("_id") or {}).get("campaign_id")
        if not campaign_id or campaign_id in reasons:
            continue
        reason = ((row.get("_id") or {}).get("reason") or "").strip() or "Unknown"
        reasons[campaign_id] = {"reason": reason, "count": int(row.get("count") or 0)}
    return reasons


def build_failure_alert(rows, reasons):
    candidates = [
        row
        for row in rows
        if (row.get("failed_count") or 0) > 0 and (row.get("recipients") or 0) > 0
    ]
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda row: (
            _percent(row["failed_count"], row["recipients"]),
            row["failed_count"],
            row.get("activity_at") or "",
        ),
    )
    failed = best["failed_count"]
    recipients = best["recipients"]
    percentage = _percent(failed, recipients)
    reason_info = reasons.get(best["id"]) or {}
    reason = (reason_info.get("reason") or "").strip()
    recipient_word = "recipient" if recipients == 1 else "recipients"
    message = (
        f"{best['campaign_name']} failed for {failed} of {recipients} "
        f"{recipient_word} ({percentage}%)."
    )
    if reason and reason.lower() != "unknown":
        message = f"{message} Most common reason: {reason}"
    return {
        "campaign_id": best["id"],
        "campaign_code": best.get("campaign_code") or "",
        "campaign_name": best.get("campaign_name") or "",
        "failed_count": failed,
        "recipients": recipients,
        "failed_percentage": percentage,
        "reason": reason,
        "reason_count": reason_info.get("count") or 0,
        "message": message,
    }


def campaigns_to_csv(rows):
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "Campaign",
            "Campaign code",
            "Activity",
            "Template",
            "Category",
            "Status",
            "Recipients",
            "Delivered",
            "Delivered %",
            "Read",
            "Read %",
            "Failed",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                row.get("campaign_name") or "",
                row.get("campaign_code") or "",
                row.get("activity_label") or "",
                row.get("template_name") or "",
                row.get("template_category") or "",
                row.get("status") or "",
                row.get("recipients") if row.get("recipients") is not None else "",
                "" if row.get("delivered_count") is None else row.get("delivered_count"),
                "" if row.get("delivered_percentage") is None else row.get("delivered_percentage"),
                "" if row.get("read_count") is None else row.get("read_count"),
                "" if row.get("read_percentage") is None else row.get("read_percentage"),
                "" if row.get("failed_count") is None else row.get("failed_count"),
            ]
        )
    return buffer.getvalue()


def build_campaign_logs(db, user_id, filters):
    campaigns = db.find_documents(
        "campaigns",
        campaign_log_query(user_id, filters),
        sort=[("created_at", -1)],
    )
    templates = _template_options(campaigns)
    if filters["template"]:
        selected = filters["template"].lower()
        campaigns = [
            campaign
            for campaign in campaigns
            if (campaign.get("template_name") or "").lower() == selected
        ]

    stats_by_campaign = campaign_delivery_stats(
        db,
        user_id,
        [str(campaign["_id"]) for campaign in campaigns],
    )
    rows = [
        build_campaign_row(campaign, stats_by_campaign.get(str(campaign["_id"])))
        for campaign in campaigns
    ]
    summary = build_campaign_summary(rows)
    counts = campaign_status_counts(rows)
    if filters["status"] == "all":
        visible = rows
    else:
        label = _DISPLAY_STATUS[filters["status"]]
        visible = [row for row in rows if row["status"] == label]
    visible = _sort_rows(visible, filters["sort"])

    failed_ids = [row["id"] for row in visible if (row.get("failed_count") or 0) > 0]
    reasons = failure_reasons_by_campaign(db, user_id, failed_ids)
    alert = build_failure_alert(visible, reasons)
    page_rows, pagination = _paginate(visible, filters["page"], filters["limit"], filters["skip"])
    payload = {
        "message": "Campaign logs fetched successfully",
        "summary": summary,
        "status_counts": counts,
        "templates": templates,
        "alert": alert,
        "filters": {
            "search": filters["search"],
            "start_date": filters["start_date"],
            "end_date": filters["end_date"],
            "range_label": format_range_label(filters["start_date"], filters["end_date"]),
            "template": filters["template"],
            "status": filters["status"],
            "sort": filters["sort"],
        },
        "pagination": pagination,
        "count": pagination["total"],
        "data": page_rows,
    }
    return payload, visible


RECIPIENT_STATUSES = ("all", "read", "delivered", "failed", "queued", "replied")
_SENT_TO_WHATSAPP_STATUSES = {"sent", "accepted", "ok", "delivered", "read", "failed", "error"}
_FAILURE_TITLES = {
    131026: "Message undeliverable",
    131056: "Too many messages to one number",
    131047: "24-hour window closed",
    131049: "Held back by Meta's marketing limit",
    131050: "Promotional messages stopped",
    131021: "Can't message your own number",
    130403: "Recipient is blocked",
    130472: "Excluded by a Meta test",
    130497: "Country not allowed",
    131048: "Sending restricted",
    131042: "Billing problem",
    132001: "Template unavailable",
    132015: "Template paused",
    4: "Sending limit reached",
    80007: "Sending limit reached",
    130429: "Sending too quickly",
}


def _last10(number):
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _number_variants(number):
    raw = str(number or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    last10 = digits[-10:] if len(digits) >= 10 else digits
    values = []
    for value in (
        raw,
        digits,
        last10,
        f"91{last10}" if last10 else "",
        f"+91{last10}" if last10 else "",
        f"+{digits}" if digits else "",
    ):
        if value and value not in values:
            values.append(value)
    return values


def mask_phone_number(number):
    digits = "".join(ch for ch in str(number or "") if ch.isdigit())
    national = digits[-10:] if len(digits) >= 10 else digits
    if len(national) < 4:
        return str(number or "")
    if len(national) >= 10:
        masked = f"{national[:5]} •••{national[-2:]}"
    else:
        masked = f"{national[:2]} •••{national[-2:]}"
    if digits.startswith("91") or len(digits) > 10:
        return f"+91 {masked}"
    return masked


def contact_initials(name):
    parts = [part for part in re.split(r"\s+", str(name or "").strip()) if part and part[0].isalpha()]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if len(parts) == 1:
        letters = [char for char in parts[0] if char.isalpha()]
        return "".join(letters[:2]).upper()
    return ""


def format_log_clock(value):
    if value is None or value == "" or value == 0:
        return "—"
    if isinstance(value, (int, float)):
        moment = datetime.datetime.fromtimestamp(value, datetime.timezone.utc)
    elif isinstance(value, datetime.datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
        moment = moment.astimezone(datetime.timezone.utc)
    else:
        return "—"
    local = moment.astimezone(pytz.timezone("Asia/Kolkata"))
    return f"{local.strftime('%I')}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def format_campaign_date_long(value, tz_name="Asia/Kolkata"):
    moment = _as_utc(value)
    if moment is None:
        return ""
    try:
        tz = pytz.timezone(tz_name or "Asia/Kolkata")
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Asia/Kolkata")
    local = moment.astimezone(tz)
    hour = local.strftime("%I")
    return f"{local.day} {local.strftime('%b')} {local.year}, {hour}:{local.strftime('%M')} {local.strftime('%p').lower()}"


def _status_count(by_status, *names):
    return sum(int(by_status.get(name) or 0) for name in names)


def _campaign_object_id(campaign_id):
    try:
        return ObjectId(str(campaign_id))
    except Exception:
        return campaign_id


def message_log_search_clause(db, user_id, search):
    search = (search or "").strip()
    if not search:
        return None
    if len(search) > 100:
        raise ValueError("search must be 100 characters or fewer")
    pattern = {"$regex": re.escape(search), "$options": "i"}
    clauses = [{"number": pattern}]
    digits = "".join(ch for ch in search if ch.isdigit())
    if digits and digits != search:
        clauses.append({"number": {"$regex": re.escape(digits)}})
    user_ids = [user_id]
    if str(user_id) not in user_ids:
        user_ids.append(str(user_id))
    customers = db.find_documents(
        "customers",
        {"user_id": {"$in": user_ids}, "name": pattern},
        projection={"number": 1},
        limit=200,
    )
    numbers = []
    for customer in customers:
        for value in _number_variants(customer.get("number")):
            if value not in numbers:
                numbers.append(value)
    if numbers:
        clauses.append({"number": {"$in": numbers}})
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


def apply_recipient_status_filter(query_filter, recipient_status, replied_numbers):
    status_name = (recipient_status or "all").strip().lower()
    if status_name in ("", "all"):
        return query_filter, None
    if status_name not in RECIPIENT_STATUSES:
        return None, "recipient_status must be one of all, read, delivered, failed, queued, replied"
    if status_name == "read":
        query_filter["message_status"] = "read"
    elif status_name == "delivered":
        query_filter["message_status"] = "delivered"
    elif status_name == "failed":
        query_filter["message_status"] = {"$in": ["failed", "error"]}
    elif status_name == "queued":
        query_filter["message_status"] = {
            "$nin": ["read", "delivered", "failed", "error", "sent", "accepted", "ok", "received"]
        }
    elif status_name == "replied":
        query_filter["number"] = {"$in": list(replied_numbers or [])}
    return query_filter, None


def _failure_reason_rows(grouped):
    by_code = {}
    for row in grouped:
        identity = row.get("_id") or {}
        try:
            code = int(identity.get("code") or 0)
        except (TypeError, ValueError):
            code = 0
        count = int(row.get("count") or 0)
        message = (identity.get("message") or identity.get("title") or "").strip()
        bucket = by_code.setdefault(code, {"count": 0, "message": "", "best": 0})
        bucket["count"] += count
        if count >= bucket["best"] and message:
            bucket["message"] = message
            bucket["best"] = count
    reasons = []
    failed_total = sum(bucket["count"] for bucket in by_code.values())
    for code, bucket in by_code.items():
        title = _FAILURE_TITLES.get(code) or "Failed"
        reasons.append(
            {
                "code": code or None,
                "title": title,
                "message": bucket["message"] or title,
                "count": bucket["count"],
                "percentage": _percent(bucket["count"], failed_total),
            }
        )
    reasons.sort(key=lambda item: (-item["count"], item["title"]))
    return failed_total, reasons


def _replied_numbers(db, user_id, numbers, campaign):
    raw_numbers = [row.get("_id") for row in numbers if row.get("_id")]
    if not raw_numbers or not campaign:
        return set(), []
    start = _as_utc(campaign.get("sent_at") or campaign.get("created_at"))
    if start is None:
        return set(), []
    variants = []
    raw_by_key = {}
    for number in raw_numbers:
        key = _last10(number)
        raw_by_key.setdefault(key, [])
        if number not in raw_by_key[key]:
            raw_by_key[key].append(number)
        for value in _number_variants(number):
            if value not in variants:
                variants.append(value)
    user_ids = [user_id]
    if str(user_id) not in user_ids:
        user_ids.append(str(user_id))
    received = db.find_documents(
        "whatsapp_message_logs",
        {
            "user_id": {"$in": user_ids},
            "message_status": "received",
            "number": {"$in": variants},
            "created_at": {"$gte": start},
        },
        projection={"number": 1},
    )
    replied_keys = {_last10(row.get("number")) for row in received if _last10(row.get("number"))}
    replied_values = []
    for key in replied_keys:
        for number in raw_by_key.get(key, []):
            if number not in replied_values:
                replied_values.append(number)
    return replied_keys, replied_values


def build_message_campaign_detail(db, user_id, campaign_id, campaign_code, base_filter):
    user_ids = [str(user_id)]
    if user_id not in user_ids:
        user_ids.append(user_id)
    campaign_query = {"user_id": {"$in": user_ids}}
    if campaign_id:
        campaign_query["_id"] = _campaign_object_id(campaign_id)
    else:
        campaign_query["campaign_code"] = campaign_code
    campaign = db.find_document("campaigns", campaign_query)

    facets = db.aggregate(
        "whatsapp_message_logs",
        [
            {"$match": base_filter},
            {
                "$facet": {
                    "by_status": [{"$group": {"_id": "$message_status", "count": {"$sum": 1}}}],
                    "failures": [
                        {"$match": {"message_status": {"$in": ["failed", "error"]}}},
                        {
                            "$group": {
                                "_id": {
                                    "code": "$code",
                                    "title": "$title",
                                    "message": "$error_message",
                                },
                                "count": {"$sum": 1},
                            }
                        },
                    ],
                    "numbers": [{"$group": {"_id": "$number"}}],
                }
            },
        ],
    )
    facet = facets[0] if facets else {}
    by_status = {
        (row.get("_id") or ""): int(row.get("count") or 0)
        for row in facet.get("by_status") or []
    }
    read = _status_count(by_status, "read")
    delivered_only = _status_count(by_status, "delivered")
    delivered = delivered_only + read
    failed = _status_count(by_status, "failed", "error")
    sent_waiting = _status_count(by_status, "sent", "accepted", "ok")
    logged = sum(by_status.values())
    sent = sum(count for status_name, count in by_status.items() if status_name in _SENT_TO_WHATSAPP_STATUSES)
    recipients = int((campaign or {}).get("recipients") or 0) or logged
    queued = max(0, recipients - sent)
    replied_keys, replied_values = _replied_numbers(db, user_id, facet.get("numbers") or [], campaign)
    failed_total, reasons = _failure_reason_rows(facet.get("failures") or [])

    if campaign and campaign.get("status") == "scheduled":
        timing_label = "Scheduled"
        timing_value = format_campaign_date_long(
            campaign.get("scheduled_at_utc") or campaign.get("created_at"),
            (campaign or {}).get("schedule_timezone") or "Asia/Kolkata",
        )
        screen_status = "Scheduled"
    else:
        timing_label = "Started"
        timing_source = (campaign or {}).get("sent_at") or (campaign or {}).get("created_at")
        timing_value = format_campaign_date_long(timing_source, "Asia/Kolkata")
        stats = {"logged": logged, "delivered": delivered, "read": read, "failed": failed}
        if campaign:
            screen_status = build_campaign_row(campaign, stats)["status"]
        else:
            screen_status = "Running" if queued else "Completed"

    audience_name = ((campaign or {}).get("audience_name") or "").strip()
    audience_label = f"{audience_name} · {recipients}" if audience_name else str(recipients)
    denominator = recipients or logged
    funnel = [
        {"key": "recipients", "label": "Recipients", "count": recipients, "percentage": 100 if denominator else 0},
        {"key": "sent", "label": "Sent to WhatsApp", "count": sent, "percentage": _percent(sent, denominator)},
        {"key": "delivered", "label": "Delivered", "count": delivered, "percentage": _percent(delivered, denominator)},
        {"key": "read", "label": "Read", "count": read, "percentage": _percent(read, denominator)},
        {
            "key": "replied",
            "label": "Replied",
            "count": len(replied_keys),
            "percentage": _percent(len(replied_keys), denominator),
        },
    ]
    detail = {
        "id": str(campaign["_id"]) if campaign else (campaign_id or ""),
        "campaign_name": (campaign or {}).get("campaign_name") or "",
        "campaign_code": (campaign or {}).get("campaign_code") or (campaign_code or ""),
        "status": screen_status,
        "template_name": (campaign or {}).get("template_name") or "",
        "template_category": category_label((campaign or {}).get("template_category")),
        "audience_name": audience_name,
        "audience_label": audience_label,
        "recipients": recipients,
        "timing_label": timing_label,
        "timing_value": timing_value,
        "progress_sent": sent,
        "progress_label": f"{sent} of {recipients} sent",
        "funnel": funnel,
        "failures": {"failed": failed_total, "reasons": reasons},
        "recipient_counts": {
            "all": recipients,
            "read": read,
            "delivered": delivered_only,
            "failed": failed,
            "queued": queued,
            "replied": len(replied_keys),
            "sent": sent_waiting,
        },
    }
    return detail, replied_keys, replied_values


def _recipient_status_label(message_status):
    status_name = (message_status or "").lower()
    if status_name == "read":
        return "Read"
    if status_name == "delivered":
        return "Delivered"
    if status_name in ("failed", "error"):
        return "Failed"
    if status_name in ("sent", "accepted", "ok"):
        return "Sent"
    return "Queued"


def recipient_row_fields(message, customer_name, replied_keys):
    status_name = (message.get("message_status") or "").lower()
    sent_time = format_log_clock(message.get("sent_at"))
    if sent_time == "—" :
        sent_time = format_log_clock(message.get("created_at"))
    note = ""
    if status_name in ("failed", "error"):
        try:
            code = int(message.get("code") or 0)
        except (TypeError, ValueError):
            code = 0
        note = _FAILURE_TITLES.get(code) or (message.get("error_message") or message.get("title") or "")
    phone_key = _last10(message.get("number"))
    return {
        "contact_initials": contact_initials(customer_name),
        "phone_masked": mask_phone_number(message.get("number")),
        "status_label": _recipient_status_label(status_name),
        "sent_time": sent_time,
        "delivered_time": format_log_clock(message.get("delivered_at")),
        "read_time": format_log_clock(message.get("read_at")),
        "note": note,
        "replied": bool(phone_key and phone_key in replied_keys),
    }


def campaign_recipient_rows_to_csv(rows):
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(["Contact", "Phone", "Status", "Sent", "Delivered", "Read", "Note", "Replied"])
    for row in rows:
        writer.writerow(
            [
                row.get("customer_name") or "",
                row.get("number") or "",
                row.get("status_label") or row.get("message_status") or "",
                row.get("sent_time") or "",
                row.get("delivered_time") or "",
                row.get("read_time") or "",
                row.get("note") or "",
                "Yes" if row.get("replied") else "No",
            ]
        )
    return buffer.getvalue()
