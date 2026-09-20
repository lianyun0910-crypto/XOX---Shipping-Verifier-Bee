from pathlib import Path
import shutil
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .analyzer import analyze_uploaded_batch
from .gmail_bridge import router as gmail_router
from .review_store import enqueue_reviews, get_review, list_reviews, resolve_review
from .storage import (
    append_history,
    archive_run_to_cloud,
    clear_history,
    cloud_storage_enabled,
    get_excel_cloud_url,
    get_history,
    list_history,
)

app = FastAPI(title="Shipping Verifier", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(gmail_router)

BASE_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
RECORD_DIR = BASE_DIR / "data" / "records"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RECORD_DIR.mkdir(parents=True, exist_ok=True)

JOBS: dict[str, dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def update_job(job_id: str, **updates):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(updates)


def get_job_payload(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        payload = dict(job)
        payload.pop("paths", None)
        payload["results"] = list(job.get("results", []))
        return payload


def make_progress_callback(job_id: str):
    def callback(processed: int, total: int, result: Any, phase: str):
        current = result.get("filename", "") if isinstance(result, dict) else ""
        update_job(
            job_id,
            processed_cases=processed,
            total_cases=total,
            phase=phase,
            progress=round(processed / total * 100) if total else 0,
            current_filename=current,
        )
        if isinstance(result, dict):
            with JOBS_LOCK:
                if job_id not in JOBS:
                    return
                live = JOBS[job_id].setdefault("results", [])
                live.append(result)
                JOBS[job_id]["ok"] = sum(x.get("status") == "OK" for x in live)
                JOBS[job_id]["mismatch"] = sum(x.get("status") == "MISMATCH" for x in live)
                JOBS[job_id]["needs_review"] = sum(x.get("status") == "NEEDS_REVIEW" for x in live)
    return callback


def run_analysis_job(job_id: str, paths: list[Path]):
    update_job(job_id, status="PROCESSING", phase="processing", started_at=utc_now())
    try:
        final = analyze_uploaded_batch(paths, make_progress_callback(job_id))
        summary = final["summary"]
        results = final["results"]
        run_id = final["run_id"]

        update_job(job_id, phase="saving_history")
        history = append_history(run_id, "upload", results, summary)
        review_cases = enqueue_reviews(run_id, "upload", results)

        try:
            update_job(job_id, phase="cloud_archive")
            cloud_archive = archive_run_to_cloud(run_id, results, summary, paths, source="upload")
        except Exception as exc:
            cloud_archive = {"enabled": True, "uploaded": False, "error": str(exc)}

        update_job(
            job_id,
            status="COMPLETED",
            phase="completed",
            progress=100,
            processed_cases=summary["total"],
            total_cases=summary["total"],
            total_files=len(paths),
            ok=summary["ok"],
            mismatch=summary["mismatch"],
            needs_review=summary["needs_review"],
            results=results,
            summary=summary,
            excel=final.get("excel"),
            history=history,
            review_cases=review_cases,
            cloud_archive=cloud_archive,
            run_id=run_id,
            completed_at=utc_now(),
            current_filename="",
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        update_job(job_id, status="ERROR", phase="error", error=str(exc), completed_at=utc_now())


@app.get("/api/health")
def health():
    with JOBS_LOCK:
        active = sum(1 for job in JOBS.values() if job.get("status") in {"QUEUED", "PROCESSING"})
    return {
        "status": "ok",
        "service": "shipping-verifier",
        "cloud_storage": cloud_storage_enabled(),
        "active_jobs": active,
    }


@app.post("/api/analyze/upload-batch")
async def analyze_upload_batch(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")
    job_id = uuid.uuid4().hex
    saved_paths: list[Path] = []
    try:
        for upload in files:
            original_name = Path(upload.filename or "uploaded_file").name
            destination = UPLOAD_DIR / f"{uuid.uuid4().hex}_{original_name}"
            with destination.open("wb") as output:
                shutil.copyfileobj(upload.file, output)
            saved_paths.append(destination)

        with JOBS_LOCK:
            JOBS[job_id] = {
                "job_id": job_id,
                "status": "QUEUED",
                "phase": "queued",
                "progress": 0,
                "total_files": len(saved_paths),
                "total_cases": 0,
                "processed_cases": 0,
                "ok": 0,
                "mismatch": 0,
                "needs_review": 0,
                "results": [],
                "summary": None,
                "excel": None,
                "history": None,
                "review_cases": [],
                "cloud_archive": None,
                "error": "",
                "current_filename": "",
                "created_at": utc_now(),
                "started_at": None,
                "completed_at": None,
                "paths": saved_paths,
            }

        threading.Thread(target=run_analysis_job, args=(job_id, saved_paths), daemon=True).start()
        return {"job_id": job_id, "status": "QUEUED", "total_files": len(saved_paths)}
    except Exception as exc:
        for path in saved_paths:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
        raise HTTPException(status_code=500, detail=f"Unable to create analysis job: {exc}")


@app.get("/api/analyze/status/{job_id}")
def analyze_status(job_id: str):
    payload = get_job_payload(job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Analysis job not found.")
    return payload


@app.get("/api/history")
def history(limit: int = 100):
    return {"items": list_history(limit)}


@app.get("/api/history/{run_id}")
def history_detail(run_id: str):
    entry = get_history(run_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="History record not found.")
    return entry


@app.delete("/api/history")
def clear_history_endpoint():
    clear_history()
    return {"status": "ok"}


@app.get("/api/review-queue")
def review_queue(status: str = "OPEN", limit: int = 100):
    return {"items": list_reviews(status, limit)}


@app.get("/api/review-queue/{case_id}")
def review_queue_detail(case_id: str):
    case = get_review(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Review case not found.")
    return case


@app.post("/api/review-queue/{case_id}")
def review_queue_resolve(case_id: str, payload: dict):
    decision = str(payload.get("decision") or "").strip()
    reviewer = str(payload.get("reviewer") or "local-operator").strip()
    note = str(payload.get("note") or "").strip()
    try:
        return resolve_review(case_id, decision, reviewer, note)
    except KeyError:
        raise HTTPException(status_code=404, detail="Review case not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/api/excel")
def download_excel():
    path = RECORD_DIR / "shipping_verification_audit.xlsx"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel report does not exist yet.")
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/api/excel/cloud-url")
def cloud_excel_url():
    if not cloud_storage_enabled():
        return {"enabled": False, "cloud_url": None, "message": "Cloud storage is not configured."}
    try:
        url = get_excel_cloud_url()
    except Exception as exc:
        return {"enabled": True, "cloud_url": None, "message": str(exc)}
    return {"enabled": True, "cloud_url": url, "message": None if url else "Excel report is not available yet."}
