# auto_paper

一个面向快速迭代的论文追踪项目：每天按主题搜索论文，自动生成摘要和推荐排序，并提供网页预览与 Markdown/CSV 下载。

## 第一版能力

- 主题管理：配置多个论文主题和搜索关键词。
- 每日搜索：基于 arXiv API 拉取最新论文，可手动触发，也支持服务启动后的每日后台任务。
- 自动摘要：先用轻量启发式摘要跑通闭环，后续可替换为 LLM 总结。
- 推荐排序：结合关键词匹配、发布时间和摘要信号生成推荐分。
- 在线预览：内置 Web 页面查看主题、论文、摘要和推荐理由。
- 下载导出：支持 Markdown 与 CSV 下载。

## 快速启动

```powershell
python -m auto_paper.server
```

然后打开：

```text
http://127.0.0.1:8000
```

默认会创建一个 `AI Agent` 示例主题。你可以在页面里新增主题，点击“运行今日搜索”后查看论文。第一版摘要和推荐不依赖外部模型，但搜索需要当前网络可以访问 arXiv API。

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
  recommender.py     # 推荐分与推荐理由
  scheduler.py       # 每日后台任务
  server.py          # HTTP API 与静态页面服务
  summarizer.py      # 摘要生成
docs/
  architecture.md    # MVP 架构设计
  iteration-loop.md  # 循环工程迭代方式
public/
  index.html
  styles.css
  app.js
```

## 下一轮迭代建议

1. 接入 OpenAI/本地模型，把启发式摘要替换成结构化 LLM 总结。
2. 增加用户反馈按钮，让“感兴趣/不感兴趣”进入推荐权重。
3. 增加 GitHub Pages/Vercel/Render 部署配置，实现真正公网预览。
4. 扩展数据源：Semantic Scholar、OpenReview、PubMed、Papers With Code。
