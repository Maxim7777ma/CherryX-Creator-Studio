(function () {
  const panelSelector = ".detail-panel[data-section='files']";
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
      console.error("Failed to load stats files:", error);
      panel.classList.add("has-load-error");
    } finally {
      document.querySelector(panelSelector)?.classList.remove("is-loading");
    }
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
          button.textContent = original || "Редактировать дизайн";
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
      if (!target || !form) return;
      event.preventDefault();
      submitFilters(form, Number(target.dataset.page || 1) || 1);
    });

    setupShare(panel);
    setupDesignButtons(panel);
  }

  function initLanguageSwitchers() {
    document.querySelectorAll(".language-switcher").forEach((switcher) => {
      if (switcher.dataset.languageReady === "1") return;
      switcher.dataset.languageReady = "1";
      const button = switcher.querySelector(".language-current");
      if (!button) return;
      switcher.addEventListener("click", (event) => event.stopPropagation());
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const open = switcher.classList.toggle("is-open");
        button.setAttribute("aria-expanded", open ? "true" : "false");
      });
    });
    if (!window.__statsLanguageCloseBound) {
      window.__statsLanguageCloseBound = true;
      document.addEventListener("click", (event) => {
        document.querySelectorAll(".language-switcher").forEach((switcher) => {
          if (switcher.contains(event.target)) return;
          switcher.classList.remove("is-open");
          switcher.querySelector(".language-current")?.setAttribute("aria-expanded", "false");
        });
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initStatsPanel);
  document.addEventListener("DOMContentLoaded", initLanguageSwitchers);
  window.addEventListener("popstate", function () {
    const state = getQueryState();
    loadPanel(buildUrl(state.q, state.type, state.page), false);
  });
})();
