"""Soft context budget and traceable compaction."""
import json
import math
from pathlib import Path


def tokens(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    # Simple deterministic approximation: each non-ASCII character or four ASCII characters.
    non_ascii = sum(ord(c) > 127 for c in text)
    return non_ascii + math.ceil((len(text) - non_ascii) / 4)


def message_tokens(messages):
    return sum(tokens(m['role']) + tokens(m['content']) for m in messages)


class ContextManager:
    # A soft input budget, not the model's full context window: leave room for output.
    def __init__(self, context_budget_tokens=3000, store_path=None):
        if context_budget_tokens <= 0:
            raise ValueError('context budget must be positive')
        self.budget = context_budget_tokens
        self.store_path = Path(store_path) if store_path else Path('out/external_store.jsonl')

    def assemble(self, system, tools, history, question):
        return [{'role': 'system', 'content': system},
                {'role': 'system', 'content': json.dumps(tools, ensure_ascii=False)},
                *history, {'role': 'user', 'content': question}]

    def prepare(self, system, tools, history, question):
        messages = self.assemble(system, tools, history, question)
        before = message_tokens(messages) / self.budget
        action = 'none'
        if .6 <= before <= .85:
            for item in history:
                if item.get('kind') == 'tool' and not item.get('compacted'):
                    item['content'] = item.get('conclusion', '')
                    item['compacted'] = True
                    action = 'drop_intermediate_outputs'
        elif before > .85:
            for item in history:
                if message_tokens(self.assemble(system, tools, history, question)) / self.budget <= .85:
                    break
                if item.get('importance', 'normal') != 'normal' or item.get('externalized'):
                    continue
                self.store_path.parent.mkdir(parents=True, exist_ok=True)
                with self.store_path.open('a', encoding='utf-8') as out:
                    out.write(json.dumps(item, ensure_ascii=False) + '\n')
                item['content'] = '[已外置] ' + item.get('conclusion', item['content'][:100])
                item['externalized'] = True
                item['compacted'] = True
                action = 'externalize_oldest_normal'
        messages = self.assemble(system, tools, history, question)
        return messages, {'context_ratio': before, 'ratio_after': message_tokens(messages) / self.budget, 'action_taken': action}
