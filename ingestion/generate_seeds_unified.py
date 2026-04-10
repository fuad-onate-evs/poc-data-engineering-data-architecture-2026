"""
Unified Seed Generator — Chile SEN → Final Fantasy Gaia Grid
=============================================================
Uses real Chilean energy data as source of truth, then maps to FF cities.

REAL DATA SOURCES (Chile):
──────────────────────────
1. Coordinador Eléctrico Nacional (CEN)
   - API Portal:     https://portal.api.coordinador.cl/
   - SCADA real-time: https://www.coordinador.cl/operacion/graficos/operacion-real/generacion-real-horaria-scada/
   - Hourly gen CSV:  https://www.coordinador.cl/reportes-y-estadisticas/ → "Generación Horaria por Central"
   - Reservoir data:  https://www.coordinador.cl/reportes-y-estadisticas/ → "Histórico Embalses"
   - Curtailment:     CEN monthly reports (reducción ERV)
   - SIP API docs:    https://www.coordinador.cl/wp-content/uploads/2019/01/Uso-Api-SIP-v1.1.pdf

2. Comisión Nacional de Energía (CNE) — Energía Abierta
   - Portal:          https://energiaabierta.cl/
   - Dev API:         https://desarrolladores.energiaabierta.cl/
   - Installed cap:   /capacidad-instalada/v1/convencional.json?auth_key=YOUR_KEY
   - Generation:      /generacion-bruta/v1/ernc.json?auth_key=YOUR_KEY
   - Marginal cost:   /costos-marginales/v1/barras.json?auth_key=YOUR_KEY
   - Junar datasets:  https://datos.energiaabierta.cl/

3. RENOVA — Renewable Traceability Registry
   - Portal:          https://www.coordinador.cl/renova/

4. Generadoras de Chile (industry association)
   - Monthly bulletin with renewable share, curtailment, capacity

PIPELINE: Chile (source of truth) → Chile seeds → FF seeds (mapped)
═══════════════════════════════════════════════════════════════════

  ┌──────────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
  │  CEN API / CSV       │────▶│  Chile 12 nodes    │────▶│  FF 12 nodes         │
  │  Energía Abierta API │     │  (real SEN data)   │     │  (mapped via         │
  │  RENOVA              │     │  transform/seeds/  │     │   CHILE_TO_FF table) │
  │  Generadoras Chile   │     └────────────────────┘     │  transform/seeds_ff/ │
  └──────────────────────┘                                └──────────────────────┘

Run:
  python ingestion/generate_seeds_unified.py --mode chile    # Only Chile
  python ingestion/generate_seeds_unified.py --mode ff       # Only FF
  python ingestion/generate_seeds_unified.py --mode both     # Both (default)
  python ingestion/generate_seeds_unified.py --mode both --days 30  # 30 days
"""

import argparse
import csv
import math
import os
import random
from datetime import datetime, timedelta

random.seed(42)

# ═══════════════════════════════════════════════════════════════
# CHILE NODES — Based on real SEN data (Dec 2025: 36,390 MW installed, 72% renewable)
# Source: CEN Reporte Anual + Generadoras de Chile boletín mensual
# Capacity values approximated from CNE Energía Abierta regional breakdown
# ═══════════════════════════════════════════════════════════════
CHILE_NODES = [
    {
        "node_id": "CL01",
        "name": "Arica",
        "region": "Arica y Parinacota",
        "lat": -18.48,
        "lon": -70.33,
        "solar_cap": 280,
        "wind_cap": 40,
        "hydro_cap": 0,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 90,
        "peak_mult": 1.3,
        "ppa_usd": 40,
        "cen_barra": "Parinacota__220",
        "climate": "desert",
        "notes": "Northernmost SEN node. High irradiance (>2500 kWh/m²/yr). PMGD solar growth.",
    },
    {
        "node_id": "CL02",
        "name": "Iquique",
        "region": "Tarapacá",
        "lat": -20.21,
        "lon": -70.13,
        "solar_cap": 350,
        "wind_cap": 60,
        "hydro_cap": 0,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 150,
        "peak_mult": 1.3,
        "ppa_usd": 41,
        "cen_barra": "Lagunas__220",
        "climate": "desert",
        "notes": "Mining + port demand. Solar dominant. Collahuasi/Quebrada Blanca loads.",
    },
    {
        "node_id": "CL03",
        "name": "Calama",
        "region": "Antofagasta",
        "lat": -22.46,
        "lon": -68.93,
        "solar_cap": 500,
        "wind_cap": 50,
        "hydro_cap": 0,
        "geo_cap": 30,
        "tidal_cap": 0,
        "base_demand": 600,
        "peak_mult": 1.1,
        "ppa_usd": 44,
        "cen_barra": "Crucero__220",
        "climate": "desert",
        "notes": "Chuquicamata/Escondida mining load. Cerro Pabellón geothermal (48MW). Highest curtailment zone.",
    },
    {
        "node_id": "CL04",
        "name": "Copiapó",
        "region": "Atacama",
        "lat": -27.37,
        "lon": -70.33,
        "solar_cap": 420,
        "wind_cap": 90,
        "hydro_cap": 0,
        "geo_cap": 20,
        "tidal_cap": 0,
        "base_demand": 200,
        "peak_mult": 1.4,
        "ppa_usd": 42,
        "cen_barra": "Cardones__220",
        "climate": "desert",
        "notes": "Nueva Cardones-Maitencillo 2x500kV bottleneck. Major curtailment point. Solar+CSP.",
    },
    {
        "node_id": "CL05",
        "name": "La Serena",
        "region": "Coquimbo",
        "lat": -29.90,
        "lon": -71.25,
        "solar_cap": 200,
        "wind_cap": 320,
        "hydro_cap": 40,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 180,
        "peak_mult": 1.5,
        "ppa_usd": 45,
        "cen_barra": "Pan_de_Azucar__220",
        "climate": "coastal",
        "notes": "Wind corridor (Punta Colorada, Cabo Leones). Transition zone solar→wind.",
    },
    {
        "node_id": "CL06",
        "name": "Valparaíso",
        "region": "Valparaíso",
        "lat": -33.05,
        "lon": -71.61,
        "solar_cap": 120,
        "wind_cap": 150,
        "hydro_cap": 80,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 450,
        "peak_mult": 1.5,
        "ppa_usd": 50,
        "cen_barra": "Quillota__220",
        "climate": "coastal",
        "notes": "Port + urban demand. Ventanas coal phase-out zone. Aconcagua hydro.",
    },
    {
        "node_id": "CL07",
        "name": "Santiago",
        "region": "Metropolitana",
        "lat": -33.45,
        "lon": -70.65,
        "solar_cap": 150,
        "wind_cap": 60,
        "hydro_cap": 200,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 1400,
        "peak_mult": 1.6,
        "ppa_usd": 52,
        "cen_barra": "Alto_Jahuel__220",
        "climate": "temperate",
        "notes": "Main demand center (~40% national). Net importer. Maipo hydro cascade.",
    },
    {
        "node_id": "CL08",
        "name": "Rancagua",
        "region": "O'Higgins",
        "lat": -34.17,
        "lon": -70.74,
        "solar_cap": 100,
        "wind_cap": 80,
        "hydro_cap": 250,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 350,
        "peak_mult": 1.3,
        "ppa_usd": 46,
        "cen_barra": "Rapel__220",
        "climate": "temperate",
        "notes": "Rapel reservoir (380MW). El Teniente mining. Cachapoal/Tinguiririca hydro.",
    },
    {
        "node_id": "CL09",
        "name": "Concepción",
        "region": "Biobío",
        "lat": -36.82,
        "lon": -73.05,
        "solar_cap": 60,
        "wind_cap": 240,
        "hydro_cap": 380,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 520,
        "peak_mult": 1.3,
        "ppa_usd": 38,
        "cen_barra": "Charrua__220",
        "climate": "temperate",
        "notes": "Charrúa-Puerto Montt congestion (42% hours). Ralco/Pangue hydro. Forestry biomass.",
    },
    {
        "node_id": "CL10",
        "name": "Temuco",
        "region": "Araucanía",
        "lat": -38.74,
        "lon": -72.60,
        "solar_cap": 30,
        "wind_cap": 180,
        "hydro_cap": 300,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 250,
        "peak_mult": 1.4,
        "ppa_usd": 37,
        "cen_barra": "Temuco__220",
        "climate": "temperate",
        "notes": "Biobío river hydro. Wind growth. Leña demand for heating (winter peak).",
    },
    {
        "node_id": "CL11",
        "name": "Puerto Montt",
        "region": "Los Lagos",
        "lat": -41.47,
        "lon": -72.94,
        "solar_cap": 20,
        "wind_cap": 200,
        "hydro_cap": 520,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 200,
        "peak_mult": 1.4,
        "ppa_usd": 35,
        "cen_barra": "Puerto_Montt__220",
        "climate": "rainy",
        "notes": "Run-of-river hydro dominant. Southern congestion zone. Salmonicultura load.",
    },
    {
        "node_id": "CL12",
        "name": "Coyhaique",
        "region": "Aysén",
        "lat": -45.57,
        "lon": -72.07,
        "solar_cap": 10,
        "wind_cap": 160,
        "hydro_cap": 600,
        "geo_cap": 0,
        "tidal_cap": 0,
        "base_demand": 80,
        "peak_mult": 1.2,
        "ppa_usd": 33,
        "cen_barra": "Aysén__066",
        "climate": "rainy",
        "notes": "Future HidroAysén potential. Currently isolated SEM. Massive hydro resource.",
    },
]

# ═══════════════════════════════════════════════════════════════
# CHILE → FINAL FANTASY MAPPING TABLE
# Chile is the BASE REFERENCE, FF nodes diverge with realistic
# variations: capacity jitter, demand reshaping, unique traits.
# ═══════════════════════════════════════════════════════════════
CHILE_TO_FF = {
    # cap_jitter: (min_mult, max_mult) applied per-source randomly
    # demand_base: independent FF demand (NOT scaled from Chile)
    # source_overrides: override specific source capacities
    # unique_traits: FF-specific generation modifiers
    "CL01": {
        "ff_id": "MID",
        "ff_name": "Midgar",
        "ff_region": "Shinra Territory",
        "ff_climate": "urban",
        "demand_base": 2200,
        "peak_mult": 1.7,
        "cap_jitter": (0.3, 0.6),  # low: urban rooftop only
        "source_overrides": {"solar_cap": 120, "wind_cap": 40, "hydro_cap": 60, "geo_cap": 80},
        "add_tidal": 0,
        "unique_traits": {
            "demand_night_boost": 1.4,
            "demand_note": "24/7 mega-city, Sector 7 industrial",
        },
        "notes": "Post-Mako transition. Minimal local gen, massive import dependency.",
    },
    "CL02": {
        "ff_id": "JNV",
        "ff_name": "Junon",
        "ff_region": "Western Continent",
        "ff_climate": "coastal",
        "demand_base": 650,
        "peak_mult": 1.4,
        "cap_jitter": (0.8, 1.3),
        "source_overrides": {"solar_cap": 80, "wind_cap": 280},
        "add_tidal": 200,
        "unique_traits": {
            "wind_boost": 1.25,
            "demand_note": "Military port, cannon maintenance load",
        },
        "notes": "Offshore wind corridor. Tidal from harbor currents.",
    },
    "CL03": {
        "ff_id": "GLD",
        "ff_name": "Gold Saucer",
        "ff_region": "Corel Desert",
        "ff_climate": "desert",
        "demand_base": 500,
        "peak_mult": 1.8,
        "cap_jitter": (0.9, 1.2),
        "source_overrides": {"solar_cap": 600, "wind_cap": 80},
        "add_tidal": 0,
        "unique_traits": {
            "demand_evening_spike": 1.6,
            "demand_note": "Entertainment peak 18:00-02:00",
        },
        "notes": "Mega-solar in Corel desert. Demand inverted: peaks at night for entertainment.",
    },
    "CL04": {
        "ff_id": "RAB",
        "ff_name": "Rabanastre",
        "ff_region": "Dalmascan Desert",
        "ff_climate": "arid",
        "demand_base": 700,
        "peak_mult": 1.4,
        "cap_jitter": (0.85, 1.15),
        "source_overrides": {"solar_cap": 550, "wind_cap": 100, "geo_cap": 60},
        "add_tidal": 0,
        "unique_traits": {"solar_boost": 1.1, "demand_note": "Trade hub, bazaar economy"},
        "notes": "Arid kingdom. Strong solar with geothermal from Dalmascan underground.",
    },
    "CL05": {
        "ff_id": "RKT",
        "ff_name": "Rocket Town",
        "ff_region": "Western Continent",
        "ff_climate": "plains",
        "demand_base": 250,
        "peak_mult": 1.3,
        "cap_jitter": (0.7, 1.4),
        "source_overrides": {"solar_cap": 200, "wind_cap": 300, "hydro_cap": 40},
        "add_tidal": 0,
        "unique_traits": {"wind_boost": 1.15, "demand_note": "Aerospace R&D, intermittent spikes"},
        "notes": "Open plains wind corridor. Launch facility demand spikes.",
    },
    "CL06": {
        "ff_id": "BAL",
        "ff_name": "Balamb",
        "ff_region": "Balamb Archipelago",
        "ff_climate": "island",
        "demand_base": 200,
        "peak_mult": 1.3,
        "cap_jitter": (0.75, 1.25),
        "source_overrides": {"solar_cap": 150, "wind_cap": 220, "hydro_cap": 80},
        "add_tidal": 150,
        "unique_traits": {"tidal_boost": 1.2, "demand_note": "Garden academy + fishing village"},
        "notes": "Island microgrid. Diversified: wind, tidal, small hydro. Self-sufficient.",
    },
    "CL07": {
        "ff_id": "LIN",
        "ff_name": "Lindblum",
        "ff_region": "Mist Continent",
        "ff_climate": "highland",
        "demand_base": 900,
        "peak_mult": 1.5,
        "cap_jitter": (0.8, 1.2),
        "source_overrides": {"solar_cap": 180, "wind_cap": 260, "hydro_cap": 300},
        "add_tidal": 0,
        "unique_traits": {
            "hydro_boost": 1.15,
            "demand_morning_spike": 1.3,
            "demand_note": "Air cab + theater district industrial",
        },
        "notes": "Industrial capital. Hydro from Mist highlands. Airship manufacturing load.",
    },
    "CL08": {
        "ff_id": "ALX",
        "ff_name": "Alexandria",
        "ff_region": "Mist Continent",
        "ff_climate": "temperate",
        "demand_base": 550,
        "peak_mult": 1.4,
        "cap_jitter": (0.85, 1.15),
        "source_overrides": {"solar_cap": 220, "wind_cap": 100, "hydro_cap": 200},
        "add_tidal": 0,
        "unique_traits": {"demand_note": "Royal castle + civilian quarters, stable profile"},
        "notes": "Balanced royal city. Moderate in everything. Stable demand curve.",
    },
    "CL09": {
        "ff_id": "WUT",
        "ff_name": "Wutai",
        "ff_region": "Wutai Continent",
        "ff_climate": "monsoon",
        "demand_base": 320,
        "peak_mult": 1.5,
        "cap_jitter": (0.7, 1.3),
        "source_overrides": {"solar_cap": 100, "wind_cap": 150, "hydro_cap": 400},
        "add_tidal": 60,
        "unique_traits": {
            "hydro_seasonal_var": 0.35,
            "demand_note": "Mountain pagoda kingdom, seasonal monsoon",
        },
        "notes": "Hydro dominant with heavy seasonal variation. Monsoon = high hydro, dry = deficit.",
    },
    "CL10": {
        "ff_id": "CST",
        "ff_name": "Costa del Sol",
        "ff_region": "Western Continent",
        "ff_climate": "tropical",
        "demand_base": 180,
        "peak_mult": 1.6,
        "cap_jitter": (0.8, 1.3),
        "source_overrides": {"solar_cap": 400, "wind_cap": 60},
        "add_tidal": 80,
        "unique_traits": {
            "solar_boost": 1.15,
            "demand_seasonal": 1.5,
            "demand_note": "Resort town, tourism peaks",
        },
        "notes": "Solar paradise. Low base demand but extreme seasonal tourism spikes.",
    },
    "CL11": {
        "ff_id": "ZAN",
        "ff_name": "Zanarkand",
        "ff_region": "Northern Reach",
        "ff_climate": "arctic",
        "demand_base": 400,
        "peak_mult": 1.3,
        "cap_jitter": (0.75, 1.25),
        "source_overrides": {"solar_cap": 20, "wind_cap": 350, "hydro_cap": 500, "geo_cap": 40},
        "add_tidal": 100,
        "unique_traits": {
            "wind_boost": 1.3,
            "demand_heating": 1.4,
            "demand_note": "Arctic city, blitzball stadium, heating load",
        },
        "notes": "Arctic powerhouse. Wind + hydro + tidal. Huge heating demand in winter.",
    },
    "CL12": {
        "ff_id": "NVH",
        "ff_name": "Nibelheim",
        "ff_region": "Mt. Nibel Range",
        "ff_climate": "mountain",
        "demand_base": 60,
        "peak_mult": 1.2,
        "cap_jitter": (0.6, 1.0),
        "source_overrides": {"solar_cap": 30, "wind_cap": 120, "hydro_cap": 0, "geo_cap": 350},
        "add_tidal": 0,
        "unique_traits": {
            "geo_boost": 1.1,
            "demand_note": "Small village, Shinra reactor ruins, volcanic baseload",
        },
        "notes": "Volcanic geothermal hub. Tiny demand = massive net exporter. Mt. Nibel heat.",
    },
}

# Climate factors for generation profiles
CLIM_SOLAR = {
    "desert": 1.1,
    "arid": 1.05,
    "tropical": 0.95,
    "arctic": 0.5,
    "mountain": 0.7,
    "monsoon": 0.75,
    "coastal": 0.85,
    "island": 0.9,
    "urban": 0.7,
    "plains": 0.9,
    "highland": 0.85,
    "temperate": 0.85,
    "rainy": 0.55,
}
CLIM_WIND = {
    "coastal": 1.3,
    "island": 1.25,
    "arctic": 1.4,
    "plains": 1.2,
    "mountain": 1.1,
    "desert": 0.7,
    "arid": 0.75,
    "monsoon": 1.0,
    "urban": 0.5,
    "tropical": 0.6,
    "highland": 1.0,
    "temperate": 0.9,
    "rainy": 1.1,
}


# ═══════════════════════════════════════════════════════════════
# GENERATION PROFILES (trait-aware for FF divergence)
# ═══════════════════════════════════════════════════════════════
def solar_mw(h, cap, climate, traits=None):
    if h < 5 or h > 20:
        return 0.0
    cf = CLIM_SOLAR.get(climate, 0.85)
    boost = (traits or {}).get("solar_boost", 1.0)
    return cap * math.exp(-0.5 * ((h - 13) / 3.5) ** 2) * cf * boost * random.uniform(0.80, 0.98)


def wind_mw(h, cap, climate, traits=None):
    nt = 1.3 if (h < 6 or h > 20) else 0.85
    cf = CLIM_WIND.get(climate, 1.0)
    boost = (traits or {}).get("wind_boost", 1.0)
    return (
        cap
        * (0.22 + 0.18 * math.sin(h / 24 * math.pi * 2))
        * nt
        * cf
        * boost
        * random.uniform(0.70, 1.08)
    )


def hydro_mw(h, cap, traits=None):
    if cap == 0:
        return 0.0
    seasonal_var = (traits or {}).get("hydro_seasonal_var", 0.2)
    boost = (traits or {}).get("hydro_boost", 1.0)
    return (
        cap
        * (0.55 + seasonal_var * math.sin((h - 8) / 24 * math.pi * 2))
        * boost
        * random.uniform(0.85, 1.0)
    )


def geo_mw(h, cap, traits=None):
    if not cap:
        return 0.0
    boost = (traits or {}).get("geo_boost", 1.0)
    return cap * 0.9 * boost * random.uniform(0.93, 1.0)


def tidal_mw(h, cap, traits=None):
    if cap == 0:
        return 0.0
    boost = (traits or {}).get("tidal_boost", 1.0)
    return (
        cap
        * (0.4 + 0.3 * abs(math.sin(h / 12.42 * math.pi * 2)))
        * boost
        * random.uniform(0.85, 1.0)
    )


def demand_mw(h, base, pm, traits=None):
    t = traits or {}
    m = math.exp(-0.5 * ((h - 9) / 2) ** 2) * 0.3
    e = math.exp(-0.5 * ((h - 20) / 2.5) ** 2) * 0.5
    base_load = base * (0.58 + m + e) * (pm / 1.4)

    # FF unique demand modifiers
    if t.get("demand_night_boost") and (h >= 22 or h <= 5):
        base_load *= t["demand_night_boost"]
    if t.get("demand_evening_spike") and 18 <= h <= 2:
        evening_factor = (
            t["demand_evening_spike"] if 18 <= h <= 23 else t["demand_evening_spike"] * 0.8
        )
        base_load *= evening_factor
    if t.get("demand_morning_spike") and 7 <= h <= 10:
        base_load *= t["demand_morning_spike"]
    if t.get("demand_heating") and (h <= 7 or h >= 20):
        base_load *= t["demand_heating"]

    return base_load * random.uniform(0.90, 1.10)


# ═══════════════════════════════════════════════════════════════
# TRANSFORM: Chile node → FF node (with realistic divergence)
# Chile is a REFERENCE, not a copy. FF nodes get:
#   - Independent capacity values (source_overrides + jitter)
#   - Independent demand (not scaled from Chile)
#   - Unique generation traits per city
# ═══════════════════════════════════════════════════════════════
def chile_to_ff_node(cl_node):
    m = CHILE_TO_FF[cl_node["node_id"]]
    rng = random.Random(hash(m["ff_id"]))  # deterministic per FF city

    # Start from source_overrides (independent of Chile values)
    lo, hi = m["cap_jitter"]
    ff = {
        "node_id": m["ff_id"],
        "name": m["ff_name"],
        "region": m["ff_region"],
        "climate": m["ff_climate"],
        "solar_cap": round(m["source_overrides"].get("solar_cap", 0) * rng.uniform(lo, hi)),
        "wind_cap": round(m["source_overrides"].get("wind_cap", 0) * rng.uniform(lo, hi)),
        "hydro_cap": round(m["source_overrides"].get("hydro_cap", 0) * rng.uniform(lo, hi)),
        "geo_cap": round(m["source_overrides"].get("geo_cap", 0) * rng.uniform(lo, hi)),
        "tidal_cap": round(m["add_tidal"] * rng.uniform(0.8, 1.2)) if m["add_tidal"] else 0,
        "base_demand": round(m["demand_base"] * rng.uniform(0.85, 1.15)),
        "peak_mult": round(m["peak_mult"] * rng.uniform(0.9, 1.1), 2),
        "ppa_usd": round(cl_node["ppa_usd"] * rng.uniform(0.8, 1.2)),
        "unique_traits": m.get("unique_traits", {}),
    }
    return ff


# ═══════════════════════════════════════════════════════════════
# SEED GENERATION
# ═══════════════════════════════════════════════════════════════
def generate_seeds(nodes, out_dir, days, currency="usd", is_ff=False):
    os.makedirs(out_dir, exist_ok=True)
    cur = "gil" if is_ff else "usd"

    # Plants
    plants = []
    pid = 1
    for n in nodes:
        for src, cap in [
            ("solar", n["solar_cap"]),
            ("wind", n["wind_cap"]),
            ("hydro", n["hydro_cap"]),
            ("geothermal", n.get("geo_cap", 0)),
            ("tidal", n.get("tidal_cap", 0)),
        ]:
            if cap == 0:
                continue
            num = max(1, cap // 100)
            for _ in range(num):
                p = {
                    "plant_id": f"PLT-{pid:04d}",
                    "node_id": n["node_id"],
                    "node_name": n["name"],
                    "region": n["region"],
                    "source_type": src,
                    "capacity_mw": round(cap / num, 1),
                    "climate": n["climate"],
                    f"ppa_price_{cur}_mwh": n["ppa_usd"],
                }
                if not is_ff and "lat" in n:
                    p["lat"] = round(n["lat"] + random.uniform(-0.15, 0.15), 4)
                    p["lon"] = round(n["lon"] + random.uniform(-0.15, 0.15), 4)
                if not is_ff and "cen_barra" in n:
                    p["cen_barra"] = n["cen_barra"]
                plants.append(p)
                pid += 1

    # Time series
    start = datetime(2026, 4, 1)
    scada, weather, demand_rows, dispatch = [], [], [], []

    for day in range(days):
        for h in range(24):
            ts = (start + timedelta(days=day, hours=h)).isoformat()
            for n in nodes:
                clim = n["climate"]
                traits = n.get("unique_traits", {})
                s = round(solar_mw(h, n["solar_cap"], clim, traits), 1)
                w = round(wind_mw(h, n["wind_cap"], clim, traits), 1)
                hy = round(hydro_mw(h, n["hydro_cap"], traits), 1)
                ge = round(geo_mw(h, n.get("geo_cap", 0), traits), 1)
                ti = round(tidal_mw(h, n.get("tidal_cap", 0), traits), 1)
                tg = round(s + w + hy + ge + ti, 1)
                dm = round(demand_mw(h, n["base_demand"], n["peak_mult"], traits), 1)
                bl = round(tg - dm, 1)
                cu = round(max(0, bl * 0.3), 1)
                sp = round(
                    n["ppa_usd"] * (dm / (tg if tg > 0 else 1)) * random.uniform(0.85, 1.15), 2
                )

                scada.append(
                    {
                        "timestamp": ts,
                        "node_id": n["node_id"],
                        "solar_mw": s,
                        "wind_mw": w,
                        "hydro_mw": hy,
                        "geothermal_mw": ge,
                        "tidal_mw": ti,
                        "total_generation_mw": tg,
                    }
                )
                weather.append(
                    {
                        "timestamp": ts,
                        "node_id": n["node_id"],
                        "climate": clim,
                        "solar_irradiance_wm2": max(0, round(solar_mw(h, 1000, clim, traits), 1)),
                        "wind_speed_ms": round(max(0, wind_mw(h, 15, clim, traits)), 1),
                        "temperature_c": round(
                            18 + 8 * math.sin((h - 6) / 24 * math.pi * 2) + random.uniform(-3, 3), 1
                        ),
                        "humidity_pct": round(random.uniform(20, 90), 1),
                    }
                )
                demand_rows.append(
                    {
                        "timestamp": ts,
                        "node_id": n["node_id"],
                        "demand_mw": dm,
                        "residential_pct": round(random.uniform(25, 52), 1),
                        "industrial_pct": round(random.uniform(25, 55), 1),
                        "commercial_pct": round(random.uniform(10, 28), 1),
                    }
                )
                dispatch.append(
                    {
                        "timestamp": ts,
                        "node_id": n["node_id"],
                        "total_generation_mw": tg,
                        "total_demand_mw": dm,
                        "balance_mw": bl,
                        "curtailment_mw": cu,
                        f"spot_price_{cur}": sp,
                        f"ppa_price_{cur}": n["ppa_usd"],
                        f"revenue_{cur}": round(tg * n["ppa_usd"], 2),
                        f"curtailment_cost_{cur}": round(cu * n["ppa_usd"], 2),
                        "carbon_offset_tco2e": round(tg * 0.42, 2),
                    }
                )

    def write_csv(name, rows):
        path = os.path.join(out_dir, f"{name}.csv")
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  ✅ {name}.csv — {len(rows):,} rows")

    label = "Gaia (FF)" if is_ff else "Chile (SEN)"
    print(f"\n⚡ Generating {label}: {len(nodes)} nodes × {days}d × 24h")
    write_csv("seed_plants", plants)
    for name, rows in [
        ("seed_scada", scada),
        ("seed_weather", weather),
        ("seed_demand", demand_rows),
        ("seed_dispatch", dispatch),
    ]:
        write_csv(name, rows)

    total = len(plants) + len(scada) + len(weather) + len(demand_rows) + len(dispatch)
    print(f"  🔋 {label} total: {total:,} rows in {out_dir}/")
    return total


# ═══════════════════════════════════════════════════════════════
# MAPPING TABLE OUTPUT
# ═══════════════════════════════════════════════════════════════
def write_mapping_table(out_dir, chile_nodes, ff_nodes):
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for cl, ff in zip(chile_nodes, ff_nodes, strict=True):
        m = CHILE_TO_FF[cl["node_id"]]
        rows.append(
            {
                "chile_node": cl["node_id"],
                "chile_name": cl["name"],
                "chile_solar": cl["solar_cap"],
                "chile_wind": cl["wind_cap"],
                "chile_hydro": cl["hydro_cap"],
                "chile_demand": cl["base_demand"],
                "ff_node": ff["node_id"],
                "ff_name": ff["name"],
                "ff_climate": ff["climate"],
                "ff_solar": ff["solar_cap"],
                "ff_wind": ff["wind_cap"],
                "ff_hydro": ff["hydro_cap"],
                "ff_geo": ff.get("geo_cap", 0),
                "ff_tidal": ff.get("tidal_cap", 0),
                "ff_demand": ff["base_demand"],
                "divergence_note": m["notes"],
                "demand_traits": m.get("unique_traits", {}).get("demand_note", ""),
            }
        )
    path = os.path.join(out_dir, "chile_to_ff_mapping.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\n📋 chile_to_ff_mapping.csv — {len(rows)} mappings (Chile vs FF values side-by-side)")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Generate Chile + FF energy seed data")
    parser.add_argument("--mode", choices=["chile", "ff", "both"], default="both")
    parser.add_argument("--days", type=int, default=7, help="Days of data to generate")
    args = parser.parse_args()

    base = os.path.join(os.path.dirname(__file__), "..", "transform")
    total = 0

    if args.mode in ("chile", "both"):
        total += generate_seeds(CHILE_NODES, os.path.join(base, "seeds"), args.days, "usd", False)

    if args.mode in ("ff", "both"):
        ff_nodes = [chile_to_ff_node(cl) for cl in CHILE_NODES]
        total += generate_seeds(ff_nodes, os.path.join(base, "seeds_ff"), args.days, "gil", True)
        write_mapping_table(os.path.join(base, "seeds_ff"), CHILE_NODES, ff_nodes)

    print(f"\n{'=' * 60}")
    print(
        f"✨ Grand total: {total:,} rows across {'both datasets' if args.mode == 'both' else args.mode}"
    )
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
