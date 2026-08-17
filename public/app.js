const state = {
  projects: [],
  currentProjectId: null,
  materials: [],
};

const statusEl = document.querySelector("#status");
const projectsEl = document.querySelector("#projects");
const boardEl = document.querySelector("#board");
const metricsEl = document.querySelector("#board-metrics");
const profileSummaryEl = document.querySelector("#profile-summary");
const formEl = document.querySelector("#project-form");
const AREAS = ["Backbone", "Neck", "Head", "Loss", "Data", "Training", "Experiment"];
const AREA_LABELS = {
  Backbone: "骨干",
  Neck: "融合",
  Head: "预测",
  Loss: "损失",
  Data: "数据",
  Training: "训练",
  Experiment: "实验",
};
const AREA_MARKS = {
  Backbone: "BB",
  Neck: "NK",
  Head: "HD",
  Loss: "LS",
  Data: "DT",
  Training: "TR",
  Experiment: "EX",
};

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

async function loadProjects() {
  state.projects = await api("/api/projects");
  if (!state.currentProjectId && state.projects.length) {
    const completeProject = state.projects.find(
      (project) => project.idea || project.domain || project.backbone,
    );
    state.currentProjectId = (completeProject || state.projects[0]).id;
  }
  renderProjects();
  fillProjectForm(currentProject());
  renderProfileSummary();
}

async function loadMaterials() {
  const query = state.currentProjectId ? `?topic_id=${state.currentProjectId}` : "";
  state.materials = await api(`/api/papers${query}`);
  renderBoard();
}

function currentProject() {
  return state.projects.find((project) => project.id === state.currentProjectId) || state.projects[0];
}

function renderProjects() {
  if (state.projects.length === 0) {
    projectsEl.innerHTML = '<p class="meta">还没有项目。</p>';
    return;
  }
  projectsEl.innerHTML = state.projects
    .map(
      (project) => `
        <article class="project-item ${project.id === state.currentProjectId ? "active" : ""}" data-project="${project.id}">
          <strong>${escapeHtml(project.name)}</strong>
          <span>${escapeHtml(project.task_type || "未填写任务")} · ${escapeHtml(project.backbone || "未填写 backbone")}</span>
          <code>${escapeHtml(project.keywords || project.query)}</code>
        </article>
      `,
    )
    .join("");
}

function renderProfileSummary() {
  const project = currentProject();
  if (!project) {
    profileSummaryEl.innerHTML = "";
    return;
  }
  profileSummaryEl.innerHTML = `
    <div class="profile-hero">
      <span class="summary-label">当前项目</span>
      <strong>${escapeHtml(project.name)}</strong>
      <p>${escapeHtml(project.idea || "未填写 idea")}</p>
    </div>
    <div class="profile-cell"><span>领域</span><strong>${escapeHtml(project.domain || "-")}</strong></div>
    <div class="profile-cell"><span>任务</span><strong>${escapeHtml(project.task_type || "-")}</strong></div>
    <div class="profile-cell"><span>Backbone</span><strong>${escapeHtml(project.backbone || "-")}</strong></div>
    <div class="profile-cell"><span>Neck</span><strong>${escapeHtml(project.neck || "-")}</strong></div>
    <div class="profile-cell"><span>Dataset</span><strong>${escapeHtml(project.dataset || "-")}</strong></div>
  `;
}

function renderBoard() {
  renderMetrics();
  if (state.materials.length === 0) {
    boardEl.innerHTML = `
      <article class="empty-state">
        <strong>等待素材进入工作台</strong>
        <p>保存项目画像后运行搜索，系统会把论文转成按接入位置组织的素材卡。</p>
      </article>
    `;
    return;
  }
  boardEl.innerHTML = AREAS.map((area) => {
    const materials = state.materials.filter((material) => material.integration_area === area);
    return `
      <section class="board-column" data-area="${area}">
        <header>
          <div>
            <b>${AREA_MARKS[area]}</b>
            <h3>${area}</h3>
            <p>${AREA_LABELS[area]}</p>
          </div>
          <span>${materials.length}</span>
        </header>
        <div class="column-items">
          ${
            materials.length
              ? materials.map(renderMaterialCard).join("")
              : '<p class="column-empty">暂无素材</p>'
          }
        </div>
      </section>
    `;
  }).join("");
}

function renderMetrics() {
  const total = state.materials.length;
  const best = state.materials.reduce(
    (max, material) => Math.max(max, Number(material.stitchability_score || 0)),
    0,
  );
  const codeReady = state.materials.filter(
    (material) => Number(material.code_availability_score || 0) >= 55,
  ).length;
  metricsEl.innerHTML = `
    <div><span>素材卡</span><strong>${total}</strong></div>
    <div><span>最高缝合度</span><strong>${best.toFixed(1)}</strong></div>
    <div><span>代码线索</span><strong>${codeReady}</strong></div>
  `;
}

function renderMaterialCard(paper) {
  const stitchScore = Number(paper.stitchability_score || paper.recommendation_score || 0);
  return `
    <article class="material-card">
      <div class="card-topline">
        <span>${escapeHtml(paper.material_type)}</span>
        <strong>${stitchScore.toFixed(1)}</strong>
      </div>
      <h4>${escapeHtml(paper.title)}</h4>
      <div class="tag-row">
        <span>${escapeHtml(paper.integration_subtag || "General")}</span>
        <span>难度 ${escapeHtml(paper.stitch_difficulty || "中")}</span>
      </div>
      <dl class="score-grid">
        <div><dt>相关</dt><dd>${Number(paper.relevance_score || 0).toFixed(1)}</dd></div>
        <div><dt>缝合</dt><dd>${Number(paper.stitchability_score || 0).toFixed(1)}</dd></div>
        <div><dt>代码</dt><dd>${Number(paper.code_availability_score || 0).toFixed(1)}</dd></div>
      </dl>
      <p class="action-text">${escapeHtml(paper.stitch_action || paper.recommendation_reason)}</p>
      <p class="evidence"><strong>${escapeHtml(paper.evidence_sources || "证据")}</strong>：${escapeHtml(paper.evidence_quote || paper.summary)}</p>
      <details>
        <summary>摘要</summary>
        <p>${escapeHtml(paper.summary)}</p>
      </details>
      <div class="meta">
        <span>${escapeHtml(String(paper.published_at || "").slice(0, 10))}</span>
        <span>${escapeHtml(paper.authors)}</span>
      </div>
      <div class="links">
        <a href="${paper.entry_url}" target="_blank" rel="noreferrer">论文页</a>
        <a href="${paper.pdf_url}" target="_blank" rel="noreferrer">PDF</a>
      </div>
    </article>
  `;
}

function fillProjectForm(project) {
  if (!project) return;
  for (const field of [
    "id",
    "name",
    "domain",
    "task_type",
    "idea",
    "keywords",
    "backbone",
    "neck",
    "head",
    "dataset",
    "max_results",
  ]) {
    if (formEl.elements[field]) {
      formEl.elements[field].value = project[field] || "";
    }
  }
}

function projectPayloadFromForm() {
  const form = new FormData(formEl);
  return {
    name: form.get("name"),
    domain: form.get("domain"),
    task_type: form.get("task_type"),
    idea: form.get("idea"),
    keywords: form.get("keywords"),
    backbone: form.get("backbone"),
    neck: form.get("neck"),
    head: form.get("head"),
    dataset: form.get("dataset"),
    max_results: Number(form.get("max_results") || 20),
  };
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
  const payload = projectPayloadFromForm();
  const id = formEl.elements.id.value;
  try {
    setStatus("正在保存项目画像...");
    const saved = id
      ? await api(`/api/projects?id=${id}`, { method: "PUT", body: JSON.stringify(payload) })
      : await api("/api/projects", { method: "POST", body: JSON.stringify(payload) });
    state.currentProjectId = saved.id;
    await loadProjects();
    setStatus("项目画像已保存");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
});

projectsEl.addEventListener("click", async (event) => {
  const item = event.target.closest("[data-project]");
  if (!item) return;
  state.currentProjectId = Number(item.dataset.project);
  renderProjects();
  fillProjectForm(currentProject());
  renderProfileSummary();
  try {
    await loadMaterials();
    setStatus("已切换项目");
  } catch (error) {
    setStatus(`切换失败：${error.message}`);
  }
});

document.querySelector("#run-search").addEventListener("click", async () => {
  const project = currentProject();
  if (!project) {
    setStatus("请先保存项目画像");
    return;
  }
  try {
    setStatus("正在搜索论文并生成素材卡...");
    const result = await api(`/api/run?topic_id=${project.id}`, { method: "POST" });
    await loadMaterials();
    if (result.errors?.length) {
      setStatus(`完成 ${result.fetched_count} 张素材卡，部分失败：${result.errors.join("；")}`);
    } else {
      setStatus(`搜索完成：${result.fetched_count} 张素材卡`);
    }
  } catch (error) {
    setStatus(`搜索失败：${error.message}`);
  }
});

document.querySelector("#refresh-projects").addEventListener("click", loadProjects);

async function boot() {
  try {
    await loadProjects();
    await loadMaterials();
    setStatus("准备就绪");
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  }
}

boot();
