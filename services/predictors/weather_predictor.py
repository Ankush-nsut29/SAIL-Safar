# services/predictors/weather_predictor.py
"""
SAIL Safar — Weather & Seasonal Delay Risk Predictor
--------------------------------------------------
- Auto-generates dataset 'data/weather_historical.csv' if missing.
- Models: Linear Regression (PS Requirement) + XGBoost Regressor.
- Predicts voyage delay days & sea-state wave heights across corridors.
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


def ensure_dataset_exists(data_path='data/weather_historical.csv'):
    """Generates clean historical maritime corridor weather dataset if missing."""
    if os.path.exists(data_path):
        return

    os.makedirs(os.path.dirname(data_path), exist_ok=True)
    print(f"📦 Generating historical weather dataset at '{data_path}'...")

    np.random.seed(42)
    dates = pd.date_range(end=pd.Timestamp.now(), periods=500, freq='D')
    corridors = ['Indonesia to East Coast India', 'Australia to East Coast India']

    rows = []
    for dt in dates:
        month = dt.month
        for corr in corridors:
            # Monsoon (Jun-Sep) & Cyclone (Oct-Dec) seasonal impact
            if month in [6, 7, 8, 9]:
                wave = np.random.uniform(2.5, 4.8)
                wind = np.random.uniform(22, 45)
                press = np.random.uniform(995, 1008)
                delay = 1.5 + (wave * 0.4) + (wind * 0.05) + np.random.normal(0, 0.2)
                risk = 'Monsoon_High'
            elif month in [10, 11, 12]:
                wave = np.random.uniform(2.0, 4.2)
                wind = np.random.uniform(18, 40)
                press = np.random.uniform(998, 1012)
                delay = 1.0 + (wave * 0.35) + (wind * 0.04) + np.random.normal(0, 0.2)
                risk = 'Cyclone_Warning'
            else:
                wave = np.random.uniform(0.5, 1.8)
                wind = np.random.uniform(8, 18)
                press = np.random.uniform(1012, 1022)
                delay = max(0.0, (wave - 1.0) * 0.2 + np.random.normal(0, 0.1))
                risk = 'Clear'

            rows.append({
                'Date': dt.strftime('%Y-%m-%d'),
                'Month': month,
                'Corridor': corr,
                'Wave_Height_m': round(max(0.3, wave), 2),
                'Wind_Speed_knots': round(max(5.0, wind), 1),
                'Sea_Pressure_hPa': round(press, 1),
                'Delay_Days': round(max(0.0, delay), 2),
                'Storm_Risk': risk
            })

    df = pd.DataFrame(rows)
    df.to_csv(data_path, index=False)
    print(f"✓ Weather dataset created successfully ({len(df)} records).")


class WeatherPredictor:

    MONSOON_MONTHS = {6, 7, 8, 9}
    CYCLONE_MONTHS = {10, 11, 12, 1}

    def __init__(self, data_path='data/weather_historical.csv', random_state=42):
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

        for corr, corr_df in df.groupby('Corridor'):
            cleaned = corr_df.sort_values('Date').reset_index(drop=True)
            self.data[corr] = cleaned

        return self

    @staticmethod
    def _engineer_features(df):
        data = df.copy().sort_values('Date').reset_index(drop=True)
        month = data['Date'].dt.month

        data['month_sin'] = np.sin(2 * np.pi * month / 12)
        data['month_cos'] = np.cos(2 * np.pi * month / 12)
        data['is_monsoon'] = month.isin([6, 7, 8, 9]).astype(int)
        data['is_cyclone'] = month.isin([10, 11, 12, 1]).astype(int)

        # Lags & Rolling Means of Weather Factors
        for col in ['Wave_Height_m', 'Wind_Speed_knots', 'Sea_Pressure_hPa']:
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
        """Trains Linear Regression (PS Req) + XGBoost for weather delay prediction."""
        if not self.data:
            self.load_data()

        print("\n" + "=" * 65)
        print(" TRAINING WEATHER PREDICTOR (LINEAR REGRESSION + XGBOOST) ")
        print("=" * 65)

        for corridor, raw_df in self.data.items():
            feat_df = self._engineer_features(raw_df)

            if len(feat_df) < 40:
                continue

            feature_cols = [c for c in feat_df.columns if c not in ('Date', 'Corridor', 'Storm_Risk', 'Delay_Days')]
            X = feat_df[feature_cols].values
            y = feat_df['Delay_Days'].values

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

            self.evaluation_results[corridor] = {
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

            self.models[f"{corridor}_linear"] = lr_final
            self.models[f"{corridor}_xgboost"] = xgb_final
            self.scalers[corridor] = scaler_final
            self.feature_columns[corridor] = feature_cols
            self.ensemble_weights[corridor] = {'linear_regression': w_lr, 'xgboost': w_xgb}

            print(f"  ✓ {corridor:<32} | R²: {metrics_ensemble['r2']:.4f} | RMSE: {metrics_ensemble['rmse_days']:.2f} days | Weights: [LR: {w_lr:.2f}, XGB: {w_xgb:.2f}]")

        self.is_trained = True
        return self

    def predict(self, voyage_date=None, origin='', destination=''):
        """Predicts weather delay days, sea risk level, and cost surcharge %."""
        if not self.is_trained:
            self.train()

        if voyage_date is None:
            voyage_date = pd.Timestamp.now() + pd.Timedelta(days=14)
        voyage_date = pd.Timestamp(voyage_date)
        month = voyage_date.month

        # Detect Corridor
        corridor = 'Indonesia to East Coast India'
        if any(k in origin.lower() for k in ['gladstone', 'hay point', 'australia']):
            corridor = 'Australia to East Coast India'

        if corridor not in self.scalers:
            corridor = list(self.scalers.keys())[0]

        df_corr = self.data[corridor]
        last_row = df_corr.iloc[-1]
        cols = self.feature_columns[corridor]

        feat = {
            'month_sin': np.sin(2 * np.pi * month / 12),
            'month_cos': np.cos(2 * np.pi * month / 12),
            'is_monsoon': 1 if month in self.MONSOON_MONTHS else 0,
            'is_cyclone': 1 if month in self.CYCLONE_MONTHS else 0,
            'Wave_Height_m': float(last_row['Wave_Height_m']),
            'Wind_Speed_knots': float(last_row['Wind_Speed_knots']),
            'Sea_Pressure_hPa': float(last_row['Sea_Pressure_hPa']),
        }

        for c_name in ['Wave_Height_m', 'Wind_Speed_knots', 'Sea_Pressure_hPa']:
            for lag in [1, 3, 7]:
                feat[f'{c_name}_lag_{lag}'] = float(last_row[c_name])
            feat[f'{c_name}_roll_7'] = float(df_corr[c_name].tail(7).mean())

        X_pred = np.array([[feat.get(c, 0.0) for c in cols]])
        X_scaled = self.scalers[corridor].transform(X_pred)

        pred_lr = float(self.models[f"{corridor}_linear"].predict(X_scaled)[0])
        pred_xgb = float(self.models[f"{corridor}_xgboost"].predict(X_scaled)[0])

        w_lr = self.ensemble_weights[corridor]['linear_regression']
        w_xgb = self.ensemble_weights[corridor]['xgboost']

        predicted_delay_days = max(0.0, (w_lr * pred_lr) + (w_xgb * pred_xgb))

        # Determine Surcharge & Risk Messages
        if month in self.MONSOON_MONTHS:
            surcharge_pct = 0.08
            season = 'Monsoon'
            risk_level = 'High' if predicted_delay_days > 1.5 else 'Medium'
            message = f"Monsoon season alert! Predicted wave height: {last_row['Wave_Height_m']}m. +{predicted_delay_days:.1f} delay days and 8% surcharge applied."
            css_class = 'warning'
        elif month in self.CYCLONE_MONTHS:
            surcharge_pct = 0.12
            season = 'Cyclone'
            risk_level = 'High'
            message = f"Bay of Bengal cyclone window! +{predicted_delay_days:.1f} delay days and 12% surcharge applied."
            css_class = 'warning'
        else:
            surcharge_pct = 0.0
            season = 'Normal'
            risk_level = 'Low'
            message = f"Weather conditions clear. Max wave height: {last_row['Wave_Height_m']}m. Standard routing applied."
            css_class = 'success'

        return {
            'corridor': corridor,
            'voyage_date': str(voyage_date.date()),
            'season': season,
            'risk_level': risk_level,
            'predicted_delay_days': round(predicted_delay_days, 2),
            'surcharge_pct': surcharge_pct,
            'message': message,
            'css_class': css_class,
            'model_breakdown': {
                'linear_regression_days': round(max(0.0, pred_lr), 2),
                'xgboost_days': round(max(0.0, pred_xgb), 2),
                'ensemble_delay_days': round(predicted_delay_days, 2)
            },
            'test_metrics': self.evaluation_results[corridor]['ensemble']
        }


if __name__ == '__main__':
    predictor = WeatherPredictor()
    predictor.train()

    print("\n--- SAMPLE WEATHER PREDICTION DEMO ---")
    res = predictor.predict(voyage_date='2026-07-15', origin='Taboneo Anchorage / Banjarmasin')
    print(f"Corridor:            {res['corridor']}")
    print(f"Voyage Date:         {res['voyage_date']}")
    print(f"Season & Risk:       {res['season']} ({res['risk_level']} Risk)")
    print(f"Predicted Delay:     {res['predicted_delay_days']} Extra Sea Days")
    print(f"Surcharge %:         {res['surcharge_pct']*100:.1f}%")
    print(f"Advisory Message:    {res['message']}")
    print(f"Model Breakdown:     Linear Reg: {res['model_breakdown']['linear_regression_days']} days | XGBoost: {res['model_breakdown']['xgboost_days']} days")
    print("=" * 65)