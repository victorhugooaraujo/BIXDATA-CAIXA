import pytest

from caixa_inteligente.demo.checkout import CheckoutError, CheckoutStore


@pytest.fixture
def checkout(tmp_path):
    return CheckoutStore(
        tmp_path / "checkout.sqlite3",
        [
            {"sku": "a", "name": "Produto A", "price_cents": 125},
            {"sku": "b", "name": "Produto B", "price_cents": 250},
        ],
    )


def observe(checkout, session, event="one", sku="a", decision="accepted", now=100):
    return checkout.observe(session, event, "image-hash", sku, decision, now=now, ttl=10)


def test_retry_after_ack_does_not_add_another_unit_even_after_expiration(checkout):
    sale = checkout.create_session()
    observe(checkout, sale, now=100)
    first = checkout.commit("one", now=101)
    assert checkout.commit("one", now=200) == first
    receipt = checkout.receipt(sale)
    assert len(receipt["items"]) == 1
    assert receipt["total_cents"] == 125
    assert first["status"] == "acknowledged"


def test_two_identical_products_are_two_physical_units(checkout):
    sale = checkout.create_session()
    for event in ("first", "second"):
        observe(checkout, sale, event)
        checkout.commit(event, now=101)
    assert checkout.receipt(sale)["total_cents"] == 250
    assert len(checkout.receipt(sale)["items"]) == 2


def test_expired_review_and_unknown_product_never_enter_receipt(checkout):
    sale = checkout.create_session()
    observe(checkout, sale, "expired")
    with pytest.raises(CheckoutError):
        checkout.commit("expired", now=111)
    observe(checkout, sale, "uncertain", decision="review")
    with pytest.raises(CheckoutError):
        checkout.commit("uncertain", now=101)
    with pytest.raises(CheckoutError):
        observe(checkout, sale, "invented", sku="missing")
    assert checkout.receipt(sale)["total_cents"] == 0


def test_manual_confirmation_is_explicit_and_uses_authoritative_demo_catalog(checkout):
    sale = checkout.create_session()
    observe(checkout, sale, decision="review")
    ack = checkout.commit("one", sku="b", operator_confirmed=True, now=101)
    assert ack["sku"] == "b"
    assert checkout.receipt(sale)["total_cents"] == 250


def test_reusing_event_with_different_payload_or_session_is_a_conflict(checkout):
    sale = checkout.create_session()
    observe(checkout, sale)
    with pytest.raises(CheckoutError):
        checkout.observe(sale, "one", "different-image", "a", "accepted", now=101)
    with pytest.raises(CheckoutError):
        observe(checkout, checkout.create_session())


def test_closed_sale_cannot_receive_late_result(checkout):
    sale = checkout.create_session()
    observe(checkout, sale)
    checkout.close_session(sale)
    with pytest.raises(CheckoutError):
        checkout.commit("one", now=101)
    assert checkout.receipt(sale)["items"] == []


def test_concurrent_retries_share_one_transaction(checkout):
    from concurrent.futures import ThreadPoolExecutor

    sale = checkout.create_session()
    observe(checkout, sale)
    with ThreadPoolExecutor(max_workers=4) as pool:
        acks = list(pool.map(lambda _: checkout.commit("one", now=101), range(8)))
    assert all(ack == acks[0] for ack in acks)
    assert len(checkout.receipt(sale)["items"]) == 1
