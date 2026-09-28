"""Read-only source inspection and pure shadow-function probes; no app/DB import."""
import hashlib
import json
import runpy
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name('evidence.json')
shadow = runpy.run_path(str(ROOT / 'backend/app/services/shadow_router.py'))
now = datetime(2026, 9, 28, 12)
started = now - timedelta(days=8)
observations = dict(score=0.9, latency_ms=100, samples=[0.89, 0.90, 0.91])
forged = shadow['evaluate_shadow'](observations, observations, started_at=started, now=now)
empty = shadow['evaluate_shadow']({}, {}, started_at=started, now=now)
files = [
    'frontend/src/views/Agents.vue', 'frontend/src/views/Resources.vue',
    'frontend/src/views/EvalServices.vue', 'frontend/src/views/Ops.vue',
    'frontend/src/views/Safety.vue', 'backend/app/services/agent_runtime.py',
    'backend/app/services/shadow_router.py', 'backend/app/api/resources.py',
    'backend/app/api/tasks.py', 'backend/app/services/scenario_simulators.py',
    'backend/app/services/media_adapter.py',
]
report = {
    'executed_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'Pure function probes and source hashes only. No database, network, app startup, or browser.',
    'shadow_client_named_score': {
        'input': observations, 'status': forged['status'],
        'promotable': forged['promotable'],
        'can_promote_after_8_days': shadow['can_promote'](forged, started_at=started, now=now),
    },
    'shadow_empty_observations': {
        'status': empty['status'], 'promotable': empty['promotable'],
        'can_promote_after_8_days': shadow['can_promote'](empty, started_at=started, now=now),
    },
    'view_count': len(list((ROOT / 'frontend/src/views').glob('*.vue'))),
    'source_sha256': {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in files},
}
OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'source_sha256'}, ensure_ascii=False, indent=2))
