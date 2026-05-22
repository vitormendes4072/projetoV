/* sku_scatter.js — scatter plots de margem por SKU */
(function () {
  "use strict";

  var c = ChartTheme.colors();

  /* Cor por margem */
  function marginColor(margin, alpha) {
    alpha = alpha || 0.75;
    if (margin >= 20) return "rgba(22,163,74,"  + alpha + ")";  // verde
    if (margin >= 10) return "rgba(234,179,8,"  + alpha + ")";  // amarelo
    if (margin >= 0)  return "rgba(249,115,22," + alpha + ")";  // laranja
    return               "rgba(220,38,38,"      + alpha + ")";  // vermelho
  }

  /* ---- Scatter Real (Amazon) ---- */
  var realCtx = document.getElementById("scatterReal");
  var chartReal = null;
  if (realCtx && SKU_CHART.real && SKU_CHART.real.length > 0) {
    var realData = SKU_CHART.real.map(function (p) {
      return {
        x: p.units_sold,
        y: p.margin_pct,
        label: p.product_name,
        sku: p.sku,
        revenue: p.revenue_total,
        lucro: p.lucro_total,
        lucro_un: p.avg_lucro_per_unit,
        bgColor: marginColor(p.margin_pct),
      };
    });

    chartReal = new Chart(realCtx, {
      type: "scatter",
      data: {
        datasets: [{
          label: "SKUs (margem real)",
          data: realData,
          backgroundColor: realData.map(function (d) { return d.bgColor; }),
          pointRadius: 7,
          pointHoverRadius: 10,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                var raw = items[0].raw;
                return raw.label + (raw.label !== raw.sku ? " (" + raw.sku + ")" : "");
              },
              label: function (item) {
                var r = item.raw;
                return [
                  "Unidades: " + r.x.toLocaleString("pt-BR"),
                  "Margem: " + r.y.toFixed(1) + "%",
                  "Lucro total: R$ " + r.lucro.toLocaleString("pt-BR", {minimumFractionDigits: 2}),
                  "Lucro/un.: R$ " + r.lucro_un.toLocaleString("pt-BR", {minimumFractionDigits: 2}),
                ];
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "Unidades vendidas", color: c.tick, font: { size: 12 } },
            ticks: { color: c.tick },
            grid:  { color: c.grid },
          },
          y: {
            title: { display: true, text: "Margem % real", color: c.tick, font: { size: 12 } },
            ticks: { color: c.tick, callback: function (v) { return v + "%"; } },
            grid:  { color: c.grid },
          },
        },
      },
    });
  }

  /* ---- Scatter Estimado (simulações) ---- */
  var estCtx = document.getElementById("scatterEstimado");
  var chartEst = null;
  if (estCtx && SKU_CHART.estimado && SKU_CHART.estimado.length > 0) {
    var estData = SKU_CHART.estimado.map(function (p) {
      return {
        x: p.sim_count,
        y: p.avg_margin_pct,
        label: p.product_name,
        sku: p.sku,
        net: p.avg_net_profit,
        bgColor: marginColor(p.avg_margin_pct, 0.65),
      };
    });

    chartEst = new Chart(estCtx, {
      type: "scatter",
      data: {
        datasets: [{
          label: "Produtos (margem estimada)",
          data: estData,
          backgroundColor: estData.map(function (d) { return d.bgColor; }),
          pointRadius: 7,
          pointHoverRadius: 10,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: function (items) {
                var raw = items[0].raw;
                return raw.label + " (" + raw.sku + ")";
              },
              label: function (item) {
                var r = item.raw;
                return [
                  "Simulações: " + r.x,
                  "Margem média: " + r.y.toFixed(1) + "%",
                  "Lucro médio/un.: R$ " + r.net.toLocaleString("pt-BR", {minimumFractionDigits: 2}),
                ];
              },
            },
          },
        },
        scales: {
          x: {
            title: { display: true, text: "Simulações salvas", color: c.tick, font: { size: 12 } },
            ticks: { color: c.tick, stepSize: 1 },
            grid:  { color: c.grid },
          },
          y: {
            title: { display: true, text: "Margem estimada %", color: c.tick, font: { size: 12 } },
            ticks: { color: c.tick, callback: function (v) { return v + "%"; } },
            grid:  { color: c.grid },
          },
        },
      },
    });
  }

  /* Atualiza eixos ao trocar de tema */
  ChartTheme.watch(function (c) {
    [chartReal, chartEst].forEach(function (chart) {
      if (!chart) return;
      ["x", "y"].forEach(function (axis) {
        chart.options.scales[axis].title.color  = c.tick;
        chart.options.scales[axis].ticks.color  = c.tick;
        chart.options.scales[axis].grid.color   = c.grid;
      });
      chart.update("none");
    });
  });

})();
