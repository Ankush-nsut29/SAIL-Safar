from flask import Blueprint, render_template, session, redirect, url_for, request, jsonify
from services.data_loader import get_eastcoast_ports, get_foreign_ports, get_vessels, load_csv_as_dataframe
from services.vessel_engine import check_feasibility
from services.calculator import calculate_route_stats

dashboard_bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

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
        
    df = load_csv_as_dataframe(largest_vessel['class_name'])
    
    analysis = calculate_route_stats(largest_vessel, contract_window_days, transit_days, cargo_volume, fuel_price, df)
    
    return jsonify({
        "vessels": results,
        "largest_vessel": largest_vessel['class_name'],
        "analysis": analysis
    })
