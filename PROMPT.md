You are a senior Python engineer. Build a Plotly Dash web app that reads
'JE_Tariff_Shock_Demo_v2.xlsx' from the working directory and renders a dynamic
tariff impact dashboard for actuator SKUs (AX100, AX200) sold into the US market.

Data model:
- Read sheets: Products, BOM, Components, Sites, AssemblyOptions, LogisticsLanes,
  TariffScenarios, Tariffs_US, TariffInputs, MapNodes.
- Join BOM -> Components -> Sites (by OriginSiteID) to get origin country and class.
- Conversion costs come from AssemblyOptions per (SKU, AssemblySiteID).
- Logistics cost: approximate per component as weight * lane $/kg from origin country
  to the selected final assembly site, then from assembly site country to US for the
  finished good. Ignore fixed-per-shipment in the first pass (keep the column for later).
- Tariff rate logic:
  1) If TariffInputs.UserRate_pct is not null for (ComponentClass, OriginCountry), use it.
  2) Otherwise lookup Tariffs_US by ScenarioDate selected in the UI.
  3) Apply 'FinalAssembly' tariff to finished goods imported into the US if assembly is outside US.
- Landed cost per SKU:
  material (Σ component base price * qty / yield) +
  logistics (components to assembly + finished good to US) +
  tariffs (component-level + final assembly import where applicable) +
  conversion (from AssemblyOptions).
- Margin = ListPrice_USD - LandedCost.

UI requirements:
- Left sidebar controls:
  * Radio: ScenarioDate (values from TariffScenarios)
  * Radio: Final Assembly Site (BU_CH_MUR, PLANT_US_MI, PLANT_MX_NL)
  * Editable tariff table: display TariffInputs with a column for UserRate_pct (nullable).
    Persist edits in memory (no file write). A button 'Reset Overrides' clears UserRate_pct.
  * Checkbox: 'Include fixed logistics fees' (applies Fixed_per_shipment_USD naively per 10k units).
- Main area tabs:
  1) 'Overview': KPI cards (Landed cost, Margin, Margin%), segmented by SKU; a bar chart
     comparing current assembly choice vs. alternatives; and a small table of cost breakdown.
  2) 'Map': world map (Plotly scattergeo) plotting MapNodes with lines representing flows
     (origin -> assembly -> US). Color lines by cost contribution (% of landed cost). Tooltip shows
     country, role, and tariff used.
  3) 'What-if': controls to toggle motor routing (China→CH/US/MX), and recompute; show a
     cost vs. lead-time scatter (approximate lead-time from LogisticsLanes LeadTime_days).
- App should recompute metrics on any change without page reload.
- Keep code modular: functions for load_data(), compute_costs(), compute_tariffs(), build_map().

Non-functional:
- Pin dependencies in requirements.txt: dash, pandas, plotly, openpyxl.
- Provide docstrings and type hints.
- Use clear variable names; keep all units in USD and kg; scenario/subtotals must be visible.

Deliverables:
- app.py (Dash app)
- requirements.txt
- A short README.md with 'How to run' steps: `pip install -r requirements.txt` and `python app.py`.
