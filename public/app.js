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
  synthesis: null,
  activeSynthesisSchemeId: "balanced",
  activeAnalysisPaperId: null,
  busy: false,
};

const AREAS = ["Backbone", "Neck", "Head", "Loss", "Data", "Training", "Experiment"];
const AREA_LABELS = {
  Backbone: "骨干网络",
  Neck: "特征融合",
  Head: "任务预测",
  Loss: "损失函数",
  Data: "数据流程",
  Training: "训练策略",
  Experiment: "实验设计",
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

const statusEl = document.querySelector("#status");
const projectsEl = document.querySelector("#projects");
const boardEl = document.querySelector("#board");
const metricsEl = document.querySelector("#board-metrics");
const profileSummaryEl = document.querySelector("#profile-summary");
const profileCheckEl = document.querySelector("#profile-check");
const formEl = document.querySelector("#project-form");
const profileDialogEl = document.querySelector("#profile-dialog");
const basketPanelEl = document.querySelector("#basket-panel");
const basketOverlayEl = document.querySelector("#basket-overlay");
const basketItemsEl = document.querySelector("#basket-items");
const basketCountEl = document.querySelector("#basket-count");
const basketSummaryEl = document.querySelector("#basket-summary");
const routeResultEl = document.querySelector("#route-result");
const filterSummaryEl = document.querySelector("#filter-summary");
const qualityMetricsEl = document.querySelector("#quality-metrics");
const analysisDrawerEl = document.querySelector("#analysis-drawer");
const analysisOverlayEl = document.querySelector("#analysis-overlay");
const analysisContentEl = document.querySelector("#analysis-content");
const synthesisDrawerEl = document.querySelector("#synthesis-drawer");
const synthesisOverlayEl = document.querySelector("#synthesis-overlay");
const synthesisContentEl = document.querySelector("#synthesis-content");
const runWorkflowEl = document.querySelector("#run-workflow");

function setStatus(message) {
  statusEl.textContent = message;
}

function setBusy(busy) {
  state.busy = busy;
  runWorkflowEl.disabled = busy;
  runWorkflowEl.textContent = busy ? "流程运行中..." : "运行完整流程";
  document.querySelectorAll("[data-stage]").forEach((button) => {
    button.disabled = busy;
  });
  document.body.toggleAttribute("aria-busy", busy);
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

function currentProject() {
  return state.projects.find((project) => project.id === state.currentProjectId) || null;
}

function updateProjectLinks() {
  const suffix = state.currentProjectId ? `&topic_id=${state.currentProjectId}` : "";
  document.querySelector("#export-markdown").href = `/api/export?format=markdown${suffix}`;
  document.querySelector("#export-csv").href = `/api/export?format=csv${suffix}`;
}

function renderProjects() {
  if (!state.projects.length) {
    projectsEl.innerHTML = '<p class="sidebar-empty">暂无项目</p>';
    return;
  }
  projectsEl.innerHTML = state.projects
    .map(
      (project) => `
        <button class="project-item ${project.id === state.currentProjectId ? "active" : ""}" data-project="${project.id}" type="button">
          <span class="project-initial">${escapeHtml((project.name || "P").slice(0, 1))}</span>
          <span class="project-copy">
            <strong>${escapeHtml(project.name)}</strong>
            <small>${escapeHtml(project.task_type || "未设置任务")} · ${escapeHtml(project.dataset || "未设置数据集")}</small>
          </span>
        </button>
      `,
    )
    .join("");
}

function renderProfileSummary() {
  const project = currentProject();
  document.querySelector("#current-project-name").textContent = project?.name || "未选择项目";
  if (!project) {
    profileSummaryEl.innerHTML = '<strong>请选择或新建项目</strong>';
    return;
  }
  profileSummaryEl.innerHTML = `
    <div class="profile-idea">
      <span>研究假设</span>
      <strong>${escapeHtml(project.idea || "尚未填写研究假设")}</strong>
    </div>
    <div class="pipeline-tags">
      <span>${escapeHtml(project.task_type || "未设置任务")}</span>
      <span>${escapeHtml(project.backbone || "Backbone 未设置")}</span>
      <span>${escapeHtml(project.neck || "Neck 未设置")}</span>
      <span>${escapeHtml(project.head || "Head 未设置")}</span>
      <span>${escapeHtml(project.dataset || "Dataset 未设置")}</span>
    </div>
  `;
}

function renderProfileCheck() {
  const check = state.profileCheck;
  if (!check) {
    profileCheckEl.innerHTML = "";
    return;
  }
  const important = (check.issues || []).find((issue) => issue.severity !== "info");
  const labels = { ready: "画像一致", warning: "画像待确认", blocked: "画像不完整" };
  profileCheckEl.className = `profile-check profile-check-${check.status}`;
  profileCheckEl.innerHTML = `
    <span class="profile-status-dot"></span>
    <div>
      <strong>${escapeHtml(labels[check.status] || "画像检查")} · ${Number(check.readiness_score || 0)}</strong>
      <p>${escapeHtml(important?.message || check.summary)}</p>
    </div>
  `;
}

function renderBoard() {
  renderMetrics();
  renderQuality();
  renderBasket();
  renderWorkflowState();

  const hiddenCount = state.materials.filter((material) => !isRelevant(material)).length;
  const baseMaterials = state.showIrrelevant
    ? state.materials
    : state.materials.filter(isRelevant);
  const topIds = new Set(state.quality?.top_material_ids || []);
  let visibleMaterials = baseMaterials.filter((material) => {
    if (state.viewMode === "top") return topIds.has(material.id);
    if (state.viewMode === "code") {
      return parseEvidence(material)?.code?.status === "verified_repository";
    }
    if (state.viewMode === "low") return material.stitch_difficulty === "低";
    return true;
  });
  if (state.areaFilter !== "all") {
    visibleMaterials = visibleMaterials.filter(
      (material) => material.integration_area === state.areaFilter,
    );
  }

  filterSummaryEl.textContent = `${visibleMaterials.length} 张素材${hiddenCount ? ` · ${hiddenCount} 张参考项已隐藏` : ""}`;
  if (!visibleMaterials.length) {
    boardEl.innerHTML = `
      <div class="empty-state">
        <strong>${state.materials.length ? "当前筛选没有素材" : "还没有论文素材"}</strong>
        <p>${state.materials.length ? "调整视图或接入位置后重新查看。" : "运行完整流程后，素材会出现在这里。"}</p>
      </div>
    `;
    return;
  }

  boardEl.innerHTML = AREAS.map((area) => {
    const materials = visibleMaterials.filter((material) => material.integration_area === area);
    if (!materials.length) return "";
    return `
      <section class="material-group" data-area="${area}">
        <header class="group-header">
          <span class="area-mark">${AREA_MARKS[area]}</span>
          <div><strong>${area}</strong><small>${AREA_LABELS[area]}</small></div>
          <b>${materials.length}</b>
        </header>
        <div class="material-list">${materials.map(renderMaterialRow).join("")}</div>
      </section>
    `;
  }).join("");
}

function renderMetrics() {
  const relevant = state.materials.filter(isRelevant);
  const evidenceReady = relevant.filter((item) => item.full_text_status === "verified").length;
  const analyzed = relevant.filter((item) => Boolean(item.deep_analysis_json)).length;
  const codeReady = relevant.filter(
    (item) => parseEvidence(item)?.code?.status === "verified_repository",
  ).length;
  const basketSize = state.materials.filter((item) => Boolean(item.in_basket)).length;
  metricsEl.innerHTML = [
    ["有效素材", relevant.length],
    ["全文", evidenceReady],
    ["已分析", analyzed],
    ["代码仓库", codeReady],
    ["方案", basketSize],
  ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join("");
}

function renderQuality() {
  const quality = state.quality;
  if (!quality) {
    qualityMetricsEl.innerHTML = "";
    return;
  }
  const statusLabels = {
    collecting: "收集反馈中",
    on_track: "达到目标",
    needs_work: "需要优化",
  };
  document.querySelector("#quality-status").textContent = statusLabels[quality.status] || "待判断";
  const coverage = quality.top_n ? Math.round(quality.labeled_count / quality.top_n * 100) : 0;
  document.querySelector("#quality-progress-bar").style.width = `${coverage}%`;
  qualityMetricsEl.innerHTML = `
    <span><b>${quality.labeled_count}/${quality.top_n}</b> 已标注</span>
    <span><b>${quality.positive_count}</b> 正向</span>
    <span><b>${quality.irrelevant_count}</b> 不相关</span>
  `;
}

function renderWorkflowState(active = "") {
  const topIds = new Set(state.quality?.top_material_ids || []);
  const topMaterials = state.materials.filter((item) => topIds.has(item.id));
  const ready = {
    search: state.materials.length > 0,
    evidence: topMaterials.length > 0 && topMaterials.every(
      (item) => ["verified", "text_insufficient"].includes(item.full_text_status),
    ),
    analysis: topMaterials.length > 0 && topMaterials.every((item) => item.deep_analysis_json),
    synthesis: Boolean(
      state.synthesis && Number(state.synthesis.project_id) === Number(state.currentProjectId),
    ),
  };
  document.querySelectorAll("[data-workflow-step]").forEach((step) => {
    const name = step.dataset.workflowStep;
    step.dataset.status = name === active ? "active" : ready[name] ? "complete" : "pending";
  });
}

function parseVenueRankings(paper) {
  if (Array.isArray(paper.venue_rankings)) return paper.venue_rankings;
  try {
    const value = JSON.parse(paper.venue_rankings_json || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

function venueTypeLabel(value) {
  return {
    conference: "会议",
    journal: "期刊",
    preprint: "预印本",
  }[value] || "来源待核验";
}

function venueStatusLabel(value) {
  return {
    published: "已发表",
    accepted: "已录用 · 作者声明",
    preprint: "仅预印本",
  }[value] || "状态待核验";
}

function renderVenueRanks(paper) {
  const rankings = parseVenueRankings(paper);
  if (!rankings.length) return '<span class="venue-rank venue-rank-unrated">未定级</span>';
  return rankings.map((ranking) => {
    const rankClass = `${ranking.system || "rank"}-${ranking.rank || ""}`
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-");
    const title = [
      ranking.index,
      ranking.system,
      ranking.rank,
      ranking.year,
      ranking.category,
    ].filter(Boolean).join(" · ");
    const label = escapeHtml(ranking.label || `${ranking.system} ${ranking.rank}`);
    const sourceUrl = safeExternalUrl(ranking.source_url);
    if (sourceUrl === "#") {
      return `<span class="venue-rank venue-rank-${rankClass}" title="${escapeHtml(title)}">${label}</span>`;
    }
    return `<a class="venue-rank venue-rank-${rankClass}" href="${sourceUrl}" target="_blank" rel="noreferrer" title="${escapeHtml(title)} · 查看评级来源">${label}</a>`;
  }).join("");
}

function renderMaterialRow(paper) {
  const rank = state.materials.findIndex((item) => item.id === paper.id) + 1;
  const rankingScore = Number(paper.ranking_score || paper.stitchability_score || 0);
  const feedback = paper.user_feedback || "";
  const tier = paper.relevance_tier || "reference";
  const evidenceStatus = paper.full_text_status || "";
  const evidence = parseEvidence(paper);
  const codeStatus = evidence?.code?.status || "not_found";
  const hasEvidence = ["verified", "text_insufficient"].includes(evidenceStatus);
  const hasAnalysis = Boolean(paper.deep_analysis_json);
  const venueName = paper.venue_name || "arXiv";
  const venueStatus = venueStatusLabel(paper.venue_status || "preprint");
  const venueRanks = renderVenueRanks(paper);
  const tierLabels = {
    direct: "直接相关",
    transferable: "可迁移",
    reference: "参考",
    irrelevant: "不相关",
  };
  const evidenceLabels = {
    verified: "全文已核验",
    text_insufficient: "文本不足",
    failed: "核验失败",
  };
  const mainAction = hasEvidence ? "analyze" : "evidence";
  const mainLabel = hasEvidence ? (hasAnalysis ? "查看分析" : "生成分析") : (evidenceStatus === "failed" ? "重试核验" : "核验全文");

  return `
    <article class="material-row ${isRelevant(paper) ? "" : "low-relevance"}" data-material-id="${paper.id}">
      <div class="rank-cell"><strong>${rankingScore.toFixed(1)}</strong><span>#${rank || "-"}</span></div>
      <div class="material-main">
        <div class="material-flags">
          <span class="tier-${escapeHtml(tier)}">${escapeHtml(tierLabels[tier] || "待判断")}</span>
          <span>${escapeHtml(paper.material_type || "idea")}</span>
          <span>${escapeHtml(paper.integration_subtag || "General")}</span>
          ${paper.is_read ? '<span class="state-read">已读</span>' : ""}
        </div>
        <h3>${escapeHtml(paper.title)}</h3>
        <div class="publication-line">
          <span class="venue-kind">${escapeHtml(venueTypeLabel(paper.venue_type || "preprint"))}</span>
          <strong title="${escapeHtml(paper.journal_ref || venueName)}">${escapeHtml(venueName)}</strong>
          <span class="venue-ranks">${venueRanks}</span>
          <small>${escapeHtml(venueStatus)}</small>
        </div>
        <p>${escapeHtml(paper.stitch_action || paper.recommendation_reason)}</p>
        <small>${escapeHtml(String(paper.published_at || "").slice(0, 10))} · ${escapeHtml(paper.authors)}</small>
      </div>
      <dl class="material-scores">
        <div><dt>相关</dt><dd>${Number(paper.relevance_score || 0).toFixed(0)}</dd></div>
        <div><dt>缝合</dt><dd>${Number(paper.stitchability_score || 0).toFixed(0)}</dd></div>
        <div><dt>代码</dt><dd>${Number(paper.code_availability_score || 0).toFixed(0)}</dd></div>
      </dl>
      <div class="material-status">
        <span class="status-${escapeHtml(evidenceStatus || "pending")}">${escapeHtml(evidenceLabels[evidenceStatus] || "未核验全文")}</span>
        <span class="status-${codeStatus === "verified_repository" ? "verified" : "muted"}">${codeStatus === "verified_repository" ? "仓库可访问" : "无已验证仓库"}</span>
        <small>接入难度 ${escapeHtml(paper.stitch_difficulty || "中")}</small>
      </div>
      <div class="row-actions">
        <button class="row-primary" data-action="${mainAction}" type="button">${mainLabel}</button>
        <button class="row-secondary ${paper.in_basket ? "active" : ""}" data-action="basket" type="button">${paper.in_basket ? "已加入" : "加入方案"}</button>
      </div>
      <details class="material-detail">
        <summary>查看详情与反馈</summary>
        <div class="detail-content">
          <div class="detail-grid">
            <section><span>发表信息</span><p>${escapeHtml(venueName)} · ${escapeHtml(venueTypeLabel(paper.venue_type))} · ${escapeHtml(paper.venue_rank || "未定级")} · ${escapeHtml(venueStatus)}<br>元数据：${escapeHtml(paper.venue_source || "arXiv")}${paper.doi ? `<br>DOI：${escapeHtml(paper.doi)}` : ""}</p></section>
            <section><span>判断依据</span><p>${escapeHtml(paper.filter_reason || paper.ranking_reason || "基于项目画像判断")}</p></section>
            <section><span>关键证据</span><p>${escapeHtml(paper.evidence_quote || paper.summary)}</p></section>
            <section class="detail-summary"><span>摘要</span><p>${escapeHtml(paper.summary)}</p></section>
          </div>
          <footer class="detail-actions">
            <div class="paper-links">
              <a href="${safeExternalUrl(paper.entry_url)}" target="_blank" rel="noreferrer">论文页</a>
              <a href="${safeExternalUrl(paper.pdf_url)}" target="_blank" rel="noreferrer">PDF</a>
              ${paper.doi ? `<a href="${safeExternalUrl(`https://doi.org/${paper.doi}`)}" target="_blank" rel="noreferrer">DOI</a>` : ""}
              <button data-action="evidence" type="button">${hasEvidence ? "证据详情" : "核验全文"}</button>
            </div>
            <div class="feedback-control" aria-label="素材反馈">
              <button class="${feedback === "useful" ? "active" : ""}" data-action="feedback" data-value="useful" type="button">有用</button>
              <button class="${feedback === "stitchable" ? "active" : ""}" data-action="feedback" data-value="stitchable" type="button">可缝合</button>
              <button class="${feedback === "irrelevant" ? "active danger" : ""}" data-action="feedback" data-value="irrelevant" type="button">不相关</button>
              <button class="${paper.is_read ? "active" : ""}" data-action="read" type="button">${paper.is_read ? "已读" : "标记已读"}</button>
            </div>
          </footer>
        </div>
      </details>
    </article>
  `;
}

function renderBasket() {
  const selected = state.materials.filter((material) => Boolean(material.in_basket));
  basketCountEl.textContent = selected.length;
  basketSummaryEl.textContent = `${selected.length} 张素材`;
  if (!selected.length) {
    basketItemsEl.innerHTML = '<div class="basket-empty"><strong>方案篮子为空</strong><p>从素材列表中加入候选模块。</p></div>';
    routeResultEl.innerHTML = "";
    return;
  }
  basketItemsEl.innerHTML = selected.map((material) => `
    <div class="basket-item">
      <span>${escapeHtml(material.integration_area)}</span>
      <strong>${escapeHtml(material.title)}</strong>
      <button class="icon-button" data-remove-basket="${material.id}" type="button" title="移出方案" aria-label="移出方案">×</button>
    </div>
  `).join("");
}

function renderRoute() {
  const route = state.route;
  if (!route) {
    routeResultEl.innerHTML = "";
    return;
  }
  routeResultEl.innerHTML = `
    <section class="route-heading">
      <span>Generated Route</span>
      <h3>${escapeHtml(route.name)}</h3>
      <p>${escapeHtml(route.selection_summary)}</p>
    </section>
    <dl class="route-overview">
      <div><dt>研究假设</dt><dd>${escapeHtml(route.hypothesis)}</dd></div>
      <div><dt>基线</dt><dd>${escapeHtml(route.baseline)}</dd></div>
      <div><dt>数据集</dt><dd>${escapeHtml(route.dataset)}</dd></div>
      <div><dt>组合表述</dt><dd>${escapeHtml(route.innovation_statement)}</dd></div>
    </dl>
    <ol class="route-steps">
      ${route.steps.map((step) => `
        <li><span>${escapeHtml(step.area)} · ${escapeHtml(step.difficulty)}</span><strong>${escapeHtml(step.title)}</strong><p>${escapeHtml(step.action)}</p></li>
      `).join("")}
    </ol>
    <div class="route-notes">
      <section><strong>验证顺序</strong>${route.validation.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</section>
      <section><strong>风险提醒</strong>${route.risks.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</section>
    </div>
  `;
}

function openAnalysisDrawer(material, result) {
  const analysis = result.analysis;
  if (!analysis) return;
  closeBasketDrawer();
  closeSynthesisDrawer();
  state.activeAnalysisPaperId = material.id;
  const sourceLabels = {
    openai: "OpenAI 结构化分析",
    rules: "规则分析",
    rules_fallback: "规则降级分析",
  };
  document.querySelector("#analysis-title").textContent = material.title;
  document.querySelector("#analysis-meta").textContent = `${sourceLabels[result.source] || "深度分析"} · ${result.model || "未知模型"}${result.cache_hit ? " · 缓存" : ""}`;
  analysisContentEl.innerHTML = `
    ${result.warning ? `<div class="analysis-warning">${escapeHtml(result.warning)}</div>` : ""}
    ${renderEvidenceAudit(material)}
    <section class="analysis-lead">
      <span>${escapeHtml(analysis.integration_area)}</span>
      <strong>${escapeHtml(analysis.reusable_module)}</strong>
      <p>${escapeHtml(analysis.project_match)}</p>
    </section>
    <section class="analysis-section">
      <h3>问题与方法</h3>
      <dl class="analysis-definition">
        <div><dt>核心问题</dt><dd>${escapeHtml(analysis.core_problem)}</dd></div>
        <div><dt>方法摘要</dt><dd>${escapeHtml(analysis.method_summary)}</dd></div>
        <div><dt>预期收益</dt><dd>${escapeHtml(analysis.expected_gain)}</dd></div>
      </dl>
    </section>
    <section class="analysis-section">
      <h3>接入接口</h3>
      <div class="interface-grid">
        ${renderAnalysisList("输入", analysis.integration_interface?.inputs)}
        ${renderAnalysisList("输出", analysis.integration_interface?.outputs)}
        ${renderAnalysisList("代码改动", analysis.integration_interface?.code_changes)}
      </div>
    </section>
    <section class="analysis-section">
      <h3>最小实现</h3>
      <ol class="analysis-steps">${(analysis.minimal_implementation || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol>
    </section>
    <section class="analysis-section">
      <h3>实验计划</h3>
      <div class="experiment-list">
        ${(analysis.experiment_plan || []).map((experiment) => `
          <article><strong>${escapeHtml(experiment.name)}</strong><p>${escapeHtml(experiment.change)}</p><span>对照：${escapeHtml(experiment.control)}</span><small>${(experiment.metrics || []).map(escapeHtml).join(" · ")}</small></article>
        `).join("")}
      </div>
    </section>
    <section class="analysis-section analysis-two-column">
      ${renderAnalysisList("风险", analysis.risks)}
      ${renderAnalysisList("证据", analysis.evidence)}
    </section>
    <footer class="analysis-footer"><strong>置信度 ${Number(analysis.confidence || 0)}/100</strong><p>${escapeHtml(analysis.limitations)}</p></footer>
  `;
  analysisDrawerEl.hidden = false;
  analysisOverlayEl.hidden = false;
  syncBodyLock();
}

function renderEvidenceAudit(material) {
  const evidence = parseEvidence(material);
  if (!evidence) {
    return '<section class="evidence-audit evidence-pending"><strong>尚未核验 PDF 全文</strong><p>当前分析依据标题与摘要。</p></section>';
  }
  const statusLabels = {
    verified: "全文文本已提取",
    text_insufficient: "PDF 文本不足",
    failed: "全文核验失败",
  };
  const codeLabels = {
    verified_repository: "仓库可访问",
    reported_repository: "论文报告了仓库",
    not_found: "未发现仓库",
  };
  const pdf = evidence.pdf || {};
  const code = evidence.code || { status: "not_found", urls: [] };
  return `
    <section class="evidence-audit evidence-${escapeHtml(evidence.status || "pending")}">
      <div class="evidence-summary">
        <div><span>Full-text Evidence</span><strong>${escapeHtml(statusLabels[evidence.status] || "状态未知")}</strong></div>
        <dl>
          <div><dt>页数</dt><dd>${Number(pdf.page_count || 0)}</dd></div>
          <div><dt>文本字符</dt><dd>${Number(pdf.text_chars || 0).toLocaleString()}</dd></div>
          <div><dt>代码</dt><dd>${escapeHtml(codeLabels[code.status] || "未知")}</dd></div>
        </dl>
      </div>
      ${(code.urls || []).length ? `<div class="repository-links">${code.urls.map((item) => `<a href="${safeExternalUrl(item.url)}" target="_blank" rel="noreferrer">${item.verified ? "已验证" : "待复核"} · ${escapeHtml(item.url)}</a>`).join("")}</div>` : ""}
      ${(evidence.sections || []).length ? `<div class="evidence-sections">${evidence.sections.map((section) => `<details><summary>${escapeHtml(section.label)} · 第 ${Number(section.page || 0)} 页</summary><p>${escapeHtml(section.text)}</p></details>`).join("")}</div>` : ""}
      ${(evidence.limitations || []).map((item) => `<p class="evidence-limitation">${escapeHtml(item)}</p>`).join("")}
    </section>
  `;
}

function renderAnalysisList(title, items = []) {
  return `<div class="analysis-list"><strong>${escapeHtml(title)}</strong>${(items || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("") || "<p>-</p>"}</div>`;
}

function openSynthesisDrawer(result) {
  closeBasketDrawer();
  closeAnalysisDrawer();
  state.synthesis = result;
  state.activeSynthesisSchemeId = result.recommendation?.primary_scheme_id || "balanced";
  renderSynthesis();
  synthesisDrawerEl.hidden = false;
  synthesisOverlayEl.hidden = false;
  syncBodyLock();
}

function renderSynthesis() {
  const result = state.synthesis;
  if (!result) {
    synthesisContentEl.innerHTML = "";
    return;
  }
  const coverage = result.coverage || {};
  const schemes = result.schemes || [];
  const activeScheme = schemes.find((item) => item.id === state.activeSynthesisSchemeId)
    || schemes[0];
  const relationships = result.compatibility?.relationships || [];
  const attentionItems = relationships
    .filter((item) => item.status !== "compatible")
    .slice(0, 8);
  const relationLabels = {
    compatible: "可组合",
    conditional: "需验证",
    alternative: "互为替代",
  };
  const allInBasket = activeScheme?.material_ids?.length
    && activeScheme.material_ids.every((id) => state.materials.some(
      (material) => material.id === id && Boolean(material.in_basket),
    ));

  document.querySelector("#synthesis-meta").textContent = `${result.material_count} 张素材 · ${coverage.areas?.length || 0} 个接入位置 · 综合置信度 ${coverage.confidence || 0}`;
  synthesisContentEl.innerHTML = `
    <section class="synthesis-overview">
      <div class="synthesis-hypothesis">
        <span>研究假设</span>
        <strong>${escapeHtml(result.hypothesis)}</strong>
        <p>${escapeHtml(result.recommendation?.reason || "")}</p>
      </div>
      <dl class="synthesis-coverage">
        <div><dt>候选</dt><dd>${Number(result.material_count || 0)}</dd></div>
        <div><dt>全文</dt><dd>${Number(coverage.evidence_count || 0)}</dd></div>
        <div><dt>分析</dt><dd>${Number(coverage.analyzed_count || 0)}</dd></div>
        <div><dt>代码</dt><dd>${Number(coverage.code_count || 0)}</dd></div>
      </dl>
    </section>

    <details class="synthesis-section synthesis-comparison" open>
      <summary><span>论文能力对比</span><small>${(coverage.areas || []).map(escapeHtml).join(" · ")}</small></summary>
      <div class="synthesis-table-wrap">
        <table class="synthesis-table">
          <thead><tr><th>论文与位置</th><th>可复用模块</th><th>关键证据</th><th>决策信号</th></tr></thead>
          <tbody>
            ${(result.comparison || []).map((item) => `
              <tr>
                <td><span>${escapeHtml(item.area)} · ${escapeHtml(item.subtag)}</span><strong>${escapeHtml(item.title)}</strong></td>
                <td><strong>${escapeHtml(item.module)}</strong><p>${escapeHtml(item.action)}</p></td>
                <td><p>${escapeHtml(item.evidence)}</p></td>
                <td><b>${Number(item.score || 0).toFixed(1)}</b><small>置信 ${Number(item.confidence || 0)} · ${escapeHtml(item.difficulty)}</small></td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      </div>
    </details>

    <details class="synthesis-section synthesis-compatibility" open>
      <summary>
        <span>模块兼容性</span>
        <small>
          <b class="relation-compatible">${Number(result.compatibility?.counts?.compatible || 0)} 可组合</b>
          <b class="relation-conditional">${Number(result.compatibility?.counts?.conditional || 0)} 需验证</b>
          <b class="relation-alternative">${Number(result.compatibility?.counts?.alternative || 0)} 替代项</b>
        </small>
      </summary>
      <div class="compatibility-list">
        ${attentionItems.length ? attentionItems.map((item) => `
          <article>
            <span class="relation-${escapeHtml(item.status)}">${escapeHtml(relationLabels[item.status] || "待判断")}</span>
            <strong>${escapeHtml(item.left_title)} × ${escapeHtml(item.right_title)}</strong>
            <p>${escapeHtml(item.reason)}</p>
          </article>
        `).join("") : '<p class="synthesis-empty-note">当前组合未发现明显的同位置竞争项。</p>'}
      </div>
    </details>

    <section class="synthesis-section synthesis-schemes">
      <div class="synthesis-section-heading">
        <div><span>推荐方案</span><strong>从单项验证走向可归因组合</strong></div>
        <small>建议优先执行平衡方案</small>
      </div>
      <div class="scheme-tabs" role="tablist" aria-label="综合方案">
        ${schemes.map((scheme) => `
          <button class="${scheme.id === activeScheme?.id ? "active" : ""}" data-scheme-view="${escapeHtml(scheme.id)}" type="button" role="tab" aria-selected="${scheme.id === activeScheme?.id}">
            <strong>${escapeHtml(scheme.name)}</strong><span>${escapeHtml(scheme.strategy)}</span>
          </button>
        `).join("")}
      </div>
      ${activeScheme ? renderSynthesisScheme(activeScheme, allInBasket) : '<p class="synthesis-empty-note">当前没有足够素材生成方案。</p>'}
    </section>

    <footer class="synthesis-limitations">
      <strong>判断边界</strong>
      ${(result.limitations || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
    </footer>
  `;
}

function renderSynthesisScheme(scheme, allInBasket) {
  return `
    <div class="scheme-detail" role="tabpanel">
      <header>
        <div><strong>${escapeHtml(scheme.name)}</strong><p>${escapeHtml(scheme.rationale)}</p></div>
        <dl>
          <div><dt>成本</dt><dd>${escapeHtml(scheme.estimated_cost)}</dd></div>
          <div><dt>置信度</dt><dd>${Number(scheme.confidence || 0)}/100</dd></div>
        </dl>
      </header>
      <div class="scheme-modules">
        ${(scheme.modules || []).map((item, index) => `
          <article><b>${index + 1}</b><span>${escapeHtml(item.area)}</span><div><strong>${escapeHtml(item.module)}</strong><p>${escapeHtml(item.title)}</p></div><small>${escapeHtml(item.difficulty)} · ${Number(item.score || 0).toFixed(1)}</small></article>
        `).join("")}
      </div>
      <div class="scheme-plan-grid">
        <section><h3>实施步骤</h3><ol>${(scheme.implementation_steps || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ol></section>
        <section><h3>实验序列</h3><ol>${(scheme.experiments || []).map((item) => `<li><strong>${escapeHtml(item.name)}</strong><p>${escapeHtml(item.change)}</p></li>`).join("")}</ol></section>
      </div>
      <div class="scheme-decision-grid">
        <section><h3>评价指标</h3><p>${(scheme.metrics || []).map(escapeHtml).join(" · ")}</p></section>
        <section><h3>停止条件</h3>${(scheme.stop_conditions || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</section>
        <section><h3>主要风险</h3>${(scheme.risks || []).map((item) => `<p>${escapeHtml(item)}</p>`).join("")}</section>
      </div>
      <footer>
        <span>${scheme.material_ids.length} 张素材将加入方案篮</span>
        <button class="primary-button" data-apply-scheme="${escapeHtml(scheme.id)}" type="button" ${allInBasket ? "disabled" : ""}>${allInBasket ? "已在方案篮" : "采用此方案"}</button>
      </footer>
    </div>
  `;
}

function parseEvidence(material) {
  const raw = material?.full_text_json;
  if (!raw) return null;
  if (typeof raw === "object") return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function safeExternalUrl(value) {
  try {
    const url = new URL(String(value || ""));
    return ["http:", "https:"].includes(url.protocol) ? escapeHtml(url.href) : "#";
  } catch {
    return "#";
  }
}

function isRelevant(material) {
  if (["useful", "stitchable"].includes(material.user_feedback)) return true;
  if (material.user_feedback === "irrelevant") return false;
  return Boolean(material.is_relevant);
}

async function executeSearch() {
  state.synthesis = null;
  renderWorkflowState("search");
  setStatus("正在检索论文并生成素材...");
  const result = await api(`/api/run?topic_id=${state.currentProjectId}`, { method: "POST" });
  await loadMaterials();
  if (result.errors?.length) {
    setStatus(`检索完成，部分来源失败：${result.errors.join("；")}`);
  } else {
    setStatus(`检索完成：${result.fetched_count} 张候选素材`);
  }
  return result;
}

async function executeEvidence() {
  state.synthesis = null;
  renderWorkflowState("evidence");
  setStatus("正在并行核验 Top 10 全文与代码仓库...");
  const result = await api(`/api/evidence/top?topic_id=${state.currentProjectId}`, { method: "POST" });
  await loadMaterials();
  setStatus(`全文核验完成：${result.verified_count} 成功，${result.failed_count} 失败`);
  return result;
}

async function executeAnalysis() {
  state.synthesis = null;
  renderWorkflowState("analysis");
  setStatus("正在生成 Top 10 深度缝合分析...");
  const result = await api(`/api/analyze/top?topic_id=${state.currentProjectId}`, { method: "POST" });
  state.profileCheck = result.profile_check;
  await loadMaterials();
  renderProfileCheck();
  setStatus(`分析完成：${result.analyzed_count} 张素材`);
  return result;
}

async function executeSynthesis() {
  renderWorkflowState("synthesis");
  setStatus("正在比较 Top 10 并生成三档实验方案...");
  const result = await api(`/api/synthesis?topic_id=${state.currentProjectId}`, { method: "POST" });
  openSynthesisDrawer(result);
  renderWorkflowState();
  setStatus(`综合完成：${result.material_count} 张素材，${result.schemes?.length || 0} 套方案`);
  return result;
}

async function runStage(stage) {
  if (!currentProject() || state.busy) return;
  setBusy(true);
  document.querySelector("#more-actions").open = false;
  try {
    if (stage === "search") await executeSearch();
    if (stage === "evidence") await executeEvidence();
    if (stage === "analysis") await executeAnalysis();
    if (stage === "synthesis") await executeSynthesis();
    renderWorkflowState();
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function runCompleteWorkflow() {
  if (!currentProject() || state.busy) return;
  setBusy(true);
  try {
    await executeSearch();
    await executeEvidence();
    await executeAnalysis();
    await executeSynthesis();
    await loadProfileCheck();
    renderWorkflowState();
    setStatus("完整流程已完成，Top 10 综合方案已生成");
  } catch (error) {
    setStatus(`流程中断：${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function analyzeMaterial(material, force = false) {
  setStatus(force ? "正在重新分析素材..." : "正在打开深度分析...");
  const result = await api(`/api/analyze?paper_id=${material.id}${force ? "&force=1" : ""}`, { method: "POST" });
  if (!result.cache_hit) state.synthesis = null;
  openAnalysisDrawer(material, result);
  await loadMaterials();
  setStatus(result.cache_hit ? "已打开缓存分析" : "深度分析已生成");
}

async function verifyMaterial(material, force = false) {
  state.synthesis = null;
  closeSynthesisDrawer();
  setStatus("正在下载 PDF 并提取全文证据...");
  const result = await api(`/api/evidence?paper_id=${material.id}${force ? "&force=1" : ""}`, { method: "POST" });
  await loadMaterials();
  const updated = state.materials.find((item) => item.id === material.id) || material;
  if (result.status === "failed") {
    setStatus(`全文核验失败：${result.error || "未知错误"}`);
    return;
  }
  await analyzeMaterial(updated, true);
}

async function updateMaterial(material, payload) {
  await api(`/api/materials?id=${material.id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  if (Object.hasOwn(payload, "user_feedback")) {
    state.synthesis = null;
    closeSynthesisDrawer();
  }
  state.route = null;
  routeResultEl.innerHTML = "";
  await loadMaterials();
}

function openBasketDrawer() {
  closeAnalysisDrawer();
  closeSynthesisDrawer();
  basketPanelEl.hidden = false;
  basketOverlayEl.hidden = false;
  syncBodyLock();
}

function closeBasketDrawer() {
  basketPanelEl.hidden = true;
  basketOverlayEl.hidden = true;
  syncBodyLock();
}

function closeAnalysisDrawer() {
  analysisDrawerEl.hidden = true;
  analysisOverlayEl.hidden = true;
  syncBodyLock();
}

function closeSynthesisDrawer() {
  synthesisDrawerEl.hidden = true;
  synthesisOverlayEl.hidden = true;
  syncBodyLock();
}

function syncBodyLock() {
  const drawerOpen = !basketPanelEl.hidden || !analysisDrawerEl.hidden || !synthesisDrawerEl.hidden;
  document.body.classList.toggle("drawer-open", drawerOpen);
}

function openProfileDialog(mode = "edit") {
  if (mode === "new") {
    formEl.reset();
    formEl.elements.id.value = "";
    formEl.elements.max_results.value = 20;
    document.querySelector("#profile-dialog-title").textContent = "新建研究项目";
  } else {
    fillProjectForm(currentProject());
    document.querySelector("#profile-dialog-title").textContent = "编辑项目画像";
  }
  profileDialogEl.showModal();
}

function fillProjectForm(project) {
  if (!project) return;
  for (const field of ["id", "name", "domain", "task_type", "idea", "keywords", "backbone", "neck", "head", "dataset", "max_results"]) {
    if (formEl.elements[field]) formEl.elements[field].value = project[field] || "";
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
    state.synthesis = null;
    closeSynthesisDrawer();
    profileDialogEl.close();
    await loadProjects();
    await Promise.all([loadProfileCheck(), loadMaterials()]);
    setStatus("项目画像已保存");
  } catch (error) {
    setStatus(`保存失败：${error.message}`);
  }
});

projectsEl.addEventListener("click", async (event) => {
  const item = event.target.closest("[data-project]");
  if (!item || state.busy) return;
  state.currentProjectId = Number(item.dataset.project);
  state.route = null;
  state.synthesis = null;
  closeBasketDrawer();
  closeAnalysisDrawer();
  closeSynthesisDrawer();
  renderProjects();
  renderProfileSummary();
  updateProjectLinks();
  try {
    await Promise.all([loadProfileCheck(), loadMaterials()]);
    setStatus("项目已切换");
  } catch (error) {
    setStatus(`切换失败：${error.message}`);
  }
});

boardEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const row = button.closest("[data-material-id]");
  const material = state.materials.find((item) => item.id === Number(row?.dataset.materialId));
  if (!material) return;
  try {
    if (button.dataset.action === "feedback") {
      const value = material.user_feedback === button.dataset.value ? "" : button.dataset.value;
      await updateMaterial(material, { user_feedback: value });
      setStatus(value === "irrelevant" ? "已标记为不相关" : "反馈已记录");
    } else if (button.dataset.action === "read") {
      await updateMaterial(material, { is_read: !Boolean(material.is_read) });
      setStatus("阅读状态已更新");
    } else if (button.dataset.action === "basket") {
      await updateMaterial(material, { in_basket: !Boolean(material.in_basket) });
      setStatus(material.in_basket ? "已移出方案" : "已加入方案");
    } else if (button.dataset.action === "analyze") {
      await analyzeMaterial(material);
    } else if (button.dataset.action === "evidence") {
      if (["verified", "text_insufficient"].includes(material.full_text_status)) {
        await analyzeMaterial(material);
      } else {
        await verifyMaterial(material, material.full_text_status === "failed");
      }
    }
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});

basketItemsEl.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-remove-basket]");
  if (!button) return;
  const material = state.materials.find((item) => item.id === Number(button.dataset.removeBasket));
  if (!material) return;
  try {
    await updateMaterial(material, { in_basket: false });
    setStatus("已移出方案");
  } catch (error) {
    setStatus(`操作失败：${error.message}`);
  }
});

synthesisContentEl.addEventListener("click", async (event) => {
  const tab = event.target.closest("[data-scheme-view]");
  if (tab) {
    state.activeSynthesisSchemeId = tab.dataset.schemeView;
    renderSynthesis();
    return;
  }

  const applyButton = event.target.closest("[data-apply-scheme]");
  if (!applyButton || state.busy) return;
  const scheme = state.synthesis?.schemes?.find(
    (item) => item.id === applyButton.dataset.applyScheme,
  );
  if (!scheme) return;

  try {
    setBusy(true);
    setStatus(`正在采用${scheme.name}...`);
    await Promise.all((scheme.material_ids || []).map((id) => api(`/api/materials?id=${id}`, {
      method: "PATCH",
      body: JSON.stringify({ in_basket: true }),
    })));
    state.route = null;
    routeResultEl.innerHTML = "";
    await loadMaterials();
    renderSynthesis();
    setStatus(`${scheme.name}已加入方案篮，可继续生成实验路线`);
  } catch (error) {
    setStatus(`采用方案失败：${error.message}`);
  } finally {
    setBusy(false);
  }
});

runWorkflowEl.addEventListener("click", runCompleteWorkflow);
document.querySelector("#more-actions").addEventListener("click", (event) => {
  const stageButton = event.target.closest("[data-stage]");
  if (stageButton) runStage(stageButton.dataset.stage);
});
document.querySelector("#new-project").addEventListener("click", () => openProfileDialog("new"));
document.querySelector("#edit-project").addEventListener("click", () => openProfileDialog("edit"));
document.querySelector("#close-profile").addEventListener("click", () => profileDialogEl.close());
document.querySelector("#cancel-profile").addEventListener("click", () => profileDialogEl.close());
profileDialogEl.addEventListener("click", (event) => {
  if (event.target === profileDialogEl) profileDialogEl.close();
});

document.querySelector("#view-modes").addEventListener("click", (event) => {
  const button = event.target.closest("[data-view]");
  if (!button) return;
  state.viewMode = button.dataset.view;
  document.querySelectorAll("#view-modes [data-view]").forEach((item) => item.classList.toggle("active", item === button));
  renderBoard();
});
document.querySelector("#area-filter").addEventListener("change", (event) => {
  state.areaFilter = event.target.value;
  renderBoard();
});
document.querySelector("#show-irrelevant").addEventListener("change", (event) => {
  state.showIrrelevant = event.target.checked;
  renderBoard();
});

document.querySelector("#toggle-basket").addEventListener("click", openBasketDrawer);
document.querySelector("#close-basket").addEventListener("click", closeBasketDrawer);
basketOverlayEl.addEventListener("click", closeBasketDrawer);
document.querySelector("#generate-route").addEventListener("click", async () => {
  const selected = state.materials.filter((item) => Boolean(item.in_basket));
  if (!selected.length) {
    setStatus("请先加入方案素材");
    return;
  }
  try {
    setStatus("正在生成实验路线...");
    state.route = await api(`/api/basket/route?topic_id=${state.currentProjectId}`);
    renderRoute();
    setStatus(`实验路线已生成，共 ${state.route.steps.length} 步`);
  } catch (error) {
    setStatus(`路线生成失败：${error.message}`);
  }
});

document.querySelector("#close-analysis").addEventListener("click", closeAnalysisDrawer);
analysisOverlayEl.addEventListener("click", closeAnalysisDrawer);
document.querySelector("#refresh-analysis").addEventListener("click", async () => {
  const material = state.materials.find((item) => item.id === state.activeAnalysisPaperId);
  if (!material) return;
  try {
    await analyzeMaterial(material, true);
  } catch (error) {
    setStatus(`重新分析失败：${error.message}`);
  }
});

document.querySelector("#close-synthesis").addEventListener("click", closeSynthesisDrawer);
synthesisOverlayEl.addEventListener("click", closeSynthesisDrawer);
document.querySelector("#refresh-synthesis").addEventListener("click", () => runStage("synthesis"));

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!synthesisDrawerEl.hidden) closeSynthesisDrawer();
  else if (!analysisDrawerEl.hidden) closeAnalysisDrawer();
  else if (!basketPanelEl.hidden) closeBasketDrawer();
});
document.addEventListener("click", (event) => {
  const menu = document.querySelector("#more-actions");
  if (menu.open && !menu.contains(event.target)) menu.open = false;
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
