# auto_paper

一个面向快速迭代的科研素材工作台：围绕当前研究项目画像搜索论文，把论文转成可缝合素材卡，辅助判断哪些 idea、模块和架构思想可以落地到自己的 pipeline。

## 第一版能力

- 项目画像：配置研究领域、任务、idea、backbone、neck、head、dataset。
- 每日搜索：基于 arXiv API 围绕项目画像拉取最新论文，可手动触发，也支持服务启动后的每日后台任务。
- 自动摘要：先用轻量启发式摘要跑通闭环，后续可替换为 LLM 总结。
- 素材卡：为论文生成可接入位置、二级标签、缝合动作、接入难度和证据来源。
- 三分排序：生成相关性、可缝合度、代码可用性三类评分，主排序使用可缝合度。
- 质量过滤：使用“领域门槛 + 跨领域可迁移条件”折叠低相关素材，并保留判定原因供人工复核。
- 人工反馈：支持标记有用、可缝合、不相关、已读，并持久化到 SQLite。
- 方案篮子：选择 3-5 张素材后，按接入顺序生成第一轮实验路线、验证步骤和风险提醒。
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
  exporter.py        # Markdown/CSV 导出
  materializer.py    # 素材卡分类、评分与缝合动作建议
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

1. 用人工反馈校准过滤阈值与推荐排序，验证 Top 10 有效率。
2. 接入 OpenAI/本地模型，增强素材卡的缝合动作和实验路线生成。
3. 扩展数据源：Semantic Scholar、Papers with Code、DBLP。
4. 增加轻量代码扫描，自动识别 backbone、neck、head、dataset。
