"""HK-only collection with durable phase checkpoints and offline status."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from hk_collection import run, status
from hk_stablecoin_data import export_corpus
from collection_service import file_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--export-only', action='store_true', help='Offline export; no HTTP')
    mode.add_argument('--status', action='store_true', help='Offline run/checkpoint status; no HTTP')
    mode.add_argument('--resume', action='store_true', help='Resume matching checkpoint less than 24 hours old')
    args = parser.parse_args()
    if args.status:
        value = status(ROOT)
        code = 0
    elif args.export_only:
        with file_lock(ROOT / 'data/ingestion/automation/run.lock'):
            value = export_corpus(ROOT)
        code = int(bool(value['missing_configured_urls'] or not value['primary_database_present']))
    else:
        state = run(ROOT, resume=args.resume)
        value = dict(run_id=state['run_id'], status=state['status'],
                     resume_noop=state.get('resume_noop', False),
                     stages={k:{field:v[field] for field in ('status','error','error_type') if field in v}
                             for k,v in state['stages'].items()},
                     corpus=state['stages'].get('export', {}).get('output', {}))
        code = int(state['status'] != 'success')
    print(json.dumps(value, ensure_ascii=True, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
