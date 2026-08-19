# auto_paper

一个面向快速迭代的科研素材工作台：围绕当前研究项目画像搜索论文，把论文转成可缝合素材卡，辅助判断哪些 idea、模块和架构思想可以落地到自己的 pipeline。

## 第一版能力

- 项目画像：配置研究领域、任务、idea、backbone、neck、head、dataset。
- 每日搜索：基于 arXiv API 围绕项目画像拉取最新论文，可手动触发，也支持服务启动后的每日后台任务。
- 自动摘要：先用轻量启发式摘要跑通闭环，后续可替换为 LLM 总结。
- 素材卡：为论文生成可接入位置、二级标签、缝合动作、接入难度和证据来源。
- 三分排序：生成相关性、可缝合度、代码可用性三类评分，主排序使用可缝合度。
- 质量过滤：扩大候选池后按“直接相关 / 可迁移 / 仅供参考 / 不相关”四级筛选，并保留判定原因。
- 反馈重排：支持标记有用、可缝合、不相关、已读；个人反馈会有限度影响同类素材排序。
- 质量评估：固定模型 Top 10 作为评估集，统计标注覆盖、正向反馈、误推荐和 7/10 达标状态。
- 快速筛选：默认查看个性化 Top 10，也可切换全部有效、有代码、低成本和指定接入位置。
- 方案篮子：选择 3-5 张素材后，按接入顺序生成第一轮实验路线、验证步骤和风险提醒。
- 画像体检：自动发现任务类型、idea 与 Head 之间的明显冲突，避免检索方向被错误画像带偏。
- 深度缝合分析：为单张或 Top 10 素材生成模块接口、最小实现、对照实验、风险、证据与置信度。
- 双通道分析：默认使用本地规则；配置 OpenAI 后通过 Responses API 和严格 JSON Schema 生成，并按论文、画像与模型指纹缓存。
- 在线预览：内置 Web 页面按 Backbone / Neck / Head / Loss / Data / Training / Experiment 看板查看素材。
- 下载导出：支持 Markdown 与 CSV 下载。

## 快速启动

```powershell
python -m auto_paper.server
```

然后打开：

```text
http://127.0.0.1:8000
```

默认会创建一个遥感 Transformer 示例项目。你可以在页面里编辑项目画像，点击“搜索可缝合素材”后查看素材卡。第一版摘要、评分和缝合建议不依赖外部模型，但搜索需要当前网络可以访问 arXiv API。

深度分析不强制依赖模型。未配置 Key 时会使用规则模板，并明确提示尚未核验 PDF 与代码。需要启用 OpenAI 结构化分析时设置：

```powershell
$env:OPENAI_API_KEY="your-api-key"
$env:OPENAI_MODEL="gpt-5-mini"
python -m auto_paper.server
```

不要把 API Key 写入仓库；`.env.example` 只保留空占位。

## 命令行用法

运行所有启用主题：

```powershell
python -m auto_paper.server --run-once
```

指定端口：

```powershell
python -m auto_paper.server --host 0.0.0.0 --port 8000
```

## 项目结构

```text
auto_paper/
  arxiv_client.py    # arXiv 搜索
  database.py        # SQLite 表结构和读写
  deep_analyzer.py   # 规则/OpenAI 结构化深度缝合分析
  exporter.py        # Markdown/CSV 导出
  materializer.py    # 素材卡分类、评分与缝合动作建议
  quality.py         # 反馈重排与 Top 10 质量评估
  profile_validator.py # 项目画像一致性检查
  recommender.py     # 推荐分与推荐理由
  route_builder.py   # 方案篮子与实验路线生成
  scheduler.py       # 每日后台任务
  server.py          # HTTP API 与静态页面服务
  summarizer.py      # 摘要生成
docs/
  architecture.md    # MVP 架构设计
  iteration-loop.md  # 循环工程迭代方式
  material-workbench-mvp.md # 可缝合素材工作台设计
public/
  index.html
  styles.css
  app.js
```

## 下一轮迭代建议

1. 持续标注固定 Top 10，用真实反馈校准四级阈值与排序权重。
2. 解析 PDF 全文和架构图，替换当前仅基于摘要的证据边界。
3. 扩展 Semantic Scholar 与 Papers with Code，验证引用和真实代码仓库。
4. 增加轻量代码扫描，自动识别 backbone、neck、head、dataset，并把分析映射到真实文件。
