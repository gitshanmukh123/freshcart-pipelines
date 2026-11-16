from freshcart_data import MOCK_CRM_TIER_EVENTS
from freshcart_lib import (
    apply_b4,
    build_customer_history,
    clean_orders,
    compute_gold_orders,
    deduplicate_orders,
    expected_baseline,
)


def test_baseline_fixture_matches_reference():
    assert expected_baseline() == {
        "raw": 8,
        "clean": 8,
        "valid": 6,
        "quarantine": 2,
        "dedup": 4,
        "gold": 4,
        "amount_inr": 7785.0,
        "points": 126,
        "rejected_share": 0.25,
    }


def test_quarantine_reasons_before_b3():
    rows = {row["order_id"]: row for row in clean_orders() if not row["is_valid"]}
    assert set(rows) == {"ORD-1004", "ORD-1006"}
    assert rows["ORD-1004"]["reasons"] == ["non_positive_amount"]
    assert rows["ORD-1006"]["reasons"] == ["bad_email", "bad_pincode"]


def test_b3_adds_unsupported_currency_without_new_quarantine_row():
    rows = {
        row["order_id"]: row
        for row in clean_orders(include_unsupported=True)
        if not row["is_valid"]
    }
    assert rows["ORD-1006"]["reasons"] == [
        "bad_email",
        "bad_pincode",
        "unsupported_currency",
    ]


def test_mobile_copy_wins_dedup():
    dedup = {row["order_id"]: row for row in deduplicate_orders(clean_orders())}
    assert dedup["ORD-1002"]["source"] == "mobile"
    assert dedup["ORD-1003"]["source"] == "mobile"
    assert dedup["ORD-1003"]["amount"] == 2100.0


def test_gold_baseline_tiers_and_points():
    dedup = deduplicate_orders(clean_orders())
    gold = {row["order_id"]: row for row in compute_gold_orders(dedup)}
    assert gold["ORD-1001"]["tier"] == "Silver"
    assert gold["ORD-1001"]["amount_inr"] == 1250.0
    assert gold["ORD-1001"]["loyalty_points"] == 12
    assert gold["ORD-1002"]["tier"] == "Silver"
    assert gold["ORD-1002"]["amount_inr"] == 3536.0
    assert gold["ORD-1002"]["loyalty_points"] == 35
    assert gold["ORD-1003"]["tier"] == "Platinum"
    assert gold["ORD-1003"]["loyalty_points"] == 63
    assert gold["ORD-1005"]["tier"] == "Gold"
    assert gold["ORD-1005"]["loyalty_points"] == 16
    assert sum(row["loyalty_points"] for row in gold.values()) == 126


def test_priya_tier_changes_between_orders():
    dedup = {row["order_id"]: row for row in deduplicate_orders(clean_orders())}
    gold = {row["order_id"]: row for row in compute_gold_orders(list(dedup.values()))}
    assert gold["ORD-1001"]["tier"] == "Silver"
    assert gold["ORD-1005"]["tier"] == "Gold"


def test_b4_updates_arjun_and_total_points():
    dedup = deduplicate_orders(clean_orders())
    base = {row["order_id"]: row for row in compute_gold_orders(dedup)}
    after = {row["order_id"]: row for row in compute_gold_orders(dedup, apply_b4())}
    assert base["ORD-1002"]["tier"] == "Silver"
    assert after["ORD-1002"]["tier"] == "Gold"
    assert after["ORD-1002"]["loyalty_points"] == 70
    changed = [key for key in after if after[key] != base[key]]
    assert changed == ["ORD-1002"]
    assert sum(row["loyalty_points"] for row in after.values()) == 161


def test_b4_customer_history_has_two_arjun_versions():
    history = [row for row in build_customer_history(apply_b4()) if row["cust_id"] == "CUST-02"]
    assert [(row["tier"], row["valid_from"].isoformat(), row["valid_to"].isoformat()) for row in history] == [
        ("Silver", "2024-01-15", "2026-08-14"),
        ("Gold", "2026-08-15", "9999-12-31"),
    ]


def test_missing_amount_is_allowed():
    row = next(item for item in clean_orders() if item["order_id"] == "ORD-1003" and item["source"] == "web")
    assert row["amount"] is None
    assert row["amount_missing"] is True
    assert row["is_valid"] is True


def test_b4_event_matches_assignment():
    assert MOCK_CRM_TIER_EVENTS[2]["cust_id"] == "CUST-02"
    assert apply_b4()[-1] == {
        "cust_id": "CUST-02",
        "email": "arjun.k@yahoo.in",
        "tier": "Gold",
        "effective_from": "2026-08-15",
    }
