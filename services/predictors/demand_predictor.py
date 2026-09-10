# services/predictors/demand_predictor.py
"""
SAIL Safar — SAIL Plant Import Demand Predictor
-----------------------------------------------
- Auto-generates dataset 'data/sail_plant_demand.csv' if missing.
- Models: Linear Regression (PS Requirement) + XGBoost Regressor.
- Predicts import demand (MT) per SAIL plant & commodity.
- Evaluates demand outlook (High / Normal / Soft) for contract window sizing.
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


def ensure_dataset_exists(data_path='data/sail_plant_demand.csv'):
    """Generates clean historical plant import demand dataset if missing."""
    if os.path.exists(data_path):
        return

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    print(f"📦 Generating historical SAIL plant demand dataset at '{data_path}'...")

    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='D')
    plants = ['Bhilai Steel Plant', 'Bokaro Steel Plant', 'Rourkela Steel Plant', 'Durgapur Steel Plant']
    commodities = ['coking_coal', 'limestone', 'thermal_coal']

    rows = []
    # Weekly demand records
    for dt in dates[::7]:
        month = dt.month
        for plant in plants:
            for comm in commodities:
                base_req = 45000 if comm == 'coking_coal' else (20000 if comm == 'limestone' else 30000)
                # Q4/Q1 peak steel production restocking
                seasonal_mult = 1.18 if month in [10, 11, 12, 1, 2] else (0.88 if month in [6, 7, 8] else 0.98)
                req_mt = base_req * seasonal_mult + np.random.normal(0, 1800)

                rows.append({
                    'Date': dt.strftime('%Y-%m-%d'),
                    'Month': month,
                    'Plant': plant,
                    'Commodity': comm,
                    'Required_MT': round(max(5000.0, req_mt), 1),
                    'Target_Buffer_Days': 21
                })

    df = pd.DataFrame(rows)
    df.to_csv(data_path, index=False)
    print(f"[OK] SAIL plant demand dataset created successfully ({len(df)} records).")


class DemandPredictor:

    PLANTS = ['Bhilai Steel Plant', 'Bokaro Steel Plant', 'Rourkela Steel Plant', 'Durgapur Steel Plant']
    COMMODITIES = ['coking_coal', 'limestone', 'thermal_coal']

    def __init__(self, data_path='data/sail_plant_demand.csv', random_state=42):
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

        for (plant, comm), group_df in df.groupby(['Plant', 'Commodity']):
            key = f"{plant}_{comm}"
            cleaned = group_df.sort_values('Date').reset_index(drop=True)
            self.data[key] = cleaned

        return self

    @staticmethod
    def _engineer_features(df):
        data = df.copy().sort_values('Date').reset_index(drop=True)
        month = data['Date'].dt.month

        data['month_sin'] = np.sin(2 * np.pi * month / 12)
        data['month_cos'] = np.cos(2 * np.pi * month / 12)
        data['quarter'] = data['Date'].dt.quarter
        data['is_restocking_season'] = month.isin([10, 11, 12, 1, 2]).astype(int)

        # Lags & Rolling Means of Demand
        for lag in [1, 2, 4, 8]:
            data[f'Required_MT_lag_{lag}'] = data['Required_MT'].shift(lag)
        data['Required_MT_roll_4'] = data['Required_MT'].shift(1).rolling(4).mean()

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
            'rmse_mt': round(float(rmse), 2),
            'mae_mt': round(float(mae), 2),
            'mape_percent': round(float(mape), 4),
        }

    def train(self):
        """Trains Linear Regression (PS Req) + XGBoost for SAIL plant demand prediction."""
        if not self.data:
            self.load_data()

        print("\n" + "=" * 65)
        print(" TRAINING DEMAND PREDICTOR (LINEAR REGRESSION + XGBOOST) ")
        print("=" * 65)

        for key, raw_df in self.data.items():
            feat_df = self._engineer_features(raw_df)

            if len(feat_df) < 20:
                continue

            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Plant', 'Commodity', 'Required_MT')]
            X = feat_df[feature_cols].values
            y = feat_df['Required_MT'].values

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
                max_depth=3,
                learning_rate=0.04,
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

            self.evaluation_results[key] = {
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

            xgb_final = XGBRegressor(n_estimators=150, max_depth=3, learning_rate=0.04, random_state=self.random_state)
            xgb_final.fit(X_all_s, y)

            self.models[f"{key}_linear"] = lr_final
            self.models[f"{key}_xgboost"] = xgb_final
            self.scalers[key] = scaler_final
            self.feature_columns[key] = feature_cols
            self.ensemble_weights[key] = {'linear_regression': w_lr, 'xgboost': w_xgb}

            print(f"  [OK] {key:<35} | R²: {metrics_ensemble['r2']:.4f} | MAPE: {metrics_ensemble['mape_percent']:.2f}% | Weights: [LR: {w_lr:.2f}, XGB: {w_xgb:.2f}]")

        self.is_trained = True
        return self

    def predict_demand(self, commodity='coking_coal', plant='Bhilai Steel Plant', target_date=None, contract_days=30):
        """
        Predicts required MT for a plant/commodity and evaluates overall demand outlook.
        """
        if not self.is_trained:
            self.train()

        key = f"{plant}_{commodity}"
        if key not in self.scalers:
            key = list(self.scalers.keys())[0]

        if target_date is None:
            target_date = pd.Timestamp.now() + pd.Timedelta(days=14)
        target_date = pd.Timestamp(target_date)
        month = target_date.month

        df_key = self.data[key]
        last_row = df_key.iloc[-1]
        cols = self.feature_columns[key]

        feat = {
            'month_sin': np.sin(2 * np.pi * month / 12),
            'month_cos': np.cos(2 * np.pi * month / 12),
            'quarter': target_date.quarter,
            'is_restocking_season': 1 if month in [10, 11, 12, 1, 2] else 0,
            'Required_MT': float(last_row['Required_MT']),
        }

        for lag in [1, 2, 4, 8]:
            feat[f'Required_MT_lag_{lag}'] = float(last_row['Required_MT'])
        feat['Required_MT_roll_4'] = float(df_key['Required_MT'].tail(4).mean())

        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[key].transform(X_pred)

        pred_lr = float(self.models[f"{key}_linear"].predict(X_scaled)[0])
        pred_xgb = float(self.models[f"{key}_xgboost"].predict(X_scaled)[0])

        w_lr = self.ensemble_weights[key]['linear_regression']
        w_xgb = self.ensemble_weights[key]['xgboost']

        predicted_weekly_demand_mt = max(1000.0, (w_lr * pred_lr) + (w_xgb * pred_xgb))

        # Scale predicted weekly demand to contract window (30/60/90 days)
        total_window_demand_mt = predicted_weekly_demand_mt * (float(contract_days) / 7.0)

        # Determine Demand Outlook Indicator
        if month in [10, 11, 12, 1, 2]:
            outlook = 'High'
            note = 'Peak Q4/Q1 steel production restocking season. High import volume requirement favors locking long-term charter coverage.'
        elif month in [6, 7, 8]:
            outlook = 'Soft'
            note = 'Monsoon season plant inventory slowdown. Lower import pressure allows flexibility on spot charters.'
        else:
            outlook = 'Normal'
            note = 'Balanced plant production demand. Compare spot vs term on pure financial arbitrage.'

        return {
            'plant': plant,
            'commodity': commodity,
            'target_date': str(target_date.date()),
            'contract_days': contract_days,
            'predicted_weekly_demand_mt': round(predicted_weekly_demand_mt, 1),
            'predicted_window_demand_mt': round(total_window_demand_mt, 1),
            'outlook': outlook,
            'note': note,
            'model_breakdown': {
                'linear_regression_weekly_mt': round(pred_lr, 1),
                'xgboost_weekly_mt': round(pred_xgb, 1),
                'ensemble_weekly_mt': round(predicted_weekly_demand_mt, 1)
            },
            'test_metrics': self.evaluation_results[key]['ensemble']
        }


if __name__ == '__main__':
    predictor = DemandPredictor()
    predictor.train()

    print("\n--- SAMPLE DEMAND PREDICTION DEMO ---")
    res = predictor.predict(commodity='coking_coal', plant='Bhilai Steel Plant', target_date='2026-11-15', contract_days=30)
    print(f"Plant:                  {res['plant']}")
    print(f"Commodity:              {res['commodity']}")
    print(f"Target Date:            {res['target_date']}")
    print(f"Weekly Demand Forecast: {res['predicted_weekly_demand_mt']:,} MT")
    print(f"30-Day Window Demand:   {res['predicted_window_demand_mt']:,} MT")
    print(f"Demand Outlook:         {res['outlook']}")
    print(f"Strategic Note:         {res['note']}")
    print(f"Model Breakdown:        Linear Reg: {res['model_breakdown']['linear_regression_weekly_mt']:,} MT | XGBoost: {res['model_breakdown']['xgboost_weekly_mt']:,} MT")
    print("=" * 65)