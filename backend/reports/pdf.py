"""Scientific PDF report generation with ReportLab.

Reports are built only from persisted discovery results, stored measurements and
dataset provenance, so every number in a report is reproducible from the
database. No LLM output is included.
"""

import uuid
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.data.ingest import analysis_grid
from backend.database.models import Dataset, DiscoveryRun, Report, Site
from backend.science.explain import fmt_value
from backend.science.features import FEATURES_BY_KEY
from backend.science.terrain import hillshade
from backend.services.discovery import NotFound, serialize_run

STYLES = getSampleStyleSheet()
SMALL = ParagraphStyle("small", parent=STYLES["BodyText"], fontSize=8, leading=10)
BODY = ParagraphStyle("body", parent=STYLES["BodyText"], fontSize=9.5, leading=12.5)
H1, H2, H3 = STYLES["Title"], STYLES["Heading2"], STYLES["Heading3"]
GRID_STYLE = TableStyle([
    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2a44")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
])


def p(text: str, style=BODY) -> Paragraph:
    return Paragraph(escape(str(text)), style)


def _num(v, nd=1):
    return "n/a" if v is None else f"{v:.{nd}f}"


def _hillshade_drawing(site_id: str, title: str, size: float = 70 * mm) -> Drawing:
    grid, info, meta = analysis_grid(site_id)
    shade = hillshade(grid, info["cell_m"])
    n = shade.shape[0]
    cell = size / n
    d = Drawing(size, size + 12)
    for r in range(n):
        for c in range(n):
            v = shade[r, c]
            fill = colors.Color(1, 0, 1) if v != v else colors.Color(v, v, v)
            d.add(Rect(c * cell, size - (r + 1) * cell, cell + 0.2, cell + 0.2,
                       fillColor=fill, strokeColor=None))
    d.add(String(0, size + 3, f"{title} - {meta['product']}", fontSize=6.5))
    return d


def _dimension_chart(dimensions: list[dict]) -> Drawing:
    d = Drawing(170 * mm, 45 * mm)
    chart = HorizontalBarChart()
    chart.x, chart.y, chart.width, chart.height = 35 * mm, 5 * mm, 125 * mm, 38 * mm
    chart.data = [[dim["score"] or 0 for dim in dimensions]]
    chart.categoryAxis.categoryNames = [
        f"{dim['label']} ({dim['weight']:.0%})" + ("" if dim["score"] is not None else " - no data")
        for dim in dimensions]
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.valueMin, chart.valueAxis.valueMax, chart.valueAxis.valueStep = 0, 100, 20
    chart.valueAxis.labels.fontSize = 7
    chart.bars[0].fillColor = colors.HexColor("#3b82f6")
    d.add(chart)
    return d


def build_report(db: Session, run_id: int, site_id: str | None = None,
                 report_id: str | None = None) -> Report:
    """Render a report PDF. With ``report_id`` of an existing report, re-render its
    file (e.g. after a serverless /tmp was wiped) without creating a new record."""
    run = db.get(DiscoveryRun, run_id)
    if run is None:
        raise NotFound(f"Discovery run {run_id} not found.")
    data = serialize_run(db, run)
    if not data["results"]:
        raise ValueError("Discovery run has no results.")
    focus = next((r for r in data["results"] if r["site_id"] == site_id), None) if site_id \
        else data["results"][0]
    if focus is None:
        raise NotFound(f"Site {site_id!r} is not part of run {run_id}.")
    target = data["target"]
    existing = db.get(Report, report_id) if report_id else None
    report_id = report_id or uuid.uuid4().hex[:16]
    settings.reports_dir.mkdir(parents=True, exist_ok=True)
    path = settings.reports_dir / f"astra-report-{report_id}.pdf"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    title = f"ASTRA analog report: {focus['name']} vs {target['name']}"

    story = [p(title, H1),
             p(f"Generated {now} | Mission: {data['mission_name']} (profile "
               f"{data['profile_key']}) | Discovery run #{run.id} | Scoring engine "
               f"v{data['engine_version']}", SMALL), Spacer(1, 6)]

    story += [p("1. Summary", H2), p(focus["explanation"]["summary"]),
              p("This report ranks Earth locations by the similarity of selected measurable "
                "properties to the target region. Scores are calculated deterministically "
                "from stored datasets. A high score does not certify a site as a "
                "mission-ready analog.", SMALL)]

    story += [p("2. Ranked candidates", H2)]
    rows = [["#", "Location", "Score", "Measurement range", "Bounds incl. missing",
             "Coverage", "Confidence"]]
    for r in data["results"]:
        rows.append([r["rank"], r["name"], _num(r["score"]),
                     f"{_num(r['score_low'])}-{_num(r['score_high'])}",
                     f"{_num(r['bound_low'])}-{_num(r['bound_high'])}",
                     f"{r['coverage']:.0%}", r["confidence"]])
    t = Table(rows, repeatRows=1, colWidths=[8 * mm, 55 * mm, 15 * mm, 28 * mm, 30 * mm,
                                             17 * mm, 20 * mm])
    t.setStyle(GRID_STYLE)
    story += [t, Spacer(1, 4),
              p("Weights: " + ", ".join(f"{k} {v:.0%}" for k, v in data["weights"].items()),
                SMALL)]

    story += [p(f"3. Evidence: {focus['name']}", H2), _dimension_chart(focus["dimensions"])]
    frows = [["Feature", "Candidate", "Target", "Similarity", "Status / note"]]
    for f in focus["features"]:
        spec = FEATURES_BY_KEY[f["key"]]
        if f["kind"] == "categorical":
            cv = ", ".join(f["candidate_tags"] or []) or ("none" if f["candidate_tags"] is not None else "missing")
            tv = ", ".join(f["target_tags"] or []) or ("none" if f["target_tags"] is not None else "missing")
        else:
            cv, tv = fmt_value(f["candidate_value"], spec.unit, spec.key), fmt_value(f["target_value"], spec.unit, spec.key)
        sim = "n/a" if f["similarity"] is None else (
            f"{f['similarity']:.2f}" + (f" [{f['similarity_low']:.2f}-{f['similarity_high']:.2f}]"
                                         if f["similarity_low"] != f["similarity_high"] else ""))
        note = f["missing_reason"] if f["status"] != "scored" else f"w={f['weight']:.3f}"
        frows.append([p(spec.label, SMALL), p(cv, SMALL), p(tv, SMALL), sim, p(note, SMALL)])
    ft = Table(frows, repeatRows=1, colWidths=[35 * mm, 38 * mm, 38 * mm, 25 * mm, 40 * mm])
    ft.setStyle(GRID_STYLE)
    story += [ft, Spacer(1, 6)]
    ex = focus["explanation"]
    for heading, key in (("Strengths", "strengths"), ("Partial matches", "partial"),
                         ("Mismatches", "mismatches"), ("Missing data", "missing")):
        if ex[key]:
            story += [p(heading, H3)] + [p("- " + s, SMALL) for s in ex[key]]

    try:
        pair = Table([[_hillshade_drawing(focus["site_id"], focus["name"]),
                       _hillshade_drawing(target["id"], target["name"])]])
        story += [KeepTogether([p("Terrain on the common 500 m analysis grid (hillshade, "
                                  "30 km windows)", H3), pair])]
    except (FileNotFoundError, KeyError) as exc:
        story += [p(f"Terrain images unavailable: {exc}", SMALL)]

    story += [PageBreak(), p("4. Data provenance", H2)]
    site_ids = [focus["site_id"], target["id"]]
    drows = [["Site", "Product", "Provider", "Retrieved", "SHA-256", "Source"]]
    for ds in db.scalars(select(Dataset).where(Dataset.site_id.in_(site_ids))):
        drows.append([ds.site_id, p(ds.product_id, SMALL), p(ds.provider, SMALL),
                      ds.retrieved_at[:10], ds.sha256[:12] + "...",
                      p(ds.source_url.split("?")[0][:160], SMALL)])
    dt = Table(drows, repeatRows=1, colWidths=[30 * mm, 30 * mm, 30 * mm, 18 * mm, 22 * mm, 50 * mm])
    dt.setStyle(GRID_STYLE)
    story += [dt, Spacer(1, 4)]
    for ds in db.scalars(select(Dataset).where(Dataset.site_id.in_(site_ids))):
        for note in ds.notes:
            story.append(p(f"{ds.id}: {note}", SMALL))
        story.append(p(f"Attribution ({ds.id}): {ds.attribution}", SMALL))

    story += [p("5. Methods", H2),
              p("Terrain is resampled to a common 60 x 60 grid of 500 m cells (30 km window). "
                "Slope, terrain ruggedness index (TRI), local relief (p95-p5) and the "
                "steep-slope fraction (>15 deg) are computed on this grid. Continuous "
                "features use a Gaussian similarity exp(-0.5 (d/scale)^2) with fixed, "
                "documented scales, some in log space. Curated tags use the Jaccard index. "
                "Score = 100 x sum(w s) / sum(w) over features available for both sites. "
                "Missing features are excluded and reported through coverage and bounds. "
                "Full details are in docs/SCIENCE.md.", SMALL),
              p("6. Limitations", H2)]
    story += [p("- " + s, SMALL) for s in data["limitations"]]
    refs = []
    for sid in site_ids:
        site = db.get(Site, sid)
        refs += [r["citation"] for r in site.references]
    if refs:
        story += [p("7. References", H2)] + [p(r, SMALL) for r in dict.fromkeys(refs)]

    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title, author="ASTRA",
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)
    doc.build(story)
    if existing is not None:
        existing.file_path, existing.size_bytes = str(path), path.stat().st_size
        db.commit()
        return existing
    report = Report(id=report_id, run_id=run.id, site_id=focus["site_id"], title=title,
                    file_path=str(path), size_bytes=path.stat().st_size)
    db.add(report)
    db.commit()
    return report
