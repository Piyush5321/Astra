"""Curated catalog of Earth candidate locations and Moon/Mars target regions.

Earth sites are *candidates*: their inclusion is not a claim that they are good
analogs. Rankings come only from the scoring engine. Coordinates are approximate
centres of a 30 km analysis window, chosen from widely published site locations
(see ``coordinate_source``); they are not survey-grade positions.

Target literature thermal values are approximate reference values read from the
cited publications and carry explicit uncertainties. Where ASTRA has no vetted
reference, the value is recorded as missing rather than estimated.
"""

from dataclasses import dataclass, field

LIMITATION_NOT_VERIFIED = (
    "Curated classification; verify against primary literature before publication."
)


@dataclass(frozen=True)
class Reference:
    citation: str
    url: str = ""

    def as_dict(self) -> dict:
        return {"citation": self.citation, "url": self.url}


@dataclass(frozen=True)
class LiteratureValue:
    """A target value taken from published literature."""

    value: float
    uncertainty: float
    unit: str
    citation: str
    note: str


@dataclass(frozen=True)
class SiteSpec:
    id: str
    name: str
    body: str  # earth | moon | mars
    role: str  # candidate | target
    latitude: float
    longitude: float  # degrees east, -180..180
    region: str
    description: str
    scientific_context: str
    coordinate_source: str
    geology_tags: tuple[str, ...]
    resource_tags: tuple[str, ...]
    hazard_tags: tuple[str, ...]
    references: tuple[Reference, ...] = ()
    site_notes: tuple[str, ...] = ()
    thermal: dict[str, LiteratureValue] = field(default_factory=dict)
    thermal_missing_reason: str = ""


# --- Published references (only works the authors of ASTRA could identify) -------

WILLIAMS_2017 = (
    "Williams, J.-P., Paige, D. A., Greenhagen, B. T., Sefton-Nash, E. (2017). The global "
    "surface temperatures of the Moon as measured by the Diviner Lunar Radiometer "
    "Experiment. Icarus 283, 300-325."
)
VASAVADA_2017 = (
    "Vasavada, A. R., et al. (2017). Thermophysical properties along Curiosity's traverse "
    "in Gale crater, Mars, derived from the REMS ground temperature sensor. Icarus 284, "
    "372-386."
)
REFS = {
    "williams2017": Reference(WILLIAMS_2017, "https://doi.org/10.1016/j.icarus.2016.08.012"),
    "vasavada2017": Reference(VASAVADA_2017, "https://doi.org/10.1016/j.icarus.2016.11.035"),
    "paige2010": Reference(
        "Paige, D. A., et al. (2010). Diviner Lunar Radiometer observations of cold traps "
        "in the Moon's south polar region. Science 330, 479-482."
    ),
    "zuber2012": Reference(
        "Zuber, M. T., et al. (2012). Constraints on the volatile distribution within "
        "Shackleton crater at the lunar south pole. Nature 486, 378-381."
    ),
    "li2018": Reference(
        "Li, S., et al. (2018). Direct evidence of surface exposed water ice in the lunar "
        "polar regions. PNAS 115, 8907-8912."
    ),
    "mazarico2011": Reference(
        "Mazarico, E., Neumann, G. A., Smith, D. E., Zuber, M. T., Torrence, M. H. (2011). "
        "Illumination conditions of the lunar polar regions using LOLA topography. "
        "Icarus 211, 1066-1081."
    ),
    "gaddis2003": Reference(
        "Gaddis, L. R., et al. (2003). Compositional analyses of lunar pyroclastic "
        "deposits. Icarus 161, 262-280."
    ),
    "goudge2015": Reference(
        "Goudge, T. A., Mustard, J. F., Head, J. W., Fassett, C. I., Wiseman, S. M. (2015). "
        "Assessing the mineralogy of the watershed and fan deposits of the Jezero crater "
        "paleolake system, Mars. JGR Planets 120, 775-808."
    ),
    "farley2020": Reference(
        "Farley, K. A., et al. (2020). Mars 2020 Mission Overview. Space Science Reviews "
        "216, 142."
    ),
    "grotzinger2014": Reference(
        "Grotzinger, J. P., et al. (2014). A habitable fluvio-lacustrine environment at "
        "Yellowknife Bay, Gale Crater, Mars. Science 343, 1242777."
    ),
    "squyres2004": Reference(
        "Squyres, S. W., et al. (2004). In situ evidence for an ancient aqueous environment "
        "at Meridiani Planum, Mars. Science 306, 1709-1714."
    ),
    "fredriksson1973": Reference(
        "Fredriksson, K., Dube, A., Milton, D. J., Balasundaram, M. S. (1973). Lonar Lake, "
        "India: an impact crater in basalt. Science 180, 862-864."
    ),
    "navarro2003": Reference(
        "Navarro-Gonzalez, R., et al. (2003). Mars-like soils in the Atacama Desert, Chile, "
        "and the dry limit of microbial life. Science 302, 1018-1021."
    ),
    "marchant2007": Reference(
        "Marchant, D. R., Head, J. W. (2007). Antarctic dry valleys: microclimate zonation, "
        "variable geomorphic processes, and implications for assessing climate change on "
        "Mars. Icarus 192, 187-222."
    ),
    "pandey2020": Reference(
        "Pandey, S., et al. (2020). Ladakh: diverse, high-altitude extreme environments for "
        "off-earth analogue and astrobiology research. International Journal of "
        "Astrobiology 19, 78-98."
    ),
}

EARTH_CANDIDATES: tuple[SiteSpec, ...] = (
    SiteSpec(
        id="ladakh-tso-kar",
        name="Tso Kar basin, Ladakh",
        body="earth", role="candidate", latitude=33.30, longitude=78.00,
        region="Ladakh, India",
        description="High-altitude (~4500 m) cold desert basin with a saline lake, "
        "periglacial landforms and sparse vegetation on the Changthang plateau.",
        scientific_context="Studied as a Mars analog for cold, arid, high-UV, low-pressure "
        "conditions and saline/evaporitic environments.",
        coordinate_source="Approximate centre of Tso Kar lake (33.3 N, 78.0 E).",
        geology_tags=("sedimentary_layered", "evaporite", "glacial_periglacial",
                      "permafrost", "aeolian_bedforms", "mountainous_massif"),
        resource_tags=("water_ice", "brines"),
        hazard_tags=("high_uv", "strong_winds"),
        references=(REFS["pandey2020"],),
    ),
    SiteSpec(
        id="lonar-crater",
        name="Lonar Crater",
        body="earth", role="candidate", latitude=19.976, longitude=76.508,
        region="Maharashtra, India",
        description="~1.8 km diameter simple impact crater excavated in Deccan flood "
        "basalt, hosting a saline-alkaline lake.",
        scientific_context="One of few well-preserved impact craters in basalt on Earth; "
        "relevant to basaltic impact processes on the Moon and Mars.",
        coordinate_source="Crater centre (19.976 N, 76.508 E).",
        geology_tags=("impact_structure", "basaltic_volcanic", "flood_basalt"),
        resource_tags=("basalt_feedstock", "brines"),
        hazard_tags=(),
        references=(REFS["fredriksson1973"],),
        site_notes=(
            "The crater (~1.8 km) is much smaller than the 30 km analysis window; terrain "
            "metrics are dominated by the surrounding Deccan plateau.",
            "NASA POWER grid cells (~50 km) cannot resolve the crater microclimate.",
        ),
    ),
    SiteSpec(
        id="rann-of-kutch",
        name="Great Rann of Kutch",
        body="earth", role="candidate", latitude=23.90, longitude=69.80,
        region="Gujarat, India",
        description="Vast, seasonally flooded salt flat (evaporite playa) bordering the "
        "Thar Desert.",
        scientific_context="Evaporite and salt-flat processes relevant to Martian "
        "sulfate/chloride deposits.",
        coordinate_source="Approximate position on the White Rann salt flat north of Bhuj.",
        geology_tags=("evaporite", "sedimentary_layered"),
        resource_tags=("hydrated_minerals", "brines"),
        hazard_tags=("salt_crust", "fine_dust"),
        site_notes=("No peer-reviewed Mars-analog reference curated yet in ASTRA.",),
    ),
    SiteSpec(
        id="deccan-traps-mahabaleshwar",
        name="Deccan Traps escarpment, Mahabaleshwar",
        body="earth", role="candidate", latitude=17.92, longitude=73.66,
        region="Maharashtra, India",
        description="Stacked flood-basalt flows exposed along the Western Ghats "
        "escarpment of the Deccan large igneous province.",
        scientific_context="Basaltic volcanism analogous in composition to lunar maria and "
        "Martian volcanic plains (not in emplacement environment).",
        coordinate_source="Approximate position of Mahabaleshwar plateau (17.92 N, 73.66 E).",
        geology_tags=("flood_basalt", "basaltic_volcanic", "mountainous_massif"),
        resource_tags=("basalt_feedstock",),
        hazard_tags=(),
        site_notes=("Monsoon climate and dense vegetation are strongly non-analog.",),
    ),
    SiteSpec(
        id="atacama-yungay",
        name="Yungay, Atacama Desert",
        body="earth", role="candidate", latitude=-24.08, longitude=-70.01,
        region="Antofagasta Region, Chile",
        description="Hyperarid core of the Atacama Desert with oxidising, salt-rich soils "
        "(nitrates, perchlorates, sulfates).",
        scientific_context="Classic Mars soil and astrobiology analog near the dry limit "
        "of microbial life.",
        coordinate_source="Approximate location of the Yungay research area.",
        geology_tags=("evaporite", "sulfate_minerals", "sedimentary_layered"),
        resource_tags=("perchlorates_nitrates", "hydrated_minerals"),
        hazard_tags=("high_uv", "fine_dust"),
        references=(REFS["navarro2003"],),
    ),
    SiteSpec(
        id="iceland-holuhraun",
        name="Holuhraun lava field",
        body="earth", role="candidate", latitude=64.87, longitude=-16.83,
        region="Highlands, Iceland",
        description="Basaltic lava field (2014-2015 eruption) on glacial outwash plains "
        "north of Vatnajokull, with black volcanic sands.",
        scientific_context="Fresh basaltic volcanism, glaciovolcanic and aeolian processes "
        "used as Mars and lunar surface-operations analogs.",
        coordinate_source="Approximate centre of the Holuhraun lava field.",
        geology_tags=("basaltic_volcanic", "glacial_periglacial", "aeolian_bedforms",
                      "hydrothermal"),
        resource_tags=("basalt_feedstock", "volcanic_glass", "water_ice"),
        hazard_tags=("strong_winds", "fine_dust", "dust_storms"),
        site_notes=(
            "Outside NASADEM coverage (60 N limit): terrain uses Copernicus GLO-30.",
            "No peer-reviewed Mars-analog reference curated yet in ASTRA.",
        ),
    ),
    SiteSpec(
        id="death-valley-badwater",
        name="Badwater Basin, Death Valley",
        body="earth", role="candidate", latitude=36.23, longitude=-116.77,
        region="California, USA",
        description="Below-sea-level evaporite playa flanked by alluvial fans and steep "
        "mountain fronts.",
        scientific_context="Evaporite, alluvial-fan and paleolake processes relevant to "
        "Martian sedimentary basins.",
        coordinate_source="Approximate centre of Badwater Basin salt pan.",
        geology_tags=("evaporite", "sedimentary_layered", "fluvio_lacustrine",
                      "mountainous_massif"),
        resource_tags=("hydrated_minerals", "brines"),
        hazard_tags=("salt_crust",),
        site_notes=("No peer-reviewed Mars-analog reference curated yet in ASTRA.",),
    ),
    SiteSpec(
        id="mcmurdo-wright-valley",
        name="Wright Valley, McMurdo Dry Valleys",
        body="earth", role="candidate", latitude=-77.52, longitude=161.85,
        region="Victoria Land, Antarctica",
        description="Ice-free polar desert valley with permafrost, patterned ground, "
        "hypersaline Don Juan Pond and katabatic winds.",
        scientific_context="Cold, hyperarid polar desert: among the most-cited terrestrial "
        "analogs for Martian surface processes.",
        coordinate_source="Approximate centre of Wright Valley.",
        geology_tags=("glacial_periglacial", "permafrost", "polar_terrain",
                      "aeolian_bedforms", "evaporite", "mountainous_massif"),
        resource_tags=("water_ice", "brines"),
        hazard_tags=("strong_winds",),
        references=(REFS["marchant2007"],),
        site_notes=("Outside NASADEM coverage (56 S limit): terrain uses Copernicus GLO-30.",),
    ),
)

TARGETS: tuple[SiteSpec, ...] = (
    SiteSpec(
        id="moon-south-pole-shackleton",
        name="Lunar South Pole - Shackleton region",
        body="moon", role="target", latitude=-90.0, longitude=0.0,
        region="Lunar south polar region",
        description="30 km window centred on the lunar south pole, including Shackleton "
        "crater (~21 km) and the connecting ridge; candidate region for Artemis surface "
        "missions.",
        scientific_context="Permanently shadowed cold traps may retain water ice; "
        "nearby ridges receive extended illumination.",
        coordinate_source="Window centred on the geographic south pole so polar "
        "stereographic conventions cannot shift it.",
        geology_tags=("anorthositic_highland", "impact_structure", "regolith_fines",
                      "polar_terrain"),
        resource_tags=("water_ice", "volatile_cold_traps", "extended_illumination"),
        hazard_tags=("fine_dust", "high_uv", "permanent_shadow"),
        references=(REFS["paige2010"], REFS["zuber2012"], REFS["li2018"], REFS["mazarico2011"]),
        site_notes=(
            "Water-ice abundance inside Shackleton itself is debated; 'water_ice' reflects "
            "evidence for ice in south polar cold traps generally.",
        ),
        thermal_missing_reason="ASTRA does not yet ingest Diviner polar temperature "
        "products; polar temperatures vary from <50 K in shadow to far warmer on sunlit "
        "ridges, so a single reference value would be misleading.",
    ),
    SiteSpec(
        id="moon-apollo11-tranquillitatis",
        name="Mare Tranquillitatis - Apollo 11 site",
        body="moon", role="target", latitude=0.674, longitude=23.473,
        region="Mare Tranquillitatis",
        description="Equatorial high-titanium mare basalt plain; Apollo 11 landing site.",
        scientific_context="Baseline lunar mare environment with returned-sample ground truth.",
        coordinate_source="Apollo 11 lunar module landing site (0.674 N, 23.473 E).",
        geology_tags=("basaltic_volcanic", "impact_structure", "regolith_fines"),
        resource_tags=("ilmenite_titanium", "basalt_feedstock"),
        hazard_tags=("fine_dust", "high_uv"),
        references=(REFS["williams2017"],),
        thermal={
            "surface_temp_max_k": LiteratureValue(
                390.0, 10.0, "K", WILLIAMS_2017,
                "Approximate equatorial daytime maximum from Diviner."),
            "surface_temp_min_k": LiteratureValue(
                95.0, 10.0, "K", WILLIAMS_2017,
                "Approximate equatorial pre-dawn minimum from Diviner."),
            "surface_temp_diurnal_range_k": LiteratureValue(
                295.0, 15.0, "K", WILLIAMS_2017,
                "Difference of the approximate equatorial maximum and minimum; the lunar "
                "day lasts ~29.5 Earth days."),
        },
    ),
    SiteSpec(
        id="moon-aristarchus-plateau",
        name="Aristarchus Plateau",
        body="moon", role="target", latitude=26.0, longitude=-51.0,
        region="Oceanus Procellarum",
        description="Elevated volcanic plateau mantled by extensive pyroclastic deposits "
        "and cut by Vallis Schroteri.",
        scientific_context="Volcanic glass deposits are of interest for lunar volcanism "
        "and volatile/oxygen resources.",
        coordinate_source="Approximate plateau centre near Vallis Schroteri.",
        geology_tags=("pyroclastic_deposits", "basaltic_volcanic", "impact_structure",
                      "regolith_fines"),
        resource_tags=("volcanic_glass", "basalt_feedstock"),
        hazard_tags=("fine_dust", "high_uv"),
        references=(REFS["gaddis2003"],),
        thermal_missing_reason="No vetted mid-latitude surface temperature reference "
        "curated in ASTRA for this target.",
    ),
    SiteSpec(
        id="mars-jezero",
        name="Jezero Crater",
        body="mars", role="target", latitude=18.4447, longitude=77.4508,
        region="Isidis Planitia margin",
        description="~45 km paleolake crater with a preserved delta; Perseverance landing "
        "site.",
        scientific_context="Fluvio-lacustrine sediments with carbonates and clays; Mars "
        "Sample Return astrobiology target.",
        coordinate_source="Perseverance landing site (18.4447 N, 77.4508 E).",
        geology_tags=("fluvio_lacustrine", "deltaic", "carbonates", "clay_phyllosilicates",
                      "basaltic_volcanic", "impact_structure", "aeolian_bedforms"),
        resource_tags=("hydrated_minerals",),
        hazard_tags=("fine_dust", "dust_storms", "high_uv"),
        references=(REFS["goudge2015"], REFS["farley2020"]),
        thermal_missing_reason="No vetted MEDA-derived surface temperature reference "
        "curated in ASTRA for this target.",
    ),
    SiteSpec(
        id="mars-gale",
        name="Gale Crater - Aeolis Palus",
        body="mars", role="target", latitude=-4.5895, longitude=137.4417,
        region="Gale crater",
        description="Crater floor near Curiosity's landing site at the foot of Aeolis "
        "Mons (Mount Sharp).",
        scientific_context="Ancient habitable fluvio-lacustrine environment with clays "
        "and sulfates in layered sediments.",
        coordinate_source="Curiosity (Bradbury) landing site (4.5895 S, 137.4417 E).",
        geology_tags=("sedimentary_layered", "fluvio_lacustrine", "clay_phyllosilicates",
                      "sulfate_minerals", "impact_structure", "aeolian_bedforms"),
        resource_tags=("hydrated_minerals",),
        hazard_tags=("fine_dust", "dust_storms", "high_uv"),
        references=(REFS["grotzinger2014"], REFS["vasavada2017"]),
        thermal={
            "surface_temp_max_k": LiteratureValue(
                285.0, 15.0, "K", VASAVADA_2017,
                "Approximate typical afternoon ground temperature maximum (REMS GTS)."),
            "surface_temp_min_k": LiteratureValue(
                185.0, 15.0, "K", VASAVADA_2017,
                "Approximate typical pre-dawn ground temperature minimum (REMS GTS)."),
            "surface_temp_diurnal_range_k": LiteratureValue(
                90.0, 20.0, "K", VASAVADA_2017,
                "Approximate typical diurnal ground temperature range; varies seasonally."),
        },
    ),
    SiteSpec(
        id="mars-meridiani",
        name="Meridiani Planum - Opportunity site",
        body="mars", role="target", latitude=-1.9462, longitude=-5.5266,
        region="Meridiani Planum",
        description="Flat plain of sulfate-rich sandstones with hematite concretions; "
        "Opportunity landing site (Eagle crater).",
        scientific_context="Evidence of ancient acidic, evaporitic groundwater "
        "environments.",
        coordinate_source="Opportunity landing site (1.9462 S, 354.4734 E).",
        geology_tags=("sulfate_minerals", "hematite_concretions", "evaporite",
                      "sedimentary_layered", "aeolian_bedforms", "impact_structure"),
        resource_tags=("hydrated_minerals",),
        hazard_tags=("fine_dust", "dust_storms", "high_uv"),
        references=(REFS["squyres2004"],),
        thermal_missing_reason="No vetted Mini-TES surface temperature reference curated "
        "in ASTRA for this target.",
    ),
)

ALL_SITES: tuple[SiteSpec, ...] = EARTH_CANDIDATES + TARGETS
SITES_BY_ID: dict[str, SiteSpec] = {s.id: s for s in ALL_SITES}

# Physical-constraint value for liquid precipitation on target bodies.
TARGET_PRECIPITATION_NOTE = {
    "moon": "The Moon has no atmosphere; liquid precipitation is physically impossible.",
    "mars": "Liquid precipitation cannot occur at present Martian surface pressure and "
    "temperature. Water-ice and CO2 frost/snowfall occur, mainly at high latitudes, and "
    "are not equivalent to rainfall.",
}

PRESET_MISSIONS: tuple[dict, ...] = (
    {
        "name": "Artemis south-pole surface operations analog",
        "target_site_id": "moon-south-pole-shackleton",
        "profile_key": "surface_operations",
        "objectives": "Identify terrain and hazard analogs for crewed surface "
        "operations near the lunar south pole.",
    },
    {
        "name": "Lunar polar volatiles (ISRU) analog",
        "target_site_id": "moon-south-pole-shackleton",
        "profile_key": "isru",
        "objectives": "Find Earth sites for testing ice-prospecting and resource "
        "extraction workflows.",
    },
    {
        "name": "Apollo 11 mare analog",
        "target_site_id": "moon-apollo11-tranquillitatis",
        "profile_key": "general_analog",
        "objectives": "General-purpose analog search for an equatorial mare basalt plain.",
    },
    {
        "name": "Jezero astrobiology analog",
        "target_site_id": "mars-jezero",
        "profile_key": "astrobiology",
        "objectives": "Find Earth sites with comparable sedimentary/aqueous geology for "
        "biosignature and sampling studies.",
    },
    {
        "name": "Gale crater rover traverse analog",
        "target_site_id": "mars-gale",
        "profile_key": "rover_traverse",
        "objectives": "Find Earth terrain suitable for rover mobility and navigation "
        "testing.",
    },
    {
        "name": "Meridiani sulfate analog",
        "target_site_id": "mars-meridiani",
        "profile_key": "astrobiology",
        "objectives": "Find evaporitic, sulfate-bearing Earth environments.",
    },
)
