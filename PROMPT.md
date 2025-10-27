You are a senior front-end engineer. Generate ONE self-contained HTML file
(no external build, no framework) that implements a browser-based, interactive
tariff-impact dashboard for actuator SKUs. Use the same tech stack as my reference:
Plotly for charts, PapaParse for CSV parsing, and Tabulator for interactive tables.
Add SheetJS (xlsx) to read an uploaded Excel workbook. Everything runs 100% in the browser.

Libraries (via CDN, latest stable):
- Plotly (plotly-latest.min.js)
- PapaParse (for CSV fallback)
- Tabulator (CSS + JS)
- SheetJS xlsx (to parse .xlsx in browser)

Data input:
- Primary: user uploads JE_Tariff_Shock_Demo_v5.xlsx (from working dir; example in repo) using a file input.
- Fallback: allow uploading a zipped set of CSVs OR pasting JSON rows.
- Read these sheets from the workbook: Products, BOM, Components, Sites, AssemblyOptions,
  LogisticsLanes, TariffScenarios, Tariffs_US, TariffInputs, MapNodes, FX (for display only).
- All monetary fields are already in CHF. DO NOT convert currencies.

Model & calculations (CHF everywhere):
- Join: BOM -> Components -> Sites (by OriginSiteID) to get OriginCountry and ComponentClass.
- Conversion costs: AssemblyOptions.BaseConvCost_CHF by (SKU, AssemblySiteID).
- Logistics cost:
  • Component legs: OriginCountry -> AssemblySite.Country using LogisticsLanes.Cost_per_kg_CHF × UnitWeight_kg.
  • Finished-good leg: AssemblySite.Country -> United States (unless assembly site is US).
  • Add Fixed_per_shipment_CHF naively per 10,000 units if the user enables a checkbox.
- Tariff logic (ad valorem % on customs value in CHF):
  1) If TariffInputs.UserRate_pct (by ComponentClass, OriginCountry) is not null, use it.
  2) Else use Tariffs_US for the selected ScenarioDate.
  3) Apply 'FinalAssembly' tariff when importing the finished good into the US and assembly is outside US.
- LandedCost_CHF per SKU = Material (Σ BasePrice_CHF × Qty / Yield)
  + Logistics (components→assembly + finished→US)
  + Tariffs (component-level + final-assembly where applicable)
  + Conversion (BaseConvCost_CHF).
- Margin_CHF = Products.ListPrice_CHF − LandedCost_CHF; also compute MarginPct.

UI/UX (JE-style, responsive, 3-pane layout):
- Header with title and small toolbar: file upload (.xlsx), “Paste JSON”, “Reset Overrides”, “Download CSV/XLSX (filtered)”.
- Left sidebar (filters/controls):
  • Radio: ScenarioDate (from TariffScenarios)
  • Radio: Final Assembly Site (BU_CH_MUR, PLANT_US_MI, PLANT_MX_NL)
  • Checkbox: “Include fixed logistics fees”
  • List of tariffs, each with a slider to adjust the value bound to TariffInputs.UserRate_pct 
    Keep edits in memory; “Reset Overrides” clears only UserRate_pct.
- Main area:
  • Top filter bar: SKU selector; counters for rows.
  • Card 1: KPI tiles per SKU: LandedCost_CHF, Margin_CHF, MarginPct (format CHF with thousands sep and 2 decimals).
  • Card 2: Stacked horizontal bar comparing cost components (Material / Logistics / Tariffs / Conversion) by assembly site.
  • Card 3: Table (Tabulator) of per-SKU cost breakdown, sortable/filterable, exportable (CSV/XLSX).
  • Tabs below:
    - “Map”: Plotly scattergeo showing MapNodes; draw geodesic lines reflecting flows
      (origin → assembly → US). Line color encodes share of landed cost; hover shows site role,
      country, tariff % used.
    - “What-if”: toggle motor routing (China→CH/US/MX) and recompute; show scatter of
      MarginPct vs. approx LeadTime (sum of LogisticsLanes.LeadTime_days).

Behavior:
- Recompute all metrics live on any UI change (scenario, assembly site, tariff overrides, what-if routing, checkbox).
- Keep code modular inside the single HTML: loadWorkbook(), toRowsFromSheets(), computeTariffs(), computeLogistics(),
  computeCosts(), renderKPIs(), renderCharts(), renderMap(), renderTables().
- Defensive parsing: if a sheet is missing, show a clear inline warning; never crash.
- Color-code consistently by assembly site or manufacturer; include a small legend.
- Currency formatting: always display “CHF” with the value (e.g., CHF 12’345.67).

Styling:
- Use CSS variables for JE-like palette:
  :root { --brand:#e9a16f; --sidebar:#f5c6a5; --panel:#fff7f1; --text:#333; --muted:#666; }
- Three-column responsive grid: left sidebar (filters), main content (charts/tables), right info panel.
- Right panel: “Insights” box that prints a short textual summary from current state
  (no AI—just imperative JS: e.g., “Assembling in MX improves Margin by +7.9 pts vs CH.”).

Deliverables:
- EXACTLY one HTML file, fully working offline after download.
- Use only the specified CDNs; no bundlers, no external CSS other than Tabulator.
- Keep the code clean, comment key functions, and ensure all units and labels say CHF.
