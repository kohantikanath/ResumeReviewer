/* ResumeVerify dashboard */

const STORAGE_KEY = "rv_recent_jobs";
const RESULTS_CACHE_KEY = "rv_job_results";

const ROUTES = {
  dashboard: "/dashboard",
  history: "/history",
  docs: "/docs",
  results: "/results",
};

const RESULTS_PAGE_SIZE = 5;

const state = {
  currentJobId: null,
  currentJobData: null,
  uploadMethod: null,
  pollTimer: null,
  resultsPage: 1,
  processingJobId: null,
  liveProcessing: false,
  lastPollProcessed: -1,
  lastProgressAt: 0,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function shortJobId(id) {
  if (!id) return "";
  return `#JOB-${id.slice(0, 8).toUpperCase()}`;
}

function formatIssues(outcome) {
  if (!outcome.issues?.length) {
    return outcome.verdict === "PASS" ? "No issues detected." : "See report for details.";
  }
  return outcome.issues.map((i) => i.reason || i.rule).join("; ");
}

function getResultsCache() {
  return JSON.parse(localStorage.getItem(RESULTS_CACHE_KEY) || "{}");
}

function cacheJobResults(data) {
  if (!data?.id || !data.outcomes_summary?.length) return;
  const cache = getResultsCache();
  cache[data.id] = {
    id: data.id,
    status: data.status,
    total: data.total,
    created_at: data.created_at,
    outcomes_summary: data.outcomes_summary,
    report_ready: data.report_ready || false,
  };
  const keys = Object.keys(cache);
  if (keys.length > 20) {
    keys.sort((a, b) => (cache[b].created_at || "").localeCompare(cache[a].created_at || ""));
    keys.slice(20).forEach((k) => delete cache[k]);
  }
  localStorage.setItem(RESULTS_CACHE_KEY, JSON.stringify(cache));
}

function getCachedJobResults(jobId) {
  const cached = getResultsCache()[jobId];
  if (!cached?.outcomes_summary?.length) return null;
  return cached;
}

function saveRecentJob(entry) {
  const list = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  const filtered = list.filter((j) => j.id !== entry.id);
  filtered.unshift(entry);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered.slice(0, 20)));
}

function getRecentJobs() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
}

function formatJobTime(createdAt) {
  if (!createdAt) return "Completed";
  try {
    return new Date(createdAt).toLocaleString();
  } catch {
    return createdAt;
  }
}

function bindJobViewLinks(root) {
  root.querySelectorAll("[data-job-view]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      openJobResults(el.dataset.jobView);
    });
  });
}

async function fetchJobData(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (res.ok) {
      const data = await res.json();
      cacheJobResults(data);
      return data;
    }
  } catch {
    /* server unreachable */
  }

  const fromBrowser = getCachedJobResults(jobId);
  if (fromBrowser) return fromBrowser;

  const fromList = getRecentJobs().find((j) => j.id === jobId);
  if (fromList?.outcomes_summary?.length) {
    const data = {
      id: jobId,
      status: fromList.status || "completed",
      total: fromList.total,
      created_at: fromList.created_at,
      outcomes_summary: fromList.outcomes_summary,
      report_ready: fromList.report_ready || false,
    };
    cacheJobResults(data);
    return data;
  }
  return null;
}

function showHistoryNotice(message) {
  const el = $("#historyNotice");
  if (!el) return;
  if (message) {
    el.textContent = message;
    el.classList.remove("hidden");
  } else {
    el.textContent = "";
    el.classList.add("hidden");
  }
}

async function openJobResults(jobId) {
  const data = await fetchJobData(jobId);
  if (!data?.outcomes_summary?.length) {
    showHistoryNotice(
      "Could not load results for this job. Run verification again if the server was restarted before results were saved."
    );
    if (parsePath(window.location.pathname).view === "results") {
      navigateTo("dashboard", null, true);
    }
    return false;
  }

  showHistoryNotice("");
  state.currentJobId = data.id;
  state.currentJobData = data;
  navigateTo("results", data.id);
  renderResultsPage(data);
  return true;
}

function pathForView(view, jobId = null) {
  if (view === "results" && jobId) return `/results/${jobId}`;
  return ROUTES[view] || ROUTES.dashboard;
}

function parsePath(pathname) {
  const resultsMatch = pathname.match(/^\/results\/([a-f0-9-]+)$/i);
  if (resultsMatch) return { view: "results", jobId: resultsMatch[1] };
  if (pathname === "/results") return { view: "results", jobId: null };
  if (pathname === "/history") return { view: "history", jobId: null };
  if (pathname === "/docs") return { view: "docs", jobId: null };
  return { view: "dashboard", jobId: null };
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  $$(".nav-links a").forEach((a) => a.classList.remove("active"));
  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add("active");
  const nav = document.querySelector(`.nav-links a[data-view="${name}"]`);
  if (nav) nav.classList.add("active");
  if (name === "history") renderHistoryTable();
}

function navigateTo(view, jobId = null, replace = false) {
  const path = pathForView(view, jobId);
  const stateObj = { view, jobId };
  if (replace) {
    history.replaceState(stateObj, "", path);
  } else if (window.location.pathname !== path) {
    history.pushState(stateObj, "", path);
  }
  showView(view);
}

async function loadRoute() {
  const { view, jobId } = parsePath(window.location.pathname);

  if (view === "results" && jobId) {
    await openJobResults(jobId);
    return;
  }

  if (view === "results" && state.currentJobData) {
    showView("results");
    renderResultsPage(state.currentJobData);
    return;
  }

  if (view === "history") {
    showView("history");
    renderHistoryTable();
    return;
  }

  if (view === "docs") {
    showView("docs");
    return;
  }

  showView("dashboard");
}

async function checkApiHealth() {
  const dot = $("#apiStatusDot");
  const label = $("#apiStatusLabel");
  try {
    const res = await fetch("/api/health");
    if (res.ok) {
      dot.classList.remove("offline");
      label.textContent = "API Status: Online";
    } else {
      throw new Error("bad status");
    }
  } catch {
    dot.classList.add("offline");
    label.textContent = "API Status: Offline";
  }
}

function wireFilePicker(inputId, chipId, nameId, multi = false) {
  const input = document.getElementById(inputId);
  const chip = document.getElementById(chipId);
  const nameEl = document.getElementById(nameId);
  const clearBtn = document.getElementById(chipId.replace("Chip", "Clear"));

  function update() {
    if (multi) {
      if (input.files?.length) {
        nameEl.textContent =
          input.files.length === 1
            ? input.files[0].name
            : `${input.files.length} PDFs selected`;
        chip.classList.remove("hidden");
      } else {
        chip.classList.add("hidden");
      }
    } else if (input.files?.[0]) {
      nameEl.textContent = input.files[0].name;
      chip.classList.remove("hidden");
    } else {
      chip.classList.add("hidden");
    }
  }

  input.addEventListener("change", update);
  clearBtn.addEventListener("click", () => {
    const clone = input.cloneNode(true);
    input.parentNode.replaceChild(clone, input);
    clone.addEventListener("change", update);
    chip.classList.add("hidden");
  });
}

function setProgress(pct, message) {
  const bar = $("#progressBar");
  const msg = $("#runStatus");
  if (bar) bar.style.width = `${pct}%`;
  if (msg) msg.textContent = message || "";
}

const PHASE_LABELS = {
  queued: "Job queued — starting soon…",
  prepare: "Preparing batch…",
  download: "Downloading resumes from Google Drive",
  links: "Checking live links — this step can take a while on large batches",
  rules: "Running rule checks on each resume",
  report: "Building Excel report…",
  done: "Complete",
  error: "Failed",
};

function phaseDetail(data) {
  const phase = data.phase || "";
  const total = data.total || 0;
  const processed = data.processed || 0;
  if (phase === "download" && total) {
    const next = Math.min(processed + 1, total);
    return `Downloading resume ${next} of ${total} from Drive…`;
  }
  if (phase === "links" && total) {
    const next = processed + 1;
    return `Checking links for resume ${next} of ${total}…`;
  }
  if (phase === "rules" && total) {
    return `${processed} of ${total} resumes verified`;
  }
  return PHASE_LABELS[phase] || phase || "Working…";
}

function progressPercent(data) {
  const total = data.total || 0;
  const processed = data.processed || 0;
  const phase = data.phase || "";

  if (data.status === "completed") return 100;
  if (!total) return 8;

  if (phase === "download") {
    return Math.min(35, Math.round((processed / total) * 35));
  }
  if (phase === "links") {
    const next = Math.min((data.processed || 0) + 1, data.total || 0);
    return Math.min(38, 10 + next * 25 / Math.max(data.total || 1, 1));
  }
  if (phase === "rules") {
    return 40 + Math.round((processed / total) * 55);
  }
  if (phase === "report") return 98;
  return Math.round((processed / total) * 100);
}

function liveCountLabel(data) {
  const total = data.total || 0;
  const processed = data.processed || 0;
  const done = data.outcomes_summary?.length || 0;
  const phase = data.phase || "";

  if (data.status === "completed") {
    return `${done} of ${total} resumes verified`;
  }
  if (phase === "download" && total) {
    const next = Math.min(processed + 1, total);
    return `${next} of ${total} — downloading from Drive`;
  }
  if (phase === "links" && total) {
    const next = Math.min(processed + 1, total);
    return `Checking links for resume ${next} of ${total}…`;
  }
  if (done > 0 && total) {
    return `${done} of ${total} ready to review`;
  }
  if (total) {
    return `0 of ${total} — starting…`;
  }
  return "Starting job…";
}

function updateLiveBanner(data) {
  const banner = $("#resultsLiveBanner");
  if (!banner) return;

  const isLive = data.status === "running" || data.status === "queued";
  if (!isLive && data.status !== "completed") {
    banner.classList.add("hidden");
    return;
  }

  banner.classList.remove("hidden");
  banner.classList.toggle("complete", data.status === "completed");

  const countEl = $("#liveBannerCount");
  const phaseEl = $("#liveBannerPhase");
  const bar = $("#liveBannerBar");

  if (countEl) countEl.textContent = liveCountLabel(data);
  if (phaseEl) {
    phaseEl.textContent =
      data.status === "completed"
        ? "All resumes verified — Excel report is ready."
        : phaseDetail(data);
  }
  if (bar) bar.style.width = `${progressPercent(data)}%`;
}

function liveEmptyTableMessage(data) {
  const phase = data?.phase || "";
  if (phase === "download") {
    return "Downloading resumes from Google Drive — results will appear here as each one is verified.";
  }
  if (phase === "links") {
    return "Checking live links across the batch — this can take a while. Results will stream in once verification starts.";
  }
  if (phase === "report") {
    return "Building Excel report…";
  }
  return "Waiting for first resume to finish…";
}

function showLiveResults(data) {
  state.currentJobId = data.id;
  state.currentJobData = data;
  state.liveProcessing = data.status === "running" || data.status === "queued";
  state.processingJobId = state.liveProcessing ? data.id : null;

  if (data.outcomes_summary?.length) {
    cacheJobResults(data);
  }

  const path = pathForView("results", data.id);
  if (window.location.pathname !== path) {
    navigateTo("results", data.id);
  } else {
    showView("results");
  }

  renderResultsPage(data, { live: state.liveProcessing });
  setProgress(progressPercent(data), phaseDetail(data));
}

async function pollJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) {
    state.liveProcessing = false;
    setProgress(0, "Job not found.");
    $("#submitBtn").disabled = false;
    return;
  }
  const data = await res.json();

  if (data.status === "running" || data.status === "queued") {
    if (data.processed !== state.lastPollProcessed) {
      state.lastPollProcessed = data.processed;
      state.lastProgressAt = Date.now();
    } else if (
      state.lastProgressAt &&
      Date.now() - state.lastProgressAt > 120000
    ) {
      const phaseEl = $("#liveBannerPhase");
      if (phaseEl) {
        phaseEl.textContent =
          "No progress for 2+ minutes — server may have restarted. Stop and run a new job (without --reload for big batches).";
      }
    }
    showLiveResults(data);
    state.pollTimer = setTimeout(() => pollJob(jobId), 1000);
    return;
  }

  if (data.status === "failed") {
    state.liveProcessing = false;
    state.processingJobId = null;
    $("#submitBtn").disabled = false;
    $("#newVerificationBtn").disabled = false;
    if (data.outcomes_summary?.length) {
      cacheJobResults(data);
      renderResultsPage(data, { live: false });
      $("#resultsTitle").textContent = "Verification stopped (partial results)";
    }
    setProgress(0, data.error || "Job failed");
    showLiveResults({ ...data, phase: "error" });
    const phaseEl = $("#liveBannerPhase");
    if (phaseEl) phaseEl.textContent = data.error || "Job failed";
    saveRecentJob({
      id: jobId,
      method: state.uploadMethod,
      status: "failed",
      total: data.total,
      created_at: data.created_at,
      outcomes_summary: data.outcomes_summary,
    });
    renderHistoryTable();
    return;
  }

  if (data.status === "completed") {
    state.liveProcessing = false;
    state.processingJobId = null;
    cacheJobResults(data);
    renderResultsPage(data, { live: false });
    setProgress(100, "Verification complete.");
    $("#submitBtn").disabled = false;
    $("#newVerificationBtn").disabled = false;
    saveRecentJob({
      id: jobId,
      method: state.uploadMethod,
      status: "completed",
      total: data.total,
      created_at: data.created_at,
      outcomes_summary: data.outcomes_summary,
      report_ready: data.report_ready,
    });
    if (document.getElementById("view-history").classList.contains("active")) {
      renderHistoryTable();
    }
  }
}

function computeStats(summary) {
  let pass = 0;
  let review = 0;
  let error = 0;
  for (const o of summary) {
    if (o.verdict === "PASS") pass++;
    else if (o.hard_fails > 0 || o.verdict === "REVIEW") review++;
    else error++;
  }
  return { total: summary.length, pass, review, error };
}

function renderResultsPage(data, options = {}) {
  const isLive = options.live ?? false;
  state.liveProcessing = isLive;

  if (isLive) {
    $("#resultsTitle").textContent = "Live verification";
    $("#resultsSubtitle").textContent = `Job ${shortJobId(data.id)} — review results as they finish`;
    $("#resultsLiveBanner").classList.remove("hidden");
    $("#newVerificationBtn").disabled = true;
  } else {
    $("#resultsTitle").textContent = "Verification complete";
    $("#resultsSubtitle").textContent = `Job ID: ${shortJobId(data.id)} • ${formatJobTime(data.created_at)}`;
    const banner = $("#resultsLiveBanner");
    if (banner) banner.classList.add("hidden");
    $("#newVerificationBtn").disabled = false;
  }

  const summary = data.outcomes_summary || [];
  const stats = computeStats(summary);

  $("#statTotal").textContent = isLive && data.total ? data.total : stats.total;
  $("#statPass").textContent = stats.pass;
  $("#statReview").textContent = stats.review;
  $("#statError").textContent = stats.error;

  const downloadBtn = $("#downloadExcelBtn");
  downloadBtn.disabled = !data.report_ready;

  if (!isLive) {
    state.resultsPage = 1;
  }

  updateLiveBanner(data);
  renderResultsTable(summary, $("#resultFilter").value, data);
}

function showResults(data) {
  state.currentJobId = data.id;
  state.currentJobData = data;
  state.liveProcessing = false;
  cacheJobResults(data);
  navigateTo("results", data.id);
  renderResultsPage(data, { live: false });
}

function filterResultRows(summary, filter) {
  if (filter === "PASS") return summary.filter((o) => o.verdict === "PASS");
  if (filter === "REVIEW") return summary.filter((o) => o.verdict !== "PASS");
  if (filter === "ERROR") return summary.filter((o) => o.hard_fails > 0);
  return summary;
}

function renderResultsPagination(totalPages, currentPage) {
  const container = $("#tablePagination");
  if (!container) return;

  if (totalPages <= 1) {
    container.innerHTML = "";
    container.classList.add("hidden");
    return;
  }

  container.classList.remove("hidden");
  const filtered = filterResultRows(
    state.currentJobData?.outcomes_summary || [],
    $("#resultFilter").value,
  ).length;
  const start = (currentPage - 1) * RESULTS_PAGE_SIZE + 1;
  const end = Math.min(currentPage * RESULTS_PAGE_SIZE, filtered);
  container.innerHTML = `
    <button type="button" class="pagination-btn" id="resultsPrevPage" ${currentPage <= 1 ? "disabled" : ""}>Previous</button>
    <span class="pagination-meta">${start}–${end} · Page ${currentPage} of ${totalPages}</span>
    <button type="button" class="pagination-btn" id="resultsNextPage" ${currentPage >= totalPages ? "disabled" : ""}>Next</button>
  `;

  const prev = $("#resultsPrevPage");
  const next = $("#resultsNextPage");
  if (prev) {
    prev.addEventListener("click", () => {
      if (state.resultsPage > 1) {
        state.resultsPage -= 1;
        renderResultsTable(state.currentJobData.outcomes_summary, $("#resultFilter").value);
      }
    });
  }
  if (next) {
    next.addEventListener("click", () => {
      if (state.resultsPage < totalPages) {
        state.resultsPage += 1;
        renderResultsTable(state.currentJobData.outcomes_summary, $("#resultFilter").value);
      }
    });
  }
}

function renderResultsTable(summary, filter, jobData = null) {
  const tbody = $("#resultsTableBody");
  const rows = filterResultRows(summary, filter);
  const totalFiltered = rows.length;
  const totalPages = Math.max(1, Math.ceil(totalFiltered / RESULTS_PAGE_SIZE));

  if (state.resultsPage > totalPages) state.resultsPage = totalPages;
  if (state.resultsPage < 1) state.resultsPage = 1;

  const start = (state.resultsPage - 1) * RESULTS_PAGE_SIZE;
  const end = Math.min(start + RESULTS_PAGE_SIZE, totalFiltered);
  const pageRows = rows.slice(start, end);

  if (!pageRows.length) {
    const emptyMsg = state.liveProcessing
      ? liveEmptyTableMessage(jobData || state.currentJobData)
      : "No entries match this filter.";
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--text-muted);padding:1rem">${emptyMsg}</td></tr>`;
    $("#tableShowing").textContent = state.liveProcessing
      ? "Waiting for results…"
      : "Showing 0 entries";
    renderResultsPagination(1, 1);
    return;
  }

  tbody.innerHTML = pageRows
    .map((o, idx) => {
      const rowIdx = start + idx;
      const badgeClass =
        o.verdict === "PASS" ? "badge-pass" : o.hard_fails > 0 ? "badge-review" : "badge-review";
      const badgeLabel = o.verdict === "PASS" ? "PASS" : "REVIEW";
      const issues = formatIssues(o);
      const issuesClass = o.verdict === "PASS" ? "issues-cell muted" : "issues-cell";
      const pdfLink = o.resume_url
        ? `<a href="${o.resume_url}" target="_blank" rel="noopener" class="link-action">View PDF</a> · `
        : "";
      return `<tr>
        <td>${o.name || "—"}</td>
        <td>${o.roll_number || "—"}</td>
        <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
        <td class="${issuesClass}">${issues}</td>
        <td>${pdfLink}<button type="button" class="link-action" data-issue-idx="${rowIdx}">Details</button></td>
      </tr>`;
    })
    .join("");

  const showingText = `Showing ${start + 1}–${end} of ${totalFiltered}`;
  $("#tableShowing").textContent = state.liveProcessing
    ? `${showingText} (more arriving as they finish)`
    : showingText;
  renderResultsPagination(totalPages, state.resultsPage);

  tbody.querySelectorAll("[data-issue-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const o = rows[Number(btn.dataset.issueIdx)];
      showIssueModal(o);
    });
  });
}

function showIssueModal(outcome) {
  const modal = $("#issueModal");
  $("#modalTitle").textContent = outcome.name || outcome.filename;
  const content = outcome.issues?.length
    ? JSON.stringify(outcome.issues, null, 2)
    : "No rule failures.";
  $("#modalContent").textContent = content;
  modal.classList.remove("hidden");
}

function hideModal() {
  $("#issueModal").classList.add("hidden");
}

function methodLabel(method) {
  const map = {
    forms: "CSV (Drive Links)",
    zip: "ZIP Bundle",
    direct: "Direct Upload",
  };
  return map[method] || "Verification";
}

async function loadMergedJobs() {
  const byId = new Map();
  for (const j of getRecentJobs()) {
    byId.set(j.id, { ...j });
  }

  try {
    const res = await fetch("/api/jobs?limit=20");
    if (res.ok) {
      for (const sj of (await res.json()).jobs || []) {
        const existing = byId.get(sj.id);
        const cached = getCachedJobResults(sj.id);
        byId.set(sj.id, {
          id: sj.id,
          method: existing?.method || sj.method,
          status: sj.status,
          total: sj.total,
          created_at: sj.created_at || existing?.created_at,
          report_ready: sj.report_ready || existing?.report_ready || false,
          outcomes_summary: existing?.outcomes_summary || cached?.outcomes_summary,
        });
      }
    }
  } catch {
    /* local list only */
  }

  return Array.from(byId.values()).sort((a, b) =>
    (b.created_at || "").localeCompare(a.created_at || "")
  );
}

function renderJobRows(jobs) {
  return jobs
    .map((j) => {
      let statusBadge;
      let reportCell;
      if (j.status === "completed") {
        statusBadge = `<span class="badge badge-pass">COMPLETED</span>`;
        reportCell = `<button type="button" class="link-action" data-job-view="${j.id}">View</button> · <a href="/api/jobs/${j.id}/report" class="link-action">Download</a>`;
      } else if (j.status === "failed") {
        statusBadge = `<span class="badge badge-error">Failed</span>`;
        reportCell = "—";
      } else {
        statusBadge = `<span class="badge badge-processing">Processing</span>`;
        reportCell = "Pending…";
      }
      return `<tr>
        <td>${shortJobId(j.id)}</td>
        <td>${methodLabel(j.method)}</td>
        <td>${statusBadge}</td>
        <td>${reportCell}</td>
      </tr>`;
    })
    .join("");
}

function clearHistory() {
  if (
    !confirm(
      "Clear all job history? This removes saved jobs and reports from this computer."
    )
  ) {
    return;
  }
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(RESULTS_CACHE_KEY);
  showHistoryNotice("");
  fetch("/api/jobs/clear", { method: "POST" })
    .catch(() => {})
    .finally(() => renderHistoryTable());
}

async function renderHistoryTable() {
  const tbody = $("#historyTableBody");
  const jobs = await loadMergedJobs();

  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--text-muted);padding:1rem">No history yet. Run a verification from the Dashboard.</td></tr>`;
    return;
  }

  tbody.innerHTML = renderJobRows(jobs);
  bindJobViewLinks(tbody);
}

async function runVerification() {
  const formsCsv = document.getElementById("formsCsv").files[0];
  const bundle = document.getElementById("bundle").files[0];
  const pdfs = document.getElementById("pdfs").files;
  const meta = document.getElementById("metadata").files[0];
  const checkLinks = document.getElementById("checkLinks").checked;

  if (!formsCsv && !bundle && !pdfs.length) {
    setProgress(0, "Choose one upload method: Forms CSV, ZIP, or PDF files.");
    return;
  }

  $("#submitBtn").disabled = true;
  $("#progressWrap").classList.remove("hidden");
  setProgress(5, "Uploading…");

  let res;

  try {
    if (formsCsv) {
      state.uploadMethod = "forms";
      const form = new FormData();
      form.append("form_csv", formsCsv);
      res = await fetch(`/api/batch/forms-csv?check_links=${checkLinks}`, { method: "POST", body: form });
    } else {
      const form = new FormData();
      if (bundle) {
        state.uploadMethod = "zip";
        form.append("bundle", bundle);
      } else {
        state.uploadMethod = "direct";
        for (const f of pdfs) form.append("resumes", f);
        if (meta) form.append("metadata", meta);
      }
      res = await fetch(`/api/batch?check_links=${checkLinks}`, { method: "POST", body: form });
    }
  } catch {
    setProgress(0, "Upload failed — check your connection.");
    $("#submitBtn").disabled = false;
    return;
  }

  if (!res.ok) {
    const err = await res.json();
    setProgress(0, err.detail || "Upload failed");
    $("#submitBtn").disabled = false;
    return;
  }

  const { job_id, total } = await res.json();
  state.currentJobId = job_id;
  state.processingJobId = job_id;
  state.lastPollProcessed = -1;
  state.lastProgressAt = Date.now();
  state.liveProcessing = true;

  $("#newVerificationBtn").disabled = true;

  const placeholder = {
    id: job_id,
    status: "queued",
    total: total || 0,
    processed: 0,
    phase: "queued",
    outcomes_summary: [],
    report_ready: false,
    created_at: new Date().toISOString(),
  };
  showLiveResults(placeholder);
  setProgress(10, "Job queued…");
  pollJob(job_id);
}

function init() {
  wireFilePicker("formsCsv", "formsCsvChip", "formsCsvName");
  wireFilePicker("bundle", "bundleChip", "bundleName");
  wireFilePicker("metadata", "metadataChip", "metadataName");
  wireFilePicker("pdfs", "pdfsChip", "pdfsName", true);

  $$(".nav-links a[data-view]").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo(a.dataset.view);
    });
  });

  window.addEventListener("popstate", () => loadRoute());

  $("#submitBtn").addEventListener("click", runVerification);
  $("#clearHistoryBtn").addEventListener("click", clearHistory);
  $("#newVerificationBtn").addEventListener("click", () => {
    if (state.liveProcessing) return;
    navigateTo("dashboard");
    $("#progressWrap").classList.add("hidden");
    setProgress(0, "");
  });
  $("#downloadExcelBtn").addEventListener("click", () => {
    if (state.currentJobId) window.location.href = `/api/jobs/${state.currentJobId}/report`;
  });
  $("#resultFilter").addEventListener("change", () => {
    state.resultsPage = 1;
    if (state.currentJobData?.outcomes_summary) {
      renderResultsTable(state.currentJobData.outcomes_summary, $("#resultFilter").value);
    }
  });
  $("#modalCloseBtn").addEventListener("click", hideModal);
  $("#issueModal").addEventListener("click", (e) => {
    if (e.target.id === "issueModal") hideModal();
  });

  $$(".footer-links a[data-view]").forEach((a) => {
    a.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo(a.dataset.view);
    });
  });

  checkApiHealth();
  setInterval(checkApiHealth, 30000);
  loadRoute();
}

document.addEventListener("DOMContentLoaded", init);
