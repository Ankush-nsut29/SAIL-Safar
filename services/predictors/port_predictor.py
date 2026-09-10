# services/predictors/port_predictor.py
"""
SAIL Safar — Port Charges, Demurrage Risk & Draft Feasibility Predictor
----------------------------------------------------------------------
- Auto-generates dataset 'data/port_congestion_historical.csv' if missing.
- Models: Linear Regression (PS Requirement) + XGBoost Regressor.
- Predicts port waiting time (days), demurrage cost, and port dues.
- Evaluates Vessel Draft Feasibility Matrix (Haldia, Paradip, Vizag, etc.).
- Chronological Split: 70% Train, 15% Validation, 15% Test.
- Metrics: Calculates R², RMSE, MAE, MAPE on unseen test set.
"""

import os
import math
import warnings
import numpy as np
import pandas as pd
from datetime import datetime

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')


def ensure_dataset_exists(data_path='data/port_congestion_historical.csv'):
    """Generates clean historical port waiting time & congestion dataset if missing."""
    if os.path.exists(data_path):
        return

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    print(f"📦 Generating historical port congestion dataset at '{data_path}'...")

    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='D')
    ports = ['Haldia Dock Complex', 'Paradip Port', 'Vizag Port', 'Dhamra Port', 'Hay Point Coal Terminal', 'Taboneo Anchorage']

    rows = []
    for dt in dates:
        month = dt.month
        for port in ports:
            # High congestion during Q4 & Q1 (peak import season) and monsoon
            base_wait = 3.0 if 'Haldia' in port else (2.0 if 'Paradip' in port else 1.5)
            seasonal_mult = 1.35 if month in [10, 11, 12, 1, 2] else (1.20 if month in [6, 7, 8, 9] else 0.90)

            vessel_queue = int(np.random.poisson(5 * seasonal_mult))
            cargo_traffic_kmt = np.random.uniform(40, 120) * seasonal_mult

            wait_days = base_wait * seasonal_mult + (vessel_queue * 0.15) + (cargo_traffic_kmt * 0.005) + np.random.normal(0, 0.2)
            wait_days = max(0.2, wait_days)

            rows.append({
                'Date': dt.strftime('%Y-%m-%d'),
                'Month': month,
                'Port_Name': port,
                'Vessels_In_Queue': vessel_queue,
                'Cargo_Traffic_KMT': round(cargo_traffic_kmt, 1),
                'Waiting_Days': round(wait_days, 2)
            })

    df = pd.DataFrame(rows)
    df.to_csv(data_path, index=False)
    print(f"✓ Port congestion dataset created successfully ({len(df)} records).")


class PortPredictor:

    # Draft depth limits (meters) for Indian and Foreign ports
    PORT_DRAFT_LIMITS = {
        'Haldia Dock Complex': 8.5,     # Shallow riverine port
        'Paradip Port': 14.5,           # Deep water port
        'Vizag Port': 14.0,             # Deep water port
        'Dhamra Port': 17.5,            # Deep water port
        'Hay Point Coal Terminal': 18.0,# Australia loading terminal
        'Taboneo Anchorage': 15.0       # Indonesia loading anchorage
    }

    # Vessel Class Physical Specs
    VESSEL_SPECS = {
        'Handysize': {'dwt': 35000,  'draft': 10.0, 'grt': 18000, 'demurrage_rate': 9000},
        'Supramax':  {'dwt': 58000,  'draft': 12.8, 'grt': 32000, 'demurrage_rate': 12000},
        'Panamax':   {'dwt': 75000,  'draft': 14.5, 'grt': 45000, 'demurrage_rate': 15000},
        'Capesize':  {'dwt': 180000, 'draft': 18.5, 'grt': 95000, 'demurrage_rate': 25000}
    }

    # Official Port Tariff Schedules
    PORT_TARIFFS = {
        'Haldia Dock Complex': {'dues_grt': 0.15, 'fixed': 22500, 'handling_mt': 3.50},
        'Paradip Port':        {'dues_grt': 0.12, 'fixed': 18000, 'handling_mt': 3.00},
        'Vizag Port':          {'dues_grt': 0.13, 'fixed': 19500, 'handling_mt': 3.20},
        'Dhamra Port':         {'dues_grt': 0.11, 'fixed': 16000, 'handling_mt': 2.80},
        'Hay Point Coal Terminal': {'dues_grt': 0.10, 'fixed': 15000, 'handling_mt': 2.50},
        'Taboneo Anchorage':   {'dues_grt': 0.08, 'fixed': 12000, 'handling_mt': 2.00},
        'default':             {'dues_grt': 0.12, 'fixed': 18000, 'handling_mt': 3.00}
    }

    def __init__(self, data_path='data/port_congestion_historical.csv', random_state=42):
        self.data_path = data_path
        self.random_state = random_state
        self.data = {}
        self.models = {}
        self.scalers = {}
        self.feature_columns = {}
        self.ensemble_weights = {}
        self.evaluation_results = {}
        self.is_trained = False

    def load_data(self):
        ensure_dataset_exists(self.data_path)
        df = pd.read_csv(self.data_path)
        df['Date'] = pd.to_datetime(df['Date'])

        for port, port_df in df.groupby('Port_Name'):
            cleaned = port_df.sort_values('Date').reset_index(drop=True)
            self.data[port] = cleaned

        return self

    @staticmethod
    def _engineer_features(df):
        data = df.copy().sort_values('Date').reset_index(drop=True)
        month = data['Date'].dt.month

        data['month_sin'] = np.sin(2 * np.pi * month / 12)
        data['month_cos'] = np.cos(2 * np.pi * month / 12)
        data['is_peak_season'] = month.isin([10, 11, 12, 1, 2]).astype(int)

        # Lags & Rolling Averages of Queue and Traffic
        for col in ['Vessels_In_Queue', 'Cargo_Traffic_KMT', 'Waiting_Days']:
            for lag in [1, 3, 7]:
                data[f'{col}_lag_{lag}'] = data[col].shift(lag)
            data[f'{col}_roll_7'] = data[col].shift(1).rolling(7).mean()

        return data.dropna().reset_index(drop=True)

    @staticmethod
    def _calculate_metrics(actual, predicted):
        actual = np.asarray(actual, dtype=float)
        predicted = np.asarray(predicted, dtype=float)

        rmse = math.sqrt(mean_squared_error(actual, predicted))
        mae = mean_absolute_error(actual, predicted)
        non_zero = np.abs(actual) > 1e-4
        mape = np.mean(np.abs((actual[non_zero] - predicted[non_zero]) / actual[non_zero])) * 100 if non_zero.any() else 0.0
        r2 = r2_score(actual, predicted) if len(actual) >= 2 else np.nan

        return {
            'r2': round(float(r2), 4),
            'rmse_days': round(float(rmse), 4),
            'mae_days': round(float(mae), 4),
            'mape_percent': round(float(mape), 4),
        }

    def train(self):
        """Trains Linear Regression (PS Req) + XGBoost for port waiting time prediction."""
        if not self.data:
            self.load_data()

        print("\n" + "=" * 65)
        print(" TRAINING PORT & DEMURRAGE PREDICTOR (LINEAR REGRESSION + XGBOOST) ")
        print("=" * 65)

        for port, raw_df in self.data.items():
            feat_df = self._engineer_features(raw_df)

            if len(feat_df) < 40:
                continue

            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Port_Name', 'Waiting_Days')]
            X = feat_df[feature_cols].values
            y = feat_df['Waiting_Days'].values

            # 70% Train, 15% Validation, 15% Test
            train_end = int(len(X) * 0.70)
            val_end = int(len(X) * 0.85)

            X_train, y_train = X[:train_end], y[:train_end]
            X_val, y_val = X[train_end:val_end], y[train_end:val_end]
            X_test, y_test = X[val_end:], y[val_end:]

            scaler = StandardScaler()
            X_train_s = scaler.fit_transform(X_train)
            X_val_s = scaler.transform(X_val)
            X_test_s = scaler.transform(X_test)

            # MODEL 1: LINEAR REGRESSION (PS REQUIREMENT)
            lr_eval = LinearRegression()
            lr_eval.fit(X_train_s, y_train)

            # MODEL 2: XGBOOST REGRESSOR
            xgb_eval = XGBRegressor(
                n_estimators=150,
                max_depth=4,
                learning_rate=0.05,
                subsample=0.8,
                random_state=self.random_state,
                n_jobs=2
            )
            xgb_eval.fit(X_train_s, y_train)

            # Inverse-RMSE Validation Weighting
            val_lr = lr_eval.predict(X_val_s)
            val_xgb = xgb_eval.predict(X_val_s)

            rmse_lr = math.sqrt(mean_squared_error(y_val, val_lr))
            rmse_xgb = math.sqrt(mean_squared_error(y_val, val_xgb))

            inv_lr = 1.0 / max(rmse_lr, 1e-8)
            inv_xgb = 1.0 / max(rmse_xgb, 1e-8)
            w_lr = inv_lr / (inv_lr + inv_xgb)
            w_xgb = inv_xgb / (inv_lr + inv_xgb)

            # Unseen Test Evaluation
            test_lr = lr_eval.predict(X_test_s)
            test_xgb = xgb_eval.predict(X_test_s)
            test_ensemble = (w_lr * test_lr) + (w_xgb * test_xgb)

            metrics_ensemble = self._calculate_metrics(y_test, test_ensemble)

            self.evaluation_results[port] = {
                'linear_regression': self._calculate_metrics(y_test, test_lr),
                'xgboost': self._calculate_metrics(y_test, test_xgb),
                'ensemble': metrics_ensemble,
                'weights': {'linear_regression': round(w_lr, 4), 'xgboost': round(w_xgb, 4)}
            }

            # Refit Production Models on 100% Data
            scaler_final = StandardScaler()
            X_all_s = scaler_final.fit_transform(X)

            lr_final = LinearRegression()
            lr_final.fit(X_all_s, y)

            xgb_final = XGBRegressor(n_estimators=150, max_depth=4, learning_rate=0.05, random_state=self.random_state)
            xgb_final.fit(X_all_s, y)

            self.models[f"{port}_linear"] = lr_final
            self.models[f"{port}_xgboost"] = xgb_final
            self.scalers[port] = scaler_final
            self.feature_columns[port] = feature_cols
            self.ensemble_weights[port] = {'linear_regression': w_lr, 'xgboost': w_xgb}

            print(f"  ✓ {port:<25} | R²: {metrics_ensemble['r2']:.4f} | RMSE: {metrics_ensemble['rmse_days']:.2f} days | Weights: [LR: {w_lr:.2f}, XGB: {w_xgb:.2f}]")

        self.is_trained = True
        return self

    def _match_port_key(self, port_name):
        name_l = str(port_name).lower()
        for k in self.data.keys():
            if k.lower() in name_l or name_l in k.lower():
                return k
        for k in self.PORT_DRAFT_LIMITS.keys():
            if k.lower() in name_l or name_l in k.lower():
                return k
        return 'Paradip Port'

    def predict_port_costs(self, port_name, vessel_class='Panamax', cargo_mt=55000, target_date=None):
        """
        Predicts total port dues, waiting time, and demurrage exposure.
        """
        if not self.is_trained:
            self.train()

        port_key = self._match_port_key(port_name)

        if target_date is None:
            target_date = pd.Timestamp.now() + pd.Timedelta(days=14)
        target_date = pd.Timestamp(target_date)
        month = target_date.month

        df_port = self.data.get(port_key, list(self.data.values())[0])
        last_row = df_port.iloc[-1]
        cols = self.feature_columns[port_key]

        feat = {
            'month_sin': np.sin(2 * np.pi * month / 12),
            'month_cos': np.cos(2 * np.pi * month / 12),
            'is_peak_season': 1 if month in [10, 11, 12, 1, 2] else 0,
            'Vessels_In_Queue': float(last_row['Vessels_In_Queue']),
            'Cargo_Traffic_KMT': float(last_row['Cargo_Traffic_KMT']),
            'Waiting_Days': float(last_row['Waiting_Days']),
        }

        for c_name in ['Vessels_In_Queue', 'Cargo_Traffic_KMT', 'Waiting_Days']:
            for lag in [1, 3, 7]:
                feat[f'{c_name}_lag_{lag}'] = float(last_row[c_name])
            feat[f'{c_name}_roll_7'] = float(df_port[c_name].tail(7).mean())

        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[port_key].transform(X_pred)

        pred_lr = float(self.models[f"{port_key}_linear"].predict(X_scaled)[0])
        pred_xgb = float(self.models[f"{port_key}_xgboost"].predict(X_scaled)[0])

        w_lr = self.ensemble_weights[port_key]['linear_regression']
        w_xgb = self.ensemble_weights[port_key]['xgboost']

        predicted_waiting_days = max(0.2, (w_lr * pred_lr) + (w_xgb * pred_xgb))

        # Financial Port Dues & Demurrage Calculation
        vessel_spec = self.VESSEL_SPECS.get(vessel_class, self.VESSEL_SPECS['Panamax'])
        tariff = self.PORT_TARIFFS.get(port_key, self.PORT_TARIFFS['default'])

        grt = vessel_spec['grt']
        port_dues = tariff['dues_grt'] * grt
        cargo_handling = tariff['handling_mt'] * float(cargo_mt)
        fixed_charges = tariff['fixed']

        # Demurrage Risk = Expected Waiting Days × Daily Demurrage Rate
        demurrage_daily_rate = vessel_spec['demurrage_rate']
        expected_demurrage_cost = predicted_waiting_days * demurrage_daily_rate

        total_port_cost = port_dues + cargo_handling + fixed_charges + expected_demurrage_cost

        return {
            'port_name': port_key,
            'vessel_class': vessel_class,
            'cargo_mt': float(cargo_mt),
            'predicted_waiting_days': round(predicted_waiting_days, 2),
            'demurrage_daily_rate_usd': demurrage_daily_rate,
            'expected_demurrage_cost_usd': round(expected_demurrage_cost, 2),
            'total_port_cost_usd': round(total_port_cost, 2),
            'breakdown': {
                'port_dues': round(port_dues, 2),
                'cargo_handling': round(cargo_handling, 2),
                'fixed_charges': round(fixed_charges, 2),
                'demurrage_risk': round(expected_demurrage_cost, 2)
            },
            'model_breakdown': {
                'linear_regression_days': round(max(0.0, pred_lr), 2),
                'xgboost_days': round(max(0.0, pred_xgb), 2),
                'ensemble_waiting_days': round(predicted_waiting_days, 2)
            },
            'test_metrics': self.evaluation_results[port_key]['ensemble']
        }

    def evaluate_vessel_feasibility(self, discharge_port, cargo_mt):
        """
        Evaluates Port Channel Draft Limit vs Vessel Required Draft.
        Generates the status rows for your UI Feasibility Table.
        """
        port_key = self._match_port_key(discharge_port)
        max_port_draft = self.PORT_DRAFT_LIMITS.get(port_key, 14.5)
        cargo_mt = float(cargo_mt)

        matrix = []
        for vclass, specs in self.VESSEL_SPECS.items():
            req_draft = specs['draft']
            dwt = specs['dwt']

            if req_draft > max_port_draft:
                status = "Draft Exceeded"
                css_class = "danger"
            elif cargo_mt > dwt * 1.1:
                status = "Cargo Exceeds Capacity"
                css_class = "warning"
            elif cargo_mt < dwt * 0.3:
                status = "Uneconomical Size"
                css_class = "secondary"
            else:
                status = "Feasible"
                css_class = "success"

            matrix.append({
                'vessel_class': vclass,
                'dwt_capacity': f"{dwt:,}",
                'required_draft': req_draft,
                'port_max_draft': max_port_draft,
                'status': status,
                'css_class': css_class
            })

        return matrix


if __name__ == '__main__':
    predictor = PortPredictor()
    predictor.train()

    print("\n--- SAMPLE PORT PREDICTION DEMO ---")
    res = predictor.predict_port_costs(port_name='Haldia Dock Complex', vessel_class='Panamax', cargo_mt=55000)
    print(f"Port Name:              {res['port_name']}")
    print(f"Vessel Class:           {res['vessel_class']}")
    print(f"Predicted Waiting Time: {res['predicted_waiting_days']} Days")
    print(f"Demurrage Exposure:     ${res['expected_demurrage_cost_usd']:,.2f} (@ ${res['demurrage_daily_rate_usd']:,}/day)")
    print(f"Total Port Charges:     ${res['total_port_cost_usd']:,.2f}")
    print(f"Model Breakdown:        Linear Reg: {res['model_breakdown']['linear_regression_days']} days | XGBoost: {res['model_breakdown']['xgboost_days']} days")

    print("\n--- VESSEL FEASIBILITY MATRIX (Haldia Dock Complex) ---")
    feasibility = predictor.evaluate_vessel_feasibility('Haldia Dock Complex', 55000)
    for row in feasibility:
        print(f"  {row['vessel_class']:<10} | DWT: {row['dwt_capacity']:<8} | Draft Req: {row['required_draft']}m (Port Max: {row['port_max_draft']}m) -> [{row['status']}]")
    print("=" * 65)