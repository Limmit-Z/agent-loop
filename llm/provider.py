"""Deterministic mock and optional OpenAI-compatible decision provider."""
import json
import os
import re
import urllib.request


class MockProvider:
    def decide(self, messages, tools):
        question = messages[-1]['content']
        history = [m for m in messages if m.get('kind') == 'tool']
        if not history:
            if question.strip() in ('怎么处理？', '帮我看看', '这个怎么做？'):
                return {'kind': 'tool', 'name': 'ask_user', 'args': {'question': '请说明具体的 Vue 功能或错误信息。'}, 'thought': '问题缺少可检索的主题。', 'importance': 'important'}
            path = re.search(r'(?:guide|api|examples)/[\w./-]+\.md', question)
            if path and ('目录' in question or '标题' in question):
                return {'kind': 'tool', 'name': 'doc_toc', 'args': {'path': path.group()}, 'thought': '先查看文档标题树。', 'importance': 'normal'}
            query = 'Vue 响应式 ref reactive' if '对照检索' in question else question
            return {'kind': 'tool', 'name': 'kb_search', 'args': {'query': query, 'top_k': 5}, 'thought': '检索与问题相关的文档。', 'importance': 'normal'}
        if '对照检索' in question and len(history) < 3:
            queries = ['Vue 响应式 ref reactive', 'Vue 计算属性 computed 缓存', 'Vue watch 侦听器']
            return {'kind': 'tool', 'name': 'kb_search', 'args': {'query': queries[len(history)], 'top_k': 5}, 'thought': '继续检索对照主题。', 'importance': 'normal'}
        latest = history[-1]
        if not latest.get('ok'):
            return {'kind': 'tool', 'name': 'ask_user', 'args': {'question': '检索未成功，请检查文档路径或补充问题。'}, 'thought': '工具未返回可用结果。', 'importance': 'important'}
        answer = '\n\n'.join(item.get('conclusion', item['content']) for item in history) if '对照检索' in question else latest.get('conclusion', latest['content'])
        return {'kind': 'tool', 'name': 'finish', 'args': {'answer': answer}, 'thought': '根据工具返回的证据收尾。', 'importance': 'important'}


class OpenAICompatProvider:
    def decide(self, messages, tools):
        base, key, model = (os.environ[k] for k in ('BASE_URL', 'API_KEY', 'MODEL'))
        payload = {'model': model, 'messages':
                   [{'role': m['role'] if m['role'] in ('user', 'assistant', 'system') else 'user',
                     'content': m['content']} for m in messages], 'response_format': {'type': 'json_object'}}
        req = urllib.request.Request(base.rstrip('/') + '/chat/completions', data=json.dumps(payload).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            decision = json.loads(json.load(response)['choices'][0]['message']['content'])
        if decision.get('kind') not in ('tool', 'answer'):
            raise ValueError('provider returned an invalid decision')
        if decision.get('importance') not in ('important', 'normal'):
            raise ValueError('provider must return an importance label')
        return decision
