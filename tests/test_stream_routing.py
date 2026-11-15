from stream.common import DRIVER_BINDINGS, build_ride_message, routing_key, topic_matches


def test_exact_and_wildcard_matches():
    assert topic_matches("bangalore.koramangala.ride", "bangalore.koramangala.ride")
    assert topic_matches("bangalore.koramangala.*", "bangalore.koramangala.food")
    assert not topic_matches("bangalore.koramangala.*", "bangalore.indiranagar.food")
    assert topic_matches("bangalore.*.ride", "bangalore.whitefield.ride")
    assert not topic_matches("bangalore.*.ride", "bangalore.whitefield.food")


def test_hash_matches_zero_or_more_segments():
    assert topic_matches("bangalore.#", "bangalore.koramangala.ride")
    assert topic_matches("bangalore.#", "bangalore")
    assert not topic_matches("bangalore.#", "chennai.tnagar.food")
    assert topic_matches("freshcart.order.#", "freshcart.order.web")
    assert topic_matches("freshcart.order.#", "freshcart.order")


def test_driver_binding_examples():
    assert topic_matches(DRIVER_BINDINGS["Ravi"], "bangalore.koramangala.ride")
    assert topic_matches(DRIVER_BINDINGS["Priya"], "bangalore.indiranagar.food")
    assert topic_matches(DRIVER_BINDINGS["Arjun"], "bangalore.jayanagar.ride")
    assert not topic_matches(DRIVER_BINDINGS["Arjun"], "bangalore.jayanagar.food")
    assert topic_matches(DRIVER_BINDINGS["Meena"], "bangalore.whitefield.food")
    assert topic_matches(DRIVER_BINDINGS["Karthik"], "chennai.tnagar.food")
    assert not topic_matches(DRIVER_BINDINGS["Karthik"], "chennai.adyar.food")
    assert topic_matches(DRIVER_BINDINGS["Control"], "bangalore.jayanagar.food")


def test_missing_zone_message_still_has_routing_key():
    key = routing_key("bangalore", "koramangala", "ride")
    message = build_ride_message("bangalore", "koramangala", "ride", 10, omit_zone=True)
    assert key == "bangalore.koramangala.ride"
    assert "zone" not in message
