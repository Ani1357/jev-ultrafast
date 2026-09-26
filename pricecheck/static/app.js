const $ = (id) => document.getElementById(id);
const euro = (n) => `€${n.toFixed(2).replace(".", ",")}`;
let timer = null;

function cell(text, className) {
  const td = document.createElement("td");
  if (className) td.className = className;
  td.textContent = text;
  return td;
}

function renderShops(shops) {
  if ($("shops").childElementCount) return;
  for (const shop of shops) {
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.value = shop.key;
    box.checked = true;
    label.append(box, ` ${shop.name}`);
    $("shops").append(label);
  }
}

function renderProgress(state) {
  const rows = $("rows");
  rows.replaceChildren();
  for (const [key, status] of Object.entries(state.progress)) {
    const shop = state.shops.find((s) => s.key === key);
    const tr = document.createElement("tr");
    tr.className = "missing";
    tr.append(cell(""), cell(shop ? shop.name : key), cell("…"), cell(""), cell(""), cell(""), cell(""), cell(""),
      cell(status));
    rows.append(tr);
  }
}

function renderReport(report) {
  $("unit-head").textContent = report.unit_label || "Unit price";
  const rows = $("rows");
  rows.replaceChildren();
  report.results.forEach((r, i) => {
    const b = r.best;
    const tr = document.createElement("tr");
    tr.className = b ? (i === 0 ? "best" : "") : "missing";
    const shop = cell("");
    const link = document.createElement("a");
    link.href = r.final_url || r.start_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = r.name;
    shop.append(link);
    if (!b) {
      const status = cell(r.status === "error" ? "error" : "not found");
      if (r.note) {
        const note = document.createElement("span");
        note.className = "note";
        note.textContent = r.note;
        status.append(note);
      }
      tr.append(cell(String(i + 1)), shop, cell("-"), cell("-", "n"), cell("-"), cell("-", "n"), cell("-"),
        cell("-", "n"), status);
    } else {
      tr.append(
        cell(String(i + 1)),
        shop,
        cell(b.title),
        cell(euro(b.price), "n"),
        cell(b.promo || "-", b.promo ? "promo" : ""),
        cell(euro(b.effective_price), "n"),
        cell(b.size_text || "-"),
        cell(b.unit_price == null ? "-" : `${euro(b.unit_price)}/${b.unit}`, "n"),
        cell("found"),
      );
    }
    rows.append(tr);
  });
}

async function refresh() {
  const state = await fetch("/api/state").then((r) => r.json());
  renderShops(state.shops);
  $("go").disabled = state.running;
  if (state.running) {
    $("message").textContent = `Checking ${Object.keys(state.progress).length} shops for “${state.product}”…`;
    renderProgress(state);
  } else if (state.error) {
    $("message").textContent = state.error;
  } else if (state.report) {
    const found = state.report.results.filter((r) => r.best).length;
    $("message").textContent = `“${state.report.product}”: ${found} of ${state.report.results.length} shops`;
    renderReport(state.report);
  }
  clearTimeout(timer);
  if (state.running) timer = setTimeout(refresh, 1000);
}

$("search").addEventListener("submit", async (event) => {
  event.preventDefault();
  const shops = [...$("shops").querySelectorAll("input:checked")].map((b) => b.value);
  const response = await fetch("/api/search", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Demo-Token": window.DEMO_TOKEN },
    body: JSON.stringify({ product: $("product").value, shops }),
  });
  if (!response.ok) {
    $("message").textContent = (await response.json()).error;
    return;
  }
  refresh();
});

refresh();
