import pandas as pd
import numpy as np
from services.predictors import (
    FreightRatePredictor, FuelPredictor, CommodityPredictor, 
    WeatherPredictor, PortPredictor, DemandPredictor
)

# Instantiate models at module level to avoid retraining on every request
freight_pred = FreightRatePredictor()
fuel_pred = FuelPredictor()
weather_pred = WeatherPredictor()
port_pred = PortPredictor()
demand_pred = DemandPredictor()
commodity_pred = CommodityPredictor()

def run_voyage_simulation(voyage_data):
    vessel_class = voyage_data.get('vessel_class', 'Panamax')
    origin = voyage_data.get('origin_port', '')
    discharge = voyage_data.get('discharge_port', 'Paradip Port')
    cargo = voyage_data.get('cargo_volume', 55000)
    window = voyage_data.get('contract_window_days', 30)
    user_fuel = voyage_data.get('fuel_price', 600)
    transit_days = voyage_data.get('transit_days', 15)
    
    target_date = pd.Timestamp.now() + pd.Timedelta(days=14)

    # Execute Predictors
    freight_res = freight_pred.predict_rate(vessel_class=vessel_class, target_date=target_date)
    stats_res = freight_pred.get_stats(vessel_class=vessel_class, window=window)
    fuel_res = fuel_pred.calculate_voyage_fuel_cost(vessel_class=vessel_class, transit_days=transit_days, port_days=5.0, fuel_price_input=user_fuel, origin_port=origin)
    weather_res = weather_pred.predict(voyage_date=target_date, origin=origin, destination=discharge)
    port_res = port_pred.predict_port_costs(port_name=discharge, vessel_class=vessel_class, cargo_mt=cargo, target_date=target_date)
    demand_res = demand_pred.predict_demand(commodity='coking_coal', plant='Bhilai Steel Plant', target_date=target_date, contract_days=window)
    commodity_res = commodity_pred.predict(commodity='coking_coal', target_date=target_date, cargo_mt=cargo)

    # Calculate Totals
    total_voyage_days = (transit_days * 2) + 4 + weather_res['predicted_delay_days']
    freight_voyage_cost = freight_res['predicted_rate'] * total_voyage_days
    
    total_estimated_cost_usd = freight_voyage_cost + fuel_res['total_fuel_cost_usd'] + port_res['total_port_cost_usd']
    landed_cost_per_mt = total_estimated_cost_usd / max(cargo, 1.0)

    ml_results = {
        'freight': freight_res,
        'stats': stats_res,
        'fuel': fuel_res,
        'weather': weather_res,
        'port': port_res,
        'demand': demand_res,
        'commodity': commodity_res,
        
        # Extracted key metrics for UI cards
        'predicted_freight_rate': freight_res['predicted_rate'],
        'mean_rate': stats_res['mean_rate'],
        'variance': stats_res['variance'],
        'skewness': stats_res['skewness'],
        'kurtosis': stats_res['kurtosis'],
        'chart_data': stats_res['chart_data'],
        'forecast_data': freight_pred.forecast_series(vessel_class=vessel_class, days=window),
        
        'weather_delay_days': weather_res['predicted_delay_days'],
        'weather_message': weather_res['message'],
        
        'total_fuel_cost': round(fuel_res['total_fuel_cost_usd'], 2),
        'total_port_cost': round(port_res['total_port_cost_usd'], 2),
        'demurrage_risk': port_res['expected_demurrage_cost_usd'],
        
        'total_estimated_cost_usd': round(total_estimated_cost_usd, 2),
        'landed_cost_per_mt': round(landed_cost_per_mt, 2),
        'total_voyage_days': round(total_voyage_days, 1)
    }
    return ml_results
