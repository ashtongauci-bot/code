"""
load_definitions.py — Floor usage load intensities per AS/NZS 1170.1:2002.

Provides superimposed dead load (SDL) and live load (LL) for each floor usage
type. These are characteristic (unfactored) service loads in kPa.

Reference: AS/NZS 1170.1:2002 Table 3.1 and Australian structural practice.
All values are conservative preliminary estimates for scheme-level modelling.

⚠️  PRELIMINARY — requires engineer review before use in design.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Load table — characteristic service loads (kPa)
# ---------------------------------------------------------------------------
# SDL: superimposed dead load (finishes, services, ceilings, partitions)
# LL:  live load from AS/NZS 1170.1 Table 3.1

USAGE_LOADS: dict[str, dict] = {
    "residential": {
        "sdl_kpa": 1.0,     # finishes + services (no heavy partitions)
        "ll_kpa": 1.5,      # AS1170.1 Table 3.1 — domestic/residential
        "label": "Residential",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Domestic areas",
    },
    "office": {
        "sdl_kpa": 1.0,     # finishes + services + flexible partitions allowance
        "ll_kpa": 3.0,      # AS1170.1 Table 3.1 — General office
        "label": "Office",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Office areas (general)",
    },
    "corridor": {
        "sdl_kpa": 1.0,
        "ll_kpa": 4.0,      # AS1170.1 — Corridors, passages, lobbies
        "label": "Corridor / Lobby",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Corridors, passages, lobbies",
    },
    "retail": {
        "sdl_kpa": 1.5,     # heavier finishes, signage, fixtures
        "ll_kpa": 5.0,      # AS1170.1 Table 3.1 — Retail/shops
        "label": "Retail / Shop",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Retail/shops",
    },
    "carpark": {
        "sdl_kpa": 0.5,     # minimal finishes
        "ll_kpa": 2.5,      # AS1170.1 Table 3.1 — Car parks (passenger vehicles)
        "label": "Car Park",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Car parks (passenger vehicles ≤ 25 kN GVM)",
    },
    "storage": {
        "sdl_kpa": 1.5,
        "ll_kpa": 5.0,      # AS1170.1 — general storage (increase for heavy storage)
        "label": "Storage",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Storage areas",
    },
    "plant_room": {
        "sdl_kpa": 2.0,     # ductwork, equipment pads, cable trays
        "ll_kpa": 7.5,      # AS1170.1 — plant rooms / mechanical areas
        "label": "Plant Room / Mechanical",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Plant/mechanical rooms",
    },
    "roof_non_trafficable": {
        "sdl_kpa": 0.5,     # waterproofing + paving + services
        "ll_kpa": 0.25,     # AS1170.1 — maintenance access only
        "label": "Roof (Non-trafficable)",
        "as_ref": "AS/NZS 1170.1 — Roof (maintenance access only)",
    },
    "roof_trafficable": {
        "sdl_kpa": 1.0,
        "ll_kpa": 4.0,      # AS1170.1 — trafficable roof / terrace (public access)
        "label": "Roof (Trafficable)",
        "as_ref": "AS/NZS 1170.1 — Trafficable roof / roof terrace",
    },
    "roof_garden": {
        "sdl_kpa": 3.0,     # soil, planters, waterproofing, paving
        "ll_kpa": 4.0,      # AS1170.1 — trafficable with soft landscaping
        "label": "Roof Garden / Podium Landscape",
        "as_ref": "AS/NZS 1170.1 — Trafficable roof with garden/planters",
    },
    "assembly": {
        "sdl_kpa": 1.0,
        "ll_kpa": 5.0,      # AS1170.1 — assembly without fixed seating
        "label": "Assembly / Function",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Assembly areas (without fixed seating)",
    },
    "health_care": {
        "sdl_kpa": 1.5,
        "ll_kpa": 3.0,      # AS1170.1 — wards, corridors in hospitals
        "label": "Health Care / Hospital",
        "as_ref": "AS/NZS 1170.1 Table 3.1 — Health care (general ward/corridor)",
    },
}

# Concrete slab self-weight per mm of thickness (kN/m³ × m / 1000 = kPa/mm)
CONCRETE_UNIT_WEIGHT_KN_M3 = 25.0
SLAB_SW_KPA_PER_MM = CONCRETE_UNIT_WEIGHT_KN_M3 / 1000.0   # 0.025 kPa/mm


# ---------------------------------------------------------------------------
# AS/NZS 1170.0 — ULS load combination factors (strength)
# ---------------------------------------------------------------------------
ULS_COMBOS = {
    "1.2G + 1.5Q": {"G": 1.2, "Q": 1.5},
    "1.35G":        {"G": 1.35, "Q": 0.0},
}

# SLS combination (serviceability)
SLS_COMBO = {"G": 1.0, "Q": 1.0}

# ψs (short-term) and ψl (long-term) combination factors (AS1170.0 Table 4.1)
PSI_FACTORS = {
    "residential": {"short": 0.7, "long": 0.4},
    "office":      {"short": 0.7, "long": 0.4},
    "retail":      {"short": 0.7, "long": 0.4},
    "carpark":     {"short": 0.7, "long": 0.4},
    "storage":     {"short": 1.0, "long": 0.6},
    "roof_non_trafficable": {"short": 0.7, "long": 0.0},
    "roof_trafficable":     {"short": 0.7, "long": 0.4},
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_loads(usage: str) -> dict:
    """
    Return SDL and LL (kPa) for the given floor usage type.
    Falls back to 'office' if the usage key is not recognised.
    """
    key = _normalise_key(usage)
    if key in USAGE_LOADS:
        return USAGE_LOADS[key]
    # Fallback
    return USAGE_LOADS["office"]


def total_service_kpa(usage: str, slab_thickness_mm: float) -> float:
    """Total service load (kPa) = slab SW + SDL + LL."""
    loads = get_loads(usage)
    sw = SLAB_SW_KPA_PER_MM * slab_thickness_mm
    return sw + loads["sdl_kpa"] + loads["ll_kpa"]


def uls_load_kpa(usage: str, slab_thickness_mm: float) -> float:
    """
    Factored ULS gravity load intensity (kPa) for column axial load estimation.
    Uses 1.2G + 1.5Q where G = slab SW + SDL, Q = LL.
    """
    loads = get_loads(usage)
    sw = SLAB_SW_KPA_PER_MM * slab_thickness_mm
    G = sw + loads["sdl_kpa"]
    Q = loads["ll_kpa"]
    return max(1.2 * G + 1.5 * Q, 1.35 * G)


def list_usages() -> list[str]:
    return list(USAGE_LOADS.keys())


def _normalise_key(usage: str) -> str:
    """Convert usage string variants to canonical key."""
    return usage.lower().strip().replace(" ", "_").replace("-", "_")
