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
