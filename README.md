# agent-loop

一个使用顺序工具调用、结构化轨迹和离线回放的最小 Agent 运行时。**这是一个最小实现，不是生产系统。**

## 依赖与复现

Python 3.10+；默认仅使用标准库、MockProvider 和本地语料，不需要网络或 API key。仓库 A `rag-eval` 必须与本仓库同级，数据也应保留在同级：

```text
父目录/
  agent-loop/
  rag-eval/
  data/corpus.jsonl
  corpus/docs-zh-cn/src/
```

`kb_search` 通过相对路径导入 A 的 `ingest.load_documents`、`chunkers.chunk` 和 `retriever.Retriever`，采用 recursive 分块和默认 mock 向量/BM25 搜索；不复制 A 的实现。它只读取 A 和原语料，在 B 的 `out/kb.sqlite` 建索引。`doc_toc` 从语料读取指定文档的标题树。

在本仓库根目录执行：

```sh
python run_demo.py
python replay.py
python -m unittest discover -s tests -v
```

`out/summary.json` 记录逐题结果与汇总，`out/trace.jsonl` 记录每步决策、参数、完整观察、上下文变化和终止原因，`out/external_store.jsonl` 保存外置的普通轮次。`out/replay.html` 是单文件回放页，可选问题、逐步查看观察并查看占用曲线。每次运行 demo 会覆盖以上输出中的轨迹、外置内容和汇总。任务成功率以 `finish` 终止为成功，澄清单独计数，因此需要澄清的运行不会算作成功；压缩次数来自每步实际执行的压缩动作。

可选 `python run_demo.py --provider openai-compatible` 使用 `BASE_URL`、`API_KEY`、`MODEL` 环境变量连接兼容的聊天接口，要求模型返回指定的结构化 JSON。该模式需要网络和服务支持，未作为默认离线验收条件。`--context-budget-tokens` 可调整软预算，默认 3000。

## 设计选择

工具通过路由顺序执行，而不是并行抢答：后续决策可以根据前一步的结果调整；这也让轨迹、失败和死锁判定容易理解。代价是多工具任务可能更慢。

默认最多 6 步，避免错误决策或工具循环无限消耗资源；连续两次相同工具和参数时，第二次转为 `ask_user`。完成、澄清、死锁、步数上限、工具收尾失败和模型异常均有明确终止原因。

上下文按相对于可配置预算的比例分档，而不是固定 token 数，以便同一策略适配不同预算。预算是输入软预算，需为模型输出保留余量；token 数使用确定性近似而非模型分词器。低于 60% 不压缩，60% 至 85% 用工具结论替换中间输出，高于 85% 时依次将最老的 normal 轮次写入外置存储并保留摘要；important 信息不外置。若重要信息本身超出预算，软预算仍可能被超过。

MockProvider 使用规则路由并从检索结果提取证据，不保证生成完整或正确的自然语言答案；真实模型的质量、上下文计数、并发安全、长期存储、鉴权及生产部署均不在此最小实现的范围内。
