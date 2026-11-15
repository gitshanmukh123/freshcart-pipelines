from freshcart_data import MOCK_CRM_TIER_EVENTS, MOCK_ORDERS
from freshcart_lib import (
    apply_b4,
    clean_orders,
    compute_gold_orders,
    deduplicate_orders,
    expected_baseline,
    validate_order,
)


def test_baseline_fixture_counts_and_totals():
    assert expected_baseline() == {
        "raw": 8,
        "clean": 8,
        "valid": 6,
        "quarantine": 2,
        "dedup": 4,
        "gold": 4,
        "amount_inr": 7785.0,
        "points": 126,
    }


def test_quarantine_reasons_for_reconstructed_fixture():
    baseline = {order["order_id"]: order for order in clean_orders() if not order["is_valid"]}
    after_b3 = {
        order["order_id"]: order
        for order in clean_orders(include_unsupported=True)
        if not order["is_valid"]
    }
    assert set(baseline) == {"ORD-1004", "ORD-1006"}
    assert baseline["ORD-1004"]["validation_errors"] == ["invalid_quantity"]
    assert baseline["ORD-1006"]["validation_errors"] == ["invalid_quantity"]
    assert after_b3["ORD-1006"]["validation_errors"] == [
        "invalid_quantity",
        "unsupported_currency",
    ]


def test_later_mobile_record_wins_dedup():
    dedup = {row["order_id"]: row for row in deduplicate_orders(clean_orders())}
    assert dedup["ORD-1002"]["channel"] == "mobile_app"
    assert dedup["ORD-1003"]["channel"] == "mobile_app"
    assert dedup["ORD-1003"]["amount"] == 2100.0


def test_gold_base_tiers_and_points():
    dedup = deduplicate_orders(clean_orders())
    gold = {row["order_id"]: row for row in compute_gold_orders(dedup)}
    assert gold["ORD-1001"]["tier"] == "Silver"
    assert gold["ORD-1001"]["points_earned"] == 22
    assert gold["ORD-1002"]["tier"] == "Bronze"
    assert gold["ORD-1002"]["points_earned"] == 19
    assert gold["ORD-1003"]["tier"] == "Gold"
    assert gold["ORD-1003"]["points_earned"] == 42
    assert gold["ORD-1005"]["tier"] == "Gold"
    assert gold["ORD-1005"]["points_earned"] == 43


def test_b4_updates_only_arjun():
    dedup = deduplicate_orders(clean_orders())
    base = {row["order_id"]: row for row in compute_gold_orders(dedup)}
    after = {
        row["order_id"]: row
        for row in compute_gold_orders(dedup, apply_b4())
    }
    assert base["ORD-1002"]["tier"] == "Bronze"
    assert after["ORD-1002"]["tier"] == "Gold"
    assert after["ORD-1002"]["points_earned"] == 39
    changed = [key for key in after if after[key] != base[key]]
    assert changed == ["ORD-1002"]
    assert sum(row["points_earned"] for row in after.values()) == 146


def test_b4_crm_event_matches_pdf():
    assert MOCK_CRM_TIER_EVENTS[1]["customer_id"] == "CUST-02"
    added = apply_b4()[-1]
    assert added == {
        "event_id": "EVT-006",
        "customer_id": "CUST-02",
        "email": "arjun.k@yahoo.in",
        "tier": "Gold",
        "effective_from": "2026-08-15 00:00:00",
    }


def test_invalid_amount_rule():
    order = dict(MOCK_ORDERS[0])
    order["amount"] = "0.00"
    assert "invalid_amount" in validate_order(order)
