(() => {
  const emerald = "#10b981";
  const rose = "#f43f5e";

  /* ------------------------------------------------------------- toast */
  let toastContainer = null;
  const ensureToastContainer = () => {
    if (toastContainer) return toastContainer;
    toastContainer = document.createElement("div");
    toastContainer.className =
      "fixed top-5 right-5 z-50 flex flex-col gap-2 pointer-events-none";
    document.body.appendChild(toastContainer);
    return toastContainer;
  };

  const toast = (message, level = "info", duration = 5000) => {
    const container = ensureToastContainer();
    const el = document.createElement("div");
    const isError = level === "error";
    el.className = `pointer-events-auto flex items-start gap-3 rounded-xl border px-4 py-3 text-sm min-w-[320px] ${
      isError
        ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
        : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
    }`;
    el.innerHTML = `
      <span class="mt-0.5 text-base leading-none shrink-0">${isError ? "!" : "✓"}</span>
      <span class="leading-relaxed">${escapeHtml(message)}</span>
      <button class="ml-auto shrink-0 opacity-50 hover:opacity-100" onclick="this.closest('.flex').remove()">×</button>
    `;
    container.appendChild(el);

    // Animate in
    requestAnimationFrame(() => {
      el.classList.add("opacity-100", "translate-x-0");
    });
    el.style.opacity = "0";
    el.style.transform = "translateX(20px)";
    el.style.transition = "all 0.25s ease";

    if (duration > 0) {
      setTimeout(() => {
        el.style.opacity = "0";
        el.style.transform = "translateX(20px)";
        setTimeout(() => el.remove(), 250);
      }, duration);
    }
    return el;
  };

  const escapeHtml = (text) => {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  };

  /* ------------------------------------------------------------- ajax */
  const csrfHeaderName = "X-Requested-With";
  const ajaxOptions = {
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      Accept: "application/json",
    },
  };

  const showButtonLoading = (button, loading) => {
    if (!button) return;
    if (loading) {
      button.dataset.label = button.textContent;
      button.textContent = "Working…";
      button.disabled = true;
    } else {
      button.textContent = button.dataset.label || button.textContent;
      button.disabled = false;
    }
  };

  const handleFormSubmit = async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;

    // Skip forms that opt out of AJAX
    if (form.dataset.ajax === "false") return;

    const confirmMessage = form.dataset.confirm;
    if (confirmMessage && !window.confirm(confirmMessage)) {
      event.preventDefault();
      return;
    }

    event.preventDefault();

    const button = form.querySelector("button[type='submit']");
    const isLoading = form.dataset.loading === "true";
    showButtonLoading(button, true);

    try {
      const formData = new FormData(form);
      const response = await fetch(form.action, {
        method: form.method || "post",
        body: formData,
        ...ajaxOptions,
      });

      let result;
      const contentType = response.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        result = await response.json();
      } else {
        // Non-JSON response (e.g. redirect fallback) — treat as success and reload relevant parts
        result = { ok: response.ok, message: "Operation completed." };
      }

      if (result.ok) {
        toast(result.message || "Saved successfully.", "info");

        // If this was the settings form, refresh HTMX partials to reflect new values
        if (form.action.endsWith("/settings")) {
          refreshPartials();
        }

        // If this was a mode change, reload page to reflect mode badge changes
        if (form.action.includes("/actions/mode")) {
          setTimeout(() => window.location.reload(), 800);
        }

        // If kill switch, reload to show updated state
        if (form.action.includes("/actions/kill")) {
          setTimeout(() => window.location.reload(), 800);
        }
      } else {
        toast(result.error || "Operation failed.", "error");
      }
    } catch (error) {
      console.error("AJAX error:", error);
      toast(error.message || "Network error. Please try again.", "error");
    } finally {
      showButtonLoading(button, false);
    }
  };

  /* ------------------------------------------------------------- partial refresh */
  const refreshPartials = async () => {
    const partials = ["stats", "positions", "signals", "scanner"];
    await Promise.all(
      partials.map((name) =>
        fetch(`/partials/${name}`, { headers: { ...ajaxOptions.headers } })
          .then((r) => r.text())
          .then((html) => {
            const target = document.getElementById(`partial-${name}`);
            if (target) target.innerHTML = html;
          })
          .catch((err) => console.warn(`partial ${name}`, err))
      )
    );
  };

  /* ------------------------------------------------------------- HTMX boost */
  // Make htmx requests also send the AJAX header so backend returns JSON
  document.body.addEventListener("htmx:configRequest", (event) => {
    event.detail.headers["X-Requested-With"] = "XMLHttpRequest";
    event.detail.headers["Accept"] = "application/json, text/html";
  });

  /* ------------------------------------------------------------- boot */
  const boot = () => {
    // Intercept all form submissions for AJAX
    document.addEventListener("submit", handleFormSubmit);

    // HTMX error handling
    document.addEventListener("htmx:responseError", (event) => {
      console.error("HTMX error", event.detail);
      const xhr = event.detail.xhr;
      try {
        const body = JSON.parse(xhr.responseText);
        toast(body.error || "Request failed.", "error");
      } catch (_) {
        toast("Request failed. Please try again.", "error");
      }
    });

    // HTMX after swap — re-attach any dynamic behaviors
    document.addEventListener("htmx:afterSwap", (event) => {
      if (event.target.id && event.target.id.startsWith("partial-")) {
        // Partial refreshed, nothing extra needed
      }
    });

    // Auto-dismiss flash
    const flash = document.getElementById("flash");
    if (flash) {
      window.setTimeout(() => {
        flash.classList.add("opacity-0", "transition-opacity", "duration-500");
        window.setTimeout(() => flash.remove(), 600);
      }, 6000);
    }

    // Equity chart
    const loadEquity = async () => {
      const canvas = document.getElementById("equityChart");
      if (!canvas || !window.Chart) return;
      try {
        const response = await fetch("/api/equity?limit=600", {
          headers: { Accept: "application/json" },
        });
        if (!response.ok) return;
        const data = await response.json();
        window.equityChart = window.equityChart || null;
        const ctx = canvas.getContext("2d");
        const gradient = ctx.createLinearGradient(
          0,
          0,
          0,
          canvas.parentElement.clientHeight || 280
        );
        gradient.addColorStop(0, "rgba(16, 185, 129, 0.28)");
        gradient.addColorStop(1, "rgba(16, 185, 129, 0.00)");
        const values = data.values || [];
        const rising = values.length < 2 || values[values.length - 1] >= values[0];
        const line = rising ? emerald : rose;
        if (window.equityChart) {
          window.equityChart.data.labels = data.labels || [];
          window.equityChart.data.datasets[0].data = values;
          window.equityChart.options.datasets = window.equityChart.options.datasets || {};
          window.equityChart.data.datasets[0].borderColor = line;
          window.equityChart.data.datasets[0].backgroundColor = gradient;
          window.equityChart.update("none");
        } else {
          window.equityChart = new Chart(ctx, {
            type: "line",
            data: { labels: data.labels || [], datasets: [{ data: values, borderColor: line, backgroundColor: gradient, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, fill: true, tension: 0.25 }] },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              interaction: { intersect: false, mode: "index" },
              plugins: { legend: { display: false }, tooltip: { backgroundColor: "rgba(2, 6, 23, 0.95)", borderColor: "rgba(51, 65, 85, 0.8)", borderWidth: 1, titleColor: "#94a3b8", bodyColor: "#f1f5f9", padding: 10, callbacks: { label: (item) => ` ${item.parsed.y?.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT` } } },
              scales: { x: { grid: { display: false }, ticks: { color: "#475569", maxTicksLimit: 6, font: { size: 10 } }, border: { display: false } }, y: { position: "right", grid: { color: "rgba(51, 65, 85, 0.25)" }, ticks: { color: "#475569", font: { size: 10 }, callback: (v) => v.toLocaleString(undefined, { maximumFractionDigits: 2 }) }, border: { display: false } } },
            },
          });
        }
      } catch (error) {
        console.warn("equity chart", error);
      }
    };

    const loadBacktest = () => {
      const canvas = document.getElementById("backtestChart");
      if (!canvas || !window.BACKTEST_CURVE || !window.Chart) return;
      const curve = window.BACKTEST_CURVE;
      const labels = curve.map((point) => (point[0] || "").replace("T", " ").slice(5, 16));
      const values = curve.map((point) => Number(point[1]));
      const ctx = canvas.getContext("2d");
      const gradient = ctx.createLinearGradient(0, 0, 0, canvas.parentElement.clientHeight || 280);
      gradient.addColorStop(0, "rgba(16, 185, 129, 0.28)");
      gradient.addColorStop(1, "rgba(16, 185, 129, 0.00)");
      const rising = values.length < 2 || values[values.length - 1] >= values[0];
      const line = rising ? emerald : rose;
      new Chart(ctx, {
        type: "line",
        data: { labels, datasets: [{ data: values, borderColor: line, backgroundColor: gradient, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, fill: true, tension: 0.25 }] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { intersect: false, mode: "index" },
          plugins: { legend: { display: false }, tooltip: { backgroundColor: "rgba(2, 6, 23, 0.95)", borderColor: "rgba(51, 65, 85, 0.8)", borderWidth: 1, titleColor: "#94a3b8", bodyColor: "#f1f5f9", padding: 10, callbacks: { label: (item) => ` ${item.parsed.y?.toLocaleString(undefined, { maximumFractionDigits: 2 })} USDT` } } },
          scales: { x: { grid: { display: false }, ticks: { color: "#475569", maxTicksLimit: 6, font: { size: 10 } }, border: { display: false } }, y: { position: "right", grid: { color: "rgba(51, 65, 85, 0.25)" }, ticks: { color: "#475569", font: { size: 10 }, callback: (v) => v.toLocaleString(undefined, { maximumFractionDigits: 2 }) }, border: { display: false } } },
        },
      });
    };

    loadEquity();
    loadBacktest();
    window.setInterval(loadEquity, 30000);
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
