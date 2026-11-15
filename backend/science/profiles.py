"""Mission weight profiles (dimension weights, normalised to sum to 1)."""

from backend.science.features import DIMENSIONS

PROFILES: dict[str, dict] = {
    "general_analog": {
        "label": "General analog",
        "description": "Balanced default weighting across all dimensions.",
        "weights": {"geology": 0.25, "terrain": 0.25, "thermal": 0.20,
                    "resources": 0.15, "hazards": 0.15},
    },
    "surface_operations": {
        "label": "Surface operations / landing",
        "description": "Emphasises terrain and hazards for crewed or robotic surface "
        "operations and landing rehearsal.",
        "weights": {"geology": 0.15, "terrain": 0.35, "thermal": 0.15,
                    "resources": 0.10, "hazards": 0.25},
    },
    "isru": {
        "label": "In-situ resource utilisation",
        "description": "Emphasises resources and geology for prospecting and extraction "
        "testing.",
        "weights": {"geology": 0.25, "terrain": 0.10, "thermal": 0.20,
                    "resources": 0.35, "hazards": 0.10},
    },
    "astrobiology": {
        "label": "Astrobiology / sampling",
        "description": "Emphasises geology and environmental conditions relevant to "
        "habitability and biosignature preservation.",
        "weights": {"geology": 0.35, "terrain": 0.10, "thermal": 0.20,
                    "resources": 0.20, "hazards": 0.15},
    },
    "rover_traverse": {
        "label": "Rover traverse / mobility",
        "description": "Emphasises terrain geometry and hazards for mobility and "
        "navigation testing.",
        "weights": {"geology": 0.15, "terrain": 0.35, "thermal": 0.10,
                    "resources": 0.10, "hazards": 0.30},
    },
}


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    """Validate dimension weights and rescale them to sum to 1."""
    unknown = set(weights) - set(DIMENSIONS)
    if unknown:
        raise ValueError(f"Unknown dimensions: {', '.join(sorted(unknown))}.")
    clean = {d: float(weights.get(d, 0.0)) for d in DIMENSIONS}
    if any(w < 0 or w != w for w in clean.values()):
        raise ValueError("Weights must be non-negative numbers.")
    total = sum(clean.values())
    if total <= 0:
        raise ValueError("At least one dimension weight must be positive.")
    return {d: w / total for d, w in clean.items()}


def profile_weights(profile_key: str) -> dict[str, float]:
    if profile_key not in PROFILES:
        raise ValueError(f"Unknown mission profile {profile_key!r}.")
    return normalize_weights(PROFILES[profile_key]["weights"])
