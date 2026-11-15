# ASTRA scientific methods, assumptions and limitations

This document describes exactly how ASTRA produces every number it shows. The
implementation lives in `backend/science/` and `backend/data/`; engine version
`1.0.0` (`backend/science/similarity.py`).

## 1. Data sources

| Body | Product | Provider | Native spacing | Access |
|------|---------|----------|----------------|--------|
| Earth (60 N–56 S) | NASADEM_HGT v001 | NASA JPL / LP DAAC | ~30 m (1 arcsec) | COGs on Microsoft Planetary Computer |
| Earth (outside NASADEM) | Copernicus DEM GLO-30 | ESA / Airbus (not NASA) | ~30 m | COGs on Microsoft Planetary Computer |
| Earth | NASA POWER Daily API v2.x | NASA LaRC | ~0.5° x 0.625° (MERRA-2) | `power.larc.nasa.gov` |
| Moon | LOLA GDR LDEM_64 (V3.1) | NASA GSFC / PDS Geosciences | 473.8 m | HTTP Range reads of the PDS IMG |
| Moon (south pole) | LOLA GDR LDEM_75S_240M (V2.1) | NASA GSFC / PDS Geosciences | 240 m (polar stereographic) | HTTP Range reads |
| Mars | MOLA MEGDR 128 px/deg (v2.0) | NASA GSFC / PDS Geosciences | ~463 m | HTTP Range reads |

Each acquired subset is stored in `datasets/<body>/` with a JSON sidecar
(source URL, product, georeferencing, SHA-256, retrieval time). Ingestion
re-verifies the checksum. NASA POWER daily data for 2020-01-01 to 2023-12-31
are stored as JSON in `datasets/earth/power/`.

Iceland (Holuhraun, 64.9 N) and the McMurdo Dry Valleys (77.5 S) lie outside
NASADEM coverage, so their terrain uses Copernicus GLO-30. The UI and the
reports label this explicitly.

No synthetic or sample data are used anywhere in the database. The tests use
analytic synthetic surfaces only inside the test process.

## 2. Terrain analysis (T11)

1. A 30 km x 30 km window (plus a 1.5 km margin) centred on the site is extracted.
2. It is resampled to a **common 60 x 60 grid of 500 m cells** in local metric
   coordinates (`science/resample.py`). For geographic grids, local coordinates
   use a spherical tangent approximation: x = R cos(lat) Δlon, y = R Δlat. The
   radii are Earth 6371.0088 km, Moon 1737.4 km and Mars 3396.0 km (from the PDS
   labels). Polar stereographic metres are used directly.
   - Native spacing ≤ 250 m (Earth 30 m, lunar polar 240 m): block mean of the
     native pixel centres inside each cell.
   - Native spacing > 250 m (LDEM_64, MEGDR): bilinear interpolation at cell centres.
3. Metrics (`science/terrain.py`):
   - Slope: arctan |∇z| from central differences, in degrees.
   - TRI: mean absolute difference between a cell and its 8 neighbours, in metres.
   - Local relief: 95th minus 5th percentile elevation, in metres.
   - Steep-slope fraction: the share of cells with slope > 15°.
4. At least 90 % of cells must have data, or the terrain features are recorded
   as missing.

**Why a common grid:** slope and roughness grow as the horizontal resolution
gets finer. Comparing 30 m Earth slopes with 474 m lunar slopes would be
meaningless. A common 500 m grid makes the values comparable at that scale
only. Native-resolution Earth slope is stored for display and is never scored.

**Absolute elevation is never compared.** Each body has a different datum
(geoid, reference sphere, areoid).

## 3. Thermal and climate features

| Feature | Earth (NASA POWER) | Targets |
|---|---|---|
| `surface_temp_max_k` | 95th percentile of daily `TS_MAX` (skin temperature) per year, mean over years | Literature typical daytime maximum |
| `surface_temp_min_k` | 5th percentile of daily `TS_MIN` per year | Literature typical night minimum |
| `surface_temp_diurnal_range_k` | Mean daily `TS_MAX − TS_MIN` | Literature range |
| `annual_precipitation_mm` | Annual sum of `PRECTOTCORR` | 0, as a physical constraint (no liquid precipitation) |

Earth uncertainty is the interannual standard deviation over 2020–2023. It
excludes reanalysis model error.

Literature target values exist only for:
- **Apollo 11 / equatorial mare**: ~390 K maximum and ~95 K minimum (Williams et
  al. 2017, Diviner).
- **Gale crater**: ~285 K and ~185 K (Vasavada et al. 2017, REMS).

Both carry uncertainties of ±10–20 K, assigned by the curators. They are
approximate typical values, so verify them against the papers before
publication. For the other targets, the thermal values are **missing**, with
reasons. This lowers coverage instead of guessing.

**Comparability caveat:** POWER `TS` is a modelled skin temperature for a grid
cell of about 50 km. Target values are surface (kinetic or brightness)
temperatures measured from orbit or by a rover. Treating them as equivalent is
an approximation. POWER precipitation in complex terrain (Ladakh, the Rann of
Kutch, the Icelandic highlands) can differ substantially from local station
climatology.

## 4. Categorical features

Geology, resource and hazard tags come from controlled vocabularies
(`backend/data/vocabulary.py`), assigned by the curators from general
literature. Their `source_type` is `curated_classification` and they are not
measurements. They are compared with the Jaccard index |A∩B| / |A∪B|, and two
empty sets are defined as identical (1.0).

Hazards that have no Earth analog are reported as limitations, not tags:
unshielded radiation, vacuum or a thin CO₂ atmosphere, and reduced gravity.
Treating them as tags would penalise every Earth site equally and hide that
fact.

## 5. Similarity scoring (T12–T14)

For dimension weight W_d (mission profile, normalised to sum to 1) and feature
sub-weight v_f (sums to 1 within each dimension):

```
w_f   = W_d(f) · v_f
s_f   = exp(−½ (Δ_f / σ_f)²)         continuous, Δ = T(candidate) − T(target)
s_f   = Jaccard(A, B)                categorical
score = 100 · Σ_valid w_f s_f / Σ_valid w_f
```

| Feature | Transform T | Scale σ | Sub-weight |
|---|---|---|---|
| slope_mean_deg | identity | 3° | 0.4 |
| tri_mean_m | log10 | 0.3 (≈ ×2) | 0.3 |
| relief_p95_p5_m | log10 | 0.3 | 0.3 |
| surface_temp_max_k | identity | 30 K | 0.3 |
| surface_temp_min_k | identity | 30 K | 0.3 |
| surface_temp_diurnal_range_k | identity | 30 K | 0.2 |
| annual_precipitation_mm | log10(1+P) | 1.0 | 0.2 |
| steep_slope_fraction | identity | 0.10 | 0.5 |
| geology / resource tags | Jaccard | – | 1.0 |
| hazard tags | Jaccard | – | 0.5 |

The scales are fixed, documented tolerances. They do not depend on which
candidates are loaded, so scores are reproducible between runs. Min–max
normalisation (`science/normalization.py`) is used only for chart display.

**Missing data:** a feature is valid only if both sites have a value. ASTRA reports:
- **coverage** = Σ_valid w_f / Σ_all w_f
- **measurement interval**: each s_f is evaluated at |Δ| ± (u_cand + u_target).
  This is a worst-case linear combination, propagated to log space to first
  order.
- **full bounds**: the score over all features, with missing features set to 0
  (lower) or 1 (upper), combined with the measurement interval.
- **confidence**:
  - *high*: coverage ≥ 0.85 and bound width ≤ 20
  - *medium*: coverage ≥ 0.6 and width ≤ 40
  - *low*: anything else

Explanations (`science/explain.py`) are templates filled from computed
FeatureScores. They report strengths (s ≥ 0.8), partial matches, mismatches
(s < 0.5) and the reason for each missing value.

Mission profiles (`science/profiles.py`):

| Profile | Geology | Terrain | Thermal | Resources | Hazards |
|---|---|---|---|---|---|
| general_analog | .25 | .25 | .20 | .15 | .15 |
| surface_operations | .15 | .35 | .15 | .10 | .25 |
| isru | .25 | .10 | .20 | .35 | .10 |
| astrobiology | .35 | .10 | .20 | .20 | .15 |
| rover_traverse | .15 | .35 | .10 | .10 | .30 |

Custom weights are accepted through the API and validated (non-negative, known
dimensions, positive sum).

## 6. Fundamental limitations

No Earth site reproduces:
- lunar gravity (1.62 m/s²) or Martian gravity (3.71 m/s²)
- lunar vacuum, or the ~0.6 kPa CO₂ atmosphere of Mars
- unshielded galactic cosmic ray and solar particle radiation
- lunar regolith properties
- the ~29.5-day lunar thermal cycle

Earth sites are shaped by liquid water, biology and plate tectonics. These
statements are attached to every result, comparison and report.

Other known limitations:
- **Scale**: a 30 km window and 500 m cells hide metre-scale hazards such as
  boulders and small craters. Lonar crater (~1.8 km) is much smaller than the
  window.
- **Interpolation**: LOLA LDEM_64 and MOLA MEGDR interpolate between laser
  tracks, which smooths the terrain.
- **Tag coverage**: curated tags are coarse and incomplete, and some candidates
  have no peer-reviewed analog reference curated yet.
- **Thermal coverage**: target thermal coverage is limited to two sites.
- **Fixed scales**: the similarity scales are expert choices, not fitted
  parameters. Changing them changes the scores, so the weights and scales are
  shown alongside every result.
