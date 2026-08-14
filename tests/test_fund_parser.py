from pathlib import Path

from fund_parser import parse_email_body

FIXTURES = Path(__file__).parent / "fixtures"


def load(uid: str) -> str:
    return (FIXTURES / f"uid{uid}.txt").read_text(encoding="utf-8")


def test_single_purchase_schroder_old():
    recs = parse_email_body(load("1"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "施羅德台灣樂活中小基金-A類型"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 53.0
    assert recs[0]["date"] == "2026/05/29"


def test_single_purchase_allianz_tech():
    recs = parse_email_body(load("5"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "安聯台灣科技基金"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 12.4
    assert recs[0]["date"] == "2026/06/29"


def test_single_purchase_allianz_dam():
    recs = parse_email_body(load("8"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "安聯台灣大壩基金-A類型-新臺幣"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 37.2
    assert recs[0]["date"] == "2026/07/31"


def test_single_purchase_schroder_recent():
    recs = parse_email_body(load("9"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "施羅德台灣樂活中小基金-A類型"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 58.1
    assert recs[0]["date"] == "2026/08/03"


def test_regular_purchase_20260806():
    recs = parse_email_body(load("10"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "安聯台灣大壩基金-A類型-新臺幣"
    assert recs[0]["amount"] == 1000
    assert recs[0]["units"] == 3.2
    assert recs[0]["date"] == "2026/08/06"


def test_regular_purchase_20260805():
    recs = parse_email_body(load("11"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "安聯台灣大壩基金-A類型-新臺幣"
    assert recs[0]["amount"] == 1000
    assert recs[0]["units"] == 3.2
    assert recs[0]["date"] == "2026/08/05"


def test_no_amount_field_returns_empty():
    body = "交易類型：定期定額 基金名稱：某基金 單位數：3.2 交易日期：2026/08/05"
    assert parse_email_body(body) == []


def test_amount_in_twd_with_symbol():
    body = (
        "基金名稱：測試基金 &bull; 申購金額： NT$5,000 TWD &bull; 單位數：20.5"
        " &bull; 交易日期：2026/08/05"
    )
    recs = parse_email_body(body)
    assert len(recs) == 1
    assert recs[0]["amount"] == 5000
    assert recs[0]["units"] == 20.5
