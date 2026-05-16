// static/js/financeiro/menus.js
export function initMenus() {
  const openState = {
    btn: null,
    menu: null,
    placeholder: null,
    onScrollOrResize: null,
  };

  function isOpen() {
    return !!openState.menu && !!openState.placeholder;
  }

  function closeMenu() {
    if (!isOpen()) return;

    // volta o menu para o lugar original
    openState.placeholder.replaceWith(openState.menu);

    openState.menu.classList.add("hidden");
    openState.menu.style.position = "";
    openState.menu.style.top = "";
    openState.menu.style.left = "";
    openState.menu.style.width = "";
    openState.menu.style.zIndex = "";

    if (openState.btn) openState.btn.setAttribute("aria-expanded", "false");

    window.removeEventListener("scroll", openState.onScrollOrResize, true);
    window.removeEventListener("resize", openState.onScrollOrResize);

    openState.btn = null;
    openState.menu = null;
    openState.placeholder = null;
    openState.onScrollOrResize = null;
  }

  function positionMenu(btn, menu) {
    const r = btn.getBoundingClientRect();

    // largura do menu (mantém o w-56 do Tailwind, mas garante um mínimo)
    const menuWidth = menu.offsetWidth || 224;

    // posição padrão: alinhado à direita do botão
    let left = r.right - menuWidth;
    if (left < 8) left = 8;

    menu.style.width = `${menuWidth}px`;

    // tenta abrir para baixo
    let top = r.bottom + 8;

    // se não couber para baixo, abre para cima
    const menuHeight = menu.offsetHeight || 180;
    const bottomLimit = window.innerHeight - 8;

    if (top + menuHeight > bottomLimit) {
      top = r.top - 8 - menuHeight;
      if (top < 8) top = 8; // fallback
    }

    menu.style.position = "fixed";
    menu.style.top = `${top}px`;
    menu.style.left = `${left}px`;
    menu.style.zIndex = "9999";
  }

  function openMenu(btn, menu) {
    // fecha outro aberto
    closeMenu();

    // placeholder para recolocar o menu depois
    const ph = document.createElement("span");
    ph.setAttribute("data-menu-ph", "1");
    menu.replaceWith(ph);

    // move para o body (fora de qualquer overflow)
    document.body.appendChild(menu);

    menu.addEventListener("click", () => closeMenu(), { once: true });

    // mostra e posiciona
    menu.classList.remove("hidden");
    btn.setAttribute("aria-expanded", "true");

    positionMenu(btn, menu);

    // reposiciona em scroll/resize (captura true pra pegar scroll em containers)
    const handler = () => {
      if (!isOpen()) return;
      positionMenu(openState.btn, openState.menu);
    };
    window.addEventListener("scroll", handler, true);
    window.addEventListener("resize", handler);

    openState.btn = btn;
    openState.menu = menu;
    openState.placeholder = ph;
    openState.onScrollOrResize = handler;
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-menu-btn]");
    const clickedInsideMenu = e.target.closest("[data-menu]");

    // clique dentro do menu: deixa (botões/forms funcionarem)
    if (clickedInsideMenu) return;

    // clique no botão
    if (btn) {
      const id = btn.getAttribute("data-menu-btn");
      const menu = document.querySelector(`[data-menu="${id}"]`);
      if (!menu) return;

      // toggle
      if (isOpen() && openState.btn === btn) {
        closeMenu();
      } else {
        openMenu(btn, menu);
      }
      return;
    }

    // clique fora
    closeMenu();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
  });
}
