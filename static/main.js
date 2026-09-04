document.addEventListener('DOMContentLoaded', function() {
    const analyzeForm = document.getElementById('analyze-form');
    let forecastChart = null;

    if (analyzeForm) {
        analyzeForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const payload = {
                origin_port: document.getElementById('origin_port').value,
                discharge_port: document.getElementById('discharge_port').value,
                cargo_volume: parseFloat(document.getElementById('cargo_volume').value),
                contract_window_days: parseInt(document.getElementById('contract_window_days').value),
                fuel_price: parseFloat(document.getElementById('fuel_price').value),
                transit_days: parseFloat(document.getElementById('transit_days').value)
            };

            const btn = this.querySelector('button');
            const originalText = btn.innerText;
            btn.innerText = 'Analyzing...';
            btn.disabled = true;

            fetch('/dashboard/api/analyze', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            })
            .then(response => response.json())
            .then(data => {
                btn.innerText = originalText;
                btn.disabled = false;

                if (data.error) {
                    alert(data.error);
                    return;
                }

                // Update Recommendation Banner
                const recBanner = document.getElementById('rec-banner');
                const recText = document.getElementById('rec-text');
                recBanner.style.display = 'block';
                recText.innerText = data.analysis.recommendation;
                if (data.analysis.decision_type === 'Period Time Charter') {
                    recBanner.style.backgroundColor = '#d4edda';
                    recBanner.style.color = '#155724';
                    recBanner.style.border = '1px solid #c3e6cb';
                } else {
                    recBanner.style.backgroundColor = '#cce5ff';
                    recBanner.style.color = '#004085';
                    recBanner.style.border = '1px solid #b8daff';
                }

                // Update KPIs
                document.getElementById('kpi-cards').style.display = 'grid';
                document.getElementById('kpi-mean').innerText = '$' + data.analysis.stats.mean.toLocaleString();
                document.getElementById('kpi-variance').innerText = data.analysis.stats.variance.toLocaleString();
                document.getElementById('kpi-skewness').innerText = data.analysis.stats.skewness;
                document.getElementById('kpi-kurtosis').innerText = data.analysis.stats.kurtosis;
                document.getElementById('kpi-landed-cost').innerText = '$' + data.analysis.stats.landed_cost_per_mt + '/MT';

                // Update Chart
                document.getElementById('chart-container').style.display = 'block';
                const ctx = document.getElementById('forecastChart').getContext('2d');
                if (forecastChart) {
                    forecastChart.destroy();
                }
                forecastChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: data.analysis.chart_data.labels,
                        datasets: [{
                            label: `Historical Rates (${data.largest_vessel})`,
                            data: data.analysis.chart_data.values,
                            borderColor: '#004085',
                            backgroundColor: 'rgba(0, 64, 133, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false
                    }
                });

                // Update Vessels Table
                document.getElementById('vessels-container').style.display = 'block';
                const tbody = document.getElementById('vessels-table');
                tbody.innerHTML = '';
                data.vessels.forEach(v => {
                    const row = document.createElement('tr');
                    const isFeasible = v.status === 'Feasible';
                    row.style.borderBottom = '1px solid #eee';
                    row.innerHTML = `
                        <td style="padding: 12px;">${v.class_name}</td>
                        <td style="padding: 12px;">${v.dwt.toLocaleString()}</td>
                        <td style="padding: 12px;">${v.draft}</td>
                        <td style="padding: 12px; font-weight: bold; color: ${isFeasible ? '#138808' : '#dc3545'};">${v.status}</td>
                    `;
                    tbody.appendChild(row);
                });
            })
            .catch(err => {
                console.error(err);
                alert("An error occurred during analysis.");
                btn.innerText = originalText;
                btn.disabled = false;
            });
        });
    }
});
