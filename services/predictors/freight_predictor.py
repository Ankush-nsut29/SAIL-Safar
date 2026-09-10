# services/predictors/freight_predictor.py
"""
SAIL Safar — Freight / Charter Rate Predictor
---------------------------------------------
- Auto-detects / loads 'Cleaned_Capesize.csv', 'Cleaned_Panamax.csv', etc.
- Models: Linear Regression (PS Requirement) + XGBoost Regressor.
- Validation-Weighted Ensemble (Inverse-RMSE Weighting).
- Chronological Split: 70% Train, 15% Validation, 15% Test.
- Metrics Calculated: R², RMSE, MAE, MAPE on unseen test set.
- Provides Mean, Variance, Skewness, Kurtosis metrics for dashboard UI cards.
"""

import os
import math
import warnings
import numpy as np
import pandas as pd
from datetime import datetime
from scipy import stats

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

warnings.filterwarnings('ignore')


def ensure_freight_datasets_exist(data_dir='data'):
    """Generates synthetic historical freight CSV datasets if files are missing."""
    os.makedirs(data_dir, exist_ok=True)
    vessel_baselines = {
        'Capesize': (2200.0, 45.0),
        'Panamax': (1350.0, 25.0),
        'Supramax': (1100.0, 20.0),
        'Handysize': (900.0, 15.0)
    }

    dates = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='D')

    for vc, (base_price, noise_std) in vessel_baselines.items():
        path = os.path.join(data_dir, f'Cleaned_{vc}.csv')
        if not os.path.exists(path):
            print(f"📦 Generating fallback freight dataset at '{path}'...")
            np.random.seed(42)
            prices = base_price + np.cumsum(np.random.normal(0, noise_std, len(dates)))
            df = pd.DataFrame({
                'Date': dates.strftime('%Y-%m-%d'),
                'Price': np.round(np.maximum(prices, 400.0), 2)
            })
            df.to_csv(path, index=False)
            print(f"  ✓ Created fallback dataset for {vc}.")


class FreightRatePredictor:

    VESSEL_CLASSES = ['Capesize', 'Panamax', 'Supramax', 'Handysize']

    def __init__(self, data_dir='data', random_state=42):
        self.data_dir = data_dir
        self.random_state = random_state
        self.rate_data = {}
        self.models = {}
        self.scalers = {}
        self.feature_columns = {}
        self.ensemble_weights = {}
        self.evaluation_results = {}
        self.is_trained = False

    @staticmethod
    def _clean_price_series(series):
        """Cleans quotes, commas, dollar signs, and converts series to float."""
        cleaned = (
            series.astype(str)
            .str.replace('$', '', regex=False)
            .str.replace('"', '', regex=False)
            .str.replace(',', '', regex=False)
            .str.strip()
        )
        return pd.to_numeric(cleaned, errors='coerce')

    def load_data(self):
        """Loads and cleans Cleaned_Capesize.csv, Cleaned_Panamax.csv, etc."""
        ensure_freight_datasets_exist(self.data_dir)

        for vc in self.VESSEL_CLASSES:
            path = os.path.join(self.data_dir, f'Cleaned_{vc}.csv')
            if not os.path.exists(path):
                continue

            df = pd.read_csv(path)
            date_col = next((c for c in df.columns if 'date' in c.lower() or 'day' in c.lower()), df.columns[0])
            price_col = next((c for c in df.columns if 'price' in c.lower() or 'value' in c.lower() or 'rate' in c.lower()), df.columns[-1])

            df['Date'] = pd.to_datetime(df[date_col], errors='coerce')
            df['Price'] = self._clean_price_series(df[price_col])

            df = df.dropna(subset=['Date', 'Price']).sort_values('Date').reset_index(drop=True)
            df = df[df['Price'] > 0]

            if len(df) > 0:
                self.rate_data[vc] = df

        return self

    @staticmethod
    def _engineer_features(df):
        """Creates lag, momentum, and rolling statistical features for time series ML."""
        data = df.copy().sort_values('Date').reset_index(drop=True)

        data['day_of_week'] = data['Date'].dt.dayofweek
        data['month'] = data['Date'].dt.month
        data['quarter'] = data['Date'].dt.quarter
        data['day_of_year'] = data['Date'].dt.dayofyear
        data['year'] = data['Date'].dt.year

        # Lags
        for lag in [1, 3, 5, 7, 14, 30]:
            data[f'lag_{lag}'] = data['Price'].shift(lag)

        # Rolling Statistics (shifted by 1 to prevent leakage)
        past_prices = data['Price'].shift(1)
        for w in [7, 14, 30]:
            data[f'roll_mean_{w}'] = past_prices.rolling(w).mean()
            data[f'roll_std_{w}'] = past_prices.rolling(w).std()

        # Momentum
        for lag in [3, 7, 30]:
            data[f'momentum_{lag}'] = data['Price'].shift(1) - data['Price'].shift(lag + 1)

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
            'rmse_usd_day': round(float(rmse), 2),
            'mae_usd_day': round(float(mae), 2),
            'mape_percent': round(float(mape), 2),
        }

    def train(self):
        """Trains Linear Regression (PS Req) + XGBoost with Validation Weighting."""
        if not self.rate_data:
            self.load_data()

        print("\n" + "=" * 65)
        print(" TRAINING FREIGHT RATE PREDICTOR (LINEAR REGRESSION + XGBOOST) ")
        print("=" * 65)

        for vc, raw_df in self.rate_data.items():
            feat_df = self._engineer_features(raw_df)

            if len(feat_df) < 40:
                print(f"Skipping {vc}: Insufficient features rows ({len(feat_df)})")
                continue

            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Price')]
            X = feat_df[feature_cols].values
            y = feat_df['Price'].values

            # 70% Train, 15% Validation, 15% Test (Chronological Split)
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

            self.evaluation_results[vc] = {
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

            xgb_final = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.04, random_state=self.random_state)
            xgb_final.fit(X_all_s, y)

            self.models[f"{vc}_linear"] = lr_final
            self.models[f"{vc}_xgboost"] = xgb_final
            self.scalers[vc] = scaler_final
            self.feature_columns[vc] = feature_cols
            self.ensemble_weights[vc] = {'linear_regression': w_lr, 'xgboost': w_xgb}

            print(f"  ✓ {vc:<12} | R²: {metrics_ensemble['r2']:.4f} | MAPE: {metrics_ensemble['mape_percent']:.2f}% | Weights: [LR: {w_lr:.2f}, XGB: {w_xgb:.2f}]")

        self.is_trained = True
        return self

    def predict_rate(self, vessel_class='Panamax', target_date=None):
        """Predicts daily charter rate (USD/day) with confidence bounds."""
        if not self.is_trained:
            self.train()

        if vessel_class not in self.scalers:
            vessel_class = list(self.scalers.keys())[0] if self.scalers else 'Panamax'

        if target_date is None:
            target_date = pd.Timestamp.now() + pd.Timedelta(days=14)
        target_date = pd.Timestamp(target_date)

        df_vc = self.rate_data[vessel_class]
        last_date = pd.Timestamp(df_vc['Date'].iloc[-1])
        recent_prices = df_vc['Price'].values
        cols = self.feature_columns[vessel_class]

        days_ahead = max((target_date - last_date).days, 1)

        feat = {
            'day_of_week': target_date.dayofweek,
            'month': target_date.month,
            'quarter': target_date.quarter,
            'day_of_year': target_date.timetuple().tm_yday,
            'year': target_date.year,
        }

        for lag in [1, 3, 5, 7, 14, 30]:
            feat[f'lag_{lag}'] = float(recent_prices[-min(lag, len(recent_prices))])
        for w in [7, 14, 30]:
            sl = recent_prices[-min(w, len(recent_prices)):]
            feat[f'roll_mean_{w}'] = float(np.mean(sl))
            feat[f'roll_std_{w}'] = float(np.std(sl))
        for lag in [3, 7, 30]:
            feat[f'momentum_{lag}'] = float(recent_prices[-1] - recent_prices[-min(lag + 1, len(recent_prices))])

        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[vessel_class].transform(X_pred)

        pred_lr = float(self.models[f"{vessel_class}_linear"].predict(X_scaled)[0])
        pred_xgb = float(self.models[f"{vessel_class}_xgboost"].predict(X_scaled)[0])

        w_lr = self.ensemble_weights[vessel_class]['linear_regression']
        w_xgb = self.ensemble_weights[vessel_class]['xgboost']

        final_rate = max(100.0, (w_lr * pred_lr) + (w_xgb * pred_xgb))

        # Confidence bounds based on test RMSE
        test_rmse = self.evaluation_results[vessel_class]['ensemble']['rmse_usd_day']
        unc = 1.96 * test_rmse * math.sqrt(days_ahead / 30.0)

        return {
            'vessel_class': vessel_class,
            'target_date': str(target_date.date()),
            'predicted_rate': round(final_rate, 2),
            'lower': round(max(final_rate - unc, 50.0), 2),
            'upper': round(final_rate + unc, 2),
            'confidence': 'high' if days_ahead <= 14 else ('medium' if days_ahead <= 60 else 'low'),
            'model_breakdown': {
                'linear_regression_rate': round(pred_lr, 2),
                'xgboost_rate': round(pred_xgb, 2),
                'linear_weight': round(w_lr, 4),
                'xgboost_weight': round(w_xgb, 4),
                'ensemble_rate': round(final_rate, 2)
            },
            'test_metrics': self.evaluation_results[vessel_class]['ensemble']
        }

    def get_stats(self, vessel_class='Panamax', window=90):
        """Computes distribution stats (Mean, Variance, Skewness, Kurtosis) for UI cards."""
        if not self.is_trained:
            self.train()

        if vessel_class not in self.rate_data:
            vessel_class = list(self.rate_data.keys())[0] if self.rate_data else 'Panamax'

        df = self.rate_data[vessel_class]
        prices = df['Price'].values[-window:]

        mean_val = float(np.mean(prices))
        var_val = float(np.var(prices))
        skew_val = float(stats.skew(prices))
        kurt_val = float(stats.kurtosis(prices))

        chart_df = df.tail(60)[['Date', 'Price']].copy()
        chart_df['Date'] = chart_df['Date'].dt.strftime('%Y-%m-%d')
        chart_data = chart_df.to_dict(orient='records')

        return {
            'mean_rate': round(mean_val, 2),
            'variance': round(var_val, 2),
            'skewness': round(skew_val, 2),
            'kurtosis': round(kurt_val, 2),
            'chart_data': chart_data
        }

    def forecast_series(self, vessel_class='Panamax', days=30):
        """Generates day-by-day rate forecast for spot contract window."""
        series = []
        today = pd.Timestamp.now()
        for d in range(1, days + 1):
            pred = self.predict_rate(vessel_class, today + pd.Timedelta(days=d))
            series.append({
                'day': d,
                'date': str((today + pd.Timedelta(days=d)).date()),
                'rate': pred['predicted_rate'],
                'lower': pred['lower'],
                'upper': pred['upper'],
            })
        return series


if __name__ == '__main__':
    predictor = FreightRatePredictor()
    predictor.train()

    print("\n--- SAMPLE FREIGHT RATE PREDICTION DEMO ---")
    res = predictor.predict_rate(vessel_class='Panamax', target_date='2026-10-15')
    print(f"Vessel Class:        {res['vessel_class']}")
    print(f"Target Date:         {res['target_date']}")
    print(f"Predicted Daily Rate:${res['predicted_rate']:,.2f} / day")
    print(f"Rate Range:          [${res['lower']:,.2f} - ${res['upper']:,.2f}]")
    print(f"Confidence Level:    {res['confidence'].upper()}")
    print(f"Model Breakdown:     Linear Reg: ${res['model_breakdown']['linear_regression_rate']:,.2f} | XGBoost: ${res['model_breakdown']['xgboost_rate']:,.2f}")

    print("\n--- STATISTICAL CARDS METRICS (Panamax) ---")
    st = predictor.get_stats('Panamax')
    print(f"Mean Rate: ${st['mean_rate']:,.2f} | Variance: {st['variance']:,.2f} | Skewness: {st['skewness']} | Kurtosis: {st['kurtosis']}")
    print("=" * 65)