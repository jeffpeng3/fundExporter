from decimal import Decimal

import fund_exporter as fe


def reset(holdings: dict[str, tuple[int, float]]):
    with fe.records_lock:
        fe.records.clear()
        for name, (cost, units) in holdings.items():
            fe.records[name] = {
                "cost": cost,
                "units": Decimal(str(units)),
                "nav": Decimal(0),
                "nav_date": "",
            }


def test_redeem_only_deducts_units():
    reset({"A": (10000, 100)})
    fe._apply_records(
        [{"type": "redeem", "fund_name": "A", "amount": 5000, "units": 40.0, "date": "2026/11/23"}]
    )
    assert fe.records["A"]["units"] == Decimal("60.0")
    assert fe.records["A"]["cost"] == 10000


def test_redeem_to_zero_removes_holding():
    reset({"A": (10000, 99.4)})
    fe._apply_records(
        [{"type": "redeem", "fund_name": "A", "amount": 5503, "units": 99.4, "date": "2026/11/18"}]
    )
    assert "A" not in fe.records


def test_redeem_more_than_held_removes_holding():
    reset({"A": (10000, 10)})
    fe._apply_records(
        [{"type": "redeem", "fund_name": "A", "amount": 5503, "units": 12.5, "date": "2026/11/18"}]
    )
    assert "A" not in fe.records


def test_redeem_missing_holding_is_skipped():
    reset({})
    fe._apply_records(
        [{"type": "redeem", "fund_name": "X", "amount": 1823, "units": 0.23, "date": "2025/08/25"}]
    )
    assert fe.records == {}


def test_buy_still_adds_cost_and_units():
    reset({})
    fe._apply_records(
        [{"type": "buy", "fund_name": "A", "amount": 1000, "units": 4.2, "date": "2026/11/18"}]
    )
    assert fe.records["A"]["cost"] == 1000
    assert fe.records["A"]["units"] == Decimal("4.2")


def test_mixed_batch_applies_by_date():
    reset({"A": (10000, 100)})
    fe._apply_records([
        {"type": "buy", "fund_name": "A", "amount": 1000, "units": 10.0, "date": "2026/11/24"},
        {"type": "redeem", "fund_name": "A", "amount": 3000, "units": 30.0, "date": "2026/11/20"},
    ])
    assert fe.records["A"]["units"] == Decimal("80.0")
    assert fe.records["A"]["cost"] == 11000
