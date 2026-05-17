const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function initBulkActions() {
  const selectAll = qs("#selectAll");
  const bulkBar = qs("#bulkBar");
  const bulkCount = qs("#bulkCount");
  const bulkAction = qs("#bulkAction");
  const bulkForm = qs("#bulkForm");
  const bulkIds = qs("#bulkIds");

  if (!bulkForm) return;

  const rowChecks = () => qsa(".rowCheck");

  const selectedIds = () =>
    rowChecks().filter((c) => c.checked).map((c) => c.getAttribute("data-id")).filter(Boolean);

  const rebuildHiddenIds = (ids) => {
    bulkIds.innerHTML = "";
    ids.forEach((id) => {
      const inp = document.createElement("input");
      inp.type = "hidden";
      inp.name = "selected_ids";
      inp.value = id;
      bulkIds.appendChild(inp);
    });
  };

  const updateUI = () => {
    const ids = selectedIds();
    bulkCount.textContent = String(ids.length);
    bulkBar.classList.toggle("hidden", ids.length === 0);

    const total = rowChecks().length;
    if (selectAll) {
      selectAll.indeterminate = ids.length > 0 && ids.length < total;
      selectAll.checked = total > 0 && ids.length === total;
    }
  };

  selectAll?.addEventListener("change", () => {
    rowChecks().forEach((c) => { c.checked = selectAll.checked; });
    updateUI();
  });

  document.addEventListener("change", (e) => {
    if (e.target?.classList?.contains("rowCheck")) updateUI();
  });

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-bulk-action]");
    if (!btn) return;

    const action = btn.getAttribute("data-bulk-action");
    const needsConfirm = btn.getAttribute("data-confirm") === "true";

    const ids = selectedIds();
    if (ids.length === 0) return;

    if (needsConfirm) {
      const ok = confirm(`Excluir ${ids.length} item(ns)?`);
      if (!ok) return;
    }

    rebuildHiddenIds(ids);
    bulkAction.value = action;
    bulkForm.submit();
  });

  updateUI();
}
