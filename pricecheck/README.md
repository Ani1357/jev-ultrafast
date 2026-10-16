# Price Check NL

Compare one product's price across Albert Heijn, Dirk, Kruidvat, Jumbo, Lidl, Aldi, bol, Etos, HEMA and Amazon.nl.
Results are sorted by unit price (€/kg, €/l or €/stuk).

```bash
uv sync
cp .env.example .env            # TYPESAFE_API_KEY and TEXT_MODEL_API_KEY
uv run pricecheck "Nutrilon 3"                  # CLI table + artifacts/pricecheck/nutrilon-3/report.json
uv run pricecheck "Nutrilon 3" --shops ah,jumbo # a subset
uv run pricecheck-web                           # http://127.0.0.1:8767 (or see Docker below)
```

Chrome connects through Browser Harness, as in the main README. Every run makes paid TypeSafe and text-model calls.

## Docker

The image has its own Chromium, so you don't need a local Chrome.

```bash
cp .env.example .env            # TYPESAFE_API_KEY, TEXT_MODEL_API_KEY, optional PRICECHECK_PASSWORD
docker compose up -d --build    # web page on http://localhost:8767
docker compose run --rm pricecheck pricecheck "Nutrilon 3" --shops ah,jumbo   # CLI
```

- Chromium runs headed on a virtual display (Xvfb), because some shops refuse headless Chrome. Set
  `CHROME_HEADLESS=1` for a lighter headless browser. DevTools listens only on the container's loopback.
- Reports and Chrome's profile (cookie-consent choices) persist in the `pricecheck-data` volume under `/data`.
- Compose publishes the port on `127.0.0.1` only. **Before exposing it elsewhere**, set `PRICECHECK_PASSWORD`
  (HTTP Basic auth, any user name; every search costs model calls), put HTTPS in front, and add the public
  host to `PRICECHECK_ALLOWED_HOSTS`, e.g. `localhost:8767,prices.example.nl`. Requests with any other Host
  header are refused.
- Chromium runs with `--no-sandbox` as an unprivileged user, the usual setup in containers. The container is
  the isolation boundary, so don't mount anything sensitive into it.
- Running shops from a data-centre IP gets more bot checks than a home connection. Those shops show up as
  **not found**.

## How it works

1. **Start on the shop's search page** (`shops.py`: one URL template per shop, data only).
2. **One generic goal for every shop** (`compare.py`): close cookie/consent dialogs, search with the site's box if
   results aren't shown, stop when priced results are visible, never add to cart or log in. There are no per-shop
   steps. By default 3 shops run in parallel, each in its own tab, with 12 actions and 90 s each.
3. **Extract** (`extract.py`): the text model copies title, price, size and promo text from the final page's
   visible text and link names. It never calculates.
4. **Verify**: an offer counts only if its price is written on the page, its title is on the page, every
   word and number of the query is in its title ("Nutrilon 4" never matches "Nutrilon 3"), and the page is on the shop's
   own domain. Anything else is shown as **not found**. A `DONE` from the agent is not evidence.
5. **Calculate** (`prices.py`, deterministic): promotions become a price per item: `1+1`/`2e gratis` → ½,
   `2+1` → ⅔, `2e halve prijs` → ¾, `2 voor €X` → X/2, `3 halen 2 betalen` → ⅔. Percentage and "bonus" labels are
   assumed to be included in the price already. Size is normalized, so `6 x 200 ml` becomes 1.2 l.
6. **Rank**: the most common unit across shops is the comparison unit, and each shop contributes its cheapest
   verified offer in that unit. Offers without a size come after sized offers, and then not-found shops.

## Status and limits

- **Not yet run live.** The shop URL templates come from the sites' public search pages but haven't been
  checked in a real browser. The first live test product is `Nutrilon 3`. If a template stops working, the agent
  falls back to the site's search box.
- Offline tests (`tests/test_pricecheck.py`) use synthetic pages with invented prices.
- Only the first screen of results is read. Membership prices (Lidl Plus, bonus card), delivery costs and
  marketplace sellers are not modelled; the promo text is shown as written.
- Bot checks and captcha pages end as **not found** with a note.
