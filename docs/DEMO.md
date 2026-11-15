# ASTRA demo script (~6 minutes)

**Setup:**
- Run `python -m backend.main`, then open `http://127.0.0.1:8000`.
- The status pill should read "Backend online".

## 1. The problem (30 s)
"Before Artemis or a Mars mission, teams rehearse at Earth analog sites. Choosing
those sites is usually qualitative. ASTRA ranks candidates with transparent,
reproducible measurements from NASA data, and it says exactly what it does not
know."

## 2. Mission setup: Mars (45 s)
- Click **Mars**, then **Gale Crater – Aeolis Palus**.
- Point out the preset **Gale crater rover traverse analog** (terrain 35 %,
  hazards 30 %).
- Optionally drag a weight slider. The weights renormalise to 100 %, which
  creates a custom mission.
- Click **Run discovery**.

## 3. Discovery (60 s)
- On the map, each marker's colour is its score.
- Atacama (Yungay) and Death Valley rank highest.
- For each candidate, explain:
  - the **score**
  - the **measurement range**, from the stated uncertainties
  - the **bounds including missing data**
  - **coverage** and **confidence**
- Scroll down to "What these scores cannot capture": gravity, atmosphere,
  radiation.

## 4. Evidence: Atacama vs Gale (90 s)
- Click Atacama.
- The **radar** shows the dimension scores. In the **feature similarity** chart,
  the grey bars are the uncertainty ranges.
- In the **feature table**, show:
  - mean slope 4.6° vs 5.1°, a close match
  - local relief 568 m vs 2,514 m, a mismatch
  - temperature minimum 275 K vs 185 K: Earth is far warmer at night
- Show the **hillshades**. Both are real data: NASADEM vs MOLA MEGDR, on the same
  500 m grid.
- In **Measurements and provenance**, every value carries a source-type badge:
  measured dataset, derived, literature, curated or physical constraint. Each
  also shows its dataset id, method and uncertainty.

## 5. Missing data is not a match (45 s)
- Go back to Mission, choose **Jezero**, and run the astrobiology preset.
- Coverage is 84 % and confidence is "medium". ASTRA holds no vetted surface
  temperature reference for Jezero, so the thermal features are listed under
  **Missing data** with the reason.
- The bounds widen accordingly.

## 6. Moon (30 s)
- Run **Artemis south-pole surface operations analog**.
- McMurdo Dry Valleys and Ladakh lead on terrain and hazards.
- The thermal score is near zero, because no Earth site has lunar polar
  temperatures.

## 7. Research agent (45 s)
- Open **Research agent** and ask: "Why is the Atacama similar to Gale crater?"
- Expand **tool calls** to show `calculate_similarity` and
  `explain_scientific_evidence`, each with validated inputs.
- Expand **sources**.
- Note the mode badge. Without an API key, the deterministic assistant uses the
  same tools. With `LLM_PROVIDER=anthropic`, Claude plans the tool calls, but
  can never compute scores itself.

## 8. Report (30 s)
- Open **Reports** and click **Generate PDF**.
- Walk through the report:
  - the ranking table
  - the evidence table with uncertainty intervals
  - the hillshades
  - data provenance with SHA-256 checksums and source URLs
  - methods, limitations and references

## 9. Close (15 s)
"Every number is reproducible from `datasets/` and the code in
`backend/science/`. Run `python -m pytest`; the full suite passes."
