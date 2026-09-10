# 🚢 SAIL Safar - Completed Features

This document provides a comprehensive list of all the features and capabilities that have been successfully built into the SAIL Intelligent Freight Advisory Portal (SAIL Safar) to date.

## 1. Authentication & Security
* **Secure Access:** A robust User Registration and Login system using hashed passwords.
* **Session Management:** Flask-based session handling to protect dashboard routes from unauthorized access.

## 2. Public Landing Page & Data Showcase
* **Global Network Map:** A Leaflet.js interactive showpiece map on the landing page that automatically plots visually distinct markers for all active Indian Discharge Ports and Foreign Export Ports.
* **Infrastructure Grid:** Responsive CSS-Grid cards that display deep-water port draft limits, LOA constraints, and vessel fleet capacities (Handysize up to Capesize) prior to authentication.
* **Robust Data Loaders:** Dynamic parsing of maritime constraints from structured JSON files (`vessels.json`, `eastcoast_ports.json`, `foriegnports.json`).

## 3. The Interactive Procurement Dashboard
* **Dynamic Input Form:** A responsive sidebar for officers to input critical voyage parameters: Origin Port, Discharge Port, Cargo Volume, Contract Window, Fuel Price, and Est. Transit Time.
* **Asynchronous UX:** Powered by the Fetch API, the dashboard updates all visualizations, tables, and maps in real-time without reloading the page.
* **Vessel Feasibility Matrix:** A real-time table that displays the exact draft constraints for the selected route, visually flags vessel status, and shows the newly calculated **Max Safe Load (MT)** for each vessel class.
* **Dynamic Route Map:** An interactive Leaflet.js map that instantly drops markers on the selected Origin and Discharge ports, draws a dashed maritime route between them, and automatically pans/zooms the camera to frame the specific voyage.

## 4. The Mathematical & Strategic Engine
* **Live Pandas Integration:** Reads from actual historical Baltic Dry Index (BDI) datasets (`Cleaned_Capesize.csv`, etc.) in the backend.
* **Physical Constraints Engine:** Automatically cross-references port restrictions to select the absolute largest feasible vessel, maximizing economies of scale.
* **Dynamic Cargo Capping:** If a vessel's draft exceeds a port's limit, the engine uses inverse-draft math to calculate the maximum safe payload, capping the cargo and dynamically adjusting cost estimates rather than rejecting the vessel entirely.
* **Statistical Risk Indicators:** Dynamically calculates Mean Rate, Variance, Skewness, and Kurtosis over the specific contract window requested by the user.
* **True Landed Cost Calculator:** Computes the final Estimated Landed Cost per metric ton by fusing the statistical freight rate with the dynamic global bunker fuel price and daily fuel consumption of the vessel.
* **Automated Decision Matrix:** Outputs a firm strategic recommendation banner. If market skewness is heavily positive (indicating a risk of sudden price explosions), it recommends locking in a **Period Time Charter**. Otherwise, it suggests a **Spot Voyage Charter**.
* **Financial Forecasting:** Renders a dynamic Chart.js line graph mapping the historical freight rates for the chosen vessel class to aid visual trend analysis.

## 5. UI/UX & External Integrations (Version 2)
* **Marine Weather Evasion:** Integrated the Open-Meteo Marine API. The backend dynamically checks real-time wave heights at maritime chokepoints (e.g., Torres Strait, Lombok Strait) and automatically forces a longer weather evasion route (recalculating transit days and fuel costs) if severe swells are detected.
* **Enterprise Dashboard Overhaul:** Fully redesigned the dashboard utilizing a modern CSS Grid architecture, featuring a dedicated procurement sidebar, a 5-card KPI row, and a visually balanced side-by-side split for the Leaflet map and Chart.js forecast.
* **Elegant Home Page Redesign:** Restructured the landing page with a sticky navigation bar, a premium horizontal CSS Grid layout for data sections, and smooth CSS hover animations for infrastructure cards.
* **Map Enhancements:** Upgraded Leaflet.js rendering to use free OpenStreetMap tiles with boundary constraints to prevent infinite wrapping on ultrawide monitors, and dynamic height calculations to ensure reliable rendering within CSS Grids.
* **Maintainable Styling:** Replaced hardcoded CSS values with standard CSS variables (`:root`) for colors, shadows, and borders, ensuring the SAIL brand identity is consistent and easily themeable.
