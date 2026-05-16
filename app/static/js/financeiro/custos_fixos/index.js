import { initMoneyMasks } from "./money.js";
import { initMenus } from "./menus.js";
import { initFilters } from "./filters.js";
import { initBulkActions } from "./bulk.js";
import { initEditModal } from "./modal.js";
import { initHistory } from "./history.js";

document.addEventListener("DOMContentLoaded", () => {
  const page = document.querySelector('[data-page="custos-fixos"]');
  if (!page) return;

  initMoneyMasks();
  initMenus();
  initFilters();
  initBulkActions();
  initEditModal(page);
  initHistory();
});
