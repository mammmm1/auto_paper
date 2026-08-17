const state = {
  topics: [],
  papers: [],
};

const statusEl = document.querySelector("#status");
const topicsEl = document.querySelector("#topics");
const papersEl = document.querySelector("#papers");
const formEl = document.querySelector("#topic-form");

function setStatus(message) {
  statusEl.textContent = message;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(error.error || response.statusText);
  }
  return response.json();
}

async function loadTopics() {
  state.topics = await api("/api/topics");
  renderTopics();
}

async function loadPapers() {
  state.papers = await api("/api/papers");
  renderPapers();
}

function renderTopics() {
  if (state.topics.length === 0) {
    topicsEl.innerHTML = '<p class="meta">还没有主题。</p>';
    return;
  }
  topicsEl.innerHTML = state.topics
    .map(
      (topic) => `
        <article class="topic-item">
          <strong>${escapeHtml(topic.name)}</strong>
          <code>${escapeHtml(topic.query)}</code>
          <div class="meta">每次 ${topic.max_results} 篇</div>
          <button class="ghost" type="button" data-delete-topic="${topic.id}">删除</button>
        </article>
      `,
    )
    .join("");
}

function renderPapers() {
  if (state.papers.length === 0) {
    papersEl.innerHTML = '<article class="paper"><p class="meta">还没有论文结果，先运行今日搜索。</p></article>';
    return;
  }
  papersEl.innerHTML = state.papers
    .map(
      (paper) => `
        <article class="paper">
          <div class="paper-head">
            <h3>${escapeHtml(paper.title)}</h3>
            <div class="score">${Number(paper.recommendation_score).toFixed(1)}</div>
          </div>
          <div class="meta">
            <span>${escapeHtml(paper.topic_name)}</span>
            <span>${escapeHtml(paper.published_at.slice(0, 10))}</span>
            <span>${escapeHtml(paper.authors)}</span>
          </div>
          <p class="summary">${escapeHtml(paper.summary)}</p>
          <p class="reason">${escapeHtml(paper.recommendation_reason)}</p>
          <div class="links">
            <a href="${paper.entry_url}" target="_blank" rel="noreferrer">论文页</a>
            <a href="${paper.pdf_url}" target="_blank" rel="noreferrer">PDF</a>
          </div>
        </article>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

formEl.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(formEl);
  const payload = {
    name: form.get("name"),
    query: form.get("query"),
    max_results: Number(form.get("max_results") || 10),
  };
  try {
    setStatus("正在新增主题...");
    await api("/api/topics", { method: "POST", body: JSON.stringify(payload) });
    formEl.reset();
    await loadTopics();
    setStatus("主题已新增");
  } catch (error) {
    setStatus(`新增失败：${error.message}`);
  }
});

topicsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-topic]");
  if (!button) return;
  try {
    setStatus("正在删除主题...");
    await api(`/api/topics?id=${button.dataset.deleteTopic}`, { method: "DELETE" });
    await loadTopics();
    await loadPapers();
    setStatus("主题已删除");
  } catch (error) {
    setStatus(`删除失败：${error.message}`);
  }
});

document.querySelector("#run-search").addEventListener("click", async () => {
  try {
    setStatus("正在搜索论文并生成摘要...");
    const result = await api("/api/run", { method: "POST" });
    await loadPapers();
    if (result.errors?.length) {
      setStatus(`完成 ${result.fetched_count} 篇，部分失败：${result.errors.join("；")}`);
    } else {
      setStatus(`搜索完成：${result.fetched_count} 篇`);
    }
  } catch (error) {
    setStatus(`搜索失败：${error.message}`);
  }
});

document.querySelector("#refresh-topics").addEventListener("click", loadTopics);

async function boot() {
  try {
    await loadTopics();
    await loadPapers();
    setStatus("准备就绪");
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  }
}

boot();

