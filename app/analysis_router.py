"""Dedicated registration for existing Analysis Workbench GET routes."""

from fastapi import APIRouter, FastAPI
from fastapi.responses import HTMLResponse


ANALYSIS_GET_ROUTES = (
    ("/projects/{project_id}/workspace", "workspace"),
    ("/projects/{project_id}/workspace/entries", "entries"),
    ("/projects/{project_id}/workspace/coding", "coding"),
    ("/projects/{project_id}/workspace/matrices", "matrices"),
    ("/projects/{project_id}/workspace/longitudinal", "longitudinal"),
    ("/studies/{study_id}/memos", "memos"),
    ("/studies/{study_id}/relationships", "relationships"),
    ("/projects/{project_id}/workspace/participants", "participants"),
    ("/projects/{project_id}/workspace/evidence", "evidence"),
    ("/evidence/{evidence_id}/analysis", "image_analysis"),
    ("/projects/{project_id}/workspace/themes", "themes"),
    ("/studies/{study_id}/codebook", "codebook"),
    ("/projects/{project_id}/workspace/analysis", "analysis"),
    ("/projects/{project_id}/workspace/ask-ai", "ask_ai"),
    ("/projects/{project_id}/workspace/audit", "audit"),
    ("/projects/{project_id}/workspace/export", "export"),
    ("/studies/{study_id}/theme-explorer", "theme_explorer"),
)


def include_analysis_router(app: FastAPI, endpoints: dict[str, object]) -> None:
    router = APIRouter(tags=["analysis-workbench"])
    for path, name in ANALYSIS_GET_ROUTES:
        router.add_api_route(
            path, endpoints[name], methods=["GET"], response_class=HTMLResponse
        )
    app.include_router(router)
