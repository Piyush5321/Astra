"""AI research agent and scientific report endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.agents import agent
from backend.api.schemas import ChatRequest, ReportRequest
from backend.database.models import Report
from backend.database.session import get_db
from backend.reports.pdf import build_report
from backend.services.discovery import NotFound

router = APIRouter(prefix="/api", tags=["agent", "reports"])


@router.get("/agent/status")
def agent_status() -> dict:
    return agent.status()


@router.post("/agent/chat")
def agent_chat(body: ChatRequest, db: Session = Depends(get_db)) -> dict:
    reply = agent.chat(db, body.message, [t.model_dump() for t in body.history], body.context)
    return {"answer": reply.answer, "mode": reply.mode, "tool_calls": reply.tool_calls,
            "sources": reply.sources, "notice": reply.notice}


def report_dict(r: Report) -> dict:
    return {"id": r.id, "run_id": r.run_id, "site_id": r.site_id, "title": r.title,
            "size_bytes": r.size_bytes, "created_at": r.created_at.isoformat(),
            "download_url": f"/api/reports/{r.id}/pdf"}


@router.post("/reports/generate", status_code=201)
def generate_report(body: ReportRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return report_dict(build_report(db, body.run_id, body.site_id))
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/reports")
def list_reports(db: Session = Depends(get_db)) -> list[dict]:
    return [report_dict(r) for r in db.scalars(select(Report).order_by(Report.created_at.desc()))]


@router.get("/reports/{report_id}")
def get_report(report_id: str, db: Session = Depends(get_db)) -> dict:
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, f"Report {report_id!r} not found.")
    return report_dict(r)


@router.get("/reports/{report_id}/pdf")
def download_report(report_id: str, download: bool = False, db: Session = Depends(get_db)):
    r = db.get(Report, report_id)
    if r is None:
        raise HTTPException(404, f"Report {report_id!r} not found.")
    if not Path(r.file_path).exists():
        # Ephemeral storage (serverless /tmp) was cleared: reports are
        # deterministic, so rebuild the PDF from the stored run.
        try:
            r = build_report(db, r.run_id, r.site_id, report_id=r.id)
        except (NotFound, ValueError) as exc:
            raise HTTPException(404, str(exc)) from exc
    # Send the whole (small, ~100 KB) PDF in one body: Vercel's Python runtime
    # drops streamed file responses, delivering headers with an empty body.
    disposition = "attachment" if download else "inline"
    return Response(Path(r.file_path).read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f'{disposition}; filename="{Path(r.file_path).name}"'})
