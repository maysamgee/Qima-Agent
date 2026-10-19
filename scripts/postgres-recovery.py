"""Non-destructive PostgreSQL recovery demonstration. Adds a fictional job and audit history."""
import subprocess
import sys
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

from app.auth import Actor
from app.config import get_settings
from app.database import get_engine, session_factory
from app.models import Candidate, CandidateEvidence, ScoringResult, SearchJob, SearchJobStep
from app.schemas import SearchRequest
from app.workflow.discovery import create_job, process_job

if get_engine().dialect.name != "postgresql":
    raise SystemExit("This check requires the local PostgreSQL database")
settings = get_settings()
url = make_url(settings.database_url)
if settings.app_env not in {"local", "test"} or url.host not in {"localhost", "127.0.0.1"}:
    raise SystemExit("Recovery demonstration is restricted to local PostgreSQL")
schema = "qima_recovery_" + uuid4().hex
with get_engine().begin() as connection:
    connection.execute(text(f'CREATE SCHEMA "{schema}"'))
os.environ["DATABASE_URL"] = url.update_query_dict({"options":f"-csearch_path={schema}"}).render_as_string(hide_password=False)
get_engine().dispose()
get_engine.cache_clear()
get_settings.cache_clear()
repo = Path(__file__).resolve().parent.parent
subprocess.run([sys.executable,"-m","alembic","upgrade","head"],cwd=repo / "backend",check=True)
from app.scoring import seed_policies
with session_factory()() as db:
    seed_policies(db)
    db.commit()
with session_factory()() as db:
    job = create_job(db, SearchRequest(agent_type="SOURCING", query="Recovery test: Ethiopian producers", country="Ethiopia"), Actor("recovery-test", "Recovery test", {"ADMIN"}), str(uuid4()))
    db.commit()
    job_id = job.id
code = "from app.workflow.discovery import process_job; import sys; process_job(sys.argv[1], fail_after_step='deduplication')"
result = subprocess.run([sys.executable, "-c", code, job_id], cwd=repo / "backend", capture_output=True)
assert result.returncode != 0, "Injected process termination did not occur"
assert process_job(job_id, f"recovery:{job_id}:1")
assert process_job(job_id, f"recovery:{job_id}:2")
with session_factory()() as db:
    job = db.get(SearchJob, job_id)
    steps = {s.name: s.retry_count for s in db.scalars(select(SearchJobStep).where(SearchJobStep.job_id == job_id))}
    assert job.status == "PARTIAL"
    assert steps["initial_discovery"] == 1 and steps["deduplication"] == 1
    print({"retained_test_schema":schema,"job_id": job_id, "status": job.status, "completed_step_not_repeated": True, "duplicate_delivery_safe": True, "candidates": db.scalar(select(func.count(Candidate.id))), "evidence": db.scalar(select(func.count(CandidateEvidence.id))), "scores": db.scalar(select(func.count(ScoringResult.id)))})
