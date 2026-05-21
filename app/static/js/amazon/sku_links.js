function setResult(msg, type="info") {
  const el = document.getElementById("result");
  el.classList.remove("hidden");
  const base = "rounded-lg border p-3";
  if (type === "success") el.className = base + " border-green-200 bg-green-50 text-green-800";
  else if (type === "error") el.className = base + " border-red-200 bg-red-50 text-red-800";
  else el.className = base + " border-slate-200 bg-slate-50 text-slate-700";
  el.textContent = msg;
}

function productOptionsHtml() {
  return PRODUCTS.map(p => `<option value="${p.id}">${p.sku} – ${p.name}</option>`).join("");
}

async function loadMissing() {
  const res = await fetch("/integrations/amazon/sku_links/missing");
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Falha ao carregar");

  document.getElementById("missingCount").textContent = `${data.missing_count} SKUs`;

  const box = document.getElementById("missingList");
  if (data.missing.length === 0) {
    box.innerHTML = `<div class="text-green-700 font-bold">Tudo vinculado ✅</div>`;
    return;
  }

  box.innerHTML = data.missing.map(m => `
    <div class="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-3">
      <div>
        <div class="font-bold text-slate-900">${m.seller_sku}</div>
        <div class="text-xs text-slate-500">
          Ocorrências: ${m.count} ${m.asin ? `| ASIN: ${m.asin}` : ""}
        </div>
      </div>

      <div class="flex gap-2 items-center w-full sm:w-auto">
        <select class="sku-product w-full sm:w-80 rounded-lg border border-[#d0dbe7] bg-white h-10 px-3">
          <option value="">Selecione um produto...</option>
          ${productOptionsHtml()}
        </select>

        <button class="link-btn rounded-lg bg-slate-800 text-white font-bold h-10 px-4 hover:bg-slate-900"
          data-sku="${m.seller_sku}"
          data-asin="${m.asin || ""}">
          Vincular
        </button>
      </div>
    </div>
  `).join("");
}

document.addEventListener("click", async (e) => {
  const linkBtn = e.target.closest(".link-btn");
  if (linkBtn) {
    const sku = linkBtn.getAttribute("data-sku");
    const asin = linkBtn.getAttribute("data-asin") || null;

    const select = linkBtn.parentElement.querySelector(".sku-product");
    const pid = select.value;

    if (!pid) return setResult("Selecione um produto para vincular.", "error");

    const res = await fetch("/integrations/amazon/sku_links", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify({
        amazon_seller_sku: sku,
        product_id: pid,
        asin: asin
      })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) return setResult(data.error || "Falha ao vincular", "error");

    setResult("Vínculo criado com sucesso.", "success");
    setTimeout(() => location.reload(), 600);
    return;
  }

  const delBtn = e.target.closest(".del-link");
  if (delBtn) {
    const id = delBtn.getAttribute("data-id");
    const res = await fetch(`/integrations/amazon/sku_links/${id}/delete`, { method: "POST", headers: { "X-CSRFToken": csrfToken } });
    const data = await res.json();
    if (!res.ok || !data.ok) return setResult(data.error || "Falha ao remover", "error");
    setResult("Vínculo removido.", "success");
    setTimeout(() => location.reload(), 400);
  }
});

loadMissing().catch(err => setResult(err.message, "error"));

document.getElementById("btnSyncInventory")?.addEventListener("click", async () => {
  try {
    setResult("Atualizando estoque Amazon...", "info");
    const res = await fetch("/integrations/amazon/sync_inventory", { method: "POST", headers: { "X-CSRFToken": csrfToken } });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Falha ao atualizar estoque");
    setResult(`Estoque atualizado. inserted=${data.inserted} updated=${data.updated}`, "success");
    setTimeout(() => location.reload(), 800);
  } catch (e) {
    setResult("Falha: " + e.message, "error");
  }
});
