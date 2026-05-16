const qs = (sel, root = document) => root.querySelector(sel);

const escapeHtml = (str) =>
  String(str).replace(/[&<>"']/g, (s) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[s]));

export function initFilters() {
  const form = qs("#filtersForm");
  if (!form) return;

  const typeSel = qs("#filterType", form);
  const wrap = qs("#filterValueWrap", form);
  const label = qs("#filterValueLabel", form);
  const addBtn = qs("#addFilterBtn", form);

  const hid = {
    q: qs("#hid_q", form),
    cat: qs("#hid_cat", form),
    ativo: qs("#hid_ativo", form),
    paid: qs("#hid_paid", form),
  };

  const input = {
    q: qs("#val_q", form),
    cat: qs("#val_cat", form),
    ativo: qs("#val_ativo", form),
    paid: qs("#val_paid", form),
  };

  const chipsBox = qs("#activeFilters", form);
  const sortSelect = qs("#sortSelect", form);

  const meta = {
    q: { label: "Buscar", empty: "" },
    cat: { label: "Categoria", empty: "all" },
    ativo: { label: "Status", empty: "all" },
    paid: { label: "Pagamento (mês)", empty: "all" },
  };

  const hideAllInputs = () => Object.values(input).forEach((el) => el.classList.add("hidden"));

  const showInput = (key) => {
    hideAllInputs();
    wrap.classList.remove("hidden");
    addBtn.classList.remove("hidden");
    label.textContent = meta[key].label;

    input[key].classList.remove("hidden");
    input[key].value = hid[key].value || meta[key].empty;

    if (key === "q") input[key].focus();
  };

  const hasActive = (key) => {
    const v = hid[key].value;
    if (key === "q") return (v || "").trim().length > 0;
    return v && v !== meta[key].empty;
  };

  const normalizeText = (key, value) => {
    if (key === "q") return (value || "").trim();
    if (key === "ativo") {
      if (value === "active") return "Ativos";
      if (value === "inactive") return "Inativos";
      return "Todos";
    }
    if (key === "paid") {
      if (value === "paid") return "Pago";
      if (value === "unpaid") return "Não pago";
      return "Todos";
    }
    if (key === "cat") return value === "all" ? "Todas" : value;
    return value;
  };

  const clearFilter = (key) => { hid[key].value = meta[key].empty; };
  const setFilter = (key, value) => { hid[key].value = value; };

  const renderChips = () => {
    chipsBox.innerHTML = "";

    const keys = ["q", "cat", "ativo", "paid"];
    const active = keys.filter(hasActive);
    if (active.length === 0) return;

    active.forEach((key) => {
      const text = normalizeText(key, hid[key].value);

      const chip = document.createElement("button");
      chip.type = "button";
      chip.className =
        "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold bg-white text-slate-700 border-slate-200 hover:bg-slate-50";
      chip.title = "Remover filtro";
      chip.innerHTML =
        `<span>${meta[key].label}:</span><span class="font-bold">${escapeHtml(text)}</span><span class="text-slate-400">✕</span>`;

      chip.addEventListener("click", () => {
        clearFilter(key);
        renderChips();
        form.submit();
      });

      chipsBox.appendChild(chip);
    });

    const clearAll = document.createElement("button");
    clearAll.type = "button";
    clearAll.className =
      "inline-flex items-center gap-2 px-3 py-1.5 rounded-full border text-xs font-semibold bg-white text-slate-700 border-slate-200 hover:bg-slate-50";
    clearAll.innerHTML = `<span>Limpar filtros</span><span class="text-slate-400">✕</span>`;
    clearAll.addEventListener("click", () => {
      ["q", "cat", "ativo", "paid"].forEach(clearFilter);
      renderChips();
      form.submit();
    });
    chipsBox.appendChild(clearAll);
  };

  typeSel.addEventListener("change", () => {
    const key = typeSel.value;
    if (!key) {
      wrap.classList.add("hidden");
      addBtn.classList.add("hidden");
      hideAllInputs();
      return;
    }
    showInput(key);
  });

  addBtn.addEventListener("click", () => {
    const key = typeSel.value;
    if (!key) return;

    let value = input[key].value;
    if (key === "q") value = (value || "").trim();

    setFilter(key, value);
    renderChips();

    typeSel.value = "";
    wrap.classList.add("hidden");
    addBtn.classList.add("hidden");
    hideAllInputs();

    form.submit();
  });

  input.q?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      addBtn.click();
    }
  });

  sortSelect?.addEventListener("change", () => form.submit());

  renderChips();
}
