(function () {
  const panelSelector = ".detail-panel[data-section]";
  let searchTimer = 0;

  function getQueryState() {
    const params = new URLSearchParams(window.location.search);
    return {
      q: params.get("q") || "",
      type: params.get("type") || "",
      page: Number(params.get("page") || 1) || 1,
    };
  }

  function buildUrl(query, type, page) {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (type) params.set("type", type);
    if (page > 1) params.set("page", String(page));
    const queryString = params.toString();
    return queryString ? `${window.location.pathname}?${queryString}` : window.location.pathname;
  }

  async function loadPanel(url, replaceHistory = true) {
    const panel = document.querySelector(panelSelector);
    if (!panel) return;
    panel.classList.add("is-loading");

    try {
      const response = await fetch(url, {
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      const existingPanel = document.querySelector(panelSelector);
      if (existingPanel) existingPanel.outerHTML = data.html;
      if (replaceHistory && window.history.replaceState) window.history.replaceState(null, "", url);
      initStatsPanel();
    } catch (error) {
      console.error("Failed to load stats panel:", error);
      panel.classList.add("has-load-error");
    } finally {
      document.querySelector(panelSelector)?.classList.remove("is-loading");
    }
  }

  function updateAccountStats(stats) {
    if (!stats || typeof stats !== "object") return;
    document.querySelectorAll("[data-account-stat]").forEach((node) => {
      const key = node.dataset.accountStat;
      if (!key || !(key in stats)) return;
      node.textContent = stats[key];
    });
    document.querySelectorAll("[data-account-stat-bar]").forEach((node) => {
      const key = node.dataset.accountStatBar;
      if (!key || !(key in stats)) return;
      const value = Math.max(0, Math.min(100, Number(stats[key] || 0)));
      node.style.width = `${value}%`;
    });
  }

  function currentFormState(form) {
    const formData = new FormData(form);
    return {
      query: String(formData.get("q") || "").trim(),
      type: String(formData.get("type") || "").trim(),
    };
  }

  function submitFilters(form, page = 1) {
    const state = currentFormState(form);
    loadPanel(buildUrl(state.query, state.type, page));
  }

  function setupTypePicker(panel, form) {
    const select = panel.querySelector("[data-stats-type-select]");
    const picker = panel.querySelector("[data-stats-type-picker]");
    const current = panel.querySelector("[data-stats-type-current]");
    const label = panel.querySelector("[data-stats-type-current-label]");
    const icon = panel.querySelector("[data-stats-type-current-icon]");
    const menu = panel.querySelector("[data-stats-type-menu]");
    if (!select || !picker || !current || !label || !menu) return;

    const sync = () => {
      const active = menu.querySelector(`[data-type-value="${CSS.escape(select.value)}"]`) || menu.querySelector("[data-type-value='']");
      menu.querySelectorAll("[data-type-value]").forEach((button) => {
        button.classList.toggle("is-active", button === active);
      });
      label.textContent = active?.textContent?.trim() || select.options[select.selectedIndex]?.textContent || "";
      if (icon) icon.dataset.icon = active?.dataset.typeIcon || "folder";
    };

    sync();
    current.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = menu.hidden;
      menu.hidden = !open;
      picker.classList.toggle("is-open", open);
      current.setAttribute("aria-expanded", open ? "true" : "false");
    });
    menu.addEventListener("click", (event) => {
      const button = event.target.closest("[data-type-value]");
      if (!button) return;
      select.value = button.dataset.typeValue || "";
      menu.hidden = true;
      picker.classList.remove("is-open");
      current.setAttribute("aria-expanded", "false");
      sync();
      submitFilters(form, 1);
    });
    if (!window.__statsTypePickerCloseBound) {
      window.__statsTypePickerCloseBound = true;
      document.addEventListener("click", (event) => {
        document.querySelectorAll("[data-stats-type-picker]").forEach((openPicker) => {
          if (openPicker.contains(event.target)) return;
          openPicker.classList.remove("is-open");
          openPicker.querySelector("[data-stats-type-current]")?.setAttribute("aria-expanded", "false");
          const openMenu = openPicker.querySelector("[data-stats-type-menu]");
          if (openMenu) openMenu.hidden = true;
        });
      });
    }
  }

  function setupShare(panel) {
    const shareModal = panel.querySelector("#share-modal");
    const shareLinkInput = panel.querySelector("#share-link");
    const shareChannels = panel.querySelectorAll(".share-channel");
    const shareClose = panel.querySelector(".share-modal-close");
    const shareButtons = panel.querySelectorAll(".stats-share-btn");

    shareButtons.forEach((btn) => {
      btn.addEventListener("click", function (event) {
        event.preventDefault();
        const url = btn.dataset.shareUrl;
        const name = btn.dataset.shareName;
        if (!url || !shareModal || !shareLinkInput) return;
        shareLinkInput.value = window.location.origin + url;
        shareModal.dataset.shareUrl = url;
        shareModal.dataset.shareName = name || "";
        shareModal.hidden = false;
        shareLinkInput.focus();
        shareLinkInput.select();
      });
    });

    shareChannels.forEach((channel) => {
      channel.addEventListener("click", async function (event) {
        event.preventDefault();
        const link = shareLinkInput?.value || "";
        const name = shareModal?.dataset.shareName || "";
        const ch = channel.dataset.channel;

        if (ch === "copy") {
          await navigator.clipboard.writeText(link);
          channel.textContent = "Copied";
          window.setTimeout(() => {
            channel.textContent = "Copy link";
            if (shareModal) shareModal.hidden = true;
          }, 650);
        } else if (ch === "telegram") {
          window.open(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(name)}`, "_blank");
        } else if (ch === "whatsapp") {
          window.open(`https://wa.me/?text=${encodeURIComponent(`${name} ${link}`)}`, "_blank");
        } else if (ch === "email") {
          window.location.href = `mailto:?subject=${encodeURIComponent(name)}&body=${encodeURIComponent(link)}`;
        }
      });
    });

    shareClose?.addEventListener("click", function () {
      if (shareModal) shareModal.hidden = true;
    });
  }

  function csrfToken() {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function openDeleteModal(row) {
    const modal = document.querySelector("[data-stats-delete-modal]");
    if (!modal) return Promise.resolve(window.confirm("Delete this task?"));
    const name = row?.dataset.jobTitle || row?.querySelector("b")?.textContent?.trim() || "";
    const nameNode = modal.querySelector("[data-stats-delete-name]");
    const confirmButton = modal.querySelector("[data-stats-delete-confirm]");
    if (nameNode) nameNode.textContent = name;
    modal.hidden = false;
    document.body.classList.add("stats-delete-open");
    window.requestAnimationFrame(() => modal.classList.add("is-open"));
    confirmButton?.focus();

    return new Promise((resolve) => {
      const finish = (value) => {
        modal.classList.remove("is-open");
        modal.hidden = true;
        document.body.classList.remove("stats-delete-open");
        modal.removeEventListener("click", onClick);
        document.removeEventListener("keydown", onKeydown);
        resolve(value);
      };
      const onClick = (event) => {
        if (event.target.closest("[data-stats-delete-confirm]")) finish(true);
        if (event.target.closest("[data-stats-delete-cancel]")) finish(false);
      };
      const onKeydown = (event) => {
        if (event.key === "Escape") finish(false);
      };
      modal.addEventListener("click", onClick);
      document.addEventListener("keydown", onKeydown);
    });
  }

  async function deleteStatsJob(form) {
    if (form.dataset.loading === "1") return;
    const row = form.closest("[data-stats-job-row]");
    const confirmed = await openDeleteModal(row);
    if (!confirmed) return;

    const button = form.querySelector("button[type='submit']");
    const originalText = button?.textContent || "";
    form.dataset.loading = "1";
    row?.classList.add("is-deleting");
    if (button) {
      button.disabled = true;
      button.textContent = "...";
    }

    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.ok === false) throw new Error(data.error || "Could not delete task");
      updateAccountStats(data.account_stats);
      await loadPanel(window.location.href, false);
    } catch (error) {
      row?.classList.remove("is-deleting");
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
      alert(error.message || "Could not delete task");
    } finally {
      form.dataset.loading = "0";
    }
  }

  function setupDeleteForms(panel) {
    panel.querySelectorAll("[data-stats-delete-form]").forEach((form) => {
      if (form.dataset.deleteReady === "1") return;
      form.dataset.deleteReady = "1";
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        deleteStatsJob(form);
      });
    });
  }

  function setupDesignButtons(panel) {
    panel.querySelectorAll("[data-edit-design-url]").forEach((button) => {
      if (button.dataset.designReady === "1") return;
      button.dataset.designReady = "1";
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        if (button.dataset.loading === "1") return;
        const original = button.textContent;
        button.dataset.loading = "1";
        button.textContent = "Opening...";
        try {
          const response = await fetch(button.dataset.editDesignUrl || "", {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
          });
          const data = await response.json();
          if (!response.ok || !data.designer_url) throw new Error(data.error || "Design import failed");
          window.location.href = data.designer_url;
        } catch (error) {
          button.textContent = original || "Edit design";
          button.dataset.loading = "0";
          alert(error.message || "Design import failed");
        }
      });
    });
  }

  function initStatsPanel() {
    const panel = document.querySelector(panelSelector);
    if (!panel || panel.dataset.statsReady === "1") return;
    panel.dataset.statsReady = "1";

    const form = panel.querySelector("#stats-files-filter-form");
    const pagination = panel.querySelector(".stats-files-pagination");
    if (form) {
      setupTypePicker(panel, form);
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        submitFilters(form, 1);
      });
      form.querySelector("input[type='search']")?.addEventListener("input", function () {
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => submitFilters(form, 1), 320);
      });
    }

    pagination?.addEventListener("click", function (event) {
      const target = event.target.closest("a[data-page]");
      if (!target) return;
      event.preventDefault();
      if (form) submitFilters(form, Number(target.dataset.page || 1) || 1);
      else loadPanel(target.href);
    });

    setupShare(panel);
    setupDesignButtons(panel);
    setupDeleteForms(panel);
  }

  function initLanguageSwitchers() {
    // Language switching is handled by the shared portal script in _language_switcher.html.
  }

  document.addEventListener("DOMContentLoaded", initStatsPanel);
  document.addEventListener("DOMContentLoaded", initLanguageSwitchers);
  window.addEventListener("popstate", function () {
    const state = getQueryState();
    loadPanel(buildUrl(state.q, state.type, state.page), false);
  });
})();
