(function () {
    const labels = DASHBOARD_CHART.labels;
    const margins = DASHBOARD_CHART.margins;
    const dist = DASHBOARD_CHART.dist;

    new Chart(document.getElementById('chartMargem'), {
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
                    ticks: { callback: v => v + '%' },
                    grid: { color: '#f1f5f9' }
                },
                x: { grid: { display: false } }
            }
        }
    });

    new Chart(document.getElementById('chartDist'), {
        type: 'doughnut',
        data: {
            labels: ['Negativa (<0%)', 'Baixa (0–10%)', 'Média (10–20%)', 'Boa (>20%)'],
            datasets: [{
                data: dist,
                backgroundColor: ['#ef4444', '#f59e0b', '#3b82f6', '#10b981'],
                borderWidth: 2,
                borderColor: '#fff',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 11 } }
                }
            },
            cutout: '65%',
        }
    });
}());
