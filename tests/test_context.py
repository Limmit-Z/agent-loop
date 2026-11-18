import json
import tempfile
import unittest
from pathlib import Path
from runtime.context import ContextManager, message_tokens


class ContextTests(unittest.TestCase):
    def test_low_budget_fraction_leaves_history_untouched(self):
        h = [{'role': 'assistant', 'kind': 'tool', 'importance': 'normal', 'content': '中文输出', 'conclusion': '结论'}]
        manager = ContextManager(3000)
        _, state = manager.prepare('系统', [], h, '问题')
        self.assertEqual(state['action_taken'], 'none')
        self.assertEqual(h[0]['content'], '中文输出')

    def test_middle_band_drops_only_intermediate_result(self):
        h = [{'role': 'assistant', 'kind': 'tool', 'importance': 'normal', 'content': '中'*500, 'conclusion': '结论'}]
        initial = message_tokens(ContextManager().assemble('系统', [], h, '问题'))
        manager = ContextManager(int(initial / .7))
        _, state = manager.prepare('系统', [], h, '问题')
        self.assertEqual(state['action_taken'], 'drop_intermediate_outputs')
        self.assertEqual(h[0]['content'], '结论')
        self.assertLess(state['ratio_after'], state['context_ratio'])

    def test_high_band_externalizes_oldest_normal_and_keeps_important(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d) / 'store.jsonl'
            history = [{'role':'assistant', 'kind':'tool', 'importance':'important', 'content':'关键'*10, 'conclusion':'保留'},
                       {'role':'assistant', 'kind':'tool', 'importance':'normal', 'content':'旧'*800, 'conclusion':'摘要'},
                       {'role':'assistant', 'kind':'tool', 'importance':'normal', 'content':'新'*200, 'conclusion':'新摘要'}]
            _, state = ContextManager(700, store).prepare('系统', [], history, '问题')
            self.assertEqual(state['action_taken'], 'externalize_oldest_normal')
            saved = [json.loads(s) for s in store.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(saved[0]['content'], '旧'*800)
            self.assertEqual(history[0]['content'], '关键'*10)
            self.assertIn('摘要', history[1]['content'])
            self.assertLess(state['ratio_after'], state['context_ratio'])


if __name__ == '__main__':
    unittest.main()
