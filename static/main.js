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
