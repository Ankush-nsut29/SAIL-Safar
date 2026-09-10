# services/predictors/fuel_predictor.py
"""
Bunker Fuel Predictor for SAIL Safar
------------------------------------
Ingests & cleans Daily_Bunker_Fuel_Prices.csv
Combines Linear Regression (PS Requirement) + XGBoost Regressor
to predict future VLSFO, MGO, and IFO fuel prices.
"""

import os
import warnings
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')


class FuelPredictor:
    # Regional price spread vs baseline hub (USD / Metric Ton)
    REGIONAL_SPREAD = {
        'Singapore': 0.0,
        'Indonesia': 10.0,
        'Australia': 30.0,
        'India_East': 35.0,
        'Fujairah': 15.0
    }

    # Vessel Engine Physics: Fuel burn per day (Metric Tons)
    VESSEL_BURN_RATES = {
        'Capesize':  {'sea': 45.0, 'port': 5.0},
        'Panamax':   {'sea': 32.0, 'port': 4.0},
        'Supramax':  {'sea': 26.0, 'port': 3.5},
        'Handysize': {'sea': 22.0, 'port': 3.0}
    }

    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.csv_path = os.path.join(data_dir, 'Daily_Bunker_Fuel_Prices.csv')
        self.models = {}
        self.scalers = {}
        self.feature_cols = []
        self.last_known_data = {}
        self.is_trained = False

    def _clean_price_series(self, series):
        """Removes $, quotes, commas, and converts to float."""
        cleaned = (
            series.astype(str)
            .str.replace('$', '', regex=False)
            .str.replace('"', '', regex=False)
            .str.replace(',', '', regex=False)
            .str.strip()
        )
        return pd.to_numeric(cleaned, errors='coerce')

    def load_and_clean_data(self):
        """Parses your exact Daily_Bunker_Fuel_Prices.csv format."""
        if not os.path.exists(self.csv_path):
            raise FileNotFoundError(f"CSV file not found at: {self.csv_path}")

        df = pd.read_csv(self.csv_path)

        # 1. Clean Column Names (strip whitespace & quotes)
        df.columns = [c.replace('"', '').strip() for c in df.columns]

        # 2. Parse Date from "Day" column (which contains "01/29/2019" format)
        date_col = next((c for c in df.columns if 'day' in c.lower() or 'date' in c.lower()), df.columns[0])
        df['Parsed_Date'] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=['Parsed_Date']).sort_values('Parsed_Date').reset_index(drop=True)

        # 3. Clean Target Fuel Price Columns
        vlsfo_col = next((c for c in df.columns if 'vlsfo' in c.lower()), None)
        mgo_col   = next((c for c in df.columns if 'marine gas' in c.lower() or 'mgo' in c.lower()), None)
        ifo_col   = next((c for c in df.columns if 'interm' in c.lower() or 'ifo' in c.lower()), None)

        processed_df = pd.DataFrame({'Date': df['Parsed_Date']})

        if vlsfo_col:
            processed_df['VLSFO'] = self._clean_price_series(df[vlsfo_col])
        if mgo_col:
            processed_df['MGO'] = self._clean_price_series(df[mgo_col])
        if ifo_col:
            processed_df['IFO'] = self._clean_price_series(df[ifo_col])

        # Forward fill missing weekend/holiday rows
        processed_df = processed_df.ffill().bfill()
        return processed_df

    def _engineer_features(self, df, target_col):
        """Creates lag and momentum features for ML models."""
        data = df[['Date', target_col]].copy().rename(columns={target_col: 'Price'})
        data = data.dropna()

        data['day_of_week'] = data['Date'].dt.dayofweek
        data['month'] = data['Date'].dt.month
        data['quarter'] = data['Date'].dt.quarter
        data['day_of_year'] = data['Date'].dt.dayofyear
        data['year'] = data['Date'].dt.year

        # Lags
        for lag in [1, 3, 5, 7, 14, 30]:
            data[f'lag_{lag}'] = data['Price'].shift(lag)

        # Rolling Averages & Volatility
        for w in [7, 14, 30]:
            data[f'roll_mean_{w}'] = data['Price'].rolling(w).mean()
            data[f'roll_std_{w}']  = data['Price'].rolling(w).std()

        # Price Momentum
        data['momentum_7']  = data['Price'] - data['Price'].shift(7)
        data['momentum_30'] = data['Price'] - data['Price'].shift(30)

        return data.dropna().reset_index(drop=True)

    def train(self):
        """
        Trains Linear Regression + XGBoost Ensemble on fuel price history.
        """
        df = self.load_and_clean_data()
        fuel_grades = [col for col in ['VLSFO', 'MGO', 'IFO'] if col in df.columns]

        for grade in fuel_grades:
            feat_df = self._engineer_features(df, grade)
            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Price')]

            X = feat_df[feature_cols].values
            y = feat_df['Price'].values

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # ====================================================
            # MODEL 1: LINEAR REGRESSION (PS Requirement)
            # ====================================================
            lr_model = LinearRegression()
            lr_model.fit(X_scaled, y)

            # ====================================================
            # MODEL 2: XGBOOST REGRESSOR (Advanced Spike Model)
            # ====================================================
            xgb_model = XGBRegressor(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                random_state=42
            )
            xgb_model.fit(X_scaled, y)

            # Save models and features
            self.models[f'{grade}_lr']  = lr_model
            self.models[f'{grade}_xgb'] = xgb_model
            self.scalers[grade]        = scaler
            self.models[f'{grade}_cols'] = feature_cols
            self.last_known_data[grade]  = feat_df.tail(60)

        self.is_trained = True
        return self

    def predict_bunker_price(self, fuel_type='VLSFO', region='Singapore', target_date=None, user_override=None):
        """
        Predicts future bunker fuel price using Ensemble:
        Final Price = 40% (Linear Regression) + 60% (XGBoost)
        """
        if user_override and float(user_override) > 0:
            return {
                'fuel_type': fuel_type,
                'region': region,
                'predicted_price_per_mt': round(float(user_override), 2),
                'method': 'user_override'
            }

        if not self.is_trained:
            self.train()

        if target_date is None:
            target_date = datetime.now() + timedelta(days=14)
        target_date = pd.Timestamp(target_date)

        # Select target grade
        grade_key = 'VLSFO'
        if 'mgo' in fuel_type.lower():
            grade_key = 'MGO'
        elif 'ifo' in fuel_type.lower() or 'hsfo' in fuel_type.lower():
            grade_key = 'IFO'

        if grade_key not in self.last_known_data:
            grade_key = list(self.last_known_data.keys())[0]

        last_df = self.last_known_data[grade_key]
        recent_prices = last_df['Price'].values

        # Build feature vector for target date
        feat = {
            'day_of_week': target_date.dayofweek,
            'month': target_date.month,
            'quarter': target_date.quarter,
            'day_of_year': target_date.timetuple().tm_yday,
            'year': target_date.year,
        }
        for lag in [1, 3, 5, 7, 14, 30]:
            feat[f'lag_{lag}'] = recent_prices[-min(lag, len(recent_prices))]
        for w in [7, 14, 30]:
            sl = recent_prices[-min(w, len(recent_prices)):]
            feat[f'roll_mean_{w}'] = float(np.mean(sl))
            feat[f'roll_std_{w}']  = float(np.std(sl))

        feat['momentum_7']  = float(recent_prices[-1] - recent_prices[-min(7, len(recent_prices))])
        feat['momentum_30'] = float(recent_prices[-1] - recent_prices[-min(30, len(recent_prices))])

        cols = self.models[f'{grade_key}_cols']
        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[grade_key].transform(X_pred)

        # 1. Linear Regression Prediction
        lr_pred = float(self.models[f'{grade_key}_lr'].predict(X_scaled)[0])

        # 2. XGBoost Prediction
        xgb_pred = float(self.models[f'{grade_key}_xgb'].predict(X_scaled)[0])

        # 3. Weighted Ensemble (40% Linear Regression + 60% XGBoost)
        base_predicted_price = (0.40 * lr_pred) + (0.60 * xgb_pred)

        # Apply Regional Price Spread
        regional_adj = self.REGIONAL_SPREAD.get(region, 0.0)
        final_price = base_predicted_price + regional_adj

        return {
            'fuel_type': fuel_type,
            'region': region,
            'predicted_price_per_mt': round(final_price, 2),
            'model_breakdown': {
                'linear_regression_price': round(lr_pred + regional_adj, 2),
                'xgboost_price': round(xgb_pred + regional_adj, 2),
                'ensemble_blend_price': round(final_price, 2),
            },
            'target_date': str(target_date.date())
        }

    def calculate_voyage_fuel_cost(self, vessel_class, transit_days, port_days=5.0, fuel_price_input=None, origin_port=''):
        """Calculates total voyage fuel burn and cost."""
        region = 'Singapore'
        if any(k in origin_port.lower() for k in ['gladstone', 'australia']):
            region = 'Australia'
        elif any(k in origin_port.lower() for k in ['haldia', 'paradip', 'vizag']):
            region = 'India_East'

        price_info = self.predict_bunker_price(region=region, user_override=fuel_price_input)
        px_per_mt = price_info['predicted_price_per_mt']

        burn = self.VESSEL_BURN_RATES.get(vessel_class, self.VESSEL_BURN_RATES['Panamax'])
        sea_burn_mt  = burn['sea'] * float(transit_days)
        port_burn_mt = burn['port'] * float(port_days)
        total_fuel_mt = sea_burn_mt + port_burn_mt

        total_cost_usd = total_fuel_mt * px_per_mt

        return {
            'total_fuel_cost_usd': round(total_cost_usd, 2),
            'total_fuel_mt': round(total_fuel_mt, 1),
            'sea_burn_mt': round(sea_burn_mt, 1),
            'port_burn_mt': round(port_burn_mt, 1),
            'price_per_mt_used': px_per_mt,
            'price_details': price_info
        }