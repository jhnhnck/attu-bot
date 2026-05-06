/* AttuBot — Audit Log Page Script
 * Extracted from audit_log.html inline block (L8).
 * Depends on: bootstrap (global), feather (global), escapeHtml() from app.js
 */
(function () {
  let currentPage = 0;
  let logDetailsStore = []; // stores log objects keyed by render index (M3)

  // Load audit logs
  async function loadAuditLogs() {
    const configType = document.getElementById("filterConfigType").value;
    const guildId = document.getElementById("filterGuildId").value;
    const limit = parseInt(document.getElementById("filterLimit").value);
    const skip = currentPage * limit;

    const params = new URLSearchParams({
      limit: limit.toString(),
      skip: skip.toString(),
    });

    if (configType) params.append("config_type", configType);
    if (guildId) params.append("guild_id", guildId);

    // Show loading, hide table and error
    document.getElementById("loadingSpinner").style.display = "block";
    document.getElementById("auditTable").style.display = "none";
    document.getElementById("emptyState").style.display = "none";
    document.getElementById("errorMessage").style.display = "none";
    document.getElementById("pagination").style.display = "none";

    try {
      const response = await fetch(`/api/audit?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      displayAuditLogs(data.logs);

      // Show pagination if we have results
      if (data.logs.length > 0) {
        document.getElementById("pagination").style.display = "flex";
        document.getElementById("currentPageNum").textContent =
          currentPage + 1;

        const prevBtn = document.getElementById("prevPage");
        const nextBtn = document.getElementById("nextPage");

        prevBtn.classList.toggle("disabled", currentPage === 0);
        nextBtn.classList.toggle("disabled", data.logs.length < limit);
      }
    } catch (error) {
      console.error("Error loading audit logs:", error);
      document.getElementById("errorMessage").style.display = "block";
      document.getElementById("errorText").textContent =
        "Failed to load audit logs: " + error.message;
    } finally {
      document.getElementById("loadingSpinner").style.display = "none";
    }
  }

  // Display audit logs in table
  function displayAuditLogs(logs) {
    const tbody = document.getElementById("auditTableBody");
    tbody.innerHTML = "";
    logDetailsStore = [];

    if (logs.length === 0) {
      document.getElementById("emptyState").style.display = "block";
      return;
    }

    document.getElementById("auditTable").style.display = "table";

    logs.forEach((log, index) => {
      logDetailsStore.push(log);
      const row = document.createElement("tr");
      if (!log.success) row.classList.add("table-danger");

      row.innerHTML = `
              <td>${escapeHtml(log.timestamp_formatted || new Date(log.timestamp * 1000).toLocaleString())}</td>
              <td><span class="badge ${getTypeBadgeClass(log.config_type)}">${escapeHtml(log.config_type)}</span></td>
              <td><span class="badge ${getActionBadgeClass(log.action)}">${escapeHtml(log.action)}</span></td>
              <td>${escapeHtml(log.guild_id || "-")}</td>
              <td>${escapeHtml(log.ip_address)}</td>
              <td>${log.changes ? log.changes.length : 0}</td>
              <td>
                  ${
                    log.success
                      ? '<span class="text-success"><i data-feather="check-circle"></i></span>'
                      : `<span class="text-danger" title="${escapeHtml(log.error_message || "Failed")}"><i data-feather="alert-circle"></i></span>`
                  }
              </td>
              <td>
                  ${
                    log.changes && log.changes.length > 0
                      ? `<button class="btn btn-sm btn-outline-secondary" data-log-id="${index}">Details</button>`
                      : ""
                  }
          `;
      tbody.appendChild(row);
    });

    // Attach event listeners — avoids inline JSON serialisation in onclick (M3)
    tbody.querySelectorAll("[data-log-id]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const log = logDetailsStore[parseInt(btn.dataset.logId, 10)];
        if (log) { showChangeDetails(log); }
      });
    });

    if (typeof feather !== "undefined") {
      feather.replace();
    }
  }

  function getTypeBadgeClass(type) {
    switch (type) {
      case "guild":
        return "bg-success";
      case "theme":
        return "bg-warning";
      case "system":
        return "bg-danger";
      default:
        return "bg-secondary";
    }
  }

  function getActionBadgeClass(action) {
    switch (action) {
      case "create":
        return "bg-success";
      case "delete":
        return "bg-danger";
      case "update":
        return "bg-primary";
      default:
        return "bg-secondary";
    }
  }

  // Show change details in modal
  function showChangeDetails(log) {
    const modal = new bootstrap.Modal(
      document.getElementById("logDetailsModal"),
    );
    const content = document.getElementById("logDetailsContent");

    let changesHtml = "";
    if (log.changes && log.changes.length > 0) {
      changesHtml = `
              <table class="table table-sm table-bordered">
                  <thead><tr><th>Field</th><th>Old Value</th><th>New Value</th></tr></thead>
                  <tbody>
                      ${log.changes
                        .map(
                          (c) => `
                          <tr>
                              <td><code>${escapeHtml(c.field)}</code></td>
                              <td class="text-danger">${formatValue(c.old_value)}</td>
                              <td class="text-success">${formatValue(c.new_value)}</td>
                          </tr>
                      `,
                        )
                        .join("")}
                  </tbody>
              </table>
          `;
    } else {
      changesHtml = "<p>No changes recorded.</p>";
    }

    content.innerHTML = `
          <dl class="row">
              <dt class="col-sm-3">Timestamp</dt><dd class="col-sm-9">${escapeHtml(log.timestamp_formatted || new Date(log.timestamp * 1000).toLocaleString())}</dd>
              <dt class="col-sm-3">Config Type</dt><dd class="col-sm-9">${escapeHtml(log.config_type)}</dd>
              <dt class="col-sm-3">Action</dt><dd class="col-sm-9">${escapeHtml(log.action)}</dd>
              ${log.guild_id ? `<dt class="col-sm-3">Guild ID</dt><dd class="col-sm-9">${escapeHtml(log.guild_id)}</dd>` : ""}
              <dt class="col-sm-3">IP Address</dt><dd class="col-sm-9">${escapeHtml(log.ip_address)}</dd>
              ${log.error_message ? `<dt class="col-sm-3">Error</dt><dd class="col-sm-9 text-danger">${escapeHtml(log.error_message)}</dd>` : ""}
          </dl>
          <h5>Changes</h5>
          ${changesHtml}
      `;

    modal.show();
  }

  function formatValue(value) {
    if (value === null || value === undefined)
      return '<em class="text-muted">null</em>';
    if (typeof value === "object")
      return "<code>" + escapeHtml(JSON.stringify(value, null, 2)) + "</code>";
    return escapeHtml(String(value));
  }

  // Event listeners
  document
    .getElementById("refresh-audit-btn")
    .addEventListener("click", () => {
      currentPage = 0;
      loadAuditLogs();
    });

  document
    .getElementById("filterConfigType")
    .addEventListener("change", () => {
      currentPage = 0;
      loadAuditLogs();
    });

  document.getElementById("filterGuildId").addEventListener(
    "input",
    debounce(() => {
      currentPage = 0;
      loadAuditLogs();
    }, 500),
  );

  document.getElementById("filterLimit").addEventListener("change", () => {
    currentPage = 0;
    loadAuditLogs();
  });

  document.getElementById("prevPage").addEventListener("click", (e) => {
    e.preventDefault();
    if (currentPage > 0) {
      currentPage--;
      loadAuditLogs();
    }
  });

  document.getElementById("nextPage").addEventListener("click", (e) => {
    e.preventDefault();
    currentPage++;
    loadAuditLogs();
  });

  // showChangeDetails exported for any external callers
  window.showChangeDetails = showChangeDetails;

  // Debounce helper
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  // Initial load
  loadAuditLogs();
})();
