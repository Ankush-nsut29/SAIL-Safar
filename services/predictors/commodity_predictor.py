# services/predictors/commodity_predictor.py
"""
SAIL Safar — Raw Material / Commodity Price Predictor
---------------------------------------------------
- Auto-generates dataset 'data/Raw_Material_Prices.csv' if missing.
- Models: Linear Regression (PS Requirement) + XGBoost Regressor.
- Validation-Weighted Ensemble (Inverse RMSE weighting).
- Chronological Split: 70% Train, 15% Validation, 15% Test.
- Metrics calculated: R², RMSE, MAE, MAPE on unseen test set.
"""

import os
import re
import math
import warnings
import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')


def ensure_dataset_exists(data_path='data/Raw_Material_Prices.csv'):
    """Generates clean historical raw material price dataset if not found."""
    if os.path.exists(data_path):
        return

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    print(f"📦 Generating historical commodity dataset at '{data_path}'...")

    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='D')

    # Realistic market baseline prices and random walks
    coking_coal = 230.0 + np.cumsum(np.random.normal(0, 2.2, len(dates)))
    thermal_coal = 135.0 + np.cumsum(np.random.normal(0, 1.1, len(dates)))
    iron_ore = 108.0 + np.cumsum(np.random.normal(0, 0.9, len(dates)))
    manganese = 320.0 + np.cumsum(np.random.normal(0, 1.8, len(dates)))
    limestone = 45.0 + np.cumsum(np.random.normal(0, 0.25, len(dates)))

    df = pd.DataFrame({
        'Date': dates.strftime('%Y-%m-%d'),
        'Coking_Coal': np.round(np.maximum(coking_coal, 100.0), 2),
        'Thermal_Coal': np.round(np.maximum(thermal_coal, 60.0), 2),
        'Iron_Ore': np.round(np.maximum(iron_ore, 50.0), 2),
        'Manganese_Ore': np.round(np.maximum(manganese, 150.0), 2),
        'Limestone': np.round(np.maximum(limestone, 20.0), 2),
    })

    df.to_csv(data_path, index=False)
    print(f"✓ Dataset created successfully ({len(df)} records).")


class CommodityPredictor:

    COMMODITY_ALIASES = {
        'coking_coal': {'coking_coal', 'metallurgical_coal', 'met_coal', 'hard_coking_coal'},
        'thermal_coal': {'thermal_coal', 'steam_coal', 'energy_coal'},
        'iron_ore': {'iron_ore', 'iron_ore_62', 'iron_ore_62_fe'},
        'manganese_ore': {'manganese', 'manganese_ore'},
        'limestone': {'limestone'},
    }

    def __init__(self, data_path='data/Raw_Material_Prices.csv', random_state=42):
        self.data_path = data_path
        self.random_state = random_state
        self.data = {}
        self.models = {}
        self.scalers = {}
        self.feature_columns = {}
        self.feature_configs = {}
        self.ensemble_weights = {}
        self.evaluation_results = {}
        self.cadence_days = {}
        self.max_step_changes = {}
        self.is_trained = False

    @staticmethod
    def _normalise_text(value):
        value = str(value).strip().lower()
        value = re.sub(r'[^a-z0-9]+', '_', value)
        return value.strip('_')

    def _normalise_commodity(self, value):
        norm = self._normalise_text(value)
        for canonical, aliases in self.COMMODITY_ALIASES.items():
            if norm in aliases:
                return canonical
        return norm

    @staticmethod
    def _clean_price(series):
        cleaned = (
            series.astype(str)
            .str.replace('$', '', regex=False)
            .str.replace('₹', '', regex=False)
            .str.replace(',', '', regex=False)
            .str.replace('"', '', regex=False)
            .str.strip()
        )
        return pd.to_numeric(cleaned, errors='coerce')

    def load_data(self):
        ensure_dataset_exists(self.data_path)

        df = pd.read_csv(self.data_path)
        df.columns = [str(col).replace('"', '').strip() for col in df.columns]

        date_col = next((c for c in df.columns if 'date' in c.lower() or 'day' in c.lower()), df.columns[0])

        # Convert Wide Format to Long Format if needed
        if 'commodity' not in [c.lower() for c in df.columns]:
            val_cols = [c for c in df.columns if c != date_col]
            df = df.melt(id_vars=[date_col], value_vars=val_cols, var_name='Commodity', value_name='Price')
        else:
            comm_col = next(c for c in df.columns if 'commodity' in c.lower())
            price_col = next(c for c in df.columns if 'price' in c.lower() or 'value' in c.lower())
            df = df[[date_col, comm_col, price_col]]
            df.columns = [date_col, 'Commodity', 'Price']

        df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
        df['Price'] = self._clean_price(df['Price'])
        df['Commodity'] = df['Commodity'].apply(self._normalise_commodity)

        df = df.dropna(subset=['Date', 'Price', 'Commodity'])
        df = df[df['Price'] > 0]

        df = df.groupby(['Commodity', 'Date'], as_index=False)['Price'].mean().sort_values(['Commodity', 'Date'])

        for comm, comm_df in df.groupby('Commodity'):
            cleaned = comm_df[['Date', 'Price']].sort_values('Date').drop_duplicates('Date').reset_index(drop=True)
            self.data[comm] = cleaned

        return self

    @staticmethod
    def _engineer_features(df):
        data = df.copy().sort_values('Date').reset_index(drop=True)

        data['trend_index'] = np.arange(len(data))
        month = data['Date'].dt.month
        weekday = data['Date'].dt.dayofweek

        data['month_sin'] = np.sin(2 * np.pi * month / 12)
        data['month_cos'] = np.cos(2 * np.pi * month / 12)
        data['weekday_sin'] = np.sin(2 * np.pi * weekday / 7)
        data['weekday_cos'] = np.cos(2 * np.pi * weekday / 7)

        for lag in [1, 3, 5, 7, 14, 30]:
            data[f'lag_{lag}'] = data['Price'].shift(lag)

        past_prices = data['Price'].shift(1)
        for window in [7, 14, 30]:
            data[f'roll_mean_{window}'] = past_prices.rolling(window).mean()
            data[f'roll_std_{window}'] = past_prices.rolling(window).std()

        for lag in [3, 7]:
            data[f'momentum_{lag}'] = data['Price'].shift(1) - data['Price'].shift(lag + 1)

        config = {'lags': [1, 3, 5, 7, 14, 30], 'windows': [7, 14, 30], 'cadence_days': 1.0}
        return data.dropna().reset_index(drop=True), config

    @staticmethod
    def _calculate_metrics(actual, predicted):
        actual = np.asarray(actual, dtype=float)
        predicted = np.asarray(predicted, dtype=float)

        rmse = math.sqrt(mean_squared_error(actual, predicted))
        mae = mean_absolute_error(actual, predicted)
        non_zero = np.abs(actual) > 1e-8
        mape = np.mean(np.abs((actual[non_zero] - predicted[non_zero]) / actual[non_zero])) * 100
        r2 = r2_score(actual, predicted) if len(actual) >= 2 else np.nan

        return {
            'r2': round(float(r2), 4),
            'rmse_usd_mt': round(float(rmse), 4),
            'mae_usd_mt': round(float(mae), 4),
            'mape_percent': round(float(mape), 4),
        }

    def train(self):
        """Trains Linear Regression (PS Req) + XGBoost with Validation Weighting."""
        if not self.data:
            self.load_data()

        print("\n" + "=" * 65)
        print(" TRAINING RAW MATERIAL PREDICTOR (LINEAR REGRESSION + XGBOOST) ")
        print("=" * 65)

        for commodity, raw_df in self.data.items():
            feat_df, config = self._engineer_features(raw_df)

            if len(feat_df) < 40:
                continue

            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Price')]
            X = feat_df[feature_cols].values
            y = feat_df['Price'].values

            # 70% Train, 15% Validation, 15% Test
            train_end = int(len(X) * 0.70)
            val_end = int(len(X) * 0.85)

            X_train, y_train = X[:train_end], y[:train_end]
            X_val, y_val = X[train_end:val_end], y[train_end:val_end]
            X_test, y_test = X[val_end:], y[val_end:]

            scaler_eval = StandardScaler()
            X_train_s = scaler_eval.fit_transform(X_train)
            X_val_s = scaler_eval.transform(X_val)
            X_test_s = scaler_eval.transform(X_test)

            # MODEL 1: LINEAR REGRESSION (PS REQUIREMENT)
            lr_eval = LinearRegression()
            lr_eval.fit(X_train_s, y_train)

            # MODEL 2: XGBOOST REGRESSOR
            xgb_eval = XGBRegressor(
                n_estimators=200,
                max_depth=4,
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

            self.evaluation_results[commodity] = {
                'linear_regression': self._calculate_metrics(y_test, test_lr),
                'xgboost': self._calculate_metrics(y_test, test_xgb),
                'ensemble': metrics_ensemble,
                'weights': {'linear_regression': round(w_lr, 4), 'xgboost': round(w_xgb, 4)}
            }

            # Refit Final Production Models on 100% Data
            scaler_final = StandardScaler()
            X_all_s = scaler_final.fit_transform(X)

            lr_final = LinearRegression()
            lr_final.fit(X_all_s, y)

            xgb_final = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.04, random_state=self.random_state)
            xgb_final.fit(X_all_s, y)

            self.models[f"{commodity}_linear"] = lr_final
            self.models[f"{commodity}_xgboost"] = xgb_final
            self.scalers[commodity] = scaler_final
            self.feature_columns[commodity] = feature_cols
            self.feature_configs[commodity] = config
            self.ensemble_weights[commodity] = {'linear_regression': w_lr, 'xgboost': w_xgb}
            self.cadence_days[commodity] = 1.0

            print(f"  ✓ {commodity:<15} | R²: {metrics_ensemble['r2']:.4f} | MAPE: {metrics_ensemble['mape_percent']:.2f}% | Weights: [LR: {w_lr:.2f}, XGB: {w_xgb:.2f}]")

        self.is_trained = True
        return self

    def predict(self, commodity='coking_coal', target_date=None, cargo_mt=0.0):
        """Predicts future price USD/MT and total cargo value."""
        if not self.is_trained:
            self.train()

        comm_key = self._normalise_commodity(commodity)

        if comm_key not in self.scalers:
            comm_key = list(self.scalers.keys())[0]

        df_comm = self.data[comm_key]
        last_date = pd.Timestamp(df_comm['Date'].iloc[-1])
        last_price = float(df_comm['Price'].iloc[-1])

        if target_date is None:
            target_date = last_date + pd.Timedelta(days=14)
        target_date = pd.Timestamp(target_date)

        days_ahead = max((target_date - last_date).days, 1)

        recent_prices = df_comm['Price'].values
        cols = self.feature_columns[comm_key]

        feat = {
            'trend_index': len(recent_prices) + days_ahead,
            'month_sin': np.sin(2 * np.pi * target_date.month / 12),
            'month_cos': np.cos(2 * np.pi * target_date.month / 12),
            'weekday_sin': np.sin(2 * np.pi * target_date.dayofweek / 7),
            'weekday_cos': np.cos(2 * np.pi * target_date.dayofweek / 7),
        }

        for lag in [1, 3, 5, 7, 14, 30]:
            feat[f'lag_{lag}'] = recent_prices[-min(lag, len(recent_prices))]
        for w in [7, 14, 30]:
            sl = recent_prices[-min(w, len(recent_prices)):]
            feat[f'roll_mean_{w}'] = float(np.mean(sl))
            feat[f'roll_std_{w}'] = float(np.std(sl))
        for lag in [3, 7]:
            feat[f'momentum_{lag}'] = float(recent_prices[-1] - recent_prices[-min(lag + 1, len(recent_prices))])

        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[comm_key].transform(X_pred)

        pred_lr = float(self.models[f"{comm_key}_linear"].predict(X_scaled)[0])
        pred_xgb = float(self.models[f"{comm_key}_xgboost"].predict(X_scaled)[0])

        w_lr = self.ensemble_weights[comm_key]['linear_regression']
        w_xgb = self.ensemble_weights[comm_key]['xgboost']

        final_price = (w_lr * pred_lr) + (w_xgb * pred_xgb)

        # Confidence bounds based on test RMSE
        test_rmse = self.evaluation_results[comm_key]['ensemble']['rmse_usd_mt']
        unc = 1.96 * test_rmse * math.sqrt(days_ahead / 30.0)

        cargo_mt = float(cargo_mt)
        cargo_value = final_price * cargo_mt

        return {
            'commodity': comm_key,
            'target_date': str(target_date.date()),
            'predicted_price_usd_mt': round(final_price, 2),
            'lower_bound_usd_mt': round(max(final_price - unc, 0.0), 2),
            'upper_bound_usd_mt': round(final_price + unc, 2),
            'cargo_mt': cargo_mt,
            'cargo_value_usd': round(cargo_value, 2),
            'model_breakdown': {
                'linear_regression_price': round(pred_lr, 2),
                'xgboost_price': round(pred_xgb, 2),
                'linear_weight': round(w_lr, 4),
                'xgboost_weight': round(w_xgb, 4),
                'ensemble_price': round(final_price, 2)
            },
            'test_metrics': self.evaluation_results[comm_key]['ensemble']
        }

    def list_commodities(self):
        return sorted(self.data.keys())


# Alias for compatibility
CommodityPricePredictor = CommodityPredictor


if __name__ == '__main__':
    # Test harness execution
    predictor = CommodityPredictor()
    predictor.train()

    print("\n--- SAMPLE PREDICTION DEMO ---")
    res = predictor.predict('coking_coal', target_date='2026-10-15', cargo_mt=55000)
    print(f"Commodity:                {res['commodity']}")
    print(f"Target Date:              {res['target_date']}")
    print(f"Predicted Price:          ${res['predicted_price_usd_mt']} / MT")
    print(f"Price Range:              [${res['lower_bound_usd_mt']} - ${res['upper_bound_usd_mt']}]")
    print(f"Cargo Volume:             {res['cargo_mt']:,} MT")
    print(f"Total Cargo Value:        ${res['cargo_value_usd']:,.2f}")
    print(f"Model Breakdown:          Linear Reg: ${res['model_breakdown']['linear_regression_price']} | XGBoost: ${res['model_breakdown']['xgboost_price']}")
    print("=" * 65)