"""Collect HK CBDC data, or inspect/export already persisted records offline."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from collection_service import file_lock, CollectionBusy
from hk_cbdc_collection import cycle, read
from hk_cbdc_data import export_corpus

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
actions = parser.add_mutually_exclusive_group()
actions.add_argument('--status', action='store_true')
actions.add_argument('--export-only', action='store_true')
actions.add_argument('--discover-only', action='store_true', help='Continue the persistent discovery queue without refreshing old files')
parser.add_argument('--limit', type=int, default=12, help='Maximum new HTML articles per cycle (1..50)')
args = parser.parse_args()
if args.status:
    state = read(root / 'data/ingestion/hk_cbdc/run_checkpoint.json', {'status': 'not_started'})
    try:
        with file_lock(root / 'data/ingestion/automation/run.lock'):
            if state['status'] == 'running':
                state['effective_status'] = 'interrupted'
    except CollectionBusy:
        state['collection_lock_held'] = True
    state['scheduler_process_liveness'] = 'unknown; a saved checkpoint does not prove an active worker'
else:
    with file_lock(root / 'data/ingestion/automation/run.lock'):
        state = export_corpus(root) if args.export_only else cycle(root, refresh=not args.discover_only, limit=args.limit)
print(json.dumps(state, ensure_ascii=True, indent=2))
raise SystemExit(int(state.get('status') in ('failed', 'partial_failure')))
