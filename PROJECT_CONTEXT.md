# SAIL Intelligent Freight Advisory Portal (SAIL Safar)
**Context & Project Summary**

This document serves as a persistent context file. When resuming work in a new session, reading this file will provide immediate understanding of the project's architecture, stack, and completed phases.

## 1. Executive Summary
The **SAIL Intelligent Freight Advisory Portal** is a Decision Support System (DSS) engineered to help branch procurement officers optimize ocean freight contracts for imported coal. By fusing physical maritime constraints (draft, LOA) with historical market statistics (Baltic Dry Index equivalent), the portal calculates the true landed cost of freight and strategically recommends between a **Spot Voyage Charter** and a **Period Time Charter**.

## 2. Technology Stack
* **Backend:** Python, Flask (using Blueprint architecture)
* **Database:** SQLite via SQLAlchemy
* **Data Processing & Math:** Pandas and NumPy (for fast statistical slicing and aggregations)
* **Frontend:** HTML5, CSS Grid (Government of India/SAIL Navy Blue aesthetic), Vanilla JavaScript (Fetch API for async DOM updates)
* **Data Visualization:** Chart.js

## 3. Project Architecture & Completed Phases

### Phase 1: Foundation & Authentication
* **Database (`model.py`)**: Designed `User` model (with hashed passwords) and `TradeLog` model for future audit trails.
* **Core Setup (`app.py`)**: Bootstrapped the Flask application and SQLite integration.
* **Authentication Blueprint (`blueprints/auth.py`)**: Built secure login, registration, and logout routes.
* **Base UI (`templates/base.html` & `static/style.css`)**: Established a professional, clean government aesthetic with a dynamic navigation bar.

### Phase 2: Data Loaders & Public Home Page
* **JSON Datasets (`/data`)**: Contains physical constraints for `vessels.json`, `eastcoast_ports.json`, and `foriegnports.json`.
* **Data Service (`services/data_loader.py`)**: Built robust loaders to fetch these static JSON configurations safely.
* **Public Home Page (`blueprints/home.py`)**: Created the root (`/`) route that dynamically renders Indian Discharge Ports, Foreign Export Ports, and Vessel Fleet constraints into responsive CSS-Grid cards.

### Phase 3: The Mathematical Engine & Interactive Dashboard
* **Vessel Feasibility Engine (`services/vessel_engine.py`)**: 
  - Cross-references selected Origin and Discharge port constraints.
  - Determines if a vessel is "Feasible" or restricted by "Draft Exceeded" / "LOA Exceeded".
  - **Dynamic Cargo Capping:** Uses inverse-draft math to automatically calculate the maximum safe payload if a vessel's draft exceeds the port's limit, capping the cargo instead of outright rejecting the vessel.
  - Automatically identifies the largest feasible vessel for economies of scale.
* **Statistical Calculator (`services/calculator.py`)**:
  - Dynamically loads cleaned historical freight rate CSVs (`Cleaned_{vessel_class}.csv`) via Pandas.
  - Slices data by the user's requested contract window.
  - Computes KPIs: Mean Rate, Variance, Skewness, Kurtosis, and Estimated Landed Cost (factoring transit time and fuel consumption).
  - Uses statistical skewness to power the decision matrix (recommending a Period Time Charter if volatility/skew is high).
* **Dashboard API (`blueprints/dashboard.py`)**: Exposes an internal API (`/api/analyze`) that orchestrates the data loading and calculations.
* **Asynchronous Frontend (`static/main.js` & `dashboard/index.html`)**:
  - An interactive form where procurement officers input voyage parameters.
  - Asynchronously updates KPI cards, a Recommendation Banner, a Vessel Feasibility Matrix table, and a Chart.js historical line graph.

### Phase 4: Weather Integration & Enterprise Redesign (Version 2)
* **Open-Meteo Marine API (`blueprints/dashboard.py`)**: Added real-time chokepoint wave height checks. Triggers detour penalties (extra transit days and fuel costs) if wave heights exceed safe limits.
* **CSS Grid Architecture (`static/style.css`)**: Overhauled the entire application layout. Abstracted colors and shadows into `:root` CSS variables.
* **Dashboard Split-View**: Redesigned the dashboard to feature a fixed sidebar, top-row KPIs, and a perfectly balanced split-view for mapping and financial forecasting.
* **Map Optimization**: Migrated to OpenStreetMap tiles and fixed infinite wrapping and rendering issues on ultra-wide monitors.

## 4. How the Application Flows
1. User **logs in** and navigates to the **Dashboard**.
2. User selects an Origin Port, Discharge Port, Cargo Volume, Contract Window, Fuel Price, and Transit Time.
3. On submit, JavaScript intercepts and sends a JSON payload to `/dashboard/api/analyze`.
4. The Backend Engine:
    * Calculates physical constraints and dynamic cargo caps via inverse-draft math.
    * Selects the largest feasible vessel.
    * Computes statistical risk and landed costs using Pandas, ensuring costs reflect the capped payload if constraints were breached.
5. The Backend returns JSON, and the Frontend updates the DOM in real-time, displaying the financial KPIs, visual chart, a clear charter recommendation, and any cargo cap warnings.
