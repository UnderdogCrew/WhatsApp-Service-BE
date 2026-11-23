"""
Helpers that build the extra sections returned by the `/dashboard/data` API.

Every section is computed defensively: a failure in one section (for example a
Meta Graph API error) never breaks the whole dashboard response, it only
returns that section's empty defaults.
"""
import datetime
import logging

import pytz
import requests

from whatsapp_apis.views import customer_display_name, find_customer_by_phone

GRAPH_API_BASE = "https://graph.facebook.com/v23.0"
KOLKATA_TZ = pytz.timezone("Asia/Kolkata")

# Statuses stored in `whatsapp_message_logs.message_status`
INBOUND_STATUSES = ["received"]
FAILED_STATUSES = ["failed", "error"]

RECOMMENDED_CREDIT_BUFFER = 150
LOW_BALANCE_THRESHOLD = 100

MESSAGING_LIMIT_BY_TIER = {
    "TIER_50": 50,
    "TIER_250": 250,
    "TIER_1K": 1000,
    "TIER_2K": 2000,
    "TIER_10K": 10000,
    "TIER_100K": 100000,
    "TIER_UNLIMITED": None,
}

CATEGORY_ORDER = ["MARKETING", "UTILITY", "AUTHENTICATION", "SERVICE"]

# Template names written by the webhook for inbound / free-form messages.
NON_TEMPLATE_NAMES = {
    "", "template_name", "contacts", "interactive", "text",
    "video", "image", "audio", "document",
}


def _safe_float(value, default=0.0):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return default


def _log_date_filter(start_ts, end_ts):
    """`created_at` is stored as a naive server-local datetime (datetime.now())."""
    return {
        "$gte": datetime.datetime.fromtimestamp(start_ts),
        "$lte": datetime.datetime.fromtimestamp(end_ts),
    }


def _ist_date_key(unix_ts):
    return datetime.datetime.fromtimestamp(int(unix_ts), KOLKATA_TZ).strftime("%Y-%m-%d")


def _graph_get(url, api_key, params=None):
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            params=params,
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        logging.warning(f"Graph API {url} failed: {response.status_code} {response.text}")
    except Exception as ex:
        logging.warning(f"Graph API {url} error: {ex}")
    return None


# ---------------------------------------------------------------------------
# Meta data
# ---------------------------------------------------------------------------
def fetch_meta_templates(db, user_id, waba_id, api_key):
    """Return a list of {name, status, category, quality} from Meta, falling back to the local DB."""
    templates = []
    if waba_id and api_key:
        url = f"{GRAPH_API_BASE}/{waba_id}/message_templates"
        params = {"fields": "name,status,category,quality_score", "limit": 250}
        while url:
            payload = _graph_get(url, api_key, params)
            if not payload:
                break
            for item in payload.get("data", []):
                templates.append({
                    "name": item.get("name", ""),
                    "status": str(item.get("status", "")).upper(),
                    "category": str(item.get("category", "")).upper(),
                    "quality": str((item.get("quality_score") or {}).get("score", "")).upper(),
                })
            url = (payload.get("paging") or {}).get("next")
            params = None  # the `next` url already carries the query string
            if len(templates) >= 1000:
                break

    if not templates:
        for item in db.find_documents("whatsapp_templates", {"user_id": user_id}) or []:
            templates.append({
                "name": item.get("name", ""),
                "status": str(item.get("status", "")).upper(),
                "category": str(item.get("category", "")).upper(),
                "quality": "",
            })
    return templates


def build_account_health(db, user_info, api_key, templates):
    phone_number_id = user_info.get("phone_number_id", "")
    phone_details = {}
    if phone_number_id and api_key:
        phone_details = _graph_get(
            f"{GRAPH_API_BASE}/{phone_number_id}",
            api_key,
            {"fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier,name_status,status"},
        ) or {}

    quality_rating = str(phone_details.get("quality_rating") or user_info.get("quality_rating") or "UNKNOWN").upper()
    tier = phone_details.get("messaging_limit_tier") or user_info.get("messaging_limit_tier") or ""

    # Keep the user document in sync so `/profile` can expose the latest values.
    sync_data = {}
    if phone_details.get("quality_rating") and phone_details["quality_rating"] != user_info.get("quality_rating"):
        sync_data["quality_rating"] = phone_details["quality_rating"]
    if phone_details.get("messaging_limit_tier") and phone_details["messaging_limit_tier"] != user_info.get("messaging_limit_tier"):
        sync_data["messaging_limit_tier"] = phone_details["messaging_limit_tier"]
    if sync_data:
        try:
            db.update_document("users", {"_id": user_info["_id"]}, sync_data)
        except Exception as ex:
            logging.warning(f"Could not sync account health for user: {ex}")

    flagged = [t for t in templates if t.get("quality") in ("RED", "YELLOW")]
    tier_label = ""
    if tier:
        tier_label = "Unlimited" if tier == "TIER_UNLIMITED" else tier.replace("TIER_", "Tier ")

    return {
        "messaging_limit_tier": tier,
        "messaging_limit_tier_label": tier_label,
        "messaging_limit": MESSAGING_LIMIT_BY_TIER.get(tier, 1000 if not tier else None),
        "quality_rating": quality_rating,  # GREEN | YELLOW | RED | UNKNOWN
        "display_phone_number": phone_details.get("display_phone_number") or user_info.get("meta_business_number", ""),
        "name_status": phone_details.get("name_status", ""),
        "phone_status": phone_details.get("status", ""),
        "flagged_templates_count": len(flagged),
        "flagged_templates": [t["name"] for t in flagged][:5],
    }


# ---------------------------------------------------------------------------
# Message-log based sections
# ---------------------------------------------------------------------------
def build_log_counts(db, user_id, start_ts, end_ts):
    """Counts from our own message logs for the selected range."""
    created = _log_date_filter(start_ts, end_ts)
    pipeline = [
        {"$match": {"user_id": user_id, "created_at": created}},
        {"$group": {
            "_id": None,
            "sent": {"$sum": {"$cond": [
                {"$not": [{"$in": ["$message_status", INBOUND_STATUSES + FAILED_STATUSES]}]}, 1, 0]}},
            "delivered": {"$sum": {"$cond": [
                {"$in": ["$message_status", ["delivered", "read"]]}, 1, 0]}},
            "read": {"$sum": {"$cond": [{"$eq": ["$message_status", "read"]}, 1, 0]}},
            "failed": {"$sum": {"$cond": [{"$in": ["$message_status", FAILED_STATUSES]}, 1, 0]}},
            "received": {"$sum": {"$cond": [{"$in": ["$message_status", INBOUND_STATUSES]}, 1, 0]}},
        }},
    ]
    result = list(db.aggregate("whatsapp_message_logs", pipeline) or [])
    counts = result[0] if result else {}

    replied_numbers = db.aggregate("whatsapp_message_logs", [
        {"$match": {"user_id": user_id, "created_at": created, "message_status": {"$in": INBOUND_STATUSES}}},
        {"$group": {"_id": "$number"}},
        {"$count": "total"},
    ]) or []
    replied_numbers = list(replied_numbers)

    return {
        "sent": int(counts.get("sent", 0)),
        "delivered": int(counts.get("delivered", 0)),
        "read": int(counts.get("read", 0)),
        "failed": int(counts.get("failed", 0)),
        "received": int(counts.get("received", 0)),
        "replied_contacts": int(replied_numbers[0]["total"]) if replied_numbers else 0,
    }


def build_daily_read_map(db, user_id, start_ts, end_ts):
    """{YYYY-MM-DD (IST): read count} using the webhook `read_at` timestamp."""
    rows = db.aggregate("whatsapp_message_logs", [
        {"$match": {
            "user_id": user_id,
            "message_status": "read",
            "read_at": {"$gte": start_ts, "$lte": end_ts},
        }},
        {"$project": {"read_at": 1}},
    ]) or []
    read_map = {}
    for row in rows:
        try:
            key = _ist_date_key(row["read_at"])
        except Exception:
            continue
        read_map[key] = read_map.get(key, 0) + 1
    return read_map


def build_funnel(sent, delivered, read, replied, failed):
    def pct(part, whole):
        return round((part / whole) * 100, 1) if whole else 0

    return {
        "sent": sent,
        "delivered": delivered,
        "read": read,
        "replied": replied,
        "failed": failed,
        "delivery_rate": min(pct(delivered, sent), 100),
        "read_rate": min(pct(read, delivered), 100),
        "reply_rate": min(pct(replied, sent), 100),
        "failure_rate": min(pct(failed, sent + failed), 100),
    }


def build_category_and_spend(db, user_id, start_ts, end_ts, templates):
    """Spend per conversation category plus top templates, from billable outbound logs."""
    category_by_template = {t["name"]: t["category"] for t in templates if t.get("name")}
    rows = db.aggregate("whatsapp_message_logs", [
        {"$match": {
            "user_id": user_id,
            "created_at": _log_date_filter(start_ts, end_ts),
            "message_status": {"$nin": INBOUND_STATUSES + FAILED_STATUSES},
        }},
        {"$group": {
            "_id": "$template_name",
            "count": {"$sum": 1},
            "cost": {"$sum": "$price"},
        }},
    ]) or []

    categories = {key: {"count": 0, "cost": 0.0} for key in CATEGORY_ORDER}
    template_usage = []
    total_cost = 0.0
    total_count = 0
    for row in rows:
        name = row.get("_id") or ""
        count = int(row.get("count", 0))
        cost = _safe_float(row.get("cost"))
        total_cost += cost
        total_count += count

        if name in NON_TEMPLATE_NAMES or name not in category_by_template:
            category = "SERVICE"
        else:
            category = category_by_template.get(name) or "SERVICE"
            if category not in categories:
                category = "SERVICE"
        categories[category]["count"] += count
        categories[category]["cost"] += cost

        if name and name not in NON_TEMPLATE_NAMES:
            template_usage.append({"name": name, "sent": count})

    category_list = []
    for key in CATEGORY_ORDER:
        cost = round(categories[key]["cost"], 2)
        category_list.append({
            "category": key,
            "label": key.title(),
            "count": categories[key]["count"],
            "cost": cost,
            "share": round((cost / total_cost) * 100, 1) if total_cost else 0,
        })

    template_usage.sort(key=lambda item: item["sent"], reverse=True)
    return {
        "categories": category_list,
        "total_cost": round(total_cost, 2),
        "billable_count": total_count,
        "top_templates": template_usage[:5],
    }


def build_template_summary(templates, top_templates):
    approved = sum(1 for t in templates if t["status"] == "APPROVED")
    pending = sum(1 for t in templates if t["status"] in ("PENDING", "IN_APPEAL", "PENDING_DELETION"))
    rejected = sum(1 for t in templates if t["status"] in ("REJECTED", "DISABLED", "PAUSED"))
    return {
        "total": len(templates),
        "approved": approved,
        "pending": pending,
        "rejected": rejected,
        "top_templates": top_templates,
    }


def build_credits(user_info, total_cost, billable_count, range_days):
    available = round(_safe_float(user_info.get("default_credit")), 2)
    days = max(int(range_days or 1), 1)
    burn = round(total_cost / days, 2) if total_cost else 0
    return {
        "available": available,
        "spent": round(total_cost, 2),
        "range_days": days,
        "avg_burn_per_day": burn,
        "cost_per_message": round(total_cost / billable_count, 2) if billable_count else 0,
        "runway_days": int(available // burn) if burn > 0 else None,
        "recommended_buffer": RECOMMENDED_CREDIT_BUFFER,
        "low_balance_threshold": LOW_BALANCE_THRESHOLD,
        "is_low_balance": available < LOW_BALANCE_THRESHOLD,
    }


def _activity_status(log):
    status = str(log.get("message_status", "")).lower()
    if status in INBOUND_STATUSES:
        return "replied"
    if status in FAILED_STATUSES:
        return "failed"
    if status in ("read", "delivered"):
        return status
    return "sent"


def build_recent_activity(db, user_id, limit=5):
    logs = db.find_documents(
        "whatsapp_message_logs",
        {"user_id": user_id},
        sort=[("updated_at", -1)],
        limit=limit,
    ) or []

    activity = []
    name_cache = {}
    for log in logs:
        number = str(log.get("number", ""))
        if number not in name_cache:
            try:
                customer = find_customer_by_phone(db, user_id, number)
            except Exception:
                customer = None
            name_cache[number] = customer_display_name(customer, fallback="")
        timestamp = log.get("updated_at") or log.get("created_at")
        template_name = log.get("template_name") or ""
        message = log.get("message") or ""
        if not isinstance(message, str):
            message = ""
        activity.append({
            "id": str(log.get("_id")),
            "name": name_cache[number],
            "number": number,
            "status": _activity_status(log),
            "template_name": "" if template_name in NON_TEMPLATE_NAMES else template_name,
            "message": message[:140],
            # Unix seconds; naive datetimes are server-local, which .timestamp() handles.
            "timestamp": int(timestamp.timestamp()) if isinstance(timestamp, datetime.datetime) else None,
        })
    return activity


def build_dashboard_insights(db, user_info, user_id, start_ts, end_ts, meta_totals, range_days):
    """
    Build all the extra dashboard sections.

    `meta_totals` holds the sent/delivered/read totals coming from the Meta
    analytics API, or None when Meta returned nothing.
    """
    api_key = user_info.get("api_key", "")
    waba_id = user_info.get("waba_id", "")
    insights = {}

    try:
        templates = fetch_meta_templates(db, user_id, waba_id, api_key)
    except Exception as ex:
        logging.warning(f"Dashboard templates failed: {ex}")
        templates = []

    try:
        log_counts = build_log_counts(db, user_id, start_ts, end_ts)
    except Exception as ex:
        logging.warning(f"Dashboard log counts failed: {ex}")
        log_counts = {"sent": 0, "delivered": 0, "read": 0, "failed": 0, "received": 0, "replied_contacts": 0}

    if meta_totals and (meta_totals.get("sent") or meta_totals.get("delivered")):
        sent = meta_totals.get("sent", 0)
        delivered = meta_totals.get("delivered", 0)
        read = max(meta_totals.get("read", 0), log_counts["read"])
    else:
        sent, delivered, read = log_counts["sent"], log_counts["delivered"], log_counts["read"]
    insights["funnel"] = build_funnel(
        sent, delivered, min(read, delivered) if delivered else read,
        log_counts["replied_contacts"], log_counts["failed"],
    )
    insights["received_count"] = log_counts["received"]

    try:
        spend = build_category_and_spend(db, user_id, start_ts, end_ts, templates)
    except Exception as ex:
        logging.warning(f"Dashboard spend failed: {ex}")
        spend = {"categories": [], "total_cost": 0, "billable_count": 0, "top_templates": []}

    insights["conversation_categories"] = {
        "total_count": sum(item["count"] for item in spend["categories"]),
        "total_cost": spend["total_cost"],
        "items": spend["categories"],
    }
    insights["templates"] = build_template_summary(templates, spend["top_templates"][:3])
    insights["credits"] = build_credits(user_info, spend["total_cost"], spend["billable_count"], range_days)

    try:
        insights["recent_activity"] = build_recent_activity(db, user_id)
    except Exception as ex:
        logging.warning(f"Dashboard recent activity failed: {ex}")
        insights["recent_activity"] = []

    try:
        insights["account_health"] = build_account_health(db, user_info, api_key, templates)
    except Exception as ex:
        logging.warning(f"Dashboard account health failed: {ex}")
        insights["account_health"] = {}

    return insights
