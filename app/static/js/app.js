/* ResumeVerify dashboard */

const STORAGE_KEY = "rv_recent_jobs";
const RESULTS_CACHE_KEY = "rv_job_results";

const ROUTES = {
  dashboard: "/dashboard",
  history: "/history",
  docs: "/docs",
  results: "/results",
};

const state = {
  currentJobId: null,
  currentJobData: null,
  uploadMethod: null,
  pollTimer: null,
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

async function pollJob(jobId) {
  const res = await fetch(`/api/jobs/${jobId}`);
  if (!res.ok) {
    setProgress(0, "Job not found.");
    $("#submitBtn").disabled = false;
    return;
  }
  const data = await res.json();
  state.currentJobData = data;
  cacheJobResults(data);

  const pct = data.total ? Math.round((data.processed / data.total) * 100) : 0;

  if (data.status === "running" || data.status === "queued") {
    setProgress(pct, `Processing… ${data.processed}/${data.total} (${data.phase})`);
    state.pollTimer = setTimeout(() => pollJob(jobId), 1500);
    return;
  }

  if (data.status === "failed") {
    setProgress(0, `Failed: ${data.error}`);
    $("#submitBtn").disabled = false;
    saveRecentJob({
      id: jobId,
      method: state.uploadMethod,
      status: "failed",
      total: data.total,
      created_at: data.created_at,
    });
    renderHistoryTable();
    return;
  }

  if (data.status === "completed") {
    setProgress(100, "Verification complete.");
    $("#submitBtn").disabled = false;
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
    showResults(data);
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

function renderResultsPage(data) {
  $("#resultsTitle").textContent = "Verification Complete";
  $("#resultsSubtitle").textContent = `Job ID: ${shortJobId(data.id)} • ${formatJobTime(data.created_at)}`;

  const summary = data.outcomes_summary || [];
  const stats = computeStats(summary);

  $("#statTotal").textContent = stats.total;
  $("#statPass").textContent = stats.pass;
  $("#statReview").textContent = stats.review;
  $("#statError").textContent = stats.error;

  const downloadBtn = $("#downloadExcelBtn");
  downloadBtn.disabled = !data.report_ready;

  renderResultsTable(summary, $("#resultFilter").value);
}

function showResults(data) {
  state.currentJobId = data.id;
  state.currentJobData = data;
  cacheJobResults(data);
  navigateTo("results", data.id);
  renderResultsPage(data);
}

function renderResultsTable(summary, filter) {
  const tbody = $("#resultsTableBody");
  let rows = summary;
  if (filter === "PASS") rows = summary.filter((o) => o.verdict === "PASS");
  else if (filter === "REVIEW") rows = summary.filter((o) => o.verdict !== "PASS");
  else if (filter === "ERROR") rows = summary.filter((o) => o.hard_fails > 0);

  tbody.innerHTML = rows
    .map((o, idx) => {
      const badgeClass =
        o.verdict === "PASS" ? "badge-pass" : o.hard_fails > 0 ? "badge-review" : "badge-review";
      const badgeLabel = o.verdict === "PASS" ? "PASS" : "REVIEW";
      const issues = formatIssues(o);
      const issuesClass = o.verdict === "PASS" ? "issues-cell muted" : "issues-cell";
      return `<tr>
        <td>${o.name || "—"}</td>
        <td>${o.roll_number || "—"}</td>
        <td><span class="badge ${badgeClass}">${badgeLabel}</span></td>
        <td class="${issuesClass}">${issues}</td>
        <td><button type="button" class="link-action" data-issue-idx="${idx}">Details</button></td>
      </tr>`;
    })
    .join("");

  $("#tableShowing").textContent = `Showing 1 to ${rows.length} of ${summary.length} entries`;

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

  if (!res.ok) {
    const err = await res.json();
    setProgress(0, err.detail || "Upload failed");
    $("#submitBtn").disabled = false;
    return;
  }

  const { job_id } = await res.json();
  state.currentJobId = job_id;
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
    navigateTo("dashboard");
    $("#progressWrap").classList.add("hidden");
    setProgress(0, "");
  });
  $("#downloadExcelBtn").addEventListener("click", () => {
    if (state.currentJobId) window.location.href = `/api/jobs/${state.currentJobId}/report`;
  });
  $("#resultFilter").addEventListener("change", () => {
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
