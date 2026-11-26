from fund_parser import parse_email_body


def single_purchase(name: str, amount: str, units: str, date: str) -> str:
    return (
        "LINE Bank Taiwan &nbsp; &nbsp; LINE Bank 基金申購完成通知 &nbsp; &nbsp; "
        f"您在 {date} 單筆申購{name} {amount} TWD 已交易完成， "
        "詳細內容請參閱附件交易確認書。 "
        "&bull;&nbsp;&nbsp;交易類型：單筆申購 "
        f"&bull;&nbsp;&nbsp;交易日期：{date} "
        f"&bull;&nbsp;&nbsp;基金名稱：{name} "
        f"&bull;&nbsp;&nbsp;申購金額： {amount} TWD "
        "&bull;&nbsp;&nbsp;申購手續費： 0 TWD "
        f"&bull;&nbsp;&nbsp;單位數：{units} "
        "注意事項及聲明: 本電子郵件之內容僅供指定之收件人使用。"
    )


def regular_purchase(name: str, amount: str, units: str, date: str) -> str:
    return (
        "LINE Bank Taiwan &nbsp; &nbsp; LINE Bank 基金定期定額申購完成通知 &nbsp; &nbsp; "
        f"您{date} 定期定額申購{name} 已交易完成， "
        "詳細內容請參閱附件交易確認書。 "
        "&bull;&nbsp;&nbsp;交易類型：定期定額 "
        f"&bull;&nbsp;&nbsp;交易日期：{date} "
        f"&bull;&nbsp;&nbsp;基金名稱：{name} "
        f"&bull;&nbsp;&nbsp;投資本金：{amount} TWD "
        "&bull;&nbsp;&nbsp;申購手續費：0 TWD "
        f"&bull;&nbsp;&nbsp;單位數：{units}"
    )


def redemption(name: str, units: str, amount: str | None, date: str) -> str:
    amount_part = f"&bull;&nbsp;&nbsp;贖回金額：{amount} TWD " if amount else ""
    return (
        "LINE Bank Taiwan &nbsp; &nbsp; LINE Bank 基金贖回款入帳完成通知 &nbsp; &nbsp; "
        f"您在{date} 贖回{name} ， 交易已完成， "
        "&bull;&nbsp;&nbsp;交易類型：贖回 "
        f"&bull;&nbsp;&nbsp;交易日期：{date} "
        f"&bull;&nbsp;&nbsp;基金名稱：{name} "
        f"&bull;&nbsp;&nbsp;贖回單位數：{units} "
        "&bull;&nbsp;&nbsp;贖回手續費：0 TWD "
        "&bull;&nbsp;&nbsp;信託管理費：0 TWD "
        f"{amount_part}"
        "注意事項及聲明: 本電子郵件之內容僅供指定之收件人使用。"
    )


def test_single_purchase_fullwidth_name():
    recs = parse_email_body(single_purchase("測試基金－Ａ類型", "10,000", "53", "2026/05/29"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "測試基金-A類型"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 53.0
    assert recs[0]["date"] == "2026/05/29"


def test_single_purchase_ascii_name():
    recs = parse_email_body(single_purchase("範例科技基金", "10,000", "12.4", "2026/06/29"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "範例科技基金"
    assert recs[0]["amount"] == 10000
    assert recs[0]["units"] == 12.4


def test_single_purchase_name_with_dash_suffix():
    recs = parse_email_body(single_purchase("範例大壩基金-A類型-新臺幣", "10,000", "37.2", "2026/07/31"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "範例大壩基金-A類型-新臺幣"


def test_regular_purchase_parses_investment_principal():
    recs = parse_email_body(regular_purchase("範例大壩基金-A類型-新臺幣", "1,000", "3.2", "2026/08/05"))
    assert len(recs) == 1
    assert recs[0]["fund_name"] == "範例大壩基金-A類型-新臺幣"
    assert recs[0]["amount"] == 1000
    assert recs[0]["units"] == 3.2
    assert recs[0]["date"] == "2026/08/05"


def test_regular_purchase_units_without_decimal():
    recs = parse_email_body(regular_purchase("範例基金", "1,000", "4", "2026/11/16"))
    assert recs[0]["units"] == 4.0


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


def test_buy_record_has_type():
    recs = parse_email_body(single_purchase("範例基金", "10,000", "53", "2026/05/29"))
    assert recs[0]["type"] == "buy"


def test_redeem_parses_units_and_amount():
    recs = parse_email_body(redemption("測試基金－Ａ類型", "123.4", "45,000", "2026/11/23"))
    assert len(recs) == 1
    assert recs[0]["type"] == "redeem"
    assert recs[0]["fund_name"] == "測試基金-A類型"
    assert recs[0]["units"] == 123.4
    assert recs[0]["amount"] == 45000
    assert recs[0]["date"] == "2026/11/23"


def test_redeem_without_amount_parses_units():
    recs = parse_email_body(redemption("測試基金", "0.5", None, "2026/11/18"))
    assert len(recs) == 1
    assert recs[0]["type"] == "redeem"
    assert recs[0]["units"] == 0.5
    assert recs[0]["amount"] == 0
    assert recs[0]["date"] == "2026/11/18"
