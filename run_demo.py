"""Run ten fixed questions; report only observed outcomes."""
import argparse
import json
from pathlib import Path
from llm.provider import MockProvider, OpenAICompatProvider
from runtime.loop import run
from tools.registry import make_registry
from trace import TraceWriter

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'out'
QUESTIONS = [
    'ref 和 reactive 有什么区别？', 'computed 为什么会缓存？', '怎样使用 watch 侦听器？',
    '组件之间怎样传递 props？', 'Vue 生命周期有哪些钩子？', 'v-if 和 v-show 有什么区别？',
    '如何渲染列表并使用 key？', '如何处理表单输入绑定？',
    '请对照检索响应式、计算属性和侦听器，并列出相关证据。', '怎么处理？',
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['mock', 'openai-compatible'], default='mock')
    parser.add_argument('--context-budget-tokens', type=int, default=3000)
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True)
    # Each invocation has a self-contained trace and external-store history.
    for name in ('trace.jsonl', 'external_store.jsonl'):
        (OUT / name).write_text('', encoding='utf-8')
    trace, registry = TraceWriter(OUT / 'trace.jsonl'), make_registry(OUT)
    provider = MockProvider() if args.provider == 'mock' else OpenAICompatProvider()
    results = []
    for i, question in enumerate(QUESTIONS, 1):
        result = run(question, registry, provider, trace, context_budget_tokens=args.context_budget_tokens,
                     store_path=OUT / 'external_store.jsonl', run_id=f'q{i:02}')
        results.append(result)
        print(f"{result['run_id']}: {result['termination_reason']} steps={result['steps']} compressions={result['compression_count']} clarifications={result['clarification_count']}", flush=True)
    summary = {'task_count': len(results), 'task_success_rate': sum(x['success'] for x in results)/len(results),
               'average_steps': sum(x['steps'] for x in results)/len(results),
               'average_elapsed_ms': round(sum(x['elapsed_ms'] for x in results)/len(results), 3),
               'compression_count': sum(x['compression_count'] for x in results),
               'clarification_count': sum(x['clarification_count'] for x in results), 'runs': results}
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k != 'runs'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
