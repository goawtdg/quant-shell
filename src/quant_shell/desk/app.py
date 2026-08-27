"""quant-shell Desk FastAPI — 本仓决策台 API。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from quant_shell.adapters.desk import (
    desk_health,
    desk_plugin_payload,
    desk_studio_compile,
    desk_studio_get,
    desk_studio_save,
)
from quant_shell.config.env_loader import load_env_file, project_root
from quant_shell.desk import factors as factors_api
from quant_shell.desk import jobs as jobs_api
from quant_shell.desk import paper_orders as paper_orders_api
from quant_shell.desk import services
from quant_shell.desk.loaders import load_equity_history
from quant_shell.orchestrator.linkage_report import (
    delete_linkage_report as _delete_linkage_report,
    list_linkage_reports as _list_linkage_reports,
    load_linkage_report,
    require_report_artifact,
)

load_env_file()

app = FastAPI(title="quant-shell Desk API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskBody(BaseModel):
    question: str = Field(..., min_length=1)


class NoteBody(BaseModel):
    note: str = ""


class JobStartBody(BaseModel):
    type: str = Field(..., description="shell_paper | linkage")
    params: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class FactorPatchBody(BaseModel):
    status: str = Field(..., description="active | degraded | disabled")
    reason: str = Field(..., min_length=1)


class FactorCreateBody(BaseModel):
    scope: str = Field(..., pattern="^(etf|stock)$")
    name: str = Field(..., min_length=1, max_length=64)
    expression: str = Field(..., min_length=3)
    description: str = ""
    category: str = "composite"
    weight: float = 0.05


class PaperOrderBody(BaseModel):
    symbol: str = Field(..., min_length=6, max_length=6)
    action: str = Field(..., description="BUY|SELL|REDUCE|EXIT")
    quantity: float = Field(..., gt=0)
    reason: str = Field(..., min_length=1)
    confirm: bool = False
    run_id: str = ""
    sleeve: str = "catalyst"


class StudioCompileBody(BaseModel):
    idea: str = Field(..., min_length=2, max_length=2000)


class StudioSaveBody(BaseModel):
    model: dict[str, Any]


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok", "framework": "quant-shell"}


@app.get("/api/v1/shell/health")
def shell_health() -> dict:
    payload = desk_health()
    payload["available"] = True
    return payload


@app.get("/api/v1/shell/plugins")
def shell_plugins() -> dict:
    payload = desk_plugin_payload()
    payload["available"] = True
    return payload


@app.get("/api/v1/studio/model")
def studio_get() -> dict:
    payload = desk_studio_get()
    payload["available"] = True
    return payload


@app.post("/api/v1/studio/compile")
def studio_compile(body: StudioCompileBody) -> dict:
    try:
        payload = desk_studio_compile(body.idea)
        payload["available"] = True
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/v1/studio/model")
def studio_save(body: StudioSaveBody) -> dict:
    try:
        payload = desk_studio_save(body.model)
        payload["available"] = True
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/v1/reports/linkage")
def reports_linkage(run_id: str | None = Query(None)) -> dict:
    try:
        report = load_linkage_report(run_id)
        if report is None:
            raise FileNotFoundError(f"report not found: {run_id or 'latest'}")
        return report
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/reports/linkage/list")
def reports_linkage_list(limit: int = Query(40, ge=1, le=100)) -> dict:
    return _list_linkage_reports(limit=limit)


@app.delete("/api/v1/reports/linkage/{run_id}")
def reports_linkage_delete(run_id: str) -> dict:
    try:
        return _delete_linkage_report(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/v1/reports/linkage.pdf")
def reports_linkage_pdf(run_id: str | None = Query(None)):
    try:
        path = require_report_artifact(run_id, ".pdf")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rid = run_id or path.stem
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"linkage_report_{rid}.pdf",
        content_disposition_type="attachment",
    )


@app.get("/api/v1/reports/linkage.html")
def reports_linkage_html(run_id: str | None = Query(None)):
    try:
        path = require_report_artifact(run_id, ".html")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    rid = run_id or path.stem
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        filename=f"linkage_report_{rid}.html",
    )


@app.get("/api/v1/dashboard/overview")
def dashboard_overview(
    live: bool = Query(False),
    runs_limit: int = Query(40, ge=1, le=100),
) -> dict:
    return services.build_overview(live=live, runs_limit=runs_limit)


@app.get("/api/v1/dashboard/snapshot")
def dashboard_snapshot(live: bool = Query(False)) -> dict:
    return services.build_snapshot(live=live)


@app.get("/api/v1/decisions")
def decisions(
    tab: str = Query("hold", pattern="^(etf|hold|stock)$"),
    decision_filter: str = Query("all", alias="filter", pattern="^(all|buyable|executed|manual)$"),
    run_id: str | None = Query(None),
) -> dict:
    result = services.build_decisions(tab=tab, filter_name=decision_filter, run_id=run_id)
    if result.get("error") == "run_not_found":
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return result


@app.get("/api/v1/positions")
def positions(live: bool = Query(False)) -> dict:
    return services.build_positions(live=live)


@app.get("/api/v1/positions/{code}/ohlcv")
def position_ohlcv(code: str, limit: int = Query(120, ge=20, le=500)) -> dict:
    return services.build_ohlcv(code, limit=limit)


@app.put("/api/v1/positions/{code}/note")
def position_note(code: str, body: NoteBody) -> dict:
    return services.update_note(code, body.note)


@app.post("/api/v1/paper/orders")
def paper_orders(body: PaperOrderBody) -> dict:
    try:
        return paper_orders_api.place_manual_order(
            symbol=body.symbol,
            action=body.action,
            quantity=body.quantity,
            reason=body.reason,
            confirm=body.confirm,
            run_id=body.run_id,
            sleeve=body.sleeve,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/runs")
def runs() -> dict:
    return services.build_runs()


@app.get("/api/v1/runs/diff")
def runs_diff(base_run_id: str | None = None) -> dict:
    return services.build_run_diff(base_run_id)


@app.post("/api/v1/assistant/ask")
def assistant_ask(body: AskBody) -> dict:
    return services.ask_assistant(body.question)


@app.get("/api/v1/equity/history")
def equity_history(limit: int = Query(60, ge=1, le=365)) -> dict:
    return {"rows": load_equity_history(limit=limit)}


@app.get("/api/v1/audit/tail")
def audit_tail(max_lines: int = Query(80, ge=1, le=500)) -> dict:
    from quant_shell.common.audit import AUDIT_DIR

    events: list[dict[str, Any]] = []
    if AUDIT_DIR.is_dir():
        files = sorted(AUDIT_DIR.glob("*.jsonl"), reverse=True)
        for path in files[:3]:
            for line in reversed(path.read_text(encoding="utf-8", errors="replace").splitlines()):
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(events) >= max_lines:
                    break
            if len(events) >= max_lines:
                break
    events.reverse()
    return {"events": events[-max_lines:]}


@app.get("/api/v1/jobs")
def jobs_list(limit: int = Query(10, ge=1, le=50)) -> dict:
    return jobs_api.list_jobs(limit=limit)


@app.post("/api/v1/jobs")
def jobs_start(body: JobStartBody) -> dict:
    try:
        return jobs_api.start_job(body.type, body.params, confirm=body.confirm)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/jobs/{job_id}")
def jobs_get(job_id: str, log_lines: int = Query(120, ge=20, le=500)) -> dict:
    meta = jobs_api.get_job(job_id, log_lines=log_lines)
    if not meta:
        raise HTTPException(status_code=404, detail="job not found")
    return meta


@app.post("/api/v1/jobs/{job_id}/cancel")
def jobs_cancel(job_id: str) -> dict:
    try:
        return jobs_api.cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc


@app.get("/api/v1/factors")
def factors_list(scope: str = Query("etf", pattern="^(etf|stock)$")) -> dict:
    try:
        return factors_api.list_factors(scope)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/v1/factors/{scope}/{name}")
def factors_patch(scope: str, name: str, body: FactorPatchBody) -> dict:
    try:
        return factors_api.update_factor_status(scope, name, body.status, body.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"factor not found: {name}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/factors")
def factors_create(body: FactorCreateBody) -> dict:
    try:
        return factors_api.create_plugin_factor(
            scope=body.scope,
            name=body.name,
            expression=body.expression,
            description=body.description,
            category=body.category,
            weight=body.weight,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/factors/{scope}/{name}")
def factors_delete(scope: str, name: str) -> dict:
    try:
        return factors_api.delete_plugin_factor(scope, name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"plugin not found: {name}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def create_app() -> FastAPI:
    return app
