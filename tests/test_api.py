"""API routes, agent tools and report generation (LLM disabled -> deterministic agent)."""

import pytest

from backend.agents.tools import run_tool, tool_schemas


def test_health_reports_database(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy" and body["database"]["status"] == "ok"
    assert body["llm_enabled"] is False


def test_openapi_and_frontend_served(client):
    assert client.get("/openapi.json").status_code == 200
    r = client.get("/")
    assert r.status_code == 200 and "ASTRA" in r.text
    js = client.get("/js/app.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    assert int(js.headers["content-length"]) == len(js.content) > 0
    assert client.get("/css/style.css").headers["content-type"].startswith("text/css")
    assert client.get("/../backend/config.py").status_code == 404
    assert client.get("/missing.js").status_code == 404
    assert client.get("/api/nope").status_code == 404


def test_locations_and_targets(client):
    locs = client.get("/api/locations").json()
    assert len(locs) == 8 and all(l["role"] == "candidate" for l in locs)
    assert {l["id"] for l in client.get("/api/locations?tag=evaporite").json()} >= {
        "atacama-yungay", "rann-of-kutch"}
    targets = client.get("/api/targets?body=mars").json()
    assert {t["id"] for t in targets} == {"mars-jezero", "mars-gale", "mars-meridiani"}
    assert client.get("/api/targets?body=venus").status_code == 422


def test_location_detail_has_provenance(client):
    d = client.get("/api/location/atacama-yungay").json()
    assert d["datasets"] and d["measurements"]
    tmax = next(m for m in d["measurements"] if m["feature_key"] == "surface_temp_max_k")
    assert tmax["source_type"] == "measured_dataset" and tmax["dataset_id"] == "power:atacama-yungay"
    assert client.get("/api/location/nowhere").status_code == 404


def test_terrain_grid(client):
    t = client.get("/api/location/mars-gale/terrain").json()
    assert t["info"]["size"] == 60 and len(t["elevation"]) == 60


def test_reference(client):
    ref = client.get("/api/reference").json()
    assert set(ref["dimensions"]) == {"geology", "terrain", "thermal", "resources", "hazards"}
    assert "isru" in ref["profiles"]


def test_mission_create_validation(client):
    ok = client.post("/api/missions", json={
        "name": "Custom Gale test", "target_site_id": "mars-gale",
        "weights": {"terrain": 3, "hazards": 1}})
    assert ok.status_code == 201
    body = ok.json()
    assert body["profile_key"] == "custom" and body["weights"]["terrain"] == pytest.approx(0.75)
    bad = client.post("/api/missions", json={"name": "Bad", "target_site_id": "mars-gale",
                                             "weights": {"gravity": 1}})
    assert bad.status_code == 422
    not_target = client.post("/api/missions", json={"name": "Bad target",
                                                    "target_site_id": "atacama-yungay"})
    assert not_target.status_code == 422


def _mission_id(client, target):
    return next(m["id"] for m in client.get("/api/missions").json()
                if m["target_site_id"] == target and m["is_preset"])


@pytest.mark.parametrize("target", ["moon-apollo11-tranquillitatis", "mars-gale"])
def test_discovery_workflow_moon_and_mars(client, target):
    mid = _mission_id(client, target)
    run = client.post("/api/discovery/run", json={"mission_id": mid})
    assert run.status_code == 201
    data = run.json()
    assert data["target"]["id"] == target and len(data["results"]) == 8
    scores = [r["score"] for r in data["results"]]
    assert scores == sorted(scores, reverse=True)
    top = data["results"][0]
    assert top["bound_low"] <= top["score_low"] <= top["score"] <= top["score_high"] <= top["bound_high"]
    assert data["limitations"]
    again = client.get(f"/api/discovery/results/{data['id']}").json()
    assert again["results"][0]["score"] == top["score"]
    # Determinism: a second run gives identical scores.
    rerun = client.post("/api/discovery/run", json={"mission_id": mid}).json()
    assert [r["score"] for r in rerun["results"]] == scores


def test_compare_and_errors(client):
    r = client.post("/api/analysis/compare", json={"candidate_id": "atacama-yungay",
                                                   "target_id": "mars-meridiani",
                                                   "profile_key": "astrobiology"})
    assert r.status_code == 200
    body = r.json()
    assert 0 < body["coverage"] < 1  # Meridiani thermal values are missing
    assert body["explanation"]["missing"]
    swapped = client.post("/api/analysis/compare", json={"candidate_id": "mars-meridiani",
                                                         "target_id": "atacama-yungay"})
    assert swapped.status_code == 422
    assert client.post("/api/discovery/results/999999").status_code == 405
    assert client.get("/api/discovery/results/999999").status_code == 404


def test_reports_generate_and_download(client):
    mid = _mission_id(client, "mars-jezero")
    run = client.post("/api/discovery/run", json={"mission_id": mid}).json()
    rep = client.post("/api/reports/generate", json={"run_id": run["id"]})
    assert rep.status_code == 201
    meta = rep.json()
    pdf = client.get(meta["download_url"])
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
    assert client.get(f"/api/reports/{meta['id']}").json()["run_id"] == run["id"]
    assert client.post("/api/reports/generate", json={"run_id": run["id"],
                                                      "site_id": "mars-gale"}).status_code == 404


def test_agent_deterministic_modes(client):
    mid = _mission_id(client, "mars-gale")
    run = client.post("/api/discovery/run", json={"mission_id": mid}).json()
    ctx = {"run_id": run["id"], "target_id": "mars-gale"}
    r = client.post("/api/agent/chat", json={"message": "What are the top candidates?",
                                             "context": ctx}).json()
    assert r["mode"] == "deterministic" and r["notice"]
    assert any(c["tool"] == "get_discovery_results" for c in r["tool_calls"])
    r = client.post("/api/agent/chat", json={
        "message": "Why is the Atacama similar to Gale?", "context": ctx}).json()
    assert {c["tool"] for c in r["tool_calls"]} == {"calculate_similarity",
                                                    "explain_scientific_evidence"}
    assert "Score" in r["answer"] and r["sources"]
    # Within a run's context the agent must use the run's weights (same score as the ranking).
    atacama = next(x for x in run["results"] if x["site_id"] == "atacama-yungay")
    assert f"Score {atacama['score']:.1f}/100" in r["answer"]
    # Generic words ("crater") must not resolve to the wrong sites.
    r = client.post("/api/agent/chat", json={
        "message": "Why is the Atacama similar to Gale crater?", "context": {}}).json()
    assert r["tool_calls"][0]["input"]["candidate_id"] == "atacama-yungay"
    assert r["tool_calls"][0]["input"]["target_id"] == "mars-gale"
    r = client.post("/api/agent/chat", json={"message": "Show terrain slope for Lonar crater",
                                             "context": ctx}).json()
    assert r["tool_calls"][0]["tool"] == "analyze_terrain"
    r = client.post("/api/agent/chat", json={"message": "climate at Wright Valley",
                                             "context": ctx}).json()
    assert r["tool_calls"][0]["tool"] == "get_climate_data"
    bad = client.post("/api/agent/chat", json={"message": "hi", "context": {"evil": 1}})
    assert bad.status_code == 422


def test_tool_validation_rejects_bad_input(db):
    assert {t["name"] for t in tool_schemas()} >= {"calculate_similarity", "analyze_terrain"}
    assert not run_tool(db, "analyze_terrain", {"site_id": "x; DROP TABLE"}).ok
    assert not run_tool(db, "analyze_terrain", {"site_id": "lonar-crater", "extra": 1}).ok
    assert not run_tool(db, "nonexistent", {}).ok
    assert not run_tool(db, "calculate_similarity", {"candidate_id": "lonar-crater",
                                                     "target_id": "mars-gale",
                                                     "profile_key": "made-up"}).ok
    ok = run_tool(db, "calculate_similarity", {"candidate_id": "lonar-crater",
                                               "target_id": "mars-gale"})
    assert ok.ok and ok.data["score"] is not None
