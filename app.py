"""Dash application for tariff impact analysis of actuator SKUs."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.colors import sample_colorscale

from dash import Dash, Input, Output, dcc, html, dash_table

DATA_PATH = Path(__file__).resolve().parent / "JE_Tariff_Shock_Demo_v2.xlsx"
TARGET_SKUS = ["ACTUATOR_AX100", "ACTUATOR_AX200"]
COUNTRY_TO_CURRENCY = {
    "Switzerland": "CHF",
    "China": "CNY",
    "Serbia": "RSD",
    "United States": "USD",
    "Mexico": "MXN",
    "Germany": "EUR",
}
US_CUSTOMER_NODE = {
    "SiteID": "US_CUSTOMER",
    "Country": "United States",
    "City": "US Market",
    "Role": "Customer demand",
    "Lat": 41.8781,
    "Lon": -87.6298,
    "Region": "United States",
}


def load_data(excel_path: Path = DATA_PATH) -> Dict[str, pd.DataFrame]:
    """Load workbook sheets into DataFrames and normalise column types."""
    sheet_names = [
        "Products",
        "BOM",
        "Components",
        "Sites",
        "AssemblyOptions",
        "LogisticsLanes",
        "TariffScenarios",
        "Tariffs_US",
        "TariffInputs",
        "FX",
        "MapNodes",
    ]
    raw_data = pd.read_excel(excel_path, sheet_name=sheet_names)

    products = raw_data["Products"].copy()
    products["UnitWeight_kg"] = pd.to_numeric(products["UnitWeight_kg"], errors="coerce")
    products["ListPrice_USD"] = pd.to_numeric(products["ListPrice_USD"], errors="coerce")

    bom = raw_data["BOM"].copy()
    bom["Qty"] = pd.to_numeric(bom["Qty"], errors="coerce")

    components = raw_data["Components"].copy()
    components["UnitWeight_kg"] = pd.to_numeric(components["UnitWeight_kg"], errors="coerce")
    components["BasePrice_local"] = pd.to_numeric(components["BasePrice_local"], errors="coerce")

    sites = raw_data["Sites"].copy()
    for column in ("Lat", "Lon"):
        sites[column] = pd.to_numeric(sites[column], errors="coerce")

    assembly = raw_data["AssemblyOptions"].copy()
    assembly["BaseConvCost_USD"] = pd.to_numeric(assembly["BaseConvCost_USD"], errors="coerce")
    assembly["ScrapRate"] = pd.to_numeric(assembly["ScrapRate"], errors="coerce")
    assembly["Yield"] = pd.to_numeric(assembly["Yield"], errors="coerce")

    lanes = raw_data["LogisticsLanes"].copy()
    lanes["Cost_per_kg_USD"] = pd.to_numeric(lanes["Cost_per_kg_USD"], errors="coerce")
    lanes["Fixed_per_shipment_USD"] = pd.to_numeric(
        lanes["Fixed_per_shipment_USD"], errors="coerce"
    )
    lanes["LeadTime_days"] = pd.to_numeric(lanes["LeadTime_days"], errors="coerce")

    tariff_scenarios = raw_data["TariffScenarios"].copy()
    tariff_scenarios["ScenarioDate"] = pd.to_datetime(tariff_scenarios["ScenarioDate"]).dt.date

    tariffs_us = raw_data["Tariffs_US"].copy()
    tariffs_us["ScenarioDate"] = pd.to_datetime(tariffs_us["ScenarioDate"]).dt.date
    tariffs_us["US_AdValoremTariff_pct"] = pd.to_numeric(
        tariffs_us["US_AdValoremTariff_pct"], errors="coerce"
    )

    tariff_inputs = raw_data["TariffInputs"].copy()
    tariff_inputs["ScenarioDateDefault"] = pd.to_datetime(
        tariff_inputs["ScenarioDateDefault"]
    ).dt.date
    tariff_inputs["DefaultRate_pct"] = pd.to_numeric(
        tariff_inputs["DefaultRate_pct"], errors="coerce"
    )
    tariff_inputs["UserRate_pct"] = pd.to_numeric(
        tariff_inputs["UserRate_pct"], errors="coerce"
    )

    fx = raw_data["FX"].copy()
    fx["USD_per_unit"] = pd.to_numeric(fx["USD_per_unit"], errors="coerce")

    map_nodes = raw_data["MapNodes"].copy()
    map_nodes["Lat"] = pd.to_numeric(map_nodes["Lat"], errors="coerce")
    map_nodes["Lon"] = pd.to_numeric(map_nodes["Lon"], errors="coerce")

    return {
        "Products": products,
        "BOM": bom,
        "Components": components,
        "Sites": sites,
        "AssemblyOptions": assembly,
        "LogisticsLanes": lanes,
        "TariffScenarios": tariff_scenarios,
        "Tariffs_US": tariffs_us,
        "TariffInputs": tariff_inputs,
        "FX": fx,
        "MapNodes": map_nodes,
    }


def usd_to_chf(amount_usd: float, fx_rates: pd.Series) -> float:
    """Convert a USD amount to CHF using FX rates."""
    if pd.isna(amount_usd):
        return 0.0
    usd_per_chf = fx_rates.get("CHF", 1.0)
    if not usd_per_chf:
        return 0.0
    return amount_usd / usd_per_chf


def local_to_chf(amount: float, currency: str, fx_rates: pd.Series) -> float:
    """Convert a local currency amount to CHF using FX rates."""
    if pd.isna(amount):
        return 0.0
    usd_per_unit = fx_rates.get(currency, fx_rates.get("USD", 1.0))
    amount_usd = amount * usd_per_unit
    return usd_to_chf(amount_usd, fx_rates)


def compute_tariff_rate(
    component_class: str,
    origin_country: str,
    scenario_date: object,
    tariff_inputs: pd.DataFrame,
    tariffs_us: pd.DataFrame,
) -> Tuple[float, str]:
    """Determine tariff rate and its provenance for a component class and origin."""
    if tariff_inputs is not None and not tariff_inputs.empty:
        mask = (
            (tariff_inputs["ComponentClass"] == component_class)
            & (tariff_inputs["OriginCountry"] == origin_country)
        )
        candidate = tariff_inputs.loc[mask]
    else:
        candidate = pd.DataFrame()

    if not candidate.empty:
        override_value = candidate["UserRate_pct"].iloc[0]
        if pd.notna(override_value):
            return float(override_value) / 100.0, "Override"

    scenario_mask = (
        (tariffs_us["ScenarioDate"] == scenario_date)
        & (tariffs_us["ComponentClass"] == component_class)
        & (tariffs_us["OriginCountry"] == origin_country)
    )
    scenario_match = tariffs_us.loc[scenario_mask]
    if not scenario_match.empty:
        scenario_rate = scenario_match["US_AdValoremTariff_pct"].iloc[0]
        if pd.notna(scenario_rate):
            return float(scenario_rate) / 100.0, f"Scenario {scenario_date}"

    if not candidate.empty:
        default_rate = candidate["DefaultRate_pct"].iloc[0]
        if pd.notna(default_rate):
            return float(default_rate) / 100.0, "Default"

    return 0.0, "None"


def compute_costs(
    data: Dict[str, pd.DataFrame],
    scenario_date: object,
    assembly_site_id: str,
    tariff_records: Iterable[dict],
    include_fixed_fees: bool,
) -> Dict[str, pd.DataFrame | List[dict] | dict]:
    """Compute landed cost breakdown, tariffs, and flows for the selected scenario."""
    tariff_inputs = pd.DataFrame(tariff_records)
    if not tariff_inputs.empty:
        tariff_inputs["UserRate_pct"] = pd.to_numeric(
            tariff_inputs.get("UserRate_pct"), errors="coerce"
        )
        tariff_inputs["DefaultRate_pct"] = pd.to_numeric(
            tariff_inputs.get("DefaultRate_pct"), errors="coerce"
        )

    fx_rates = data["FX"].set_index("Currency")["USD_per_unit"].astype(float)

    sites = data["Sites"].set_index("SiteID")
    if assembly_site_id not in sites.index:
        raise ValueError(f"Unknown assembly site: {assembly_site_id}")
    assembly_site = sites.loc[assembly_site_id]
    assembly_country = assembly_site["Country"]
    assembly_role = assembly_site["Role"]

    origin_info = (
        data["Sites"][["SiteID", "Country", "Role"]]
        .rename(columns={"Country": "OriginCountry", "Role": "OriginRole"})
        .set_index("SiteID")
    )

    products = data["Products"].set_index("SKU")
    components_df = data["Components"].copy()
    components_df = components_df.merge(
        origin_info.reset_index(),
        how="left",
        left_on="OriginSiteID",
        right_on="SiteID",
    )
    components_df = components_df.rename(columns={"OriginCountry": "ComponentOrigin"})

    assembly_options = data["AssemblyOptions"]
    logistics_lanes = data["LogisticsLanes"]
    tariffs_us = data["Tariffs_US"]

    scenario_results: List[dict] = []
    flow_records: List[dict] = []

    for sku in TARGET_SKUS:
        if sku not in products.index:
            continue
        sku_product = products.loc[sku]

        option_mask = (
            (assembly_options["SKU"] == sku) & (assembly_options["AssemblySiteID"] == assembly_site_id)
        )
        if not option_mask.any():
            continue
        option_row = assembly_options.loc[option_mask].iloc[0]
        yield_rate = option_row.get("Yield", 1.0)
        if not yield_rate:
            yield_rate = 1.0
        conversion_cost_chf = usd_to_chf(option_row.get("BaseConvCost_USD", 0.0), fx_rates)

        sku_bom = data["BOM"][data["BOM"]["ParentSKU"] == sku]
        if sku_bom.empty:
            continue
        bom_components = sku_bom.merge(
            components_df,
            how="left",
            on="PartID",
        )

        material_total = 0.0
        inbound_logistics_total = 0.0
        component_tariffs_total = 0.0
        component_leads: List[float] = []
        component_flow_entries: List[dict] = []

        for _, component in bom_components.iterrows():
            quantity = float(component.get("Qty", 0.0)) / yield_rate
            unit_weight = float(component.get("UnitWeight_kg", 0.0))
            component_weight = quantity * unit_weight
            origin_site = component.get("OriginSiteID")
            origin_country = component.get("ComponentOrigin")
            origin_role = None
            if origin_site in origin_info.index:
                origin_country = origin_info.loc[origin_site, "OriginCountry"]
                origin_role = origin_info.loc[origin_site, "OriginRole"]

            currency = COUNTRY_TO_CURRENCY.get(origin_country, "USD")
            base_price_local = float(component.get("BasePrice_local", 0.0))
            material_cost = local_to_chf(base_price_local * quantity, currency, fx_rates)
            material_total += material_cost

            lane_match = logistics_lanes[
                (logistics_lanes["FromCountry"] == origin_country)
                & (logistics_lanes["ToCountry"] == assembly_country)
            ]
            if not lane_match.empty:
                lane_row = lane_match.iloc[0]
                logistics_cost_usd = float(lane_row.get("Cost_per_kg_USD", 0.0)) * component_weight
                if include_fixed_fees:
                    logistics_cost_usd += float(lane_row.get("Fixed_per_shipment_USD", 0.0)) / 10000.0
                logistics_cost = usd_to_chf(logistics_cost_usd, fx_rates)
                lead_time = float(lane_row.get("LeadTime_days", 0.0))
            else:
                logistics_cost = 0.0
                lead_time = 0.0
            inbound_logistics_total += logistics_cost
            component_leads.append(lead_time)

            if assembly_country == "United States":
                tariff_rate, tariff_source = compute_tariff_rate(
                    component.get("Class"), origin_country, scenario_date, tariff_inputs, tariffs_us
                )
            else:
                tariff_rate, tariff_source = (0.0, "Outside US")
            component_tariff_value = material_cost * tariff_rate
            component_tariffs_total += component_tariff_value

            flow_entry = {
                "SKU": sku,
                "component": component.get("PartID"),
                "from_site": origin_site,
                "to_site": assembly_site_id,
                "from_country": origin_country,
                "to_country": assembly_country,
                "from_role": origin_role,
                "to_role": assembly_role,
                "tariff_rate": tariff_rate,
                "tariff_source": tariff_source,
                "cost_value": material_cost + logistics_cost + component_tariff_value,
            }
            component_flow_entries.append(flow_entry)

        outbound_lane = logistics_lanes[
            (logistics_lanes["FromCountry"] == assembly_country)
            & (logistics_lanes["ToCountry"] == "United States")
        ]
        if not outbound_lane.empty:
            outbound_row = outbound_lane.iloc[0]
            finished_weight = float(sku_product.get("UnitWeight_kg", 0.0))
            outbound_cost_usd = float(outbound_row.get("Cost_per_kg_USD", 0.0)) * finished_weight
            if include_fixed_fees:
                outbound_cost_usd += float(outbound_row.get("Fixed_per_shipment_USD", 0.0)) / 10000.0
            outbound_cost = usd_to_chf(outbound_cost_usd, fx_rates)
            outbound_lead = float(outbound_row.get("LeadTime_days", 0.0))
        else:
            outbound_cost = 0.0
            outbound_lead = 0.0

        final_tariff_rate, final_tariff_source = (0.0, "Domestic")
        if assembly_country != "United States":
            final_tariff_rate, final_tariff_source = compute_tariff_rate(
                "FinalAssembly", assembly_country, scenario_date, tariff_inputs, tariffs_us
            )
        final_tariff_base = material_total + inbound_logistics_total + conversion_cost_chf
        final_tariff_value = final_tariff_base * final_tariff_rate

        total_tariffs = component_tariffs_total + final_tariff_value
        total_logistics = inbound_logistics_total + outbound_cost
        landed_cost = material_total + total_logistics + total_tariffs + conversion_cost_chf
        list_price_chf = usd_to_chf(float(sku_product.get("ListPrice_USD", 0.0)), fx_rates)
        margin_chf = list_price_chf - landed_cost
        margin_pct = (margin_chf / list_price_chf) if list_price_chf else 0.0
        lead_time_days = (max(component_leads) if component_leads else 0.0) + outbound_lead

        scenario_results.append(
            {
                "ScenarioDate": scenario_date,
                "AssemblySite": assembly_site_id,
                "SKU": sku,
                "SKU_Display": sku.replace("ACTUATOR_", ""),
                "MaterialCost_CHF": material_total,
                "InboundLogistics_CHF": inbound_logistics_total,
                "OutboundLogistics_CHF": outbound_cost,
                "Tariffs_CHF": total_tariffs,
                "ConversionCost_CHF": conversion_cost_chf,
                "LandedCost_CHF": landed_cost,
                "ListPrice_CHF": list_price_chf,
                "Margin_CHF": margin_chf,
                "MarginPct": margin_pct,
                "LeadTime_days": lead_time_days,
            }
        )

        for entry in component_flow_entries:
            if entry["cost_value"] <= 0:
                continue
            if landed_cost:
                entry["cost_share"] = entry["cost_value"] / landed_cost
            else:
                entry["cost_share"] = 0.0
            flow_records.append(entry)

        final_flow_value = outbound_cost + final_tariff_value
        if final_flow_value > 0:
            final_flow = {
                "SKU": sku,
                "component": "Finished Good",
                "from_site": assembly_site_id,
                "to_site": US_CUSTOMER_NODE["SiteID"],
                "from_country": assembly_country,
                "to_country": "United States",
                "from_role": assembly_role,
                "to_role": US_CUSTOMER_NODE["Role"],
                "tariff_rate": final_tariff_rate,
                "tariff_source": final_tariff_source,
                "cost_value": final_flow_value,
            }
            if landed_cost:
                final_flow["cost_share"] = final_flow_value / landed_cost
            else:
                final_flow["cost_share"] = 0.0
            flow_records.append(final_flow)

    summary_df = pd.DataFrame(scenario_results)
    breakdown_df = summary_df[[
        "ScenarioDate",
        "AssemblySite",
        "SKU_Display",
        "MaterialCost_CHF",
        "InboundLogistics_CHF",
        "OutboundLogistics_CHF",
        "Tariffs_CHF",
        "ConversionCost_CHF",
        "LandedCost_CHF",
        "ListPrice_CHF",
        "Margin_CHF",
        "MarginPct",
        "LeadTime_days",
    ]].copy() if not summary_df.empty else pd.DataFrame()

    return {
        "summary": summary_df,
        "breakdown": breakdown_df,
        "flows": flow_records,
        "assembly_site": {
            "id": assembly_site_id,
            "country": assembly_country,
            "role": assembly_role,
        },
    }


def build_map(flow_records: List[dict], nodes: pd.DataFrame) -> go.Figure:
    """Create a supply chain flow map coloured by landed-cost contribution."""
    base_fig = go.Figure()
    if not flow_records:
        base_fig.update_layout(
            geo=dict(showframe=False, showcoastlines=True),
            margin=dict(l=0, r=0, t=0, b=0),
        )
        return base_fig

    nodes_ext = pd.concat([
        nodes,
        pd.DataFrame([US_CUSTOMER_NODE])
    ], ignore_index=True)
    nodes_ext = nodes_ext.drop_duplicates(subset="SiteID", keep="first").set_index("SiteID")

    flow_df = pd.DataFrame(flow_records)
    flow_df["cost_share"] = flow_df["cost_share"].fillna(0.0).clip(lower=0.0)

    for _, flow in flow_df.iterrows():
        if flow["from_site"] not in nodes_ext.index or flow["to_site"] not in nodes_ext.index:
            continue
        start = nodes_ext.loc[flow["from_site"]]
        end = nodes_ext.loc[flow["to_site"]]
        share = float(flow["cost_share"])
        color = sample_colorscale("Viridis", min(max(share, 0.0), 1.0))
        hover_text = (
            f"{flow['component']} ({flow['from_country']} → {flow['to_country']})<br>"
            f"Share: {share:.1%}<br>Tariff: {flow['tariff_rate'] * 100:.1f}% ({flow['tariff_source']})"
        )
        base_fig.add_trace(
            go.Scattergeo(
                lon=[start["Lon"], end["Lon"]],
                lat=[start["Lat"], end["Lat"]],
                mode="lines",
                line=dict(color=color, width=2 + 6 * share),
                hoverinfo="text",
                text=hover_text,
            )
        )

    unique_nodes = nodes_ext.loc[
        nodes_ext.index.isin(flow_df["from_site"]) | nodes_ext.index.isin(flow_df["to_site"])
    ]
    base_fig.add_trace(
        go.Scattergeo(
            lon=unique_nodes["Lon"],
            lat=unique_nodes["Lat"],
            mode="markers",
            marker=dict(size=8, color="#2a3f5f"),
            text=[
                f"{idx}: {row['City']}<br>{row['Role']}" for idx, row in unique_nodes.iterrows()
            ],
            hoverinfo="text",
        )
    )

    base_fig.update_layout(
        geo=dict(
            showframe=False,
            showcoastlines=True,
            projection_type="natural earth",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
    )
    return base_fig


def render_kpi_cards(summary: pd.DataFrame) -> List[html.Div]:
    """Generate KPI cards summarising landed cost and margin per SKU."""
    cards: List[html.Div] = []
    if summary.empty:
        return cards
    for _, row in summary.iterrows():
        margin_pct_display = f"{row['MarginPct'] * 100:.1f}%" if row['ListPrice_CHF'] else "N/A"
        cards.append(
            html.Div(
                [
                    html.H4(row["SKU_Display"], className="kpi-title"),
                    html.P(f"Landed cost: CHF {row['LandedCost_CHF']:.2f}"),
                    html.P(f"Margin: CHF {row['Margin_CHF']:.2f}"),
                    html.P(f"Margin %: {margin_pct_display}"),
                ],
                className="kpi-card",
            )
        )
    return cards


def build_app() -> Dash:
    """Create and configure the Dash application instance."""
    data = load_data()
    tariff_defaults = data["TariffInputs"].copy()
    tariff_defaults["UserRate_pct"] = tariff_defaults["UserRate_pct"].apply(
        lambda value: None if pd.isna(value) else value
    )
    tariff_records_default = tariff_defaults[
        ["ComponentClass", "OriginCountry", "DefaultRate_pct", "UserRate_pct"]
    ].to_dict("records")

    scenario_options = [
        {"label": f"{row['ScenarioDate']} – {row['Description']}", "value": row["ScenarioDate"]}
        for _, row in data["TariffScenarios"].iterrows()
    ]

    assembly_sites = sorted({
        row["AssemblySiteID"] for _, row in data["AssemblyOptions"].iterrows()
    })
    assembly_options = [
        {"label": site, "value": site}
        for site in assembly_sites
    ]

    app = Dash(__name__)
    app.title = "Tariff Impact Dashboard"

    app.layout = html.Div(
        [
            html.Div(
                [
                    html.H2("Tariff impact dashboard"),
                    html.Label("Scenario date"),
                    dcc.RadioItems(
                        id="scenario-radio",
                        options=scenario_options,
                        value=scenario_options[0]["value"] if scenario_options else None,
                        className="control-radio",
                    ),
                    html.Label("Final assembly site"),
                    dcc.RadioItems(
                        id="assembly-site-radio",
                        options=assembly_options,
                        value=assembly_options[0]["value"] if assembly_options else None,
                        className="control-radio",
                    ),
                    dcc.Checklist(
                        id="fixed-fee-checkbox",
                        options=[{"label": "Include fixed logistics fees", "value": "include"}],
                        value=[],
                        className="control-checkbox",
                    ),
                    html.H3("Tariff overrides"),
                    html.P(
                        "Edit the UserRate_pct column to override the scenario tariff."
                    ),
                    dash_table.DataTable(
                        id="tariff-input-table",
                        columns=[
                            {"name": "Component class", "id": "ComponentClass"},
                            {"name": "Origin country", "id": "OriginCountry"},
                            {"name": "Default rate (%)", "id": "DefaultRate_pct", "type": "numeric"},
                            {"name": "User rate (%)", "id": "UserRate_pct", "type": "numeric"},
                        ],
                        data=[dict(record) for record in tariff_records_default],
                        editable=True,
                        style_table={"maxHeight": "400px", "overflowY": "auto"},
                        style_cell={"textAlign": "left"},
                    ),
                    html.Button("Reset Overrides", id="reset-overrides-btn", n_clicks=0, className="control-button"),
                ],
                className="sidebar",
            ),
            html.Div(
                [
                    dcc.Tabs(
                        [
                            dcc.Tab(
                                label="Overview",
                                children=[
                                    html.Div(id="kpi-container", className="kpi-container"),
                                    dcc.Graph(id="assembly-comparison-chart"),
                                    dash_table.DataTable(
                                        id="cost-breakdown-table",
                                        columns=[
                                            {"name": "Scenario", "id": "ScenarioDate"},
                                            {"name": "Assembly", "id": "AssemblySite"},
                                            {"name": "SKU", "id": "SKU_Display"},
                                            {"name": "Material (CHF)", "id": "MaterialCost_CHF", "type": "numeric"},
                                            {"name": "Inbound log (CHF)", "id": "InboundLogistics_CHF", "type": "numeric"},
                                            {"name": "Outbound log (CHF)", "id": "OutboundLogistics_CHF", "type": "numeric"},
                                            {"name": "Tariffs (CHF)", "id": "Tariffs_CHF", "type": "numeric"},
                                            {"name": "Conversion (CHF)", "id": "ConversionCost_CHF", "type": "numeric"},
                                            {"name": "Landed cost (CHF)", "id": "LandedCost_CHF", "type": "numeric"},
                                            {"name": "List price (CHF)", "id": "ListPrice_CHF", "type": "numeric"},
                                            {"name": "Margin (CHF)", "id": "Margin_CHF", "type": "numeric"},
                                            {"name": "Margin %", "id": "MarginPct", "type": "numeric"},
                                            {"name": "Lead time (days)", "id": "LeadTime_days", "type": "numeric"},
                                        ],
                                        data=[],
                                        style_table={"overflowX": "auto"},
                                        style_cell={"padding": "4px", "textAlign": "left"},
                                    ),
                                ],
                            ),
                            dcc.Tab(
                                label="Map",
                                children=[
                                    dcc.Graph(id="supply-map"),
                                ],
                            ),
                            dcc.Tab(
                                label="What-if",
                                children=[
                                    html.Div(
                                        [
                                            html.Label("Motor routing (China → …)"),
                                            dcc.RadioItems(
                                                id="motor-route-radio",
                                                options=[
                                                    {"label": "China → Switzerland (Murten)", "value": "BU_CH_MUR"},
                                                    {"label": "China → United States (Monroe)", "value": "PLANT_US_MI"},
                                                    {"label": "China → Mexico (Monterrey)", "value": "PLANT_MX_NL"},
                                                ],
                                                value="BU_CH_MUR",
                                                className="control-radio",
                                            ),
                                        ]
                                    ),
                                    dcc.Graph(id="what-if-scatter"),
                                    dash_table.DataTable(
                                        id="what-if-table",
                                        columns=[
                                            {"name": "Assembly", "id": "AssemblySite"},
                                            {"name": "SKU", "id": "SKU_Display"},
                                            {"name": "Landed cost (CHF)", "id": "LandedCost_CHF", "type": "numeric"},
                                            {"name": "Margin (CHF)", "id": "Margin_CHF", "type": "numeric"},
                                            {"name": "Lead time (days)", "id": "LeadTime_days", "type": "numeric"},
                                        ],
                                        data=[],
                                        style_table={"overflowX": "auto"},
                                        style_cell={"padding": "4px", "textAlign": "left"},
                                    ),
                                ],
                            ),
                        ]
                    )
                ],
                className="main-content",
            ),
        ],
        className="app-container",
    )

    @app.callback(
        Output("tariff-input-table", "data"),
        Input("reset-overrides-btn", "n_clicks"),
        prevent_initial_call=True,
    )
    def reset_tariff_overrides(_: int) -> List[dict]:
        """Reset tariff overrides to defaults."""
        return [dict(record) for record in tariff_records_default]

    @app.callback(
        Output("kpi-container", "children"),
        Output("assembly-comparison-chart", "figure"),
        Output("cost-breakdown-table", "data"),
        Output("supply-map", "figure"),
        Output("what-if-scatter", "figure"),
        Output("what-if-table", "data"),
        Input("scenario-radio", "value"),
        Input("assembly-site-radio", "value"),
        Input("tariff-input-table", "data"),
        Input("fixed-fee-checkbox", "value"),
        Input("motor-route-radio", "value"),
    )
    def refresh_dashboard(
        scenario_value: object,
        assembly_value: str,
        tariff_table: List[dict],
        fixed_fee_selection: List[str],
        motor_route_site: str,
    ):
        include_fixed = "include" in fixed_fee_selection

        try:
            base_result = compute_costs(
                data,
                scenario_value,
                assembly_value,
                tariff_table,
                include_fixed,
            )
        except ValueError:
            empty_fig = go.Figure()
            return [], empty_fig, [], empty_fig, empty_fig, []

        # Compute comparison across all assembly options
        site_results = {}
        for site_id in assembly_sites:
            site_results[site_id] = compute_costs(
                data,
                scenario_value,
                site_id,
                tariff_table,
                include_fixed,
            )

        comparison_records: List[dict] = []
        for site_id, result in site_results.items():
            summary = result["summary"]
            for _, row in summary.iterrows():
                comparison_records.append(
                    {
                        "AssemblySite": site_id,
                        "SKU": row["SKU_Display"],
                        "LandedCost_CHF": row["LandedCost_CHF"],
                    }
                )
        comparison_df = pd.DataFrame(comparison_records)
        if comparison_df.empty:
            comparison_fig = go.Figure()
            comparison_fig.update_layout(title="Landed cost by assembly site")
        else:
            comparison_fig = px.bar(
                comparison_df,
                x="AssemblySite",
                y="LandedCost_CHF",
                color="SKU",
                barmode="group",
                title="Landed cost by assembly site",
                labels={"LandedCost_CHF": "Landed cost (CHF)", "SKU": "SKU"},
            )

        kpi_cards = render_kpi_cards(base_result["summary"])
        breakdown_data = base_result["breakdown"].to_dict("records")

        map_fig = build_map(base_result["flows"], data["MapNodes"])

        what_if_result = compute_costs(
            data,
            scenario_value,
            motor_route_site,
            tariff_table,
            include_fixed,
        )
        what_if_summary = what_if_result["summary"]
        if what_if_summary.empty:
            scatter_fig = go.Figure()
            scatter_fig.update_layout(title="Cost vs lead time (what-if motor routing)")
            what_if_table_data: List[dict] = []
        else:
            scatter_fig = px.scatter(
                what_if_summary,
                x="LeadTime_days",
                y="LandedCost_CHF",
                color="SKU_Display",
                hover_data={"Margin_CHF": ":.2f", "LandedCost_CHF": ":.2f"},
                title="Cost vs lead time (what-if motor routing)",
                labels={"LeadTime_days": "Lead time (days)", "LandedCost_CHF": "Landed cost (CHF)"},
            )
            what_if_table_data = what_if_summary[[
                "AssemblySite",
                "SKU_Display",
                "LandedCost_CHF",
                "Margin_CHF",
                "LeadTime_days",
            ]].to_dict("records")

        return (
            kpi_cards,
            comparison_fig,
            breakdown_data,
            map_fig,
            scatter_fig,
            what_if_table_data,
        )

    app.index_string = """
    <!DOCTYPE html>
    <html>
        <head>
            {%metas%}
            <title>{%title%}</title>
            {%favicon%}
            {%css%}
            <style>
                body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif; margin: 0; }
                .app-container { display: flex; min-height: 100vh; }
                .sidebar { width: 320px; padding: 20px; background-color: #f4f6f8; box-shadow: 2px 0 8px rgba(0,0,0,0.05); }
                .main-content { flex: 1; padding: 20px; }
                .kpi-container { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
                .kpi-card { background: white; border-radius: 8px; padding: 12px 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.1); min-width: 180px; }
                .kpi-title { margin-bottom: 8px; }
                .control-radio, .control-checkbox { margin-bottom: 16px; }
                .control-button { margin-top: 12px; }
            </style>
        </head>
        <body>
            {%app_entry%}
            <footer>
                {%config%}
                {%scripts%}
                {%renderer%}
            </footer>
        </body>
    </html>
    """

    return app


app = build_app()
server = app.server


if __name__ == "__main__":
    app.run_server(debug=True)
