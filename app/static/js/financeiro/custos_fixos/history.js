function el(id) {
  return document.getElementById(id);
}

function lockScroll() {
  document.documentElement.classList.add("overflow-hidden");
  document.body.classList.add("overflow-hidden");
}
function unlockScroll() {
  document.documentElement.classList.remove("overflow-hidden");
  document.body.classList.remove("overflow-hidden");
}

function openModal() {
  const modal = el("historyModal");
  if (!modal) return;
  modal.classList.remove("hidden");
  lockScroll();
  // topo
  const scrollArea = modal.querySelector("[data-history-scroll]");
  if (scrollArea) scrollArea.scrollTop = 0;
}
function closeModal() {
  const modal = el("historyModal");
  if (!modal) return;
  modal.classList.add("hidden");
  unlockScroll();
}

function setLoading(v) {
  el("historyLoading")?.classList.toggle("hidden", !v);
}
function setEmpty(v) {
  el("historyEmpty")?.classList.toggle("hidden", !v);
}

const FIELD_LABELS = {
  nome: "Nome",
  categoria: "Categoria",
  valor_mensal: "Valor mensal",
  dia_pagamento: "Dia de pagamento",
  data_inicio: "Início",
  data_fim: "Fim",
  ativo: "Status",
};

const ACTION_LABELS = {
  create: "Criado",
  update: "Atualizado",
  delete: "Excluído",
  toggle_paid: "Pagamento alterado",
  toggle_active: "Status alterado",
  bulk: "Ação em massa",
};

function isISODateString(v) {
  return typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v);
}

function formatDateBR(v) {
  try {
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return d.toLocaleDateString("pt-BR");
  } catch {
    return String(v);
  }
}

function formatMoneyBR(v) {
  if (v === null || v === undefined || v === "") return "—";
  // pode vir "20.00" ou 20 ou "20,00"
  const s = String(v).replace(/\./g, "").replace(",", ".");
  const n = Number(s);
  if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatValue(field, v) {
  if (v === null || v === undefined || v === "") return "—";

  if (field === "valor_mensal") return formatMoneyBR(v);

  if (field === "ativo") {
    // pode vir true/false ou "true"/"false"
    const b = v === true || v === "true" || v === 1 || v === "1";
    return b ? "Ativo" : "Inativo";
  }

  if (field === "dia_pagamento") {
    const n = Number(v);
    if (Number.isFinite(n) && n > 0) return `Dia ${n}`;
    return "—";
  }

  if ((field === "data_inicio" || field === "data_fim") && isISODateString(v)) {
    return formatDateBR(v);
  }

  // fallback
  return String(v);
}

function buildDiffLines(diff) {
  if (!diff || typeof diff !== "object") return [];

  const entries = Object.entries(diff);
  if (!entries.length) return [];

  return entries.map(([field, obj]) => {
    const from = obj?.from;
    const to = obj?.to;

    return {
      field,
      label: FIELD_LABELS[field] || field,
      from: formatValue(field, from),
      to: formatValue(field, to),
    };
  });
}

function render(items) {
  const list = el("historyList");
  if (!list) return;

  list.innerHTML = "";

  for (const it of items) {
    const when = it.changed_at ? new Date(it.changed_at).toLocaleString("pt-BR") : "";
    const actionKey = (it.action || "update").toLowerCase();
    const actionLabel = ACTION_LABELS[actionKey] || it.action || "Atualizado";

    const lines = buildDiffLines(it.diff);

    const li = document.createElement("li");
    li.className = "rounded-xl border bg-white p-4";

    const linesHtml = lines.length
      ? `
        <div class="mt-3 space-y-2">
          ${lines
            .map(
              (l) => `
                <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 sm:gap-3">
                  <div class="text-sm font-medium text-slate-700">${l.label}</div>
                  <div class="text-sm text-slate-700">
                    <span class="text-slate-500">${l.from}</span>
                    <span class="mx-2 text-slate-300">→</span>
                    <span class="font-semibold text-slate-900">${l.to}</span>
                  </div>
                </div>
              `
            )
            .join("")}
        </div>
      `
      : `<div class="text-sm text-slate-500 mt-3">Sem detalhes de alteração.</div>`;

    li.innerHTML = `
      <div class="flex items-start justify-between gap-3">
        <div class="text-sm font-semibold text-slate-900">${actionLabel}</div>
        <div class="text-xs text-slate-500">${when}</div>
      </div>

      ${it.note ? `<div class="text-sm text-slate-700 mt-1">${it.note}</div>` : ""}

      ${linesHtml}
    `;

    list.appendChild(li);
  }
}

export function initHistory() {
  const modal = el("historyModal");
  if (!modal) return;

  el("historyCloseBtn")?.addEventListener("click", closeModal);
  el("historyOverlay")?.addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-history-btn]");
    if (!btn) return;

    e.preventDefault();
    e.stopPropagation();

    // fecha menu de ações (se estiver aberto)
    document.body.click();

    const url = btn.getAttribute("data-history-url");
    if (!url) return;

    openModal();
    setEmpty(false);
    render([]);
    setLoading(true);

    try {
      const res = await fetch(url, { headers: { Accept: "application/json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const items = await res.json();

      setLoading(false);
      if (!items.length) {
        setEmpty(true);
        return;
      }

      render(items);
    } catch (err) {
      console.error("Erro ao carregar histórico:", err);
      setLoading(false);
      setEmpty(true);
    }
  });
}
