import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from collection_service import file_lock
from hk_cbdc_questions import check_questions

root = Path(__file__).resolve().parents[1]
with file_lock(root / 'data/ingestion/automation/run.lock'):
    report = check_questions(root)
print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
raise SystemExit(int(report['unresolved'] > 0 or report['corpus_integrity'] != 'passed'))
