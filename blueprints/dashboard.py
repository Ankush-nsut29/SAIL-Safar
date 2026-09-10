from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from services.data_loader import get_eastcoast_ports, get_foreign_ports, get_vessels, load_csv_as_dataframe, get_routes
import requests
from services.vessel_engine import check_feasibility
from services.calculator import run_voyage_simulation
import os
from openai import OpenAI

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
        return jsonify({"error": "Your session has expired. Please log in again."}), 401
        
    try:
        data = request.json or {}
        origin_port = data.get('origin_port')
        discharge_port = data.get('discharge_port')
        cargo_volume = data.get('cargo_volume') or 0
        contract_window_days = data.get('contract_window_days') or 30
    
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
            
    # Determine baseline transit days based on origin
    if origin_country == "Australia":
        transit_days = 16.0
    elif origin_country == "Indonesia":
        transit_days = 7.5
    else:
        transit_days = 12.0

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
    
    voyage_data = {
        'origin_port': origin_port,
        'discharge_port': discharge_port,
        'vessel_class': largest_vessel['class_name'],
        'cargo_volume': used_cargo_volume,
        'contract_window_days': contract_window_days,
        'transit_days': transit_days
    }
    
    ml_results = run_voyage_simulation(voyage_data)
    
    prompt_payload = f"""
    Voyage Data:
    - Route: {origin_port} to {discharge_port}
    - Vessel: {largest_vessel['class_name']}
    - Cargo: {used_cargo_volume} MT
    - Contract Window: {contract_window_days} Days
    
    ML Predictions:
    - Predicted Daily Freight Rate: ${ml_results['predicted_freight_rate']}/day
    - Total Fuel Cost: ${ml_results['total_fuel_cost']}
    - Port & Demurrage Costs: ${ml_results['total_port_cost']}
    - Est. Weather Delay: {ml_results['weather_delay_days']} days
    - Market Skewness: {ml_results['skewness']}
    - Total Estimated Landed Cost: ${ml_results['landed_cost_per_mt']}/MT
    """
    
    import json
    ai_advisory_json = {}
    try:
        client = OpenAI(api_key=os.getenv("GROQ_API_KEY", ""), base_url="https://api.groq.com/openai/v1")
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are an elite maritime procurement advisor for SAIL. Output ONLY a valid JSON object with three exact keys: 'recommended_contract' (String: 'Spot Voyage Charter' or 'Period Time Charter'), 'optimal_timing' (String: e.g., 'Immediate'), and 'strategic_rationale' (String: 2-3 sentences explaining the trade-off based on the math)."},
                {"role": "user", "content": prompt_payload}
            ]
        )
        ai_advisory_json = json.loads(response.choices[0].message.content.strip())
    except Exception as e:
        print(f"Groq API Error: {e}")
        if ml_results['skewness'] > 0.5:
            ai_advisory_json = {
                "recommended_contract": "Period Time Charter",
                "optimal_timing": "Immediate",
                "strategic_rationale": "Based on high market volatility and positive skewness, a Period Time Charter is strongly recommended to hedge against rate spikes. Expected landed cost is highly sensitive to current port congestion and weather delays. Lock in long-term tonnage to stabilize procurement costs."
            }
        else:
            ai_advisory_json = {
                "recommended_contract": "Spot Voyage Charter",
                "optimal_timing": "Within 7 Days",
                "strategic_rationale": "Market conditions show stable or negative skewness, making a Spot Voyage Charter the optimal strategy. Current predicted landed costs indicate favorable spot availability for this vessel class. Proceed with spot fixing to capture short-term value."
            }

    ml_results['ai_advisory'] = ai_advisory_json
    
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
            "ml_results": ml_results,
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
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

