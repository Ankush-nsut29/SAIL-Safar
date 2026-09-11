# 🚢 SAIL Intelligent Freight Advisory Portal (SAIL Safar)

## Overview
**SAIL Safar** is a Decision Support System (DSS) engineered for Steel Authority of India Limited (SAIL). It empowers branch procurement officers to optimize ocean freight contracts for imported coking and thermal coal.

By fusing physical maritime constraints, historical market statistics (Baltic Dry Index equivalent), and live weather data, the portal calculates the true landed cost of freight. It strategically recommends the best approach between a **Spot Voyage Charter** and a **Period Time Charter**.

---

## 🏗️ Technology Stack
* **Backend:** Python, Flask (Blueprint architecture)
* **Database:** SQLite via SQLAlchemy
* **Data Processing & Math Engine:** Pandas and NumPy
* **Frontend:** HTML5, CSS Grid (Government of India/SAIL Navy Blue aesthetic), Vanilla JavaScript
* **Data Visualization:** Chart.js for lightweight, interactive web rendering

---

## 🧮 The Mathematical & Strategic Engine

SAIL Safar doesn't just estimate costs; it calculates the exact risk profile of the market to drive procurement strategy using statistical slicing and physical constraints.

### 1. Landed Cost Calculation
To compare a Time Charter against a historical Spot Rate, the engine calculates the true landed cost per metric ton using the following formula:

```text
Total Voyage Days = Laden Transit Days + Ballast (Empty) Return Days + Port Turnaround Days

Landed Cost ($/MT) = [ (Daily Hire Rate × Total Voyage Days) + (Total Fuel Consumed × Bunker Price) ] / Cargo Volume (MT)
```

### 2. Dynamic Cargo Capping (Inverse-Draft Math)
If the physical draft limit of the port restricts the vessel, the engine automatically runs inverse-draft math to calculate the **maximum safe payload**. 

* If the requested cargo volume exceeds this safe limit, the system **caps the payload** and dynamically recalculates the Landed Cost ($/MT) based on the reduced volume.
* A warning is then flashed to the procurement officer.

### 3. Statistical Risk Indicators
The engine evaluates market datasets over a selected horizon (e.g., 30/60/90 days) using Pandas and NumPy to compute:
* **Mean Rate:** Baseline expected freight cost over the time horizon.
* **Variance:** Overall volatility and price instability.
* **Skewness (Risk Asymmetry):** The trigger metric. A high **positive skewness** indicates an impending upward price spike, which directly triggers a **Period Time Charter** recommendation to hedge against market explosions.
* **Kurtosis (Tail Risk):** Probability of extreme, unpredictable market disruptions (black swan events).

---

## 📊 Contract Decision Logic

Based on the statistical computations, the engine recommends one of the following:
* **Spot Voyage Charter (Fixed $/MT):** Recommended when market variance is low or skewness is negative. The shipowner assumes the risk of weather delays and bunker fuel spikes.
* **Period Time Charter (Fixed $/Day):** Recommended when positive skewness points to high volatility. SAIL assumes the risk of weather/fuel but hedges against extreme market surges.

---

## 🚢 Geographic & Physical Scope

The portal is heavily scoped to SAIL's primary corridors (Australia & Indonesia to India's East Coast). Physical constraints evaluated include:
* **Vessel Classes:** Handysize (~35,000 MT), Supramax (~58,000 MT), Panamax (~75,000 MT), Capesize (~180,000 MT).
* **Port Constraints:** Handled based on exact draft/LOA limits (e.g., Haldia Dock Complex restricted to 9.0m, while Paradip can handle up to 18.0m deep drafts).
