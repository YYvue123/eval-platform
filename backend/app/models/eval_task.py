from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvalTask(Base):
    __tablename__ = "eval_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200))
    task_type: Mapped[str] = mapped_column(String(50), default="capability")
    scene: Mapped[str] = mapped_column(String(80), default="qa")
    industry: Mapped[str] = mapped_column(String(50), default="general")
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    dataset_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[int] = mapped_column(Integer, index=True)
    prompt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_resource_id: Mapped[str] = mapped_column(String(120), default="builtin/exact_match")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    skip_count: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float] = mapped_column(Float, default=0)
    pass_rate: Mapped[float] = mapped_column(Float, default=0)
    snapshot_id: Mapped[str] = mapped_column(String(64), default="")
    batch_id: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    report_summary: Mapped[str] = mapped_column(Text, default="")
    trial_run: Mapped[bool] = mapped_column(default=False)
    simulation: Mapped[bool] = mapped_column(default=False)
    model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_code: Mapped[str] = mapped_column(String(80), default="")
    priority: Mapped[int] = mapped_column(Integer, default=5)
    depends_on_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metric_weights_json: Mapped[str] = mapped_column(Text, default="{}")
    token_quota: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    report_path: Mapped[str] = mapped_column(String(500), default="")
    tool_version: Mapped[str] = mapped_column(String(40), default="")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    lease_owner: Mapped[str] = mapped_column(String(120), default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("eval_tasks.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_no: Mapped[int] = mapped_column(Integer, default=0)
    input_content: Mapped[str] = mapped_column(Text, default="")
    model_output: Mapped[str] = mapped_column(Text, default="")
    reference_answer: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0)
    passed: Mapped[bool] = mapped_column(default=False)
    metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    finish_reason: Mapped[str] = mapped_column(String(32), default="")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    execution_status: Mapped[str] = mapped_column(String(32), default="unknown")
    score_status: Mapped[str] = mapped_column(String(32), default="legacy_unverified")
    simulation: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class EvalLineage(Base):
    __tablename__ = "eval_lineages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    snapshot_id: Mapped[str] = mapped_column(String(64), default="")
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_resource_id: Mapped[str] = mapped_column(String(120), default="")
    tool_version: Mapped[str] = mapped_column(String(40), default="")
    trace_id: Mapped[str] = mapped_column(String(64), default="")
    parent_trace_id: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[str] = mapped_column(String(64), default="")
    channel_type: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityReport(Base):
    __tablename__ = "quality_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="done")
    score: Mapped[float] = mapped_column(Float, default=0)
    report_json: Mapped[str] = mapped_column(Text, default="{}")
    report_path: Mapped[str] = mapped_column(String(500), default="")
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class QualityRule(Base):
    __tablename__ = "quality_rules"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(32), default="completeness")
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="error")
    enabled: Mapped[bool] = mapped_column(default=True)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class QualityIssue(Base):
    __tablename__ = "quality_issues"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    dataset_id: Mapped[int] = mapped_column(Integer, index=True)
    version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_no: Mapped[int] = mapped_column(Integer, default=0)
    rule_code: Mapped[str] = mapped_column(String(64), default="")
    issue_type: Mapped[str] = mapped_column(String(32), default="")
    severity: Mapped[str] = mapped_column(String(20), default="error")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="open")
    handler: Mapped[str] = mapped_column(String(80), default="")
    handle_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvalServiceRequest(Base):
    __tablename__ = "eval_service_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(50), default="general")
    requirement: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    report_summary: Mapped[str] = mapped_column(Text, default="")
    quote_mode: Mapped[str] = mapped_column(String(20), default="auto")
    quote_amount: Mapped[float] = mapped_column(Float, default=0)
    quote_detail_json: Mapped[str] = mapped_column(Text, default="{}")
    workspace_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scene: Mapped[str] = mapped_column(String(80), default="chat")
    gray_version: Mapped[str] = mapped_column(String(40), default="")
    production_version: Mapped[str] = mapped_column(String(40), default="v1")
    shadow_json: Mapped[str] = mapped_column(Text, default="{}")
    report_path: Mapped[str] = mapped_column(String(500), default="")
    quote_version: Mapped[str] = mapped_column(String(40), default="")
    previous_stable: Mapped[str] = mapped_column(String(40), default="")
    delivery_settled: Mapped[bool] = mapped_column(default=False)
    traffic_pct: Mapped[float] = mapped_column(Float, default=0.0)
    shadow_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvalWorkspace(Base):
    __tablename__ = "eval_workspaces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    quota_tokens: Mapped[int] = mapped_column(Integer, default=100000)
    quota_calls: Mapped[int] = mapped_column(Integer, default=10000)
    used_tokens: Mapped[int] = mapped_column(Integer, default=0)
    used_calls: Mapped[int] = mapped_column(Integer, default=0)
    owner_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="shared")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LeaderboardWeight(Base):
    __tablename__ = "leaderboard_weights"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_type: Mapped[str] = mapped_column(String(32), default="overall")
    dim_key: Mapped[str] = mapped_column(String(80))
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class LeaderboardSnapshot(Base):
    __tablename__ = "leaderboard_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_type: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LeaderboardRelease(Base):
    """正式榜发布：不可变历史；回滚只切换 current 指针。"""
    __tablename__ = "leaderboard_releases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    board_type: Mapped[str] = mapped_column(String(32), index=True)
    cohort_id: Mapped[str] = mapped_column(String(200), default="")
    snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    scale_lo: Mapped[float | None] = mapped_column(Float, nullable=True)
    scale_hi: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="published")  # published|withdrawn
    is_current: Mapped[bool] = mapped_column(default=False)
    previous_release_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|rendering|validating|ready|failed
    formats_json: Mapped[str] = mapped_column(Text, default="{}")  # {json:{status,path,error},...}
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), default="scene")
    scene: Mapped[str] = mapped_column(String(80), default="chat")
    industry: Mapped[str] = mapped_column(String(50), default="general")
    task_type: Mapped[str] = mapped_column(String(50), default="capability")
    judge_resource_id: Mapped[str] = mapped_column(String(120), default="builtin/exact_match")
    metric_weights_json: Mapped[str] = mapped_column(Text, default="{}")
    default_prompt: Mapped[str] = mapped_column(Text, default="")
    rubric: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)



class BenchmarkSuite(Base):
    __tablename__ = "benchmark_suites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), default="text")
    template_code: Mapped[str] = mapped_column(String(80), default="")
    input_modality: Mapped[str] = mapped_column(String(32), default="text")
    oracle_type: Mapped[str] = mapped_column(String(32), default="reference")
    license: Mapped[str] = mapped_column(String(80), default="")
    calibration_report: Mapped[str] = mapped_column(String(120), default="")
    metrics_json: Mapped[str] = mapped_column(Text, default="[]")
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    readiness: Mapped[str] = mapped_column(String(20), default="draft")  # draft|ready|blocked
    blockers_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TaskEvent(Base):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TaskSubtask(Base):
    __tablename__ = "task_subtasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    shard_no: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    item_from: Mapped[int] = mapped_column(Integer, default=0)
    item_to: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AlertPolicy(Base):
    __tablename__ = "alert_policies"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    event_type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    enabled: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
