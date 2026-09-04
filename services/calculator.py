import pandas as pd
import numpy as np

def calculate_route_stats(largest_vessel, contract_window_days, transit_days, cargo_volume, fuel_price, historical_df):
    if historical_df.empty or largest_vessel is None:
        return {}
        
    contract_window_days = int(contract_window_days)
    transit_days = float(transit_days)
    cargo_volume = float(cargo_volume)
    fuel_price = float(fuel_price)
    
    df_slice = historical_df.tail(contract_window_days)
    
    if 'Price' in df_slice.columns:
        prices = df_slice['Price']
    else:
        return {}
        
    mean_price = prices.mean()
    var_price = prices.var()
    skew_price = prices.skew()
    kurt_price = prices.kurt()
    
    total_voyage_days = (transit_days * 2) + 4
    vessel_fuel_consumption = largest_vessel['fuel_consumption_tons_day']
    total_fuel_cost = total_voyage_days * vessel_fuel_consumption * fuel_price
    
    landed_cost_per_mt = ((mean_price * total_voyage_days) + total_fuel_cost) / cargo_volume
    
    if skew_price > 0.5:
        recommendation = "Market is volatile and skewed positively. We recommend a Period Time Charter to lock in rates."
        decision_type = "Period Time Charter"
    else:
        recommendation = "Market is relatively stable or favorable. Spot Voyage Charter is recommended."
        decision_type = "Spot Voyage Charter"
        
    dates = df_slice['Date'].tolist() if 'Date' in df_slice.columns else list(range(len(df_slice)))
    
    # Handle NaN in case of too small window for stats
    var_price = 0 if np.isnan(var_price) else var_price
    skew_price = 0 if np.isnan(skew_price) else skew_price
    kurt_price = 0 if np.isnan(kurt_price) else kurt_price
    
    return {
        "recommendation": recommendation,
        "decision_type": decision_type,
        "stats": {
            "mean": round(mean_price, 2),
            "variance": round(var_price, 2),
            "skewness": round(skew_price, 2),
            "kurtosis": round(kurt_price, 2),
            "landed_cost_per_mt": round(landed_cost_per_mt, 2)
        },
        "chart_data": {
            "labels": dates,
            "values": prices.tolist()
        }
    }
