# 🚢 SAIL Intelligent Freight Advisory Portal — Master Project Specification

## 1. Executive Summary
The **SAIL Intelligent Freight Advisory Portal** is a two-tiered Decision Support System (DSS) engineered for Steel Authority of India Limited (SAIL). It empowers branch procurement officers to optimize ocean freight contracts for imported coking and thermal coal. By fusing physical maritime constraints, historical market statistics (Baltic Dry Index), and live weather data, the portal calculates the true landed cost of freight and strategically recommends between a **Spot Voyage Charter** and a **Period Time Charter**.

---

## 2. Tech Stack & Architecture
* **Backend:** Python, Flask (Blueprint architecture).
* **Database:** SQLite via SQLAlchemy (User authentication and future trade logging).
* **Data Processing:** Pandas and NumPy for rapid statistical crunching of historical CSV datasets.
* **Frontend:** HTML5, Vanilla JavaScript (Fetch API for asynchronous DOM updates), CSS Grid (using official Government of India / SAIL corporate design guidelines).
* **Data Visualization:** Chart.js for lightweight, interactive web rendering.

---

## 3. Geographic & Physical Data Models (JSON)
To ensure hyper-accurate calculations without database bloat, physical constraints are strictly scoped to SAIL's primary corridors (Australia & Indonesia to India's East Coast).

### A. Evaluated Vessel Classes (`vessels.json`)
* **Handysize (~35,000 MT):** Shallow draft (10.0m), fuel consumption ~22 MT/day.
* **Supramax (~58,000 MT):** Medium draft (12.8m), fuel consumption ~28 MT/day.
* **Panamax (~75,000 MT):** Deep draft (14.5m), fuel consumption ~32 MT/day.
* **Capesize (~180,000 MT):** Ultra-deep draft (18.5m), fuel consumption ~42 MT/day.

### B. Maritime Port Constraints (`eastcoast_ports.json`, `foriegnports.json`)
* **Haldia Dock Complex:** Restricted riverine draft (9.0m). Only allows Handysize/Supramax (or requires partial-loading/transloading).
* **Paradip & Visakhapatnam:** Deep-water ports (16.5m - 18.0m) capable of accommodating Panamax and Capesize vessels.

---

## 4. The Mathematical & Strategic Engine
The backend doesn't just estimate costs; it calculates the exact risk profile of the market to drive procurement strategy.

### A. Contract Decision Logic
* **Spot Voyage Charter (Fixed $/MT):** Recommended when market variance is low or skewness is negative. The shipowner assumes the risk of weather delays and bunker fuel spikes.
* **Time Charter (Fixed $/Day):** Recommended when positive skewness indicates an impending upward price spike. SAIL assumes the risk of weather/fuel but hedges against market explosions.

### B. Landed Cost Calculation (Time Charter)
To compare a Time Charter against a historical Spot Rate, the engine calculates the true landed cost per metric ton using the following formula:

`Landed Cost = ((Daily Hire Rate * Total Voyage Days) + (Total Fuel Consumed * Bunker Price)) / Cargo Volume (MT)`

> **Note:** Total Voyage Days = Laden Transit Days + Ballast (Empty) Return Days + Port Turnaround Days.

### C. Statistical Risk Indicators (Pandas/NumPy)
* **Mean Rate:** Baseline expected freight cost over the 30/60/90-day horizon.
* **Variance:** Overall volatility and price instability.
* **Skewness (Risk Asymmetry):** The trigger metric. High positive skewness directly outputs a Time Charter recommendation.
* **Kurtosis (Tail Risk):** Probability of extreme, unpredictable market disruptions (black swan events).

---

## 5. Application Flow (Current & Roadmap)

### Phase 1: Completed Features
* **Authentication Hub:** Secure register/login system with hashed passwords and session management.
* **Public Landing Page:** A data-driven homepage displaying dynamic lists of managed ports and vessels prior to authentication.
* **Procurement Dashboard UI:** A clean, accessible interface featuring dynamic font resizing, seamless sidebar inputs, and a real-time Chart.js forecasting graph.
* **Asynchronous Math Engine:** Python backend that intercepts the `/api/analyze` POST request, cross-references physical draft constraints, and returns immediate UI updates without page reloads.

### Phase 2: Imminent Integrations (The Pivot)
* **Live CSV Integration:** Wiring Pandas to replace mock data with the actual BDI historical datasets (`Cleaned_Capesize.csv`, etc.).
* **Live Fuel Slider:** Adding an interactive global bunker fuel (VLSFO) variable to the dashboard to test market shocks in real-time.

### Phase 3: Advanced Future Features
* **Interactive Map UI:** Integrating a visual map (e.g., Leaflet.js) to display the specific maritime route selected (e.g., Torres Strait vs. Lombok Strait).
* **Live Weather Evasion (`routes.json` + Open-Meteo API):** Automatically pinging marine APIs at crucial chokepoints. If wave swells exceed safe limits, the system forces a longer "weather evasion route," recalculating the transit days and total fuel costs.
* **The Branch Feedback Loop:** A secure data-entry module where branch officers log the final negotiated price of completed trades. This data feeds back into the historical dataset, preventing "data drift" and continuously refining the math model.