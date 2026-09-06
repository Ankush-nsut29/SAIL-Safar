import os
import json
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')

def load_json_file(filename):
    filepath = os.path.join(DATA_DIR, filename)
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return {}

def get_eastcoast_ports():
    data = load_json_file('eastcoast_ports.json')
    return data.get('east_coast_ports', [])

def get_foreign_ports():
    data = load_json_file('foriegnports.json')
    return data.get('foreign_export_ports', [])

def get_vessels():
    data = load_json_file('vessels.json')
    return data.get('vessel_classes', [])

def get_routes():
    data = load_json_file('routes.json')
    return data.get('voyage_routes', [])

def load_csv_as_dataframe(vessel_class):
    filepath = os.path.join(DATA_DIR, f'Cleaned_{vessel_class}.csv')
    try:
        df = pd.read_csv(filepath)
        if 'Price' in df.columns:
            df['Price'] = df['Price'].astype(str).str.replace(',', '').astype(float)
        # Assuming date is descending, reverse it for chronological charts
        df = df.iloc[::-1].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return pd.DataFrame()
