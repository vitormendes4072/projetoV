/* chart-theme.js
 * Utilitário de tema para gráficos Chart.js.
 * Expõe window.ChartTheme = { colors(), watch(fn) }
 *
 * Uso:
 *   var c = ChartTheme.colors();        // paleta atual
 *   ChartTheme.watch(function(c) { ... chart.update('none'); });
 */
(function (global) {
  "use strict";

  function isDark() {
    return document.documentElement.classList.contains("dark");
  }

  /** Retorna a paleta de cores para o tema atual. */
  function colors() {
    var dark = isDark();
    return {
      tick:           dark ? "#94a3b8" : "#49739c",
      grid:           dark ? "#334155" : "#e7edf4",
      gridLight:      dark ? "#334155" : "#f1f5f9",
      legend:         dark ? "#e2e8f0" : "#374151",
      doughnutBorder: dark ? "#1e293b" : "#ffffff",
    };
  }

  /**
   * Observa mudanças de classe no <html> e chama updateFn(colors())
   * sempre que o tema for alterado.
   */
  function watch(updateFn) {
    var obs = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === "class") {
          updateFn(colors());
          break;
        }
      }
    });
    obs.observe(document.documentElement, { attributes: true });
  }

  global.ChartTheme = { colors: colors, watch: watch };
})(window);
