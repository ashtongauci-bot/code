"""
structural_elements.py — Data classes for the ETABS model.

Represents the structural schema extracted from marked-up architectural plans,
ready for translation into an ETABS model via the CSi ETABS API or E2K import.

⚠️  PRELIMINARY STRUCTURAL MODEL — NOT FOR CONSTRUCTION
All element sizes are indicative only. This model has not been designed or
verified by a structural engineer. It MUST be reviewed by a registered
structural engineer before use in any design documentation or construction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Levels / Stories
# ---------------------------------------------------------------------------

@dataclass
class Level:
    """One floor level in the building."""
    name: str           # e.g. "Ground Floor", "Level 3"
    rl_m: float         # absolute reduced level of the slab soffit (m)
    height_m: float     # floor-to-floor height (column height for this story, m)
    floor_usage: str    # e.g. "office", "residential", "retail", "carpark"
    page_index: int = 0 # which PDF page this level's plan is on


# ---------------------------------------------------------------------------
# Sections / Properties
# ---------------------------------------------------------------------------

@dataclass
class ColumnSection:
    """Rectangular or circular concrete column section."""
    label: str          # unique name, e.g. "COL600x600"
    width_mm: float     # B dimension
    depth_mm: float     # D dimension (= width for square)
    shape: str = "rectangular"   # "rectangular" | "circular"
    material: str = "50MPa"


@dataclass
class WallSection:
    """Concrete wall (shell) section."""
    label: str          # e.g. "WALL250"
    thickness_mm: float
    material: str = "40MPa"


@dataclass
class SlabSection:
    """Concrete slab (plate/shell) section."""
    label: str          # e.g. "SLAB250"
    thickness_mm: float
    material: str = "32MPa"


# ---------------------------------------------------------------------------
# Structural elements
# ---------------------------------------------------------------------------

@dataclass
class ColumnInstance:
    """A column placed at a plan position, spanning one or more stories."""
    id: str
    x_m: float          # plan position
    y_m: float
    section_label: str  # references ColumnSection.label
    story_names: list[str] = field(default_factory=list)  # stories this column spans
    source: str = "detected"   # "detected" | "forced" | "generated"


@dataclass
class WallSegment:
    """
    A straight vertical wall panel, part of a core or shear wall.
    Defined by two plan endpoints; spans the full story height.
    """
    id: str
    story_name: str
    x1_m: float
    y1_m: float
    x2_m: float
    y2_m: float
    section_label: str   # references WallSection.label
    wall_type: str = "core"   # "core" | "shear" | "facade"


@dataclass
class SlabPanel:
    """
    A horizontal slab region at one story level.
    Defined by a plan polygon (outline). Carries a floor usage-specific load.
    """
    id: str
    story_name: str
    polygon_m: list[tuple[float, float]]   # closed plan polygon [(x,y), ...]
    section_label: str   # references SlabSection.label
    floor_usage: str = "office"


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

@dataclass
class ConcreteMaterial:
    """Normal-weight concrete material for ETABS."""
    label: str          # e.g. "50MPa"
    fc_mpa: float       # characteristic compressive strength

    @property
    def fc_kpa(self) -> float:
        return self.fc_mpa * 1000.0

    @property
    def E_mpa(self) -> float:
        """AS3600 Cl 4.1.2: Ec = ρ^1.5 × 0.043 × √fc' (MPa), ρ = 2400 kg/m³."""
        import math
        return 0.043 * (2400 ** 1.5) * math.sqrt(self.fc_mpa)

    @property
    def E_kpa(self) -> float:
        return self.E_mpa * 1000.0

    unit_weight_kn_m3: float = 25.0   # kN/m³ (includes reinforcement)
    poisson: float = 0.2
    thermal: float = 1.0e-5           # /°C


# ---------------------------------------------------------------------------
# Load definitions
# ---------------------------------------------------------------------------

@dataclass
class LoadPattern:
    """An ETABS load pattern (Dead, SDL, Live, etc.)."""
    name: str           # e.g. "SDL_Office"
    pattern_type: str   # "Dead" | "Super Dead" | "Live" | "Roof Live"
    self_weight_mult: float = 0.0  # 1.0 for Dead only


# ---------------------------------------------------------------------------
# Top-level model container
# ---------------------------------------------------------------------------

@dataclass
class ETABSModel:
    """Complete structural model ready for ETABS API or E2K export."""
    project_name: str
    base_rl_m: float                    # base/foundation level elevation (m)

    levels: list[Level] = field(default_factory=list)
    materials: list[ConcreteMaterial] = field(default_factory=list)
    column_sections: list[ColumnSection] = field(default_factory=list)
    wall_sections: list[WallSection] = field(default_factory=list)
    slab_sections: list[SlabSection] = field(default_factory=list)
    columns: list[ColumnInstance] = field(default_factory=list)
    walls: list[WallSegment] = field(default_factory=list)
    slabs: list[SlabPanel] = field(default_factory=list)
    load_patterns: list[LoadPattern] = field(default_factory=list)

    def column_section_by_label(self, label: str) -> Optional[ColumnSection]:
        for cs in self.column_sections:
            if cs.label == label:
                return cs
        return None

    def get_story_rl(self, story_name: str) -> float:
        for lv in self.levels:
            if lv.name == story_name:
                return lv.rl_m
        return self.base_rl_m

    def get_story_base_rl(self, story_name: str) -> float:
        """Return the elevation at the BOTTOM of this story's columns."""
        idx = next(
            (i for i, lv in enumerate(self.levels) if lv.name == story_name), None
        )
        if idx is None:
            return self.base_rl_m
        if idx == 0:
            return self.base_rl_m
        return self.levels[idx - 1].rl_m
