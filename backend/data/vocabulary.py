"""Controlled vocabularies for curated categorical classifications.

Tags are qualitative descriptors curated from the general geological and mission
literature. They are compared with the Jaccard index (see ``science.similarity``)
and are always labelled ``curated_classification`` — they are not measurements.
Hazards with no Earth analog (unshielded radiation, vacuum, low gravity) are
deliberately absent: they are reported as fundamental limitations instead.
"""

GEOLOGY_TAGS: dict[str, str] = {
    "basaltic_volcanic": "Basaltic lava plains, flows or basaltic bedrock dominate.",
    "flood_basalt": "Large igneous province of stacked flood-basalt flows.",
    "anorthositic_highland": "Ancient feldspar-rich (anorthositic) highland crust.",
    "impact_structure": "Impact crater(s) or impact-modified terrain are a defining feature.",
    "pyroclastic_deposits": "Explosive volcanic ash or glass-bead deposits.",
    "regolith_fines": "Unconsolidated fine-grained regolith produced by impact gardening.",
    "sedimentary_layered": "Layered sedimentary rock sequences.",
    "fluvio_lacustrine": "River and/or lake (paleolake) deposits.",
    "deltaic": "Delta or fan deposits built into a standing body of water.",
    "evaporite": "Salt deposits formed by evaporation (halite, gypsum, borates).",
    "sulfate_minerals": "Sulfate-bearing minerals (e.g. gypsum, jarosite, Mg/Ca sulfates).",
    "hematite_concretions": "Hematite concretions or hematite-rich deposits.",
    "clay_phyllosilicates": "Clay minerals / phyllosilicates from aqueous alteration.",
    "carbonates": "Carbonate minerals.",
    "hydrothermal": "Active or fossil hydrothermal systems and alteration.",
    "glacial_periglacial": "Glacial or periglacial landforms (moraines, patterned ground).",
    "permafrost": "Perennially frozen ground.",
    "aeolian_bedforms": "Wind-formed dunes, ripples or sand sheets.",
    "polar_terrain": "High-latitude polar terrain and illumination geometry.",
    "mountainous_massif": "Massifs, escarpments or high-relief mountain topography.",
}

RESOURCE_TAGS: dict[str, str] = {
    "water_ice": "Water ice in the ground or at the surface (incl. permafrost, polar ice).",
    "volatile_cold_traps": "Permanently shadowed cold traps able to retain volatiles.",
    "hydrated_minerals": "Minerals with structurally bound water (clays, sulfates, borates).",
    "ilmenite_titanium": "Ilmenite / titanium-rich materials (oxygen-extraction feedstock).",
    "volcanic_glass": "Volcanic glass or tephra (pyroclastic glass on the Moon).",
    "perchlorates_nitrates": "Oxychlorine (perchlorate) and/or nitrate salts.",
    "brines": "Saline liquid water bodies or brines.",
    "extended_illumination": "Near-continuous solar illumination (polar ridges/peaks).",
    "basalt_feedstock": "Basaltic rock or regolith usable as construction feedstock.",
}

HAZARD_TAGS: dict[str, str] = {
    "fine_dust": "Fine, abrasive, easily lofted dust or regolith.",
    "dust_storms": "Recurrent regional dust storms.",
    "permanent_shadow": "Persistently or permanently shadowed terrain (power, thermal).",
    "high_uv": "Elevated surface ultraviolet flux (thin or absent atmosphere, altitude).",
    "strong_winds": "Frequent strong winds (e.g. katabatic winds, storms).",
    "salt_crust": "Salt crusts or soft playa surfaces that affect trafficability.",
}

VOCABULARIES: dict[str, dict[str, str]] = {
    "geology_tags": GEOLOGY_TAGS,
    "resource_tags": RESOURCE_TAGS,
    "hazard_tags": HAZARD_TAGS,
}


def validate_tags(feature_key: str, tags: list[str]) -> list[str]:
    """Return sorted, de-duplicated tags; raise ValueError on unknown tags."""
    vocab = VOCABULARIES.get(feature_key)
    if vocab is None:
        raise ValueError(f"No vocabulary for feature {feature_key!r}.")
    unknown = sorted(set(tags) - set(vocab))
    if unknown:
        raise ValueError(f"Unknown {feature_key} tags: {', '.join(unknown)}.")
    return sorted(set(tags))
