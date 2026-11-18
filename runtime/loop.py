"""Sequential reason / tool / observation loop with bounded termination."""
import json
import time
from runtime.context import ContextManager, tokens

SYSTEM = ('你是 Vue 中文文档助手，先检索或查看目录，依据工具结果回答，不足时澄清。'
          '请输出 JSON 对象：kind 为 tool 或 answer；tool 时提供 name、args，answer 时提供 answer；'
          '始终提供 thought 和 importance（important 或 normal）。缺少信息时使用 ask_user，完成时使用 finish。')


def conclusion_for(name, result):
    if not result['ok']:
        return '工具失败：' + result['error']
    value = result['result']
    if name == 'kb_search':
        hits = value.get('hits', [])
        if not hits:
            return '没有检索到相关内容。'
        first = hits[0]
        return f"来源 {first['path']} {' > '.join(first['section_path'])}：{first['text'][:350]}"
    if name == 'doc_toc':
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def run(question, registry, provider, trace, max_steps=6, context_budget_tokens=3000,
        store_path=None, run_id='run'):
    if max_steps < 1:
        raise ValueError('max_steps must be positive')
    context = ContextManager(context_budget_tokens, store_path)
    history, records, previous = [], [], None
    start = time.perf_counter()
    reason, answer = 'max_steps', ''
    for step in range(1, max_steps + 1):
        messages, context_state = context.prepare(SYSTEM, registry.list_for_prompt(), history, question)
        try:
            decision = provider.decide(messages, registry.list_for_prompt())
            if not isinstance(decision, dict) or decision.get('kind') not in ('tool', 'answer'):
                raise ValueError('invalid provider decision')
            if decision.get('importance') not in ('normal', 'important'):
                raise ValueError('invalid importance label')
            thought = str(decision.get('thought', ''))
            if decision['kind'] == 'answer':
                name, args = 'finish', {'answer': str(decision.get('answer', ''))}
            else:
                name, args = decision['name'], decision.get('args', {})
            signature = json.dumps([name, args], ensure_ascii=False, sort_keys=True)
            deadlock = signature == previous
            if deadlock:
                name, args = 'ask_user', {'question': '连续重复同一操作，请补充信息以继续。'}
            previous = signature
            result = registry.call(name, args)
            observation = json.dumps(result, ensure_ascii=False)
            conclusion = conclusion_for(name, result)
            importance = decision['importance']
            history.append({'role': 'assistant', 'kind': 'tool', 'tool': name, 'content': observation,
                            'conclusion': conclusion, 'importance': importance, 'ok': result['ok']})
            if deadlock:
                reason = 'deadlock'
            elif name == 'ask_user' and result['ok']:
                reason = 'ask_user'
            elif name == 'finish' and result['ok']:
                reason = 'finish'
            elif name in ('finish', 'ask_user') and not result['ok']:
                reason = 'tool_error'
            if reason != 'max_steps':
                answer = result['result'] if result['ok'] else result['error']
            record = {'run_id': run_id, 'question': question, 'step': step, 'thought': thought,
                      'tool': name, 'args': args, 'observation': result,
                      'observation_tokens': tokens(observation), 'ok': result['ok'],
                      'elapsed_ms': result['elapsed_ms'], **context_state,
                      'termination_reason': reason if reason != 'max_steps' or step == max_steps else None}
        except Exception as exc:
            reason = 'provider_error'
            record = {'run_id': run_id, 'question': question, 'step': step, 'thought': '', 'tool': None, 'args': {},
                      'observation': {'error': f'{type(exc).__name__}: {exc}'}, 'observation_tokens': 0,
                      'ok': False, 'elapsed_ms': 0, **context_state, 'termination_reason': reason}
            answer = record['observation']['error']
        trace.write(record)
        records.append(record)
        if reason != 'max_steps':
            break
    return {'run_id': run_id, 'question': question, 'termination_reason': reason, 'answer': answer,
            'steps': len(records), 'elapsed_ms': round((time.perf_counter()-start)*1000, 3),
            'compression_count': sum(r['action_taken'] != 'none' for r in records),
            'clarification_count': sum(r['tool'] == 'ask_user' and r['ok'] for r in records),
            'success': reason == 'finish'}
