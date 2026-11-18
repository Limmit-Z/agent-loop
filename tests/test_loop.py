import json
import tempfile
import unittest
from pathlib import Path
from runtime.loop import run
from tools.registry import ToolRegistry
from trace import TraceWriter


class SequenceProvider:
    def __init__(self, decisions): self.decisions = iter(decisions)
    def decide(self, messages, tools): return next(self.decisions)


def decision(name, args):
    return {'kind': 'tool', 'name': name, 'args': args, 'importance': 'normal', 'thought': '测试'}


class LoopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.trace = TraceWriter(self.path / 'trace.jsonl')
        self.registry = ToolRegistry()
        schema = {'type':'object', 'properties':{'query':{'type':'string'}}, 'required':['query']}
        self.registry.register('lookup', 'lookup', schema, lambda query: {'value':query})
        schema2 = {'type':'object', 'properties':{'question':{'type':'string'}}, 'required':['question']}
        self.registry.register('ask_user', 'ask', schema2, lambda question: {'question':question})
        schema3 = {'type':'object', 'properties':{'answer':{'type':'string'}}, 'required':['answer']}
        self.registry.register('finish', 'finish', schema3, lambda answer: {'answer':answer})

    def tearDown(self): self.temp.cleanup()

    def test_deadlock_is_detected_before_repeating_call(self):
        same = decision('lookup', {'query':'abc'})
        result = run('question', self.registry, SequenceProvider([same, same]), self.trace, store_path=self.path / 'store')
        rows = [json.loads(x) for x in self.trace.path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(result['termination_reason'], 'deadlock')
        self.assertEqual([r['tool'] for r in rows], ['lookup', 'ask_user'])
        self.assertEqual(result['clarification_count'], 1)

    def test_max_steps_and_final_trace_reason(self):
        ds = [decision('lookup', {'query':str(i)}) for i in range(2)]
        result = run('question', self.registry, SequenceProvider(ds), self.trace, max_steps=2, store_path=self.path / 'store')
        self.assertEqual(result['termination_reason'], 'max_steps')
        last = json.loads(self.trace.path.read_text(encoding='utf-8').splitlines()[-1])
        self.assertEqual(last['termination_reason'], 'max_steps')

    def test_finish_and_failed_tool_observation(self):
        ds = [decision('missing', {}), decision('finish', {'answer':'已完成'})]
        result = run('question', self.registry, SequenceProvider(ds), self.trace, store_path=self.path / 'store')
        rows = [json.loads(x) for x in self.trace.path.read_text(encoding='utf-8').splitlines()]
        self.assertFalse(rows[0]['ok'])
        self.assertEqual(result['termination_reason'], 'finish')
        self.assertEqual(result['answer']['answer'], '已完成')

    def test_provider_error_terminates_with_trace(self):
        result = run('question', self.registry, SequenceProvider([]), self.trace, store_path=self.path / 'store')
        self.assertEqual(result['termination_reason'], 'provider_error')
        self.assertEqual(json.loads(self.trace.path.read_text(encoding='utf-8'))['termination_reason'], 'provider_error')


if __name__ == '__main__':
    unittest.main()
