import re


def parse_email_body(text: str) -> list[dict]:
    blocks = re.split(r"(?=•?\s*基金名稱)", text)
    records = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        name_m = re.search(r"基金名稱[：:]\s*(.+?)(?:\n|\s*[&]|\s*$)", block)
        amount_m = re.search(r"申購金額[：:]\s*(?:NT?\$?\s*)?([0-9,]+)", block)
        units_m = re.search(r"單位數[：:]\s*([0-9.]+)", block)
        date_m = re.search(r"交易日期[：:]\s*(\d{4}/\d{2}/\d{2})", text)

        if name_m and amount_m:
            fund_name = name_m.group(1).strip()
            fund_name = fund_name.replace("\u2015", "-").replace("\uff0d", "-")
            fund_name = fund_name.replace("\uff21", "A").replace("\uff22", "B")
            fund_name = fund_name.replace("\u00a0", " ").strip()

            records.append({
                "fund_name": fund_name,
                "amount": int(amount_m.group(1).replace(",", "")),
                "units": float(units_m.group(1)) if units_m else 0.0,
                "date": date_m.group(1) if date_m else "",
            })

    return records
