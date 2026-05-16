const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function initMoneyMasks() {
  qsa("[data-money]").forEach((input) => {
    input.addEventListener("input", () => {
      input.value = formatMoneyBR(input.value);
    });
  });
}

function formatMoneyBR(value) {
  let v = String(value || "").replace(/\D/g, "");
  if (!v) return "";
  v = (parseInt(v, 10) / 100).toFixed(2);
  v = v.replace(".", ",");
  v = v.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return v;
}
