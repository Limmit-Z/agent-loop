"""JSON-schema tool registry and adapters for the neighboring RAG project."""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAG = ROOT / '../rag-eval'
CORPUS = ROOT / '../corpus/docs-zh-cn/src'


class ToolRegistry:
    def __init__(self):
        self._tools = {}

    def register(self, name, description, parameters, handler):
        if name in self._tools:
            raise ValueError('duplicate tool: ' + name)
        self._tools[name] = ({'name': name, 'description': description, 'parameters': parameters}, handler)

    def list_for_prompt(self):
        return [item[0] for item in self._tools.values()]

    def call(self, name, args):
        start = time.perf_counter()
        try:
            spec, handler = self._tools[name]
            if not isinstance(args, dict):
                raise ValueError('arguments must be an object')
            schema = spec['parameters']
            for key in schema.get('required', []):
                if key not in args:
                    raise ValueError('missing argument: ' + key)
            for key, value in args.items():
                prop = schema['properties'].get(key)
                if prop is None:
                    raise ValueError('unexpected argument: ' + key)
                if prop['type'] == 'string' and not isinstance(value, str):
                    raise ValueError(key + ' must be a string')
                if prop['type'] == 'integer' and (not isinstance(value, int) or isinstance(value, bool)):
                    raise ValueError(key + ' must be an integer')
                if 'minimum' in prop and value < prop['minimum'] or 'maximum' in prop and value > prop['maximum']:
                    raise ValueError(key + ' out of range')
            result = handler(**args)
            return {'ok': True, 'result': result, 'error': None, 'elapsed_ms': round((time.perf_counter()-start)*1000, 3)}
        except Exception as exc:
            return {'ok': False, 'result': None, 'error': f'{type(exc).__name__}: {exc}', 'elapsed_ms': round((time.perf_counter()-start)*1000, 3)}


def _toc(path):
    file = (CORPUS / path).resolve()
    if not file.is_relative_to(CORPUS.resolve()) or not file.is_file():
        raise ValueError('unknown document')
    nodes, stack, fence = [], [], None
    for line in file.read_text(encoding='utf-8').splitlines():
        marker = re.match(r'^\s*(`{3,}|~{3,})', line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            continue
        m = None if fence else re.match(r'^(#{1,3})\s+(.+?)\s*#*\s*$', line)
        if not m:
            continue
        level = len(m.group(1))
        title = re.sub(r'\s*\{#[^}]+\}\s*$', '', m.group(2))
        node = {'level': level, 'title': title, 'children': []}
        while stack and stack[-1]['level'] >= level:
            stack.pop()
        (stack[-1]['children'] if stack else nodes).append(node)
        stack.append(node)
    return {'path': path, 'headings': nodes}


def make_registry(output_dir=None):
    output_dir = Path(output_dir) if output_dir else ROOT / 'out'
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = ToolRegistry()
    cache = {}

    def kb_search(query, top_k=5):
        if 'retriever' not in cache:
            # Import the sibling project; its corpus is only read and its index is stored here.
            sys.path.insert(0, str(RAG.resolve()))
            original = sys.dont_write_bytecode
            try:
                sys.dont_write_bytecode = True
                from ingest import load_documents
                from chunkers import chunk
                from retriever import Retriever
            finally:
                sys.dont_write_bytecode = original
            cache['retriever'] = Retriever(chunk(load_documents(), strategy='recursive'), output_dir / 'kb.sqlite')
        return cache['retriever'].search(query, top_k=top_k)

    def spec(properties, required):
        return {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}

    registry.register('kb_search', '检索 Vue 中文文档并返回相关块和得分。', spec({'query': {'type': 'string'}, 'top_k': {'type': 'integer', 'minimum': 1, 'maximum': 20}}, ['query']), kb_search)
    registry.register('doc_toc', '返回指定文档的标题树。', spec({'path': {'type': 'string'}}, ['path']), _toc)
    registry.register('ask_user', '需要更多信息时提出澄清并终止本轮。', spec({'question': {'type': 'string'}}, ['question']), lambda question: {'question': question})
    registry.register('finish', '有足够证据后结束本轮。', spec({'answer': {'type': 'string'}}, ['answer']), lambda answer: {'answer': answer})
    return registry
