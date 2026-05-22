(function () {
    var c = ChartTheme.colors();

    var labels  = DASHBOARD_CHART.labels;
    var margins = DASHBOARD_CHART.margins;
    var dist    = DASHBOARD_CHART.dist;

    var chartMargem = new Chart(document.getElementById('chartMargem'), {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Margem (%)',
                data: margins,
                borderColor: '#0d80f2',
                backgroundColor: 'rgba(13,128,242,0.08)',
                tension: 0.3,
                fill: true,
                pointRadius: 3,
                pointHoverRadius: 5,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    ticks: { color: c.tick, callback: function (v) { return v + '%'; } },
                    grid:  { color: c.gridLight }
                },
                x: {
                    ticks: { color: c.tick },
                    grid:  { display: false }
                }
            }
        }
    });

    var chartDist = new Chart(document.getElementById('chartDist'), {
        type: 'doughnut',
        data: {
            labels: ['Negativa (<0%)', 'Baixa (0–10%)', 'Média (10–20%)', 'Boa (>20%)'],
            datasets: [{
                data: dist,
                backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#10b981'],
                borderWidth: 2,
                borderColor: c.doughnutBorder,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 }, color: c.legend }
                }
            },
            cutout: '65%',
        }
    });

    ChartTheme.watch(function (c) {
        // chartMargem — eixos
        chartMargem.options.scales.y.ticks.color = c.tick;
        chartMargem.options.scales.y.grid.color  = c.gridLight;
        chartMargem.options.scales.x.ticks.color = c.tick;
        chartMargem.update('none');

        // chartDist — borda dos segmentos + legenda
        chartDist.data.datasets[0].borderColor        = c.doughnutBorder;
        chartDist.options.plugins.legend.labels.color = c.legend;
        chartDist.update('none');
    });
}());
