from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from services.data_loader import get_eastcoast_ports, get_foreign_ports, get_vessels, load_csv_as_dataframe, get_routes
import requests
from services.vessel_engine import check_feasibility
from services.calculator import calculate_route_stats

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

def check_marine_weather(lat, lng):
    try:
        url = f"https://marine-api.open-meteo.com/v1/marine?latitude={lat}&longitude={lng}&hourly=wave_height"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        wave_heights = data.get('hourly', {}).get('wave_height', [])
        if wave_heights:
            # Filter out None values just in case
            valid_heights = [h for h in wave_heights if h is not None]
            return max(valid_heights) if valid_heights else 0
    except Exception as e:
        print(f"Error fetching marine weather: {e}")
    return 0

@dashboard_bp.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
        
    eastcoast_ports = get_eastcoast_ports()
    foreign_ports = get_foreign_ports()
    return render_template('dashboard/index.html', eastcoast_ports=eastcoast_ports, foreign_ports=foreign_ports)

@dashboard_bp.route('/api/analyze', methods=['POST'])
def api_analyze():
    if 'user_id' not in session:
        return jsonify({"error": "Unauthorized"}), 401
        
    data = request.json
    origin_port = data.get('origin_port')
    discharge_port = data.get('discharge_port')
    cargo_volume = data.get('cargo_volume', 0)
    contract_window_days = data.get('contract_window_days', 30)
    fuel_price = data.get('fuel_price', 600)
    transit_days = data.get('transit_days', 15)
    
    vessels_data = get_vessels()
    foreign_ports_data = get_foreign_ports()
    eastcoast_ports_data = get_eastcoast_ports()
    
    results, largest_vessel = check_feasibility(origin_port, discharge_port, vessels_data, foreign_ports_data, eastcoast_ports_data)
    
    if not largest_vessel:
        return jsonify({"error": "No feasible vessel found for these ports."}), 400

    max_allowable_cargo = largest_vessel.get('max_allowable_cargo', largest_vessel.get('typical_dwt_capacity_mt', 0))
    cargo_capped = False
    capped_volume = 0
    original_request = cargo_volume
    
    if cargo_volume > max_allowable_cargo:
        cargo_capped = True
        capped_volume = max_allowable_cargo
        used_cargo_volume = max_allowable_cargo
    else:
        used_cargo_volume = cargo_volume
        
    df = load_csv_as_dataframe(largest_vessel['class_name'])
    
    # Identify origin country
    origin_country = ""
    for port in foreign_ports_data:
        if port['port_name'] == origin_port:
            origin_country = port.get('country', '')
            break
            
    # Evasion logic
    weather_detour_active = False
    max_wave_height = 0
    routes_data = get_routes()
    
    chokepoint_lat = None
    chokepoint_lng = None
    evasion_days = 0
    
    if origin_country == "Australia":
        chokepoint_lat, chokepoint_lng = -10.5, 142.0
        evasion_days = 3
    elif origin_country == "Indonesia":
        chokepoint_lat, chokepoint_lng = -8.8, 115.8
        evasion_days = 3
        
    if chokepoint_lat is not None and chokepoint_lng is not None:
        max_wave_height = check_marine_weather(chokepoint_lat, chokepoint_lng)
        if max_wave_height > 6.0:
            weather_detour_active = True
            transit_days += evasion_days
    
    analysis = calculate_route_stats(largest_vessel, contract_window_days, transit_days, used_cargo_volume, fuel_price, df)
    
    origin_lat = 0
    origin_lng = 0
    discharge_lat = 0
    discharge_lng = 0
    
    for port in foreign_ports_data:
        if port['port_name'] == origin_port:
            origin_lat = port.get('lat', 0)
            origin_lng = port.get('lng', 0)
            break
            
    for port in eastcoast_ports_data:
        if port['port_name'] == discharge_port:
            discharge_lat = port.get('lat', 0)
            discharge_lng = port.get('lng', 0)
            break
            
    return jsonify({
        "vessels": results,
        "largest_vessel": largest_vessel['class_name'],
        "analysis": analysis,
        "weather_detour_active": weather_detour_active,
        "max_wave_height": round(max_wave_height, 2) if max_wave_height else 0,
        "cargo_capped": cargo_capped,
        "original_request": original_request,
        "capped_volume": capped_volume,
        "route_coordinates": {
            "origin": [origin_lat, origin_lng],
            "discharge": [discharge_lat, discharge_lng]
        }
    })
