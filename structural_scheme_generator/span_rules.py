"""
span_rules.py — Span-to-depth rules for preliminary column grid sizing.

Based on AS3600:2018 and Australian structural engineering practice.
All rules are CONSERVATIVE preliminary estimates only.

⚠️  PRELIMINARY STRUCTURAL SCHEME — NOT FOR CONSTRUCTION
This module was generated algorithmically from span/depth rules of thumb.
It has NOT been designed or verified by a structural engineer.
It MUST be reviewed, checked, and approved by a registered structural engineer
before use in any design documentation or construction.
Punching shear, lateral stability, transfer structures, and serviceability
have NOT been checked. Column sizes are indicative only.
"""

# ---------------------------------------------------------------------------
# Slab system span/depth tables
# ---------------------------------------------------------------------------

# Flat plate (RC, no PT) — deflection-governed
# AS3600 Cl 9.4.4 deemed-to-comply approach
# Typical range L/d = 28-32 for interior panels at ~5kPa total load
FLAT_PLATE_RC = {
    "span_to_depth_interior": 28,   # interior panel
    "span_to_depth_edge": 24,       # edge panel (more conservative)
    "span_to_depth_corner": 20,     # corner panel (most conservative)
    "max_span_mm": 9000,            # practical limit before PT preferred
    "notes": "RC flat plate. Deflection-governed. Assumes ~5kPa total load.",
}

# Flat plate (PT) — common in Australian apartments/commercial
# 200mm PT flat plate can reach ~8.4m comfortably
FLAT_PLATE_PT = {
    "span_to_depth_interior": 40,
    "span_to_depth_edge": 35,
    "span_to_depth_corner": 30,
    "max_span_mm": 12000,
    "notes": "PT flat plate. Common for apartments. Punching shear governs at columns.",
}

# Flat slab with drop panels (RC)
FLAT_SLAB_WITH_DROPS = {
    "span_to_depth_interior": 32,
    "span_to_depth_edge": 27,
    "span_to_depth_corner": 22,
    "max_span_mm": 10000,
    "notes": "RC flat slab with drops. Drops reduce punching shear demand.",
}

# Band beam and slab (common in commercial/industrial)
BAND_BEAM_SLAB = {
    "span_to_depth_interior": 36,   # span of slab between band beams
    "slab_span_to_depth": 30,       # slab spanning between band beams
    "max_span_mm": 14000,
    "notes": "Band beam system. Column spacing follows beam direction.",
}

# ---------------------------------------------------------------------------
# Load tables
# ---------------------------------------------------------------------------

# Estimated total service loads by use type (kPa)
LOAD_ADJUSTMENTS = {
    "residential_kPa": 2.0,         # SDL ~1.0 + LL ~2.0 = light
    "office_kPa": 5.0,              # SDL ~1.5 + LL ~3.0 = moderate (baseline)
    "retail_kPa": 7.5,              # SDL ~2.0 + LL ~5.0
    "carpark_kPa": 4.5,             # AS/NZS 1170.1 car park
    "heavy_industrial_kPa": 12.0,   # heavy loads
}

# Load factor multipliers on max span (relative to office baseline of 5 kPa).
# Heavier loads → shorter spans.
LOAD_SPAN_FACTORS = {
    "residential_kPa": 1.10,
    "office_kPa": 1.00,             # baseline
    "retail_kPa": 0.90,
    "carpark_kPa": 0.95,
    "heavy_industrial_kPa": 0.75,
}

# Human-readable labels for reports
SYSTEM_LABELS = {
    "flat_plate_rc": "RC Flat Plate",
    "flat_plate_pt": "PT Flat Plate",
    "flat_slab_drops": "RC Flat Slab with Drop Panels",
    "band_beam": "Band Beam & Slab",
}

LOAD_LABELS = {
    "residential_kPa": "Residential (~2 kPa)",
    "office_kPa": "Office (~5 kPa)",
    "retail_kPa": "Retail (~7.5 kPa)",
    "carpark_kPa": "Car Park (~4.5 kPa)",
    "heavy_industrial_kPa": "Heavy Industrial (~12 kPa)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_max_span(
    slab_thickness_mm: int,
    system: str,
    load_type: str,
    panel_position: str = "interior",
) -> dict:
    """
    Calculate maximum allowable column spacing from slab thickness.

    Args:
        slab_thickness_mm: Total slab thickness in mm.
        system: One of 'flat_plate_rc', 'flat_plate_pt', 'flat_slab_drops', 'band_beam'.
        load_type: One of the keys in LOAD_ADJUSTMENTS.
        panel_position: 'interior', 'edge', or 'corner'.

    Returns dict with:
        max_span_mm             — maximum recommended column c/c spacing (rounded to 500 mm)
        raw_max_span_mm         — unrounded calculated span
        effective_depth_mm      — assumed effective depth (slab − cover − bar radius)
        span_depth_ratio_used   — L/d ratio applied
        load_factor_applied     — load adjustment multiplier
        system                  — system key
        load_type               — load key
        panel_position          — panel position used
        absolute_system_max_mm  — hard system maximum
        notes                   — engineering notes string
        punching_warning        — warning string (empty if not applicable)
        preliminary_disclaimer  — mandatory disclaimer string
    """
    systems = {
        "flat_plate_rc": FLAT_PLATE_RC,
        "flat_plate_pt": FLAT_PLATE_PT,
        "flat_slab_drops": FLAT_SLAB_WITH_DROPS,
        "band_beam": BAND_BEAM_SLAB,
    }

    if system not in systems:
        raise ValueError(
            f"Unknown system: '{system}'. Choose from: {list(systems.keys())}"
        )
    if load_type not in LOAD_ADJUSTMENTS:
        raise ValueError(
            f"Unknown load_type: '{load_type}'. Choose from: {list(LOAD_ADJUSTMENTS.keys())}"
        )

    rules = systems[system]
    cover_mm = 25          # AS3600 Table 4.10.3 — exposure class A2
    bar_radius_mm = 10     # assume N20 bar (10 mm radius)
    effective_depth = slab_thickness_mm - cover_mm - bar_radius_mm

    # Span/depth ratio for this panel position
    ratio_key = f"span_to_depth_{panel_position}"
    if ratio_key not in rules:
        ratio_key = "span_to_depth_interior"
    span_depth_ratio = rules[ratio_key]

    # Load adjustment
    load_factor = LOAD_SPAN_FACTORS.get(load_type, 1.0)

    # Raw calculated span
    raw_span = effective_depth * span_depth_ratio * load_factor

    # Apply absolute system maximum
    max_span = min(raw_span, rules["max_span_mm"])

    # Round DOWN to nearest 500 mm — practical construction module
    practical_span = int(max_span / 500) * 500

    # Punching shear warning for thin slabs on flat plate systems
    punching_warning = ""
    if slab_thickness_mm < 200 and system in ("flat_plate_rc", "flat_plate_pt"):
        punching_warning = (
            "WARNING: Slab < 200 mm — punching shear at columns will likely govern "
            "and may require column heads, drop panels, or increased slab thickness."
        )

    return {
        "max_span_mm": practical_span,
        "raw_max_span_mm": round(raw_span),
        "effective_depth_mm": effective_depth,
        "span_depth_ratio_used": span_depth_ratio,
        "load_factor_applied": load_factor,
        "system": system,
        "system_label": SYSTEM_LABELS.get(system, system),
        "load_type": load_type,
        "load_label": LOAD_LABELS.get(load_type, load_type),
        "panel_position": panel_position,
        "absolute_system_max_mm": rules["max_span_mm"],
        "notes": rules["notes"],
        "punching_warning": punching_warning,
        "preliminary_disclaimer": (
            "PRELIMINARY ONLY. Deflection-based rule of thumb. "
            "Does not check punching shear, lateral loads, or transfer structures. "
            "Must be verified by a structural engineer."
        ),
    }


def suggest_column_size(
    tributary_area_m2: float,
    num_floors: int,
    load_type: str,
    fc_MPa: int = 50,
) -> dict:
    """
    Preliminary column size estimate from accumulated axial load.

    Uses P = ULS_load_intensity × tributary_area × floors, then sizes the
    section from the phi·fc·0.3 rule of thumb (accounts roughly for
    reinforcement contribution and concentric load only).

    Returns sizes rounded to nearest 50 mm, minimum 400×400 mm.
    All values are VERY preliminary — no bending, slenderness, or biaxial check.
    """
    service_kPa = LOAD_ADJUSTMENTS.get(load_type, 5.0)

    # Approximate ULS load intensity (kPa)
    # G ≈ Q ≈ service/2; ULS ≈ 1.2G + 1.5Q ≈ 1.35 × service (rough)
    uls_kPa = service_kPa * 1.35

    # Add slab self-weight: assume 25 kN/m³ concrete × 200 mm = 5 kPa, ULS ×1.2
    total_uls = uls_kPa + 5.0 * 1.2

    # Total factored axial load (kN)
    N_star = total_uls * tributary_area_m2 * num_floors

    # Required gross area from phi·Ag·fc·0.3 rule
    phi = 0.65          # AS3600 Table 2.2.2 (compression-governed)
    required_area_mm2 = (N_star * 1000) / (phi * fc_MPa * 0.3)

    # Square column side, minimum 400 mm, rounded to nearest 50 mm
    side_mm = required_area_mm2 ** 0.5
    side_mm = max(400, round(side_mm / 50) * 50)

    return {
        "D_mm": side_mm,
        "B_mm": side_mm,
        "estimated_N_star_kN": round(N_star),
        "tributary_area_m2": tributary_area_m2,
        "num_floors": num_floors,
        "fc_MPa": fc_MPa,
        "notes": (
            "VERY preliminary. Axial load only — no bending, slenderness, or "
            "biaxial check performed. Minimum 400×400 mm enforced."
        ),
    }


# ---------------------------------------------------------------------------
# CLI self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== span_rules.py self-test ===")
    result = get_max_span(250, "flat_plate_rc", "office_kPa")
    print(f"  250mm RC flat plate, office:  max span = {result['max_span_mm']} mm")
    result = get_max_span(200, "flat_plate_pt", "residential_kPa")
    print(f"  200mm PT flat plate, resi:    max span = {result['max_span_mm']} mm")
    result = get_max_span(300, "flat_slab_drops", "retail_kPa")
    print(f"  300mm flat slab + drops, retail: max span = {result['max_span_mm']} mm")

    size = suggest_column_size(36.0, 8, "office_kPa", 50)
    print(f"  Column size (36m² trib, 8 floors, office): {size['D_mm']}×{size['B_mm']} mm  N*={size['estimated_N_star_kN']} kN")
