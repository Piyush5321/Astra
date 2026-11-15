"""Fundamental environmental differences that no Earth analog can reproduce.

Values are standard reference figures (rounded) for context only; they are not
used in scoring.
"""

ENVIRONMENT = {
    "earth": {"gravity_m_s2": 9.81, "surface_pressure_pa": 101_325,
              "atmosphere": "N2/O2, ~101 kPa at sea level", "day_length": "24 h",
              "magnetic_field": "Global dipole field"},
    "moon": {"gravity_m_s2": 1.62, "surface_pressure_pa": None,
             "atmosphere": "None (tenuous exosphere; effectively vacuum)",
             "day_length": "~29.5 Earth days (synodic)",
             "magnetic_field": "No global field"},
    "mars": {"gravity_m_s2": 3.71, "surface_pressure_pa": 600,
             "atmosphere": "~95% CO2, ~0.6 kPa mean surface pressure",
             "day_length": "24 h 39 min (sol)",
             "magnetic_field": "No global field (local crustal fields)"},
}

COMMON = [
    "Similarity scores describe selected measurable properties at a 500 m / 30 km "
    "scale; they do not certify a site as a mission-ready analog.",
    "Earth sites are affected by liquid water, vegetation, biology and plate tectonics "
    "in ways target bodies are not.",
]

BODY_LIMITATIONS = {
    "moon": [
        "Gravity: lunar surface gravity is ~1/6 of Earth's (1.62 vs 9.81 m/s2); no Earth "
        "site reproduces regolith mechanics, dust lofting or mobility under lunar gravity.",
        "Vacuum: the Moon has no atmosphere; Earth sites cannot reproduce vacuum thermal "
        "behaviour, electrostatic dust effects or the absence of wind and weathering.",
        "Radiation: the lunar surface is exposed to galactic cosmic rays and solar "
        "particle events without atmospheric or magnetic shielding.",
        "Regolith: lunar regolith (agglutinates, sharp unweathered grains, space "
        "weathering) has no natural Earth equivalent.",
        "Thermal: the ~29.5-day lunar day produces temperature swings of hundreds of "
        "kelvin, far beyond any Earth surface.",
    ],
    "mars": [
        "Gravity: Martian surface gravity is ~0.38 of Earth's (3.71 vs 9.81 m/s2).",
        "Atmosphere: Mars has a thin (~0.6 kPa) CO2 atmosphere; Earth analogs cannot "
        "reproduce its pressure, composition, or aeolian transport thresholds.",
        "Radiation: the Martian surface lacks a global magnetic field and has a thin "
        "atmosphere, giving far higher ionising and UV radiation than any Earth site.",
        "Chemistry: oxidants (e.g. perchlorates) and soil chemistry differ even in the "
        "best Earth analogs.",
        "Liquid water: Earth analog sites experience liquid water and biology at levels "
        "not present on the Martian surface today.",
    ],
}


def limitations_for(body: str) -> list[str]:
    return BODY_LIMITATIONS.get(body, []) + COMMON
