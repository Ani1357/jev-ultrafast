"""Offline price-comparison contracts. Synthetic 'Nutrilon 3' pages; prices are invented, not observed."""

import json
from unittest.mock import Mock

import pytest

from pricecheck import compare as cmp
from pricecheck import extract, web
from pricecheck.prices import matches_query, parse_price, parse_promo, parse_size, price_in_text
from pricecheck.shops import BY_KEY, SHOPS, host_allowed, start_url


@pytest.mark.parametrize(
    "text, value",
    [("€ 17,99", 17.99), ("17.99", 17.99), ("2,-", 2.0), ("1.299,00", 1299.0), ("17 99", 17.99), ("gratis", None)],
)
def test_dutch_prices(text, value):
    assert parse_price(text) == value


@pytest.mark.parametrize(
    "text, size",
    [("800 g", (0.8, "kg")), ("6 x 200 ml", (1.2, "l")), ("0,8 kg", (0.8, "kg")), ("1 liter", (1.0, "l")),
     ("Nutrilon 3 Dreumesmelk 800g", (0.8, "kg")), ("per stuk", None)],
)
def test_sizes_normalize_to_base_units(text, size):
    assert parse_size(text) == size


@pytest.mark.parametrize(
    "promo, kind, per_item",
    [
        ("1+1 gratis", "1+1 gratis", 10.0),
        ("2e gratis", "1+1 gratis", 10.0),
        ("2+1 gratis", "2+1 gratis", 20 * 2 / 3),
        ("2e halve prijs", "2e halve prijs", 15.0),
        ("2 voor 30,00", "2 voor €30.00", 15.0),
        ("3 halen, 2 betalen", "3 halen 2 betalen", 20 * 2 / 3),
        ("2e artikel 50% korting", "2e 50% korting", 15.0),
        ("25% korting", "25% korting", 20.0),
        (None, None, 20.0),
    ],
)
def test_multibuy_promotions_give_one_item_price(promo, kind, per_item):
    assert parse_promo(promo, 20.0) == (kind, pytest.approx(per_item))


def test_grounding_and_query_matching():
    assert price_in_text(17.99, "Nutrilon 3\n17\n99")
    assert not price_in_text(17.99, "117,99")
    assert not price_in_text(2.0, "2,50")
    assert price_in_text(2.0, "nu 2,-") and price_in_text(2.0, "€ 2") and not price_in_text(1.0, "1+1 gratis")
    assert matches_query("Nutrilon 3", "Nutrilon Dreumesmelk 3 800 g")
    assert not matches_query("Nutrilon 3", "Nutrilon Groeimelk 4 800 g")


def test_every_shop_has_a_search_url_on_its_own_domain():
    assert len(SHOPS) == 10
    for shop in SHOPS:
        url = start_url(shop, "Nutrilon 3")
        assert "Nutrilon" in url and host_allowed(shop, url)
    assert start_url(BY_KEY["dirk"], "Nutrilon 3").endswith("/Nutrilon%203")
    assert not host_allowed(BY_KEY["ah"], "https://evil-ah.nl.example/")


def shop_page(url, text, labels=()):
    return {
        "url": url,
        "title": "Zoeken",
        "text": text,
        "actions": [{"id": f"e{i}", "kind": "click", "label": label} for i, label in enumerate(labels)],
    }


def llm(products):
    return Mock(return_value=(json.dumps({"products": products}), {"model": "test", "latency_ms": 1}))


def test_extraction_verifies_every_offer(monkeypatch):
    page = shop_page(
        "https://www.ah.nl/zoeken?query=Nutrilon+3",
        "Nutrilon Dreumesmelk 3 800 g\n1+1 gratis\n21\n49\nNutrilon Groeimelk 4 800 g\n20\n99",
    )
    monkeypatch.setattr(
        extract,
        "text_completion",
        llm(
            [
                {"title": "Nutrilon Dreumesmelk 3", "price": "21.49", "size": "800 g", "promo": "1+1 gratis"},
                {"title": "Nutrilon Groeimelk 4", "price": "20.99", "size": "800 g"},
                {"title": "Nutrilon Dreumesmelk 3 invented", "price": "1.00", "size": "800 g"},
                "junk",
                {"title": "Nutrilon 3", "price": {"value": 1}},
            ]
        ),
    )
    offers, _ = extract.extract_offers("Nutrilon 3", page)
    assert len(offers) == 3
    good, other, invented = offers
    assert good["verified"] and good["effective_price"] == pytest.approx(10.745)
    assert good["unit_price"] == pytest.approx(10.745 / 0.8) and good["unit"] == "kg"
    assert not other["verified"] and not other["checks"]["matches_query"]
    assert not invented["verified"] and not invented["checks"]["price_on_page"]


@pytest.mark.parametrize("content", ["not json", '{"items": []}', '{"products": {}}', None])
def test_invalid_extraction_reports_no_prices(monkeypatch, content):
    monkeypatch.setattr(extract, "text_completion", Mock(return_value=(content, {})))
    with pytest.raises(ValueError, match="no prices"):
        extract.extract_offers("Nutrilon 3", shop_page("https://www.ah.nl/", "x"))


class FakeAgent:
    """Replays one final page. Records how the shop was started."""

    pages = {}
    started = []

    def __init__(self, url, goal):
        self.url, self.goal = url, goal
        FakeAgent.started.append((url, goal))
        page, self.status, self.error = FakeAgent.pages[url.split("/")[2]]
        self.state = {"page": page, "history": [], "decisions": [{}], "text_calls": [], "elapsed_ms": 5,
                      "status": "ready"}
        self.closed = False

    def run(self):
        self.state["history"].append({"action": "Weigeren"})
        yield self.state
        if self.error:
            raise self.error
        self.state["status"] = self.status
        yield self.state

    def snapshot(self):
        return self.state

    def close(self):
        self.closed = True


PRODUCTS = {
    "www.ah.nl": [{"title": "Nutrilon Dreumesmelk 3", "price": "21,49", "size": "800 g", "promo": "1+1 gratis"}],
    "www.jumbo.com": [
        {"title": "Nutrilon Dreumesmelk 3 vloeibaar", "price": "3,49", "size": "1 liter"},
        {"title": "Nutrilon Dreumesmelk 3", "price": "19,99", "size": "800 g"},
    ],
    "www.kruidvat.nl": [{"title": "Nutrilon 3 Dreumesmelk", "price": "18,99", "size": "800 g",
                         "promo": "2e halve prijs"}],
    "www.bol.com": [{"title": "Nutrilon 3 Dreumesmelk", "price": "18,50"}],
    "www.amazon.nl": [{"title": "Nutrilon 3 Dreumesmelk", "price": "17,00", "size": "800 g"}],
}


@pytest.fixture
def shops(monkeypatch):
    FakeAgent.started = []

    def page(host, text):
        return shop_page(f"https://{host}/zoeken", text)

    FakeAgent.pages = {
        "www.ah.nl": (page("www.ah.nl", "Nutrilon Dreumesmelk 3 800 g 1+1 gratis 21,49"), "done", None),
        "www.jumbo.com": (
            page("www.jumbo.com", "Nutrilon Dreumesmelk 3 vloeibaar 1 liter 3,49\nNutrilon Dreumesmelk 3 800 g 19,99"),
            "done",
            None,
        ),
        "www.kruidvat.nl": (page("www.kruidvat.nl", "Nutrilon 3 Dreumesmelk 800 g 18,99 2e halve prijs"), "done",
                            RuntimeError("Reached the demo's model-call budget")),
        "www.bol.com": (page("www.bol.com", "Nutrilon 3 Dreumesmelk € 18,50"), "done", None),
        "www.amazon.nl": (page("www.amazon.nl", "Robot check"), "blocked", None),
        "www.lidl.nl": (page("www.lidl.nl", "Geen resultaten"), "done", None),
        "www.aldi.nl": (shop_page("https://accounts.example/login", "Login"), "done", None),
    }

    def fake_extract(product, page):
        products = PRODUCTS.get(page["url"].split("/")[2], [])
        return [extract.build_offer(product, p, extract.page_evidence(page)) for p in products], {
            "model": "test",
            "latency_ms": 1,
        }

    monkeypatch.setattr(cmp, "extract_offers", fake_extract)
    return [BY_KEY[k] for k in ("ah", "jumbo", "kruidvat", "bol", "amazon", "lidl", "aldi")]


def test_compare_ranks_by_promo_adjusted_unit_price(shops):
    report = cmp.compare("Nutrilon 3", shops, parallel=3, agent_factory=FakeAgent)
    assert report["unit"] == "kg"
    rows = {r["shop"]: r for r in report["results"]}
    order = [r["shop"] for r in report["results"]]
    # AH 1+1: 10.745/item; Kruidvat 2e halve prijs: 14.2425; Jumbo picks its powder, not the liquid.
    assert order[:3] == ["ah", "kruidvat", "jumbo"]
    assert rows["jumbo"]["best"]["unit"] == "kg"
    assert rows["ah"]["best"]["promo"] == "1+1 gratis"
    assert rows["kruidvat"]["status"] == "found" and "budget" in rows["kruidvat"]["note"]
    # No size: after sized offers. Unverified or missing results: "not found", never guessed.
    assert order[3] == "bol"
    assert rows["amazon"]["status"] == "not found"  # extraction found nothing verifiable
    assert rows["lidl"]["status"] == "not found"
    assert rows["aldi"]["status"] == "not found" and "Left the shop" in rows["aldi"]["note"]
    goal = FakeAgent.started[0][1]
    assert "Nutrilon 3" in goal and "ah.nl" not in goal.lower()
    assert {g for _, g in FakeAgent.started} == {goal}  # one generic goal for every shop
    table = cmp.table(report)
    assert table.splitlines()[2].split()[1] == "Albert"
    assert "not found" in table


def test_one_failing_shop_becomes_an_error_row():
    def broken(url, goal):
        raise RuntimeError("Chrome is not connected")

    row = cmp.run_shop(BY_KEY["hema"], "Nutrilon 3", agent_factory=broken)
    assert row["status"] == "error" and "Chrome" in row["note"] and row["best"] is None


def test_web_search_validates_input_and_runs_once():
    runner = Mock(return_value={"product": "Nutrilon 3", "results": []})
    for bad in [{"product": ""}, {"product": "x" * 121}, {"product": "a", "shops": ["nope"]}, []]:
        with pytest.raises(ValueError):
            web.start(bad, runner)
    web.STATE["running"] = True
    with pytest.raises(ValueError, match="already running"):
        web.start({"product": "Nutrilon 3"}, runner)
    web.STATE["running"] = False
    web.search("Nutrilon 3", [BY_KEY["ah"]], runner)
    assert web.public_state()["report"]["product"] == "Nutrilon 3"
    assert not web.public_state()["running"]
