import re

BUY = "buy"
REDEEM = "redeem"


def _clean_fund_name(name: str) -> str:
    name = name.replace("\u2015", "-").replace("\uff0d", "-")
    name = name.replace("\uff21", "A").replace("\uff22", "B")
    return name.replace("\u00a0", " ").strip()


def _to_int(raw: str | None) -> int:
    return int(raw.replace(",", "")) if raw else 0


def parse_email_body(text: str) -> list[dict]:
    blocks = re.split(r"(?=•?\s*基金名稱)", text)
    records = []

    date_m = re.search(r"交易日期[：:]\s*(\d{4}/\d{2}/\d{2})", text)
    date = date_m.group(1) if date_m else ""

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        name_m = re.search(r"基金名稱[：:]\s*(.+?)(?:\n|\s*[&]|\s*$)", block)
        if not name_m:
            continue
        fund_name = _clean_fund_name(name_m.group(1))

        redeem_units_m = re.search(r"贖回單位數[：:]\s*([0-9.]+)", block)
        if redeem_units_m:
            amount_m = re.search(r"贖回金額[：:]\s*(?:NT?\$?\s*)?([0-9,]+)", block)
            records.append({
                "type": REDEEM,
                "fund_name": fund_name,
                "amount": _to_int(amount_m.group(1) if amount_m else None),
                "units": float(redeem_units_m.group(1)),
                "date": date,
            })
            continue

        amount_m = re.search(r"(?:申購金額|投資本金)[：:]\s*(?:NT?\$?\s*)?([0-9,]+)", block)
        units_m = re.search(r"單位數[：:]\s*([0-9.]+)", block)

        if amount_m:
            records.append({
                "type": BUY,
                "fund_name": fund_name,
                "amount": _to_int(amount_m.group(1)),
                "units": float(units_m.group(1)) if units_m else 0.0,
                "date": date,
            })

    return records
