"""CSV exports built from the same report data the screen shows. Amounts are whole TZS."""
import csv
import io
from datetime import datetime

from ..domain.clock import LOCAL_TZ, as_utc
from ..models import Order

LABELS = {
    "en": {
        "report": "Launder report", "laundry": "Laundry", "branch": "Branch", "period": "Period", "generated": "Generated",
        "section": "Section", "metric": "Metric", "value": "Value", "previous": "Previous period", "change": "Change %",
        "summary": "Summary", "money": "Money", "payments": "Payments", "sources": "Order sources", "operations": "Operations",
        "customers": "Customers", "marketplace": "Marketplace", "day_book": "Orders", "daily": "By day", "services": "Services",
        "top_customers": "Top customers", "date": "Date", "orders": "Orders", "sales": "Sales (TZS)", "collected": "Collected (TZS)",
        "name": "Name", "phone": "Phone", "spend": "Spend (TZS)", "revenue": "Revenue (TZS)", "quantity": "Quantity",
        "kinds": {"daily": "End of day report", "weekly": "Weekly performance", "monthly": "Monthly business report",
                  "sales": "Sales report", "orders": "Orders report", "customers": "Customers report",
                  "marketplace": "Marketplace report", "payments": "Payments report"},
    },
    "sw": {
        "report": "Ripoti ya Launder", "laundry": "Dobi", "branch": "Tawi", "period": "Kipindi", "generated": "Imetolewa",
        "section": "Sehemu", "metric": "Kipimo", "value": "Thamani", "previous": "Kipindi kilichopita", "change": "Mabadiliko %",
        "summary": "Muhtasari", "money": "Fedha", "payments": "Malipo", "sources": "Vyanzo vya oda", "operations": "Uendeshaji",
        "customers": "Wateja", "marketplace": "Soko la Launder", "day_book": "Oda", "daily": "Kwa siku", "services": "Huduma",
        "top_customers": "Wateja wakubwa", "date": "Tarehe", "orders": "Oda", "sales": "Mauzo (TZS)",
        "collected": "Yaliyokusanywa (TZS)", "name": "Jina", "phone": "Simu", "spend": "Matumizi (TZS)",
        "revenue": "Mapato (TZS)", "quantity": "Idadi",
        "kinds": {"daily": "Ripoti ya mwisho wa siku", "weekly": "Utendaji wa wiki", "monthly": "Ripoti ya biashara ya mwezi",
                  "sales": "Ripoti ya mauzo", "orders": "Ripoti ya oda", "customers": "Ripoti ya wateja",
                  "marketplace": "Ripoti ya Soko", "payments": "Ripoti ya malipo"},
    },
}


def _local(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return as_utc(value).astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")


def _header(w, data: dict, title: str, lang: str) -> None:
    t = LABELS[lang]
    period = data["period"]
    w.writerow([title])
    w.writerow([t["laundry"], data["business"]["name"]])
    w.writerow([t["branch"], data["business"]["branch"]])
    w.writerow([t["period"], f'{period["start_date"]} – {period["end_date"]}'])
    w.writerow([t["generated"], _local(data["generated_at"])])
    w.writerow([])


def report_csv(data: dict, lang: str = "en") -> str:
    t = LABELS[lang if lang in LABELS else "en"]
    out = io.StringIO()
    w = csv.writer(out)
    _header(w, data, t["kinds"][data["kind"]], lang if lang in LABELS else "en")
    w.writerow([t["section"], t["metric"], t["value"], t["previous"], t["change"]])
    for key, value in data["summary"].items():
        if isinstance(value, dict) and "value" in value:
            w.writerow([t["summary"], key, value["value"], value["previous"] if value["previous"] is not None else "",
                        value["change_pct"] if value["change_pct"] is not None else ""])
    for section in ("money", "operations", "customers", "marketplace", "day_book"):
        if section not in data["sections"] and section != "money":
            continue
        for key, value in (data.get(section) or {}).items():
            if isinstance(value, dict):
                for sub, v in value.items():
                    w.writerow([t[section], f"{key}.{sub}", v])
            elif not isinstance(value, list):
                w.writerow([t[section], key, "" if value is None else value])
    if "payments" in data["sections"]:
        for method, v in data["payments"].items():
            w.writerow([t["payments"], method, v["amount"], "", ""])
    if "sources" in data["sections"]:
        for s in data["sources"]:
            w.writerow([t["sources"], s["source"], s["orders"], s["sales"], ""])
    if data.get("daily"):
        w.writerow([])
        w.writerow([t["date"], t["orders"], t["sales"], t["collected"]])
        for d in data["daily"]:
            w.writerow([d["date"], d["orders"], d["sales"], d["collected"]])
    if "services" in data["sections"]:
        w.writerow([])
        w.writerow([t["services"], t["orders"], t["quantity"], t["revenue"]])
        for s in data["services"]["by_revenue"]:
            w.writerow([s["name"], s["orders"], s["quantity"], s["revenue"]])
    if data.get("top_customers"):
        w.writerow([])
        w.writerow([t["top_customers"], t["phone"], t["orders"], t["spend"]])
        for c in data["top_customers"]:
            w.writerow([c["name"], c["phone"], c["orders"], c["spend"]])
    return out.getvalue()


ORDER_COLUMNS = ["Order", "Created", "Customer", "Phone", "Source", "Status", "Fulfilment", "Due", "Ready", "Payment status",
                 "Payment method", "Subtotal TZS", "Delivery fee TZS", "Discount TZS", "Total TZS", "Items"]


def orders_csv(orders: list[Order], business_name: str, branch: str, filters: dict, generated_at: datetime) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Launder orders export"])
    w.writerow(["Laundry", business_name])
    w.writerow(["Branch", branch])
    w.writerow(["Filters", "; ".join(f"{k}={v}" for k, v in filters.items() if v) or "all orders"])
    w.writerow(["Generated", _local(generated_at)])
    w.writerow([])
    w.writerow(ORDER_COLUMNS)
    for o in orders:
        items = ", ".join(f'{float(i.quantity):g}{" kg" if i.pricing_model == "PER_KG" else "×"} {i.name}' for i in o.items)
        w.writerow([o.order_number, _local(o.created_at), o.customer.name, o.customer.phone, o.source, o.status, o.fulfillment,
                    _local(o.due_at), _local(o.ready_at), o.payment_status, o.payment_method, o.subtotal, o.delivery_fee,
                    o.discount, o.total, items])
    return out.getvalue()
