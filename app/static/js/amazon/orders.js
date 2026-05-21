function setResult(msg, type = "info") {
  const el = document.getElementById("syncResult");
  if (!el) return;
  el.classList.remove("hidden");
  const base = "rounded-lg border p-3";
  if (type === "success") el.className = base + " border-green-200 bg-green-50 text-green-800";
  else if (type === "error") el.className = base + " border-red-200 bg-red-50 text-red-800";
  else el.className = base + " border-slate-200 bg-slate-50 text-slate-700";
  el.textContent = msg;
}

async function loadOrderDetails(orderId) {
  const row = document.getElementById(`details-${orderId}`);
  if (!row || row.dataset.loaded === "1") return;

  const box = row.querySelector("div");
  box.textContent = "Carregando detalhes…";

  const res = await fetch(`/integrations/amazon/orders/${encodeURIComponent(orderId)}/details`);
  const data = await res.json();

  if (!res.ok || !data.ok) {
    box.textContent = data.error || "Falha ao carregar detalhes.";
    return;
  }

  const totals = (data.items || []).reduce((acc, it) => {
    acc.revenue  += Number(it.revenue  || 0);
    acc.net      += Number(it.net      || 0);
    acc.imposto  += Number(it.imposto  || 0);
    acc.cmv      += Number(it.cmv      || 0);
    acc.embalagem+= Number(it.embalagem|| 0);
    acc.lucro    += Number(it.lucro    || 0);
    return acc;
  }, { revenue: 0, net: 0, imposto: 0, cmv: 0, embalagem: 0, lucro: 0 });

  const margemTotal = totals.revenue > 0 ? (totals.lucro / totals.revenue * 100) : 0;
  const hasFinance  = !!data.has_finance_events;
  const note = hasFinance
    ? "Valores com taxas reais (Finances)."
    : "Valores estimados (sem Finances para este pedido).";

  const pendingHint = (data.order_status === "Pending" && totals.revenue === 0)
    ? `<div class="mt-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2">
         Pedido <b>Pendente</b>: a Amazon pode não disponibilizar valores até confirmar o pagamento.
       </div>`
    : "";

  const rowsHtml = (data.items || []).map(it => `
    <tr class="border-t border-slate-200">
      <td class="py-2 px-3"><div class="font-bold text-slate-900">${it.sku || "-"}</div>
        <div class="text-xs text-slate-500">ASIN: ${it.asin || "-"}</div></td>
      <td class="py-2 px-3">${Number(it.qty || 0)}</td>
      <td class="py-2 px-3">R$ ${Number(it.price  || 0).toFixed(2)}</td>
      <td class="py-2 px-3">R$ ${Number(it.net    || 0).toFixed(2)}</td>
      <td class="py-2 px-3">R$ ${Number(it.imposto|| 0).toFixed(2)}</td>
      <td class="py-2 px-3">R$ ${Number(it.cmv    || 0).toFixed(2)}</td>
      <td class="py-2 px-3">R$ ${Number(it.embalagem||0).toFixed(2)}</td>
      <td class="py-2 px-3 font-bold">R$ ${Number(it.lucro || 0).toFixed(2)}</td>
      <td class="py-2 px-3">
        <span class="inline-flex rounded-full px-2 py-1 text-xs font-bold
          ${Number(it.margem_pct || 0) >= 0 ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}">
          ${Number(it.margem_pct || 0).toFixed(2)}%
        </span>
      </td>
    </tr>`).join("");

  box.innerHTML = `
    <div class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-3">
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">Receita</div>
        <div class="font-bold">R$ ${totals.revenue.toFixed(2)}</div>
      </div>
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">Líquido</div>
        <div class="font-bold">R$ ${totals.net.toFixed(2)}</div>
      </div>
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">Imposto</div>
        <div class="font-bold">R$ ${totals.imposto.toFixed(2)}</div>
      </div>
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">CMV</div>
        <div class="font-bold">R$ ${totals.cmv.toFixed(2)}</div>
      </div>
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">Embalagem</div>
        <div class="font-bold">R$ ${totals.embalagem.toFixed(2)}</div>
      </div>
      <div class="p-3 bg-white border border-slate-200 rounded-lg">
        <div class="text-xs text-slate-500">Lucro / Margem</div>
        <div class="font-bold">R$ ${totals.lucro.toFixed(2)}</div>
        <div class="text-xs text-slate-500">${margemTotal.toFixed(2)}%</div>
      </div>
    </div>

    <div class="flex items-center justify-between mb-2">
      <div class="text-xs text-slate-600">
        ${note} | Imposto padrão: <b>${Number(data.imposto_rate_pct || 0).toFixed(2)}%</b>
        ${data.order_status ? ` | Status: <b>${data.order_status}</b>` : ""}
      </div>
      <div class="text-xs text-slate-500">Itens: <b>${data.items_count}</b></div>
    </div>

    ${pendingHint}

    <div class="overflow-x-auto rounded-lg border border-slate-200 bg-white">
      <table class="min-w-full text-sm">
        <thead class="bg-slate-100 text-slate-700">
          <tr>
            <th class="text-left py-2 px-3">Item</th>
            <th class="text-left py-2 px-3">Qtd</th>
            <th class="text-left py-2 px-3">Preço</th>
            <th class="text-left py-2 px-3">Líquido</th>
            <th class="text-left py-2 px-3">Imposto</th>
            <th class="text-left py-2 px-3">CMV</th>
            <th class="text-left py-2 px-3">Embalagem</th>
            <th class="text-left py-2 px-3">Lucro</th>
            <th class="text-left py-2 px-3">Margem</th>
          </tr>
        </thead>
        <tbody>
          ${rowsHtml || `<tr><td class="p-4 text-slate-600" colspan="9">Nenhum item. Clique em "Sincronizar itens (15)".</td></tr>`}
        </tbody>
      </table>
    </div>`;

  row.dataset.loaded = "1";
}

document.addEventListener("DOMContentLoaded", () => {
  const btnSyncOrders = document.getElementById("btnSyncOrders");
  const btnSyncItems  = document.getElementById("btnSyncItems");

  btnSyncOrders?.addEventListener("click", async () => {
    try {
      setResult("Sincronizando pedidos (últimos 30 dias)…", "info");
      const res  = await fetch("/integrations/amazon/sync_orders_only?days=30");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || ("Erro " + res.status));
      setResult(`Sync OK. API: ${data.orders_returned_by_api} | Gravados: ${data.orders_upserted}`, "success");
      setTimeout(() => location.reload(), 800);
    } catch (e) {
      setResult("Falha no sync: " + e.message, "error");
    }
  });

  btnSyncItems?.addEventListener("click", async () => {
    try {
      setResult("Sincronizando itens (15 pedidos)…", "info");
      const res  = await fetch("/integrations/amazon/sync_items_batch?limit=15", {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || ("Erro " + res.status));
      setResult(`Itens OK. Pedidos: ${data.processed_orders} | Itens: ${data.inserted_items}`, "success");
    } catch (e) {
      setResult("Falha ao sincronizar itens: " + e.message, "error");
    }
  });
});

document.addEventListener("click", async (e) => {
  const btn = e.target.closest(".toggle-details");
  if (!btn) return;

  const orderId    = btn.getAttribute("data-order-id");
  const detailsRow = document.getElementById(`details-${orderId}`);
  if (!detailsRow) return;

  const isHidden = detailsRow.classList.contains("hidden");
  detailsRow.classList.toggle("hidden");
  btn.textContent = isHidden ? "▲" : "▼";

  if (isHidden) await loadOrderDetails(orderId);
});
