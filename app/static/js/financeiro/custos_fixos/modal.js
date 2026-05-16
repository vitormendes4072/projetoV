const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function initEditModal(page) {
  const modal = qs("#editModal");
  const overlay = qs("#editOverlay");
  const closeBtn = qs("#editCloseBtn");
  const cancelBtn = qs("#editCancelBtn");
  const form = qs("#editForm");

  if (!modal || !form || !page) return;

  const fNome = qs("#edit_nome");
  const fCat = qs("#edit_categoria");
  const fValor = qs("#edit_valor");
  const fDia = qs("#edit_dia");
  const fInicio = qs("#edit_inicio");
  const fFim = qs("#edit_fim");

  const open = () => {
    modal.classList.remove("hidden");
    modal.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    setTimeout(() => fNome?.focus(), 0);
  };

  const close = () => {
    modal.classList.add("hidden");
    modal.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  };

  const buildUpdateUrl = (templateUrl, id) => {
    let base = templateUrl.replace("/0/update", `/${id}/update`);
    if (base === templateUrl) base = templateUrl.replace(/\/0(\/|$)/, `/${id}$1`);

    const params = new URLSearchParams({
      sort: page.dataset.sort || "",
      view: page.dataset.view || "",
      q: page.dataset.q || "",
      cat: page.dataset.cat || "all",
      ativo: page.dataset.ativo || "all",
      paid: page.dataset.paid || "all",
    });

    return `${base}?${params.toString()}#itens`;
  };

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-edit-btn]");
    if (!btn) return;

    // fecha menus
    qsa("[data-menu]").forEach((m) => m.classList.add("hidden"));

    const id = btn.getAttribute("data-id");
    fNome.value = btn.getAttribute("data-nome") || "";
    fCat.value = btn.getAttribute("data-categoria") || "Outros";
    fValor.value = btn.getAttribute("data-valor") || "";
    fDia.value = btn.getAttribute("data-dia") || "";
    fInicio.value = btn.getAttribute("data-inicio") || "";
    fFim.value = btn.getAttribute("data-fim") || "";

    const templateUrl = page.dataset.updateUrlTemplate || "";
    form.action = buildUpdateUrl(templateUrl, id);

    open();
  });

  overlay?.addEventListener("click", close);
  closeBtn?.addEventListener("click", close);
  cancelBtn?.addEventListener("click", close);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) close();
  });
}
