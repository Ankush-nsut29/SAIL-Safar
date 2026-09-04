def check_feasibility(origin_port_name, discharge_port_name, vessels_data, foreign_ports_data, eastcoast_ports_data):
    origin = next((p for p in foreign_ports_data if p['port_name'] == origin_port_name), None)
    discharge = next((p for p in eastcoast_ports_data if p['port_name'] == discharge_port_name), None)
    
    if not origin or not discharge:
        return [], None

    origin_draft = origin['max_draft_meters']
    origin_loa = origin['max_loa_meters']
    discharge_draft = discharge['max_draft_meters']
    discharge_loa = discharge['max_loa_meters']

    min_draft = min(origin_draft, discharge_draft)
    min_loa = min(origin_loa, discharge_loa)
    
    origin_allowed = origin.get('allowed_vessel_classes', [])
    discharge_allowed = discharge.get('allowed_vessel_classes', [])

    results = []
    largest_feasible = None

    for v in vessels_data:
        is_feasible = True
        status = "Feasible"
        
        if v['max_draft_meters'] > min_draft:
            is_feasible = False
            status = "Draft Exceeded"
        elif v['max_loa_meters'] > min_loa:
            is_feasible = False
            status = "LOA Exceeded"
        elif v['class_name'] not in origin_allowed or v['class_name'] not in discharge_allowed:
            is_feasible = False
            status = "Class Not Allowed at Port"
            
        results.append({
            "class_name": v['class_name'],
            "status": status,
            "dwt": v['typical_dwt_capacity_mt'],
            "draft": v['max_draft_meters'],
            "loa": v['max_loa_meters'],
            "fuel_consumption": v['fuel_consumption_tons_day']
        })
        
        if is_feasible:
            if largest_feasible is None or v['typical_dwt_capacity_mt'] > largest_feasible['typical_dwt_capacity_mt']:
                largest_feasible = v
                
    return results, largest_feasible
