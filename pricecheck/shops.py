"""Where each shop's search starts. Data only: the browser policy stays generic."""

from urllib.parse import quote, quote_plus, urlparse

# search: a URL template for the shop's own search results, or None to start on the home page.
# The agent searches with the site's own box whenever a template is missing or does not show results.
SHOPS = [
    {"key": "ah", "name": "Albert Heijn", "home": "https://www.ah.nl/", "search": "https://www.ah.nl/zoeken?query={q}"},
    {"key": "dirk", "name": "Dirk", "home": "https://www.dirk.nl/", "search": "https://www.dirk.nl/zoeken/producten/{p}"},
    {
        "key": "kruidvat",
        "name": "Kruidvat",
        "home": "https://www.kruidvat.nl/",
        "search": "https://www.kruidvat.nl/search?q={q}&text={q}",
    },
    {
        "key": "jumbo",
        "name": "Jumbo",
        "home": "https://www.jumbo.com/",
        "search": "https://www.jumbo.com/producten/?searchTerms={q}",
    },
    {"key": "lidl", "name": "Lidl", "home": "https://www.lidl.nl/", "search": "https://www.lidl.nl/q/search?q={q}"},
    {"key": "aldi", "name": "Aldi", "home": "https://www.aldi.nl/", "search": "https://www.aldi.nl/zoeken.html?query={q}"},
    {
        "key": "bol",
        "name": "bol",
        "home": "https://www.bol.com/nl/nl/",
        "search": "https://www.bol.com/nl/nl/s/?searchtext={q}",
    },
    {"key": "etos", "name": "Etos", "home": "https://www.etos.nl/", "search": "https://www.etos.nl/search/?q={q}"},
    {"key": "hema", "name": "HEMA", "home": "https://www.hema.nl/", "search": "https://www.hema.nl/search?q={q}"},
    {"key": "amazon", "name": "Amazon.nl", "home": "https://www.amazon.nl/", "search": "https://www.amazon.nl/s?k={q}"},
]
BY_KEY = {shop["key"]: shop for shop in SHOPS}


def start_url(shop, product):
    """{q} is a query-string value, {p} a path segment."""
    if not shop.get("search"):
        return shop["home"]
    return shop["search"].format(q=quote_plus(product), p=quote(product, safe=""))


def host_allowed(shop, url):
    host = urlparse(url).hostname or ""
    root = urlparse(shop["home"]).hostname.removeprefix("www.")
    return host == root or host.endswith("." + root)
