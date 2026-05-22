(function () {
    var c = ChartTheme.colors();

    var graficoPreco = new Chart(document.getElementById('graficoPreco'), {
        type: 'line',
        data: {
            labels: GRAFICO.labels,
            datasets: [
                {
                    label: 'Preço (R$)',
                    data: GRAFICO.precos,
                    borderColor: '#0d80f2',
                    backgroundColor: 'rgba(13,128,242,0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                },
                {
                    label: 'Custo (R$)',
                    data: GRAFICO.custos,
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245,158,11,0.08)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top', labels: { color: c.legend } },
                tooltip: { callbacks: { label: function (ctx) { return 'R$ ' + ctx.parsed.y.toFixed(2); } } }
            },
            scales: {
                y: {
                    ticks: { color: c.tick, callback: function (val) { return 'R$ ' + val.toFixed(2); } },
                    grid:  { color: c.grid }
                },
                x: {
                    ticks: { color: c.tick },
                    grid:  { color: c.grid }
                }
            }
        }
    });

    var graficoEstoque = new Chart(document.getElementById('graficoEstoque'), {
        type: 'line',
        data: {
            labels: GRAFICO.labels,
            datasets: [{
                label: 'Estoque (un.)',
                data: GRAFICO.estoques,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16,185,129,0.08)',
                fill: true,
                tension: 0.3,
                pointRadius: 4,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'top', labels: { color: c.legend } },
                tooltip: { callbacks: { label: function (ctx) { return ctx.parsed.y + ' un.'; } } }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { color: c.tick, stepSize: 1 },
                    grid: { color: c.grid }
                },
                x: {
                    ticks: { color: c.tick },
                    grid:  { color: c.grid }
                }
            }
        }
    });

    ChartTheme.watch(function (c) {
        // graficoPreco
        graficoPreco.options.plugins.legend.labels.color = c.legend;
        graficoPreco.options.scales.y.ticks.color        = c.tick;
        graficoPreco.options.scales.y.grid.color         = c.grid;
        graficoPreco.options.scales.x.ticks.color        = c.tick;
        graficoPreco.options.scales.x.grid.color         = c.grid;
        graficoPreco.update('none');

        // graficoEstoque
        graficoEstoque.options.plugins.legend.labels.color = c.legend;
        graficoEstoque.options.scales.y.ticks.color        = c.tick;
        graficoEstoque.options.scales.y.grid.color         = c.grid;
        graficoEstoque.options.scales.x.ticks.color        = c.tick;
        graficoEstoque.options.scales.x.grid.color         = c.grid;
        graficoEstoque.update('none');
    });
}());
