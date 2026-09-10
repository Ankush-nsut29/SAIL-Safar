document.addEventListener('DOMContentLoaded', function() {
    const analyzeForm = document.getElementById('analyze-form');
    let forecastChart = null;
    let routeMap = null;
    let routeLayerGroup = null;

    // Initialize map if container exists
    if (document.getElementById('route-map')) {
        routeMap = L.map('route-map').setView([0.0, 90.0], 3);
        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            minZoom: 2,
            noWrap: true,
            attribution: '&copy; OpenStreetMap contributors'
        }).addTo(routeMap);
        routeLayerGroup = L.layerGroup().addTo(routeMap);
        
        // Plot initial ports if available
        if (window.INITIAL_EASTCOAST_PORTS) {
            window.INITIAL_EASTCOAST_PORTS.forEach(function(port) {
                if (port.lat && port.lng) {
                    L.marker([port.lat, port.lng]).addTo(routeLayerGroup).bindPopup("<b>" + port.port_name + "</b><br>Discharge Port");
                }
            });
        }
        if (window.INITIAL_FOREIGN_PORTS) {
            window.INITIAL_FOREIGN_PORTS.forEach(function(port) {
                if (port.lat && port.lng) {
                    L.marker([port.lat, port.lng]).addTo(routeLayerGroup).bindPopup("<b>" + port.port_name + "</b><br>Origin Port");
                }
            });
        }
    }
    
    // Initialize empty chart
    const chartCtx = document.getElementById('forecastChart');
    if (chartCtx) {
        forecastChart = new Chart(chartCtx.getContext('2d'), {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Awaiting Analysis...',
                    data: [],
                    borderColor: '#ccc',
                    backgroundColor: 'rgba(200, 200, 200, 0.1)',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }

    if (analyzeForm) {
        analyzeForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const payload = {
                origin_port: document.getElementById('origin_port').value,
                discharge_port: document.getElementById('discharge_port').value,
                cargo_volume: parseFloat(document.getElementById('cargo_volume').value),
                contract_window_days: parseInt(document.getElementById('contract_window_days').value)
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

                // Update AI Advisory Card
                const aiAdvisoryCard = document.getElementById('ai-advisory-card');
                if (aiAdvisoryCard && data.ml_results.ai_advisory) {
                    aiAdvisoryCard.style.display = 'block';
                    document.getElementById('ai-contract-strategy').innerText = data.ml_results.ai_advisory.recommended_contract || 'N/A';
                    document.getElementById('ai-optimal-timing').innerText = data.ml_results.ai_advisory.optimal_timing || 'N/A';
                    document.getElementById('ai-strategic-rationale').innerText = data.ml_results.ai_advisory.strategic_rationale || 'N/A';
                }

                // Update KPIs
                document.getElementById('kpi-cards').style.display = 'grid';
                document.getElementById('kpi-freight').innerText = '$' + data.ml_results.predicted_freight_rate.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                document.getElementById('kpi-cargo').innerText = data.cargo_capped ? data.capped_volume.toLocaleString() : data.original_request.toLocaleString();
                document.getElementById('kpi-weather').innerText = data.ml_results.weather_delay_days + ' Days';
                document.getElementById('kpi-total-cost').innerText = '$' + data.ml_results.total_estimated_cost_usd.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2});
                
                // Update Statistical Cards
                const mlStatsCards = document.getElementById('ml-stats-cards');
                if (mlStatsCards) {
                    mlStatsCards.style.display = 'grid';
                    document.getElementById('stat-variance').innerText = data.ml_results.variance.toLocaleString(undefined, {maximumFractionDigits: 2});
                    
                    const skewness = data.ml_results.skewness;
                    const skewnessEl = document.getElementById('stat-skewness');
                    skewnessEl.innerText = skewness > 0 ? `+${skewness.toFixed(2)} (Bullish)` : `${skewness.toFixed(2)} (Bearish)`;
                    skewnessEl.style.color = skewness > 0 ? '#dc3545' : '#198754'; // Red if going up (expensive), Green if going down (cheap)
                    
                    const r2 = data.ml_results.freight.test_metrics.r2;
                    document.getElementById('stat-r2').innerText = `${(r2 * 100).toFixed(1)}% Accuracy`;
                }
                
                // Update Weather Alert
                const weatherAlert = document.getElementById('weather-alert');
                const weatherAlertText = document.getElementById('weather-alert-text');
                if (weatherAlert && weatherAlertText) {
                    weatherAlert.style.display = 'block';
                    if (data.weather_detour_active) {
                        weatherAlert.style.backgroundColor = '#fff3cd';
                        weatherAlert.style.color = '#856404';
                        weatherAlert.style.borderColor = '#ffeeba';
                        weatherAlertText.innerText = "⚠️ Severe Swells Detected (" + data.max_wave_height + "m). Route automatically adjusted for weather evasion. Transit time increased.";
                    } else if (data.max_wave_height > 0) {
                        weatherAlert.style.backgroundColor = '#d4edda';
                        weatherAlert.style.color = '#155724';
                        weatherAlert.style.borderColor = '#c3e6cb';
                        weatherAlertText.innerText = "✅ Weather conditions are clear. Max wave height at chokepoint: " + data.max_wave_height + "m. Standard routing applied.";
                    } else {
                        weatherAlert.style.backgroundColor = '#e2e3e5';
                        weatherAlert.style.color = '#383d41';
                        weatherAlert.style.borderColor = '#d6d8db';
                        weatherAlertText.innerText = "ℹ️ No significant weather chokepoints on this route. Standard routing applied.";
                    }
                }

                // Update Cargo Cap Alert
                const cargoCapAlert = document.getElementById('cargo-cap-alert');
                const cargoCapText = document.getElementById('cargo-cap-text');
                if (cargoCapAlert && cargoCapText) {
                    if (data.cargo_capped) {
                        cargoCapAlert.style.display = 'block';
                        cargoCapText.innerText = `⚠️ Draft Limit Exceeded: Requested ${data.original_request} MT cannot safely enter the selected ports. Cargo automatically adjusted to Maximum Safe Payload of ${data.capped_volume} MT.`;
                    } else {
                        cargoCapAlert.style.display = 'none';
                    }
                }

                // Update Chart
                document.getElementById('chart-container').style.display = 'block';
                const ctx = document.getElementById('forecastChart').getContext('2d');
                if (forecastChart) {
                    forecastChart.destroy();
                }
                
                const histDates = data.ml_results.chart_data.map(d => d.Date);
                const foreDates = data.ml_results.forecast_data.map(d => d.date);
                const allDates = [...histDates, ...foreDates];

                const histPrices = data.ml_results.chart_data.map(d => d.Price);
                
                const paddedForecast = new Array(histDates.length - 1).fill(null);
                paddedForecast.push(histPrices[histPrices.length - 1]); // Connect the lines
                const forePrices = data.ml_results.forecast_data.map(d => d.rate);
                const fullForecast = [...paddedForecast, ...forePrices];
                
                const fullHist = [...histPrices, ...new Array(foreDates.length).fill(null)];

                forecastChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: allDates,
                        datasets: [
                            {
                                label: `Historical Rates (${data.largest_vessel})`,
                                data: fullHist,
                                borderColor: '#004085',
                                backgroundColor: 'rgba(0, 64, 133, 0.1)',
                                borderWidth: 2,
                                fill: true,
                                tension: 0.1
                            },
                            {
                                label: `AI Forecast (${data.largest_vessel})`,
                                data: fullForecast,
                                borderColor: '#dc3545', // Red line for forecast
                                backgroundColor: 'rgba(220, 53, 69, 0.1)',
                                borderDash: [5, 5], // Dashed line to indicate prediction
                                borderWidth: 2,
                                fill: true,
                                tension: 0.1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false
                    }
                });

                // Update Route Map
                const routeContainer = document.getElementById('route-map-container');
                if (routeContainer && routeMap && data.route_coordinates) {
                    routeContainer.style.display = 'block';
                    setTimeout(() => {
                        routeMap.invalidateSize(); // Fix map rendering issue when container was hidden
                        routeLayerGroup.clearLayers();
                        
                        const origin = data.route_coordinates.origin;
                        const discharge = data.route_coordinates.discharge;
                        
                        if (origin[0] !== 0 && discharge[0] !== 0) {
                            L.marker(origin).addTo(routeLayerGroup).bindPopup('Origin Port');
                            L.marker(discharge).addTo(routeLayerGroup).bindPopup('Discharge Port');
                            
                            const polyline = L.polyline([origin, discharge], {
                                color: '#004085',
                                dashArray: '5, 10',
                                weight: 3
                            }).addTo(routeLayerGroup);
                            
                            routeMap.fitBounds(polyline.getBounds(), { padding: [50, 50] });
                        }
                    }, 100);
                }

                // Update Vessels Table
                document.getElementById('vessels-container').style.display = 'block';
                const tbody = document.getElementById('vessels-table');
                tbody.innerHTML = '';
                data.vessels.forEach(v => {
                    const row = document.createElement('tr');
                    const isFeasible = v.status === 'Feasible' || v.status.includes('Capped');
                    row.style.borderBottom = '1px solid #eee';
                    row.innerHTML = `
                        <td style="padding: 12px;">${v.class_name}</td>
                        <td style="padding: 12px;">${v.dwt.toLocaleString()}</td>
                        <td style="padding: 12px;">${v.draft}</td>
                        <td style="padding: 12px;">${v.max_allowable_cargo ? v.max_allowable_cargo.toLocaleString() : '0'}</td>
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
