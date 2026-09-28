"""Run existing tests with isolated data and a bounded subprocess timeout."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
subset = sys.argv[1] if len(sys.argv) > 1 else "smoke"
assert subset in {"smoke", "execution"}
env = os.environ.copy()
env.update({
    "PYTHONPATH": str(ROOT / "backend-deps") + os.pathsep + str(REPO / "backend"),
    "DATABASE_URL": "sqlite+aiosqlite:///" + (ROOT / f"{subset}.db").as_posix(),
    "UPLOAD_DIR": str(ROOT / "uploads" / subset),
    "LOG_DIR": str(ROOT / "logs" / subset),
    "BACKUP_DIR": str(ROOT / "backups" / subset),
    "LOG_LEVEL": "WARNING", "PYTHONWARNINGS": "ignore::DeprecationWarning", "PYTHONIOENCODING": "utf-8",
})
code = '''
import faulthandler, unittest, sys
faulthandler.dump_traceback_later(25, repeat=False)
from tests.test_eval_flow import EvalFlowTest
from tests.test_auth import AuthSmokeTest
excluded = {'test_end_to_end_eval', 'test_task_templates_queue_and_report'}
suite = unittest.TestSuite()
mode = sys.argv[1]
for cls in (AuthSmokeTest, EvalFlowTest):
 for name in unittest.defaultTestLoader.getTestCaseNames(cls):
  if (mode == 'smoke' and name not in excluded) or (mode == 'execution' and name == 'test_end_to_end_eval'):
   suite.addTest(cls(name))
result = unittest.TextTestRunner(verbosity=2).run(suite)
faulthandler.cancel_dump_traceback_later()
sys.exit(not result.wasSuccessful())
'''
limit = 90 if subset == "smoke" else 45
result = {"subset": subset, "timeout_seconds": limit, "data_directory": str(ROOT), "production_database_access": False}
with (ROOT / f"bounded-{subset}.txt").open("w", encoding="utf-8") as output:
    try:
        run = subprocess.run([sys.executable, "-c", code, subset], cwd=REPO / "backend", env=env,
                             stdout=output, stderr=subprocess.STDOUT, timeout=limit)
        result.update(status="finished", exit_code=run.returncode)
    except subprocess.TimeoutExpired:
        result.update(status="timeout", exit_code=None)
(ROOT / f"bounded-{subset}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
