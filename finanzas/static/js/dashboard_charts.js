// Gráfico de gastos por categoría
function initGastosChart() {
    const canvas = document.getElementById('gastosPorCategoriaChart');
    if (!canvas) return;
        // Leemos la URL de la API desde el atributo data-url del canvas
        const url = canvas.dataset.url;
        fetch(url)
            .then(resp => resp.json())
            .then(data => {
                new Chart(canvas, {
                    type: 'doughnut',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            data: data.data,
                            backgroundColor: [
                                '#FBA73C', '#F7E4D9', '#F3713E',
                                '#CB2D44', '#A02346', '#FCC856',
                                '#E34345', '#E0B3BE', '#D67987'
                            ]
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { legend: { position: 'top' } }
                    }
                });
            });
}

// Gráfico de ingresos vs gastos
function initFlujoDineroChart() {
    const canvas = document.getElementById('flujoDeDineroChart');
    if (!canvas) return;
        const url = canvas.dataset.url;
        fetch(url)
            .then(resp => resp.json())
            .then(data => {
                new Chart(canvas, {
                    type: 'bar',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: 'Flujo de Dinero',
                            data: data.data,
                            backgroundColor: [
                                'rgb(239, 104, 64)',
                                'rgb(251, 167, 60)'
                            ],
                            borderColor: [
                                'rgb(239, 104, 64)',
                                'rgb(251, 167, 60)'
                            ],
                            borderWidth: 1
                        }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            beginAtZero: true,
                            ticks: {
                                callback: value => '$' + value.toLocaleString()
                            }
                        }
                    },
                    plugins: { legend: { display: false } }
                } 
                });
            });
    }

// Gráfico de evolución de inversión
function initInversionesChart() {
    const canvas = document.getElementById('investmentLineChart');
    if (!canvas) return;
        //const labels = JSON.parse(canvas.dataset.labels || '[]');
        //const data = JSON.parse(canvas.dataset.values || '[]');
        const url = canvas.dataset.url;
        fetch(url)
            .then(resp => resp.json())
            .then(data => {
                new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels: data.labels,
                        datasets: [{
                            label: 'Capital Invertido Acumulado',
                            data: data.data,
                            fill: true,
                            borderColor: '#A02346',
                            backgroundColor: 'rgb(203, 45, 68)',
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    callback: value => '$' + value.toLocaleString()
                                }
                            }
                        },
                        plugins: { legend: { display: false } }
                   } 
                });
            });
    }

document.addEventListener('DOMContentLoaded', () => {
    initGastosChart();
    initFlujoDineroChart();
    initInversionesChart();
    initGananciasMensualesChart();
});