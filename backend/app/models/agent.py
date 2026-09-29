"""编排 Agent 与经验知识库（不是调度主链路）。"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class KnowledgeEntry(Base):
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), default="case")  # template|case|exception|profile
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    ref_type: Mapped[str] = mapped_column(String(32), default="")
    ref_id: Mapped[str] = mapped_column(String(64), default="")
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    review_status: Mapped[str] = mapped_column(String(20), default="approved")  # approved|pending|rejected
    valid_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentSession(Base):
    __tablename__ = "agent_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    requirement: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="planning")
    plan_json: Mapped[str] = mapped_column(Text, default="{}")
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default="private")
    active_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=0)
    planner_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    role: Mapped[str] = mapped_column(String(20), default="main")  # user|main|monitor|diagnose|system
    content: Mapped[str] = mapped_column(Text, default="")
    tool_name: Mapped[str] = mapped_column(String(80), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentSuggestion(Base):
    __tablename__ = "agent_suggestions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(32), default="retry")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|running|waiting|success|failed|cancelled|paused_budget
    graph_version: Mapped[str] = mapped_column(String(32), default="runtime-v1")
    provider: Mapped[str] = mapped_column(String(20), default="live")  # live only
    planner_model_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checkpoint_json: Mapped[str] = mapped_column(Text, default="{}")
    checkpoint_thread_id: Mapped[str] = mapped_column(String(64), default="", unique=True)
    lease_owner: Mapped[str] = mapped_column(String(120), default="")
    lease_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fencing_token: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    max_rounds: Mapped[int] = mapped_column(Integer, default=8)
    rounds_used: Mapped[int] = mapped_column(Integer, default=0)
    token_budget: Mapped[int] = mapped_column(Integer, default=0)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(64), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    event_seq: Mapped[int] = mapped_column(Integer, default=0)
    row_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentEvent(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    type: Mapped[str] = mapped_column(String(64), default="")
    step_id: Mapped[str] = mapped_column(String(64), default="")
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    plan_hash: Mapped[str] = mapped_column(String(64), default="")
    action_hash: Mapped[str] = mapped_column(String(64), default="")
    scope_json: Mapped[str] = mapped_column(Text, default="{}")
    plan_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="approved")  # approved|consumed|expired|invalidated|revoked
    approver_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consumed_invocation_id: Mapped[str] = mapped_column(String(64), default="")
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AgentDelegation(Base):
    __tablename__ = "agent_delegations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(Integer, index=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parent_delegation_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="monitor")  # monitor|diagnose|review|analysis
    depth: Mapped[int] = mapped_column(Integer, default=1)
    context_hash: Mapped[str] = mapped_column(String(64), default="")
    budget_slice: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running|success|failed|skipped|escalated
    result_json: Mapped[str] = mapped_column(Text, default="{}")
    evidence_json: Mapped[str] = mapped_column(Text, default="[]")
    error_code: Mapped[str] = mapped_column(String(64), default="")
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentMonitorState(Base):
    __tablename__ = "agent_monitor_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    task_id: Mapped[int] = mapped_column(Integer, index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_event_seq: Mapped[int] = mapped_column(Integer, default=0)
    last_summary_hash: Mapped[str] = mapped_column(String(64), default="")
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    last_llm_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class KnowledgeCandidate(Base):
    __tablename__ = "knowledge_candidates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    source_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_hash: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="case")
    title: Mapped[str] = mapped_column(String(200), default="")
    claim_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|approved|rejected
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    entry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AgentDefinition(Base):
    """自定义子 Agent。内置角色不入库，由目录服务合并。"""

    __tablename__ = "agent_definitions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    max_iterations: Mapped[int] = mapped_column(Integer, default=6)
    supports_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    human_in_the_loop: Mapped[bool] = mapped_column(Boolean, default=True)
    available_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    skill_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    model_config_json: Mapped[str] = mapped_column(Text, default="{}")
    evaluation_spec_json: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrchestrationProfile(Base):
    """主 Agent 描述符。每个租户一行，页面顶部可查看和修改。"""

    __tablename__ = "orchestration_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(32), default="coordinator")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    model_config_json: Mapped[str] = mapped_column(Text, default="{}")
    available_tools_json: Mapped[str] = mapped_column(Text, default="[]")
    max_iterations: Mapped[int] = mapped_column(Integer, default=10)
    supports_stream: Mapped[bool] = mapped_column(Boolean, default=False)
    human_in_the_loop: Mapped[bool] = mapped_column(Boolean, default=True)
    evaluation_spec_json: Mapped[str] = mapped_column(Text, default="")
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OrchestrationSkill(Base):
    """编排技能：提示词 / 工作流 / 显式调用。不是工具底座里的 Skill 资源。"""

    __tablename__ = "orchestration_skills"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    trigger_type: Mapped[str] = mapped_column(String(20), default="context")
    trigger_value: Mapped[str] = mapped_column(String(200), default="")
    execution_type: Mapped[str] = mapped_column(String(32), default="prompt_template")
    entry_point: Mapped[str] = mapped_column(Text, default="")
    chainable: Mapped[bool] = mapped_column(Boolean, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    variables_json: Mapped[str] = mapped_column(Text, default="{}")
    builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OrchestrationRecipe(Base):
    """一次编排沉淀出的可复用配置。"""

    __tablename__ = "orchestration_recipes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), default="")
    requirement: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    source_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    creator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
