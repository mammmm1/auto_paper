const state = {
  projects: [],
  currentProjectId: null,
  materials: [],
  quality: null,
  profileCheck: null,
  showIrrelevant: false,
  viewMode: "top",
  areaFilter: "all",
  route: null,
  activeAnalysisPaperId: null,
};

const statusEl = document.querySelector("#status");
const projectsEl = document.querySelector("#projects");
const boardEl = document.querySelector("#board");
const metricsEl = document.querySelector("#board-metrics");
const profileSummaryEl = document.querySelector("#profile-summary");
const profileCheckEl = document.querySelector("#profile-check");
const formEl = document.querySelector("#project-form");
const basketPanelEl = document.querySelector("#basket-panel");
const basketItemsEl = document.querySelector("#basket-items");
const basketCountEl = document.querySelector("#basket-count");
const routeResultEl = document.querySelector("#route-result");
const filterSummaryEl = document.querySelector("#filter-summary");
const qualityMetricsEl = document.querySelector("#quality-metrics");
const analysisDrawerEl = document.querySelector("#analysis-drawer");
const analysisOverlayEl = document.querySelector("#analysis-overlay");
const analysisContentEl = document.querySelector("#analysis-content");
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
  updateProjectLinks();
}

async function loadMaterials() {
  if (!state.currentProjectId) {
    state.materials = [];
    state.quality = null;
    renderBoard();
    return;
  }
  const [materials, quality] = await Promise.all([
    api(`/api/papers?topic_id=${state.currentProjectId}&limit=500`),
    api(`/api/quality?topic_id=${state.currentProjectId}`),
  ]);
  state.materials = materials;
  state.quality = quality;
  renderBoard();
}

async function loadProfileCheck() {
  if (!state.currentProjectId) {
    state.profileCheck = null;
    renderProfileCheck();
    return;
  }
  state.profileCheck = await api(`/api/profile-check?topic_id=${state.currentProjectId}`);
  renderProfileCheck();
}

function updateProjectLinks() {
  const suffix = state.currentProjectId ? `&topic_id=${state.currentProjectId}` : "";
  document.querySelector("#export-markdown").href = `/api/export?format=markdown${suffix}`;
  document.querySelector("#export-csv").href = `/api/export?format=csv${suffix}`;
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

function renderProfileCheck() {
  const check = state.profileCheck;
  if (!check) {
    profileCheckEl.innerHTML = "";
    return;
  }
  const labels = {
    ready: "画像一致",
    warning: "需要确认",
    blocked: "信息不足",
  };
  const importantIssues = (check.issues || []).filter((issue) => issue.severity !== "info");
  const visibleIssues = importantIssues.length ? importantIssues : (check.issues || []).slice(0, 2);
  profileCheckEl.className = `profile-check profile-check-${check.status}`;
  profileCheckEl.innerHTML = `
    <div class="profile-check-score">
      <span>${escapeHtml(labels[check.status] || "画像检查")}</span>
      <strong>${Number(check.readiness_score || 0)}</strong>
    </div>
    <div class="profile-check-body">
      <strong>${escapeHtml(check.summary)}</strong>
      ${visibleIssues.length ? `
        <div class="profile-issues">
          ${visibleIssues.map((issue) => `
            <p><b>${escapeHtml(issue.message)}</b><span>${escapeHtml(issue.suggestion)}</span></p>
          `).join("")}
        </div>
      ` : '<p>任务、idea 与模型结构描述目前没有发现明显冲突。</p>'}
    </div>
  `;
}

function renderBoard() {
  renderMetrics();
  renderQuality();
  renderBasket();
  const hiddenCount = state.materials.filter((material) => !isRelevant(material)).length;
  const baseMaterials = state.showIrrelevant
    ? state.materials
    : state.materials.filter(isRelevant);
  const topIds = new Set(state.quality?.top_material_ids || []);
  let visibleMaterials = baseMaterials.filter((material) => {
    if (state.viewMode === "top") return topIds.has(material.id);
    if (state.viewMode === "code") return Number(material.code_availability_score || 0) >= 55;
    if (state.viewMode === "low") return material.stitch_difficulty === "低";
    return true;
  });
  if (state.areaFilter !== "all") {
    visibleMaterials = visibleMaterials.filter(
      (material) => material.integration_area === state.areaFilter,
    );
  }
  filterSummaryEl.textContent = `当前 ${visibleMaterials.length} 张 · 折叠 ${hiddenCount} 张参考/不相关素材`;
  if (visibleMaterials.length === 0) {
    boardEl.innerHTML = `
      <article class="empty-state">
        <strong>等待素材进入工作台</strong>
        <p>${state.materials.length ? "低相关素材已被折叠，可使用上方开关查看。" : "保存项目画像后运行搜索，系统会把论文转成按接入位置组织的素材卡。"}</p>
      </article>
    `;
    return;
  }
  boardEl.innerHTML = AREAS.map((area) => {
    const materials = visibleMaterials.filter((material) => material.integration_area === area);
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
  const relevant = state.materials.filter(isRelevant);
  const total = relevant.length;
  const best = relevant.reduce(
    (max, material) => Math.max(max, Number(material.ranking_score || 0)),
    0,
  );
  const codeReady = relevant.filter(
    (material) => Number(material.code_availability_score || 0) >= 55,
  ).length;
  const basketSize = state.materials.filter((material) => Boolean(material.in_basket)).length;
  metricsEl.innerHTML = `
    <div><span>有效素材</span><strong>${total}</strong></div>
    <div><span>最高排序分</span><strong>${best.toFixed(1)}</strong></div>
    <div><span>代码线索</span><strong>${codeReady}</strong></div>
    <div><span>方案篮子</span><strong>${basketSize}</strong></div>
  `;
}

function renderQuality() {
  const quality = state.quality;
  if (!quality) {
    qualityMetricsEl.innerHTML = "";
    return;
  }
  const usefulRate = quality.useful_rate === null ? "待标注" : `${quality.useful_rate.toFixed(0)}%`;
  const statusLabels = {
    collecting: "收集反馈中",
    on_track: "达到目标",
    needs_work: "需要优化",
  };
  qualityMetricsEl.innerHTML = `
    <div><span>Top 10 已标注</span><strong>${quality.labeled_count}/${quality.top_n}</strong></div>
    <div><span>正向反馈</span><strong>${quality.positive_count}</strong></div>
    <div><span>不相关反馈</span><strong>${quality.irrelevant_count}/${quality.targets.irrelevant_max}</strong></div>
    <div><span>标注内有效率</span><strong>${usefulRate}</strong></div>
    <div><span>质量状态</span><strong>${escapeHtml(statusLabels[quality.status] || "待判断")}</strong></div>
    <div><span>还需标注</span><strong>${quality.remaining_labels}</strong></div>
  `;
}

function renderMaterialCard(paper) {
  const rankingScore = Number(paper.ranking_score || paper.stitchability_score || 0);
  const feedback = paper.user_feedback || "";
  const tier = paper.relevance_tier || "reference";
  const hasAnalysis = Boolean(paper.deep_analysis_json);
  const tierLabels = {
    direct: "直接相关",
    transferable: "可迁移",
    reference: "仅供参考",
    irrelevant: "不相关",
  };
  return `
    <article class="material-card ${isRelevant(paper) ? "" : "low-relevance"}" data-material-id="${paper.id}">
      <div class="card-topline">
        <div class="card-flags">
          <span>${escapeHtml(paper.material_type)}</span>
          <span class="tier-flag tier-${escapeHtml(tier)}">${escapeHtml(tierLabels[tier] || "待判断")}</span>
          ${paper.is_read ? '<span class="read-flag">已读</span>' : ""}
          ${hasAnalysis ? '<span class="analysis-flag">已分析</span>' : ""}
        </div>
        <strong title="反馈重排分">${rankingScore.toFixed(1)}</strong>
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
      <p class="filter-reason">${escapeHtml(paper.filter_reason || "基于项目画像判断相关性")}</p>
      <p class="ranking-reason">排序：${escapeHtml(paper.ranking_reason || "基础评分")}</p>
      <details>
        <summary>摘要</summary>
        <p>${escapeHtml(paper.summary)}</p>
      </details>
      <div class="meta">
        <span>${escapeHtml(String(paper.published_at || "").slice(0, 10))}</span>
        <span>${escapeHtml(paper.authors)}</span>
      </div>
      <div class="links">
        <a href="${escapeHtml(paper.entry_url)}" target="_blank" rel="noreferrer">论文页</a>
        <a href="${escapeHtml(paper.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>
      </div>
      <div class="card-actions">
        <button class="compact analysis-button" data-action="analyze" type="button">${hasAnalysis ? "查看分析" : "深度分析"}</button>
        <button class="compact ghost ${feedback === "useful" ? "active" : ""}" data-action="feedback" data-value="useful" type="button">有用</button>
        <button class="compact ghost ${feedback === "stitchable" ? "active" : ""}" data-action="feedback" data-value="stitchable" type="button">可缝合</button>
        <button class="compact ghost ${feedback === "irrelevant" ? "active danger" : ""}" data-action="feedback" data-value="irrelevant" type="button">不相关</button>
        <button class="compact ghost ${paper.is_read ? "active" : ""}" data-action="read" type="button">已读</button>
        <button class="compact basket-button ${paper.in_basket ? "active" : ""}" data-action="basket" type="button">${paper.in_basket ? "移出方案" : "加入方案"}</button>
      </div>
    </article>
  `;
}

function openAnalysisDrawer(material, result) {
  const analysis = result.analysis;
  if (!analysis) return;
  state.activeAnalysisPaperId = material.id;
  const sourceLabels = {
    openai: "OpenAI 结构化分析",
    rules: "规则分析",
    rules_fallback: "规则降级分析",
  };
  document.querySelector("#analysis-title").textContent = material.title;
  document.querySelector("#analysis-meta").textContent = `${sourceLabels[result.source] || "深度分析"} · ${result.model || "未知模型"}${result.cache_hit ? " · 已命中缓存" : ""}`;
  analysisContentEl.innerHTML = `
    ${result.warning ? `<div class="analysis-warning">${escapeHtml(result.warning)}</div>` : ""}
    <section class="analysis-lead">
      <span class="analysis-area">${escapeHtml(analysis.integration_area)}</span>
      <strong>${escapeHtml(analysis.reusable_module)}</strong>
      <p>${escapeHtml(analysis.project_match)}</p>
    </section>
    <section class="analysis-section">
      <h4>问题与方法</h4>
      <dl class="analysis-definition">
        <div><dt>核心问题</dt><dd>${escapeHtml(analysis.core_problem)}</dd></div>
        <div><dt>方法摘要</dt><dd>${escapeHtml(analysis.method_summary)}</dd></div>
        <div><dt>预期收益</dt><dd>${escapeHtml(analysis.expected_gain)}</dd></div>
      </dl>
    </section>
    <section class="analysis-section">
      <h4>接入接口</h4>
      <div class="interface-grid">
        ${renderAnalysisList("输入", analysis.integration_interface?.inputs)}
        ${renderAnalysisList("输出", analysis.integration_interface?.outputs)}
        ${renderAnalysisList("代码改动", analysis.integration_interface?.code_changes)}
      </div>
    </section>
    <section class="analysis-section">
      <h4>最小实现</h4>
      <ol class="analysis-steps">
        ${(analysis.minimal_implementation || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
      </ol>
    </section>
    <section class="analysis-section">
      <h4>实验计划</h4>
      <div class="experiment-list">
        ${(analysis.experiment_plan || []).map((experiment) => `
          <article>
            <strong>${escapeHtml(experiment.name)}</strong>
            <p>${escapeHtml(experiment.change)}</p>
            <span>对照：${escapeHtml(experiment.control)}</span>
            <small>${(experiment.metrics || []).map(escapeHtml).join(" · ")}</small>
          </article>
        `).join("")}
      </div>
    </section>
    <section class="analysis-section analysis-two-column">
      ${renderAnalysisList("风险", analysis.risks)}
      ${renderAnalysisList("证据", analysis.evidence)}
    </section>
    <footer class="analysis-footer">
      <strong>置信度 ${Number(analysis.confidence || 0)}/100</strong>
      <p>${escapeHtml(analysis.limitations)}</p>
    </footer>
  `;
  analysisDrawerEl.hidden = false;
  analysisOverlayEl.hidden = false;
  document.body.classList.add("drawer-open");
}

function renderAnalysisList(title, items = []) {
  return `
    <div class="analysis-list">
      <strong>${escapeHtml(title)}</strong>
      ${(items || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("") || "<p>-</p>"}
    </div>
  `;
}

function closeAnalysisDrawer() {
  analysisDrawerEl.hidden = true;
  analysisOverlayEl.hidden = true;
  document.body.classList.remove("drawer-open");
}

async function analyzeMaterial(material, force = false) {
  setStatus(force ? "正在重新分析论文素材..." : "正在生成深度缝合分析...");
  const result = await api(`/api/analyze?paper_id=${material.id}${force ? "&force=1" : ""}`, {
    method: "POST",
  });
  openAnalysisDrawer(material, result);
  await loadMaterials();
  setStatus(result.warning || `${result.cache_hit ? "已打开" : "已生成"} ${result.source === "openai" ? "OpenAI" : "规则"}深度分析`);
}

function isRelevant(material) {
  if (["useful", "stitchable"].includes(material.user_feedback)) return true;
  if (material.user_feedback === "irrelevant") return false;
  return Boolean(material.is_relevant);
}

function renderBasket() {
  const selected = state.materials.filter((material) => Boolean(material.in_basket));
  basketCountEl.textContent = selected.length;
  if (selected.length === 0) {
    basketItemsEl.innerHTML = '<p class="basket-empty">还没有选择素材。建议先加入 3-5 张覆盖不同接入位置的卡片。</p>';
    routeResultEl.innerHTML = "";
    return;
  }
  basketItemsEl.innerHTML = selected
    .map(
      (material) => `
        <div class="basket-item">
          <span>${escapeHtml(material.integration_area)}</span>
          <strong>${escapeHtml(material.title)}</strong>
          <button class="icon-button ghost" data-remove-basket="${material.id}" type="button" title="移出方案" aria-label="移出方案">×</button>
        </div>
      `,
    )
    .join("");
}

function renderRoute() {
  const route = state.route;
  if (!route) {
    routeResultEl.innerHTML = "";
    return;
  }
  routeResultEl.innerHTML = `
    <div class="route-heading">
      <span class="summary-label">Generated Route</span>
      <h4>${escapeHtml(route.name)}</h4>
      <p>${escapeHtml(route.selection_summary)}</p>
    </div>
    <dl class="route-overview">
      <div><dt>研究假设</dt><dd>${escapeHtml(route.hypothesis)}</dd></div>
      <div><dt>基线</dt><dd>${escapeHtml(route.baseline)}</dd></div>
      <div><dt>数据集</dt><dd>${escapeHtml(route.dataset)}</dd></div>
      <div><dt>组合表述</dt><dd>${escapeHtml(route.innovation_statement)}</dd></div>
    </dl>
    <ol class="route-steps">
      ${route.steps.map((step) => `
        <li>
          <span>${escapeHtml(step.area)} · 难度 ${escapeHtml(step.difficulty)}</span>
          <strong>${escapeHtml(step.title)}</strong>
          <p>${escapeHtml(step.action)}</p>
        </li>
      `).join("")}
    </ol>
    <div class="route-notes">
      <div><strong>验证顺序</strong>${route.validation.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>
      <div><strong>风险提醒</strong>${route.risks.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</div>
    </div>
  `;
}

async function updateMaterial(material, payload) {
  await api(`/api/materials?id=${material.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.route = null;
  routeResultEl.innerHTML = "";
  await loadMaterials();
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
    await Promise.all([loadProfileCheck(), loadMaterials()]);
    setStatus("项目画像已保存");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
});

projectsEl.addEventListener("click", async (event) => {
  const item = event.target.closest("[data-project]");
  if (!item) return;
  state.currentProjectId = Number(item.dataset.project);
  state.route = null;
  renderProjects();
  fillProjectForm(currentProject());
  renderProfileSummary();
  try {
    await Promise.all([loadProfileCheck(), loadMaterials()]);
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
      const tiers = result.tier_counts || {};
      setStatus(`候选池 ${result.fetched_count} 张：直接相关 ${tiers.direct || 0}，可迁移 ${tiers.transferable || 0}，其余进入复核区`);
    }
  } catch (error) {
    setStatus(`搜索失败：${error.message}`);
  }
});

document.querySelector("#analyze-top").addEventListener("click", async () => {
  if (!state.currentProjectId) {
    setStatus("请先保存项目画像");
    return;
  }
  try {
    setStatus("正在分析 Top 10 素材...");
    const result = await api(`/api/analyze/top?topic_id=${state.currentProjectId}`, { method: "POST" });
    state.profileCheck = result.profile_check;
    renderProfileCheck();
    await loadMaterials();
    setStatus(`Top 10 已分析 ${result.analyzed_count} 张，其中 ${result.cached_count} 张命中缓存`);
  } catch (error) {
    setStatus(`批量分析失败：${error.message}`);
  }
});

document.querySelector("#refresh-projects").addEventListener("click", loadProjects);

document.querySelector("#show-irrelevant").addEventListener("change", (event) => {
  state.showIrrelevant = event.target.checked;
  renderBoard();
});

document.querySelector("#view-modes").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button) return;
  state.viewMode = button.dataset.view;
  document.querySelectorAll("#view-modes [data-view]").forEach((item) => {
    item.classList.toggle("active", item === button);
  });
  renderBoard();
});

document.querySelector("#area-filter").addEventListener("change", (event) => {
  state.areaFilter = event.target.value;
  renderBoard();
});

document.querySelector("#toggle-basket").addEventListener("click", () => {
  basketPanelEl.hidden = !basketPanelEl.hidden;
});

document.querySelector("#close-basket").addEventListener("click", () => {
  basketPanelEl.hidden = true;
});

document.querySelector("#generate-route").addEventListener("click", async () => {
  const selected = state.materials.filter((material) => Boolean(material.in_basket));
  if (selected.length === 0) {
    setStatus("请先把素材加入方案篮子");
    return;
  }
  try {
    setStatus("正在整理第一轮实验路线...");
    state.route = await api(`/api/basket/route?topic_id=${state.currentProjectId}`);
    renderRoute();
    setStatus(`实验路线已生成，共 ${state.route.steps.length} 个接入步骤`);
  } catch (error) {
    setStatus(`生成失败：${error.message}`);
  }
});

boardEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const card = button.closest("[data-material-id]");
  const material = state.materials.find((item) => item.id === Number(card?.dataset.materialId));
  if (!material) return;
  try {
    if (button.dataset.action === "feedback") {
      const value = material.user_feedback === button.dataset.value ? "" : button.dataset.value;
      await updateMaterial(material, { user_feedback: value });
      setStatus(value === "irrelevant" ? "已标记为不相关并折叠" : "素材反馈已记录");
    } else if (button.dataset.action === "read") {
      await updateMaterial(material, { is_read: !Boolean(material.is_read) });
      setStatus("阅读状态已更新");
    } else if (button.dataset.action === "basket") {
      await updateMaterial(material, { in_basket: !Boolean(material.in_basket) });
      setStatus(material.in_basket ? "已移出方案篮子" : "已加入方案篮子");
    } else if (button.dataset.action === "analyze") {
      await analyzeMaterial(material);
    }
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});

document.querySelector("#close-analysis").addEventListener("click", closeAnalysisDrawer);
analysisOverlayEl.addEventListener("click", closeAnalysisDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !analysisDrawerEl.hidden) closeAnalysisDrawer();
});

document.querySelector("#refresh-analysis").addEventListener("click", async () => {
  const material = state.materials.find((item) => item.id === state.activeAnalysisPaperId);
  if (!material) return;
  try {
    await analyzeMaterial(material, true);
  } catch (error) {
    setStatus(`重新分析失败：${error.message}`);
  }
});

basketItemsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remove-basket]");
  if (!button) return;
  const material = state.materials.find((item) => item.id === Number(button.dataset.removeBasket));
  if (!material) return;
  try {
    await updateMaterial(material, { in_basket: false });
    setStatus("已移出方案篮子");
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});

async function boot() {
  try {
    await loadProjects();
    await Promise.all([loadProfileCheck(), loadMaterials()]);
    setStatus("准备就绪");
  } catch (error) {
    setStatus(`加载失败：${error.message}`);
  }
}

boot();
