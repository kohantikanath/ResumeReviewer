/* ResumeVerify dashboard */

const STORAGE_KEY = "rv_recent_jobs";

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

function saveRecentJob(entry) {
  const list = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  const filtered = list.filter((j) => j.id !== entry.id);
  filtered.unshift(entry);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered.slice(0, 20)));
}

function getRecentJobs() {
  return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
}

function showView(name) {
  $$(".view").forEach((v) => v.classList.remove("active"));
  $$(".nav-links a").forEach((a) => a.classList.remove("active"));
  const view = document.getElementById(`view-${name}`);
  if (view) view.classList.add("active");
  const nav = document.querySelector(`.nav-links a[data-view="${name}"]`);
  if (nav) nav.classList.add("active");
  if (name === "history") renderHistoryTable();
  if (name === "docs") return;
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
    renderRecentActivity();
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
    });
    renderRecentActivity();
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

function showResults(data) {
  state.currentJobId = data.id;
  showView("results");

  $("#resultsTitle").textContent = "Verification Complete";
  $("#resultsSubtitle").textContent = `Job ID: ${shortJobId(data.id)} • Completed just now`;

  const summary = data.outcomes_summary || [];
  const stats = computeStats(summary);

  $("#statTotal").textContent = stats.total;
  $("#statPass").textContent = stats.pass;
  $("#statReview").textContent = stats.review;
  $("#statError").textContent = stats.error;

  renderResultsTable(summary, $("#resultFilter").value);
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
  return map[method] || method || "Upload";
}

function renderRecentActivity() {
  const tbody = $("#recentTableBody");
  const jobs = getRecentJobs();
  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--text-muted);padding:1rem">No recent jobs yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = jobs
    .map((j) => {
      let statusBadge;
      let reportCell;
      if (j.status === "completed") {
        statusBadge = `<span class="badge badge-pass">Completed</span>`;
        reportCell = `<a href="/api/jobs/${j.id}/report" class="link-action">Download</a>`;
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

function renderHistoryTable() {
  const tbody = $("#historyTableBody");
  const jobs = getRecentJobs();
  if (!jobs.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="color:var(--text-muted);padding:1rem">No history yet.</td></tr>`;
    return;
  }
  tbody.innerHTML = jobs
    .map((j) => {
      const statusBadge =
        j.status === "completed"
          ? `<span class="badge badge-pass">Completed</span>`
          : j.status === "failed"
            ? `<span class="badge badge-error">Failed</span>`
            : `<span class="badge badge-processing">Processing</span>`;
      const actions =
        j.status === "completed"
          ? `<button type="button" class="link-action" data-open-job="${j.id}">View results</button> · <a href="/api/jobs/${j.id}/report">Excel</a>`
          : "—";
      return `<tr>
        <td>${shortJobId(j.id)}</td>
        <td>${methodLabel(j.method)}</td>
        <td>${j.total || "—"}</td>
        <td>${statusBadge}</td>
        <td>${actions}</td>
      </tr>`;
    })
    .join("");

  tbody.querySelectorAll("[data-open-job]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.openJob;
      const res = await fetch(`/api/jobs/${id}`);
      if (res.ok) showResults(await res.json());
    });
  });
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
      showView(a.dataset.view);
    });
  });

  $("#submitBtn").addEventListener("click", runVerification);
  $("#newVerificationBtn").addEventListener("click", () => {
    showView("dashboard");
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
      showView(a.dataset.view);
    });
  });

  renderRecentActivity();
  checkApiHealth();
  setInterval(checkApiHealth, 30000);
}

document.addEventListener("DOMContentLoaded", init);
