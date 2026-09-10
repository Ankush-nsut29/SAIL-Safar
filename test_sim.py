from services.calculator import run_voyage_simulation
import json

try:
    print("Testing run_voyage_simulation...")
    res = run_voyage_simulation({
        'origin_port': 'Gladstone Port (RG Tanna Coal Terminal)',
        'discharge_port': 'Visakhapatnam Port',
        'vessel_class': 'Capesize',
        'cargo_volume': 50000,
        'contract_window_days': 30,
        'transit_days': 16.0
    })
    print("Simulation SUCCESS!")
    print("Keys:", list(res.keys()))
except Exception as e:
    import traceback
    traceback.print_exc()
