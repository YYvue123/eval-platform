"""Async LangGraph saver scoped to one authorized run and its SQLAlchemy transaction."""
from __future__ import annotations

import asyncio
import base64

from langgraph.checkpoint.base import BaseCheckpointSaver, CheckpointTuple, WRITES_IDX_MAP
from sqlalchemy import select

from app.models.agent import AgentGraphCheckpoint
from app.utils.jsonutil import dumps, loads


class AgentCheckpointer(BaseCheckpointSaver):
    def __init__(self, db, run, *, namespace_prefix=""):
        super().__init__()
        self.db = db
        self.run = run
        self.namespace_prefix = namespace_prefix
        # Nodes and saver callbacks must not concurrently use an AsyncSession.
        self.lock = asyncio.Lock()

    def _scope(self, config):
        values = config["configurable"]
        if values["thread_id"] != self.run.checkpoint_thread_id:
            raise ValueError("checkpoint_thread_mismatch")
        return self.namespace_prefix + values.get("checkpoint_ns", "")

    def _config(self, namespace, checkpoint_id):
        return {"configurable": {
            "thread_id": self.run.checkpoint_thread_id,
            "checkpoint_ns": namespace.removeprefix(self.namespace_prefix) if self.namespace_prefix else namespace,
            "checkpoint_id": checkpoint_id,
        }}

    def _encode(self, value):
        kind, payload = self.serde.dumps_typed(value)
        return [kind, base64.b64encode(payload).decode("ascii")]

    def _decode(self, value):
        return self.serde.loads_typed((value[0], base64.b64decode(value[1])))

    async def aget_tuple(self, config):
        namespace = self._scope(config)
        async with self.lock:
            query = select(AgentGraphCheckpoint).where(
                AgentGraphCheckpoint.run_id == self.run.id,
                AgentGraphCheckpoint.namespace == namespace,
            )
            checkpoint_id = config["configurable"].get("checkpoint_id")
            if checkpoint_id:
                query = query.where(AgentGraphCheckpoint.checkpoint_id == checkpoint_id)
            row = await self.db.scalar(query.order_by(AgentGraphCheckpoint.checkpoint_id.desc()).limit(1))
            if row is None:
                return None
            writes = sorted(loads(row.writes_json, {}).values(), key=lambda w: (w[0], w[1], w[2]))
            return CheckpointTuple(
                config=self._config(namespace, row.checkpoint_id),
                checkpoint=self._decode(loads(row.checkpoint_json, [])),
                metadata=loads(row.metadata_json, {}),
                parent_config=self._config(namespace, row.parent_id) if row.parent_id else None,
                pending_writes=[(w[1], w[3], self._decode(w[4])) for w in writes],
            )

    async def aput(self, config, checkpoint, metadata, new_versions):
        namespace = self._scope(config)
        async with self.lock:
            row = AgentGraphCheckpoint(
                run_id=self.run.id,
                namespace=namespace,
                checkpoint_id=checkpoint["id"],
                parent_id=config["configurable"].get("checkpoint_id", ""),
                checkpoint_json=dumps(self._encode(checkpoint)),
                metadata_json=dumps(metadata),
                writes_json="{}",
            )
            self.db.add(row)
            await self.db.flush()
        return self._config(namespace, checkpoint["id"])

    async def aput_writes(self, config, writes, task_id, task_path=""):
        namespace = self._scope(config)
        async with self.lock:
            key = (self.run.id, namespace, config["configurable"]["checkpoint_id"])
            row = await self.db.get(AgentGraphCheckpoint, key)
            if row is None:
                raise ValueError("checkpoint_missing_for_writes")
            stored = loads(row.writes_json, {})
            for index, (channel, value) in enumerate(writes):
                index = WRITES_IDX_MAP.get(channel, index)
                write_key = f"{task_id}:{index}"
                if index >= 0 and write_key in stored:
                    continue
                stored[write_key] = [task_path, task_id, index, channel, self._encode(value)]
            row.writes_json = dumps(stored)
            await self.db.flush()
