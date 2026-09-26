"""Run one generic agent goal per shop, extract offers, verify them, and rank by unit price."""

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from jev_ultrafast import Agent

from .extract import extract_offers
from .prices import unit_label
from .shops import SHOPS, host_allowed, start_url

GOAL = (
    "Show this shop's search results for the product: {product}. "
    "If a cookie, consent, or location dialog covers the page, close it, declining optional cookies when offered. "
    "If results for the product are not visible, search for it with the site's own search box. "
    "Stop as soon as matching products with prices are visible. "
    "Do not add anything to a cart, log in, or open another website."
)
UNIT_ORDER = {"kg": 0, "l": 1, "stuk": 2}


def run_shop(shop, product, *, max_actions=12, timeout=90, agent_factory=Agent, on_update=None):
    """Never raises: every failure becomes a 'not found' or 'error' row with a note."""
    url = start_url(shop, product)
    result = {"shop": shop["key"], "name": shop["name"], "start_url": url, "status": "running", "offers": []}
    started = time.monotonic()
    agent = None
    try:
        agent = agent_factory(url, GOAL.format(product=product))
        stopped = None
        try:
            for state in agent.run():
                if on_update:
                    on_update({**result, "agent_status": state["status"], "actions": len(state["history"])})
                if len(state["history"]) >= max_actions or time.monotonic() - started > timeout:
                    stopped = "Stopped at the action/time budget."
                    break
        except Exception as error:  # noqa: BLE001 - the page may already show prices; verification decides
            stopped = str(error)[:300] or type(error).__name__
        state = agent.snapshot()
        page = state["page"]
        result.update(
            final_url=page["url"],
            agent={
                "status": state["status"],
                "actions": [h["action"] for h in state["history"]],
                "decisions": len(state["decisions"]),
                "text_calls": len(state["text_calls"]),
                "elapsed_ms": state["elapsed_ms"],
            },
        )
        if not host_allowed(shop, page["url"]):
            return finish(result, "not found", f"Left the shop's site ({page['url']}).")
        offers, meta = extract_offers(product, page)
        result.update(offers=offers, extraction={k: meta[k] for k in ("model", "latency_ms")})
        best = best_offer(offers)
        if best:
            return finish(result, "found", stopped, best)
        note = stopped or (
            "Agent stopped as blocked." if state["status"] == "blocked" else "No verified matching price on page."
        )
        return finish(result, "not found", note)
    except Exception as error:  # noqa: BLE001 - one shop must not stop the comparison
        return finish(result, "error", str(error)[:300] or type(error).__name__)
    finally:
        result["elapsed_s"] = round(time.monotonic() - started, 1)
        if agent is not None:
            try:
                agent.close()
            except Exception:  # noqa: BLE001
                pass


def finish(result, status, note, best=None):
    result.update(status=status, note=note, best=best)
    return result


def candidates(offers, unit=None):
    usable = [o for o in offers if o["verified"] and o["available"]]
    if unit:
        usable = [o for o in usable if o["unit"] == unit] or usable
    return usable


def best_offer(offers, unit=None):
    usable = candidates(offers, unit)
    if not usable:
        return None
    return min(usable, key=lambda o: (o["unit_price"] is None, o["unit_price"] or o["effective_price"]))


def rank(results):
    """Pick one offer per shop in the most common unit, then sort ascending by unit price."""
    units = Counter(o["unit"] for r in results for o in candidates(r["offers"]) if o["unit"])
    unit = min(units, key=lambda u: (-units[u], UNIT_ORDER[u])) if units else None
    for r in results:
        if r["status"] == "found":
            r["best"] = best_offer(r["offers"], unit)

    def key(r):
        b = r.get("best")
        if not b:
            return (3, 0, r["name"].lower())
        if b["unit_price"] is None:
            return (2, b["effective_price"], r["name"].lower())
        return (0 if b["unit"] == unit else 1, b["unit_price"], r["name"].lower())

    return sorted(results, key=key), unit


def compare(product, shops=None, *, parallel=3, max_actions=12, timeout=90, agent_factory=Agent, on_update=None):
    shops = shops or SHOPS
    if agent_factory is Agent:
        from browser_harness.admin import ensure_daemon

        ensure_daemon()  # Once, before threads open their own tabs.
    with ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
        futures = [
            pool.submit(
                run_shop,
                shop,
                product,
                max_actions=max_actions,
                timeout=timeout,
                agent_factory=agent_factory,
                on_update=on_update,
            )
            for shop in shops
        ]
        results = [f.result() for f in futures]
    rows, unit = rank(results)
    return {"product": product, "unit": unit, "unit_label": unit_label(unit) if unit else None, "results": rows}


def table(report):
    unit = report["unit_label"] or "unit price"
    header = ["#", "Shop", "Product", "Price", "Promo", "Per item", "Size", unit, "Status"]
    lines = []
    for i, r in enumerate(report["results"], 1):
        b = r.get("best")
        if b:
            per_unit = f"€{b['unit_price']:.2f}/{b['unit']}" if b["unit_price"] is not None else "-"
            lines.append(
                [
                    str(i),
                    r["name"],
                    b["title"][:48],
                    f"€{b['price']:.2f}",
                    b["promo"] or "-",
                    f"€{b['effective_price']:.2f}",
                    b["size_text"] or "-",
                    per_unit,
                    "found",
                ]
            )
        else:
            status = "error" if r["status"] == "error" else "not found"
            lines.append([str(i), r["name"], "-", "-", "-", "-", "-", "-", status])
    widths = [max(len(row[c]) for row in [header, *lines]) for c in range(len(header))]
    fmt = lambda row: "  ".join(cell.ljust(w) for cell, w in zip(row, widths))  # noqa: E731
    return "\n".join([fmt(header), fmt(["-" * w for w in widths]), *map(fmt, lines)])
