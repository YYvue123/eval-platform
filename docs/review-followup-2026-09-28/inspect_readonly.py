"""Read-only repository audit. No application startup, network or business DB writes."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sqlite3
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent

def pure_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def quote(name):
    return '"' + name.replace('"', '""') + '"'

def inventory(path):
    if not path.exists():
        return {"exists": False}
    db = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA query_only=ON')
    db.execute('BEGIN')
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    result = {}
    for table in tables:
        columns = list(db.execute('PRAGMA table_info(' + quote(table) + ')'))
        textcols = [r[1] for r in columns if any(t in r[2].upper() for t in ('TEXT', 'CHAR')) and not any(s in r[1].lower() for s in ('secret', 'password', 'token', 'key'))]
        entry = {"rows": db.execute('SELECT count(*) FROM ' + quote(table)).fetchone()[0]}
        column_names = {r[1] for r in columns}
        if table == 'eval_results' and 'simulation' in column_names:
            entry['simulation_true_rows'] = db.execute('SELECT count(*) FROM eval_results WHERE simulation=1').fetchone()[0]
        if table == 'agent_runs' and 'provider' in column_names:
            entry['provider_mock_rows'] = db.execute("SELECT count(*) FROM agent_runs WHERE provider='mock'").fetchone()[0]
        if table == 'eval_results' and 'metrics_json' in column_names:
            def contains_mock_true(value):
                if isinstance(value, dict):
                    return any((k in ('mock', 'mocked', 'stubbed', 'simulation') and v is True) or contains_mock_true(v) for k, v in value.items())
                return isinstance(value, list) and any(contains_mock_true(v) for v in value)
            count = 0
            for (raw,) in db.execute('SELECT metrics_json FROM eval_results'):
                try:
                    count += int(contains_mock_true(json.loads(raw or '{}')))
                except (ValueError, TypeError):
                    pass
            entry['structured_mock_true_rows'] = count
        # Candidate signals only, never deletion criteria. No row contents are emitted.
        if textcols:
            predicate = ' OR '.join('lower(coalesce(' + quote(c) + ",'')) LIKE ?" for c in textcols)
            entry['marker_candidate_rows'] = {term: db.execute('SELECT count(*) FROM ' + quote(table) + ' WHERE ' + predicate, ['%' + term + '%'] * len(textcols)).fetchone()[0] for term in ('mock', 'stub', 'demo', '示例', '模拟')}
        result[table] = entry
    db.rollback()
    db.close()
    return {"exists": True, "path": str(path.relative_to(ROOT)), "tables": result}

protocol = pure_module('audit_protocol', 'backend/app/services/protocol.py')
side_effect = pure_module('audit_side_effect', 'backend/app/services/side_effect_policy.py')
manifest = {
    'spec_version': '0.6.1', 'resource_id': 'review/tool', 'resource_type': 'tool',
    'name': 'review', 'description': 'review', 'version': '1.0.0',
    'owner': {'name': 'tenant'},
    'capabilities': {'input_schema': {'type': 'object'}, 'output_schema': {'type': 'object'}, 'call_mode': 'sync', 'timeout': 30, 'side_effects': 'none'},
    'interfaces': {'endpoint': 'local://tool/review/tool', 'method': 'exec', 'auth_type': 'none'},
}
try:
    side_effect.has_side_effects({'capabilities': {'side_effects': 'none'}})
    side_effect_check = {'raised': False}
except Exception as exc:
    side_effect_check = {'raised': True, 'error_type': type(exc).__name__, 'message': str(exc)}
env_path = ROOT / 'backend/.env'
env_keys = {}
if env_path.exists():
    for line in env_path.read_text(encoding='utf-8-sig').splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            if key.strip().startswith('L3_') or key.strip() in ('APP_ENV', 'DATABASE_URL'):
                env_keys[key.strip()] = {'configured': bool(value.strip().strip('"\''))}
sources = [
    'backend/app/services/agent_runtime.py', 'backend/app/services/tool_gateway/__init__.py',
    'backend/app/services/side_effect_policy.py', 'backend/app/services/http_adapter.py',
    'backend/app/services/protocol.py', 'backend/app/api/resources.py', 'backend/app/api/tasks.py',
    'backend/app/services/ops_governance.py', 'frontend/src/views/Agents.vue',
    'frontend/src/views/Resources.vue', 'frontend/src/components/SchemaForm.vue',
]
report = {
    'captured_at': datetime.now(timezone.utc).isoformat(),
    'scope': 'read-only metadata and pure-function probes; not live integration or browser verification',
    'wizard_manifest_validation_errors': protocol.validate_manifest(manifest),
    'capabilities_side_effects_none': side_effect_check,
    'side_effect_stub_result': side_effect.stub_side_effect_result({'side_effects': [{'type': 'write'}]}),
    'env_config_presence_only': env_keys,
    'business_db': inventory(ROOT / 'backend/eval_platform.db'),
    'historical_l3_db': inventory(ROOT / 'backend/tests/_isolated/l3/l3_live.db'),
    'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
}
(OUT / 'evidence.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: report[k] for k in ('wizard_manifest_validation_errors', 'capabilities_side_effects_none', 'side_effect_stub_result', 'env_config_presence_only')}, ensure_ascii=False, indent=2))
for key in ('business_db', 'historical_l3_db'):
    data = report[key]
    print(key, 'tables=', len(data.get('tables', {})), 'rows=', sum(t['rows'] for t in data.get('tables', {}).values()))
print('Saved:', OUT / 'evidence.json')
