/* ============================================================
   theme.js — alternância de tema claro/escuro
   ------------------------------------------------------------
   O tema inicial é aplicado por um script inline no <head> (anti
   FOUC). Este arquivo cuida do clique no botão, da persistência
   em localStorage e da sincronização dos ícones sol/lua.
   ============================================================ */
(function () {
  "use strict";

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  function syncButtons() {
    var dark = isDark();
    document.querySelectorAll("[data-theme-toggle]").forEach(function (btn) {
      var sun = btn.querySelector('[data-theme-icon="sun"]');
      var moon = btn.querySelector('[data-theme-icon="moon"]');
      // Sol visível no escuro (clique volta p/ claro); lua visível no claro.
      if (sun) sun.classList.toggle("hidden", !dark);
      if (moon) moon.classList.toggle("hidden", dark);
      btn.setAttribute(
        "aria-label",
        dark ? "Ativar modo claro" : "Ativar modo escuro"
      );
    });
  }

  function applyTheme(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
    try {
      localStorage.setItem("theme", theme);
    } catch (e) {
      /* localStorage indisponível — segue sem persistir */
    }
    syncButtons();
  }

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-theme-toggle]");
    if (!btn) return;
    e.preventDefault();
    applyTheme(isDark() ? "light" : "dark");
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncButtons);
  } else {
    syncButtons();
  }
})();
