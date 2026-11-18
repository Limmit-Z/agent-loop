"""Embed the recorded trace in a self-contained replay page."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    source = ROOT / 'out/trace.jsonl'
    if not source.is_file():
        raise SystemExit('请先运行 python run_demo.py')
    with source.open(encoding='utf-8') as f:
        records = [json.loads(line) for line in f if line.strip()]
    if not records:
        raise SystemExit('轨迹为空，请先运行 python run_demo.py')
    payload = json.dumps(records, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    template = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    (ROOT / 'out/replay.html').write_text(template.replace('/*TRACE_DATA*/', payload), encoding='utf-8')
    print(f'Wrote out/replay.html ({len(records)} steps in {len(set(r["run_id"] for r in records))} runs)')


if __name__ == '__main__':
    main()
