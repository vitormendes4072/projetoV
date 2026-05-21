new Chart(document.getElementById('graficoPreco'), {
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
            legend: { position: 'top' },
            tooltip: { callbacks: { label: ctx => 'R$ ' + ctx.parsed.y.toFixed(2) } }
        },
        scales: { y: { ticks: { callback: val => 'R$ ' + val.toFixed(2) } } }
    }
});

new Chart(document.getElementById('graficoEstoque'), {
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
            legend: { position: 'top' },
            tooltip: { callbacks: { label: ctx => ctx.parsed.y + ' un.' } }
        },
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } }
    }
});
