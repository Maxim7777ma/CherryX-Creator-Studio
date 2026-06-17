(() => {
  const roots = document.querySelectorAll("[data-project-list]");
  if (!roots.length) return;

  document.querySelectorAll(".language-switcher").forEach((switcher) => {
    const button = switcher.querySelector(".language-current");
    if (!button) return;
    const positionMenu = () => {
      const rect = button.getBoundingClientRect();
      const safeGap = 14;
      const menuWidth = 230;
      const right = Math.max(safeGap, window.innerWidth - rect.right);
      const top = Math.min(rect.bottom + 8, window.innerHeight - 80);
      switcher.style.setProperty("--language-menu-top", `${Math.max(safeGap, top)}px`);
      switcher.style.setProperty(
        "--language-menu-right",
        `${Math.min(right, Math.max(safeGap, window.innerWidth - menuWidth - safeGap))}px`
      );
    };
    switcher.addEventListener("click", (event) => event.stopPropagation());
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = switcher.classList.toggle("is-open");
      button.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) positionMenu();
    });
    window.addEventListener("resize", () => {
      if (switcher.classList.contains("is-open")) positionMenu();
    });
    window.addEventListener("scroll", () => {
      if (switcher.classList.contains("is-open")) positionMenu();
    }, { passive: true });
    document.addEventListener("click", () => {
      switcher.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
    });
  });

  roots.forEach((root) => {
    const filters = root.querySelector("[data-project-filters]");
    const grid = root.querySelector("[data-project-grid]");
    const empty = root.querySelector("[data-project-empty]");
    const total = root.querySelector("[data-project-total]");
    const modal = document.querySelector("[data-delete-modal]");
    const modalTitle = modal?.querySelector("[data-modal-title]");
    const modalCopy = modal?.querySelector("[data-modal-copy]");
    const modalList = modal?.querySelector("[data-modal-list]");
    const modalConfirm = modal?.querySelector("[data-modal-confirm]");
    const modalCancel = modal?.querySelectorAll("[data-modal-cancel]") || [];
    const bulk = root.querySelector("[data-project-bulk]");
    const selectedCount = root.querySelector("[data-selected-count]");
    if (!filters || !grid) return;

    let loading = false;
    let pendingDelete = null;
    const i18n = window.CX_MUSIC_MESSAGES || {};
    const t = (key, fallback, vars = {}) => {
      let value = i18n[key] || fallback || key;
      Object.entries(vars).forEach(([name, replacement]) => {
        value = value.replaceAll(`{${name}}`, String(replacement));
      });
      return value;
    };
    const setLoading = (value) => {
      loading = value;
      root.classList.toggle("is-loading-projects", value);
      filters.querySelectorAll("button, input, select").forEach((control) => {
        control.disabled = value;
      });
    };

    const setupSortDropdown = () => {
      const sortSelect = filters.querySelector('select[name="sort"]');
      if (!sortSelect || filters.querySelector("[data-mobile-sort-dropdown]")) return;
      sortSelect.dataset.nativeProjectSort = "";
      sortSelect.closest("label")?.classList.add("project-filter-sort", "has-custom-sort-dropdown");
      const sortDropdown = document.createElement("div");
      sortDropdown.className = "project-sort-dropdown";
      sortDropdown.dataset.mobileSortDropdown = "";
      sortDropdown.innerHTML = `
        <button class="project-sort-trigger" type="button" data-mobile-sort-trigger aria-haspopup="listbox" aria-expanded="false">
          <span data-mobile-sort-current></span>
        </button>
        <div class="project-sort-menu" role="listbox" data-mobile-sort-menu></div>
      `;
      sortSelect.insertAdjacentElement("afterend", sortDropdown);

      const trigger = sortDropdown.querySelector("[data-mobile-sort-trigger]");
      const current = sortDropdown.querySelector("[data-mobile-sort-current]");
      const menu = sortDropdown.querySelector("[data-mobile-sort-menu]");
      const closeSort = () => {
        sortDropdown.classList.remove("is-open");
        trigger?.setAttribute("aria-expanded", "false");
      };
      const renderSort = () => {
        if (!menu || !current) return;
        const options = Array.from(sortSelect.options);
        const selected = options.find((option) => option.value === sortSelect.value) || options[0];
        current.textContent = selected?.textContent?.trim() || "";
        menu.innerHTML = "";
        options.forEach((option) => {
          const item = document.createElement("button");
          item.type = "button";
          item.className = "project-sort-option";
          item.dataset.sortValue = option.value;
          item.setAttribute("role", "option");
          item.setAttribute("aria-selected", option.value === sortSelect.value ? "true" : "false");
          item.textContent = option.textContent.trim();
          item.addEventListener("click", () => {
            sortSelect.value = option.value;
            sortSelect.dispatchEvent(new Event("change", {bubbles: true}));
            renderSort();
            closeSort();
          });
          menu.appendChild(item);
        });
      };
      trigger?.addEventListener("click", (event) => {
        event.stopPropagation();
        if (trigger.disabled) return;
        const open = !sortDropdown.classList.contains("is-open");
        filters.querySelectorAll("[data-mobile-sort-dropdown].is-open").forEach((dropdown) => {
          if (dropdown !== sortDropdown) dropdown.classList.remove("is-open");
        });
        sortDropdown.classList.toggle("is-open", open);
        trigger.setAttribute("aria-expanded", open ? "true" : "false");
      });
      sortDropdown.addEventListener("click", (event) => event.stopPropagation());
      sortSelect.addEventListener("change", renderSort);
      document.addEventListener("click", closeSort);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeSort();
      });
      renderSort();
    };

    const syncFromDocument = (doc, mode) => {
      const nextGrid = doc.querySelector("[data-project-grid]");
      const nextEmpty = doc.querySelector("[data-project-empty]");
      const nextTotal = doc.querySelector("[data-project-total]");
      const nextPagination = doc.querySelector("[data-project-pagination]");
      const currentPagination = root.querySelector("[data-project-pagination]");
      if (nextGrid) {
        if (mode === "append") grid.insertAdjacentHTML("beforeend", nextGrid.innerHTML);
        else grid.innerHTML = nextGrid.innerHTML;
      }
      if (nextEmpty && empty) empty.hidden = nextEmpty.hidden;
      if (nextTotal && total) total.textContent = nextTotal.textContent;
      if (nextPagination) {
        if (currentPagination) currentPagination.replaceWith(nextPagination);
        else root.appendChild(nextPagination);
      } else if (currentPagination) {
        currentPagination.remove();
      }
      root.dispatchEvent(new CustomEvent("project-list:updated", {bubbles: true}));
      enhanceCards();
      updateBulk();
    };

    const load = async (url, mode = "replace") => {
      if (loading) return;
      setLoading(true);
      try {
        const response = await fetch(url, {headers: {"X-Requested-With": "XMLHttpRequest"}});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const html = await response.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        syncFromDocument(doc, mode);
        window.history.replaceState({}, "", url);
      } finally {
        setLoading(false);
      }
    };

    const cards = () => Array.from(grid.querySelectorAll("[data-project-id]"));

    const selectedCards = () => cards().filter((card) => card.querySelector("[data-project-select]")?.checked);

    const projectInfo = (card) => ({
      id: Number(card.dataset.projectId || 0),
      title: card.dataset.projectTitle || card.querySelector("[data-project-title-text]")?.textContent?.trim() || t("untitled_project", "Untitled project"),
    });

    const updateBulk = () => {
      const count = selectedCards().length;
      if (bulk) bulk.hidden = count === 0;
      if (selectedCount) selectedCount.textContent = `${count} ${t("selected", "selected")}`;
      cards().forEach((card) => card.classList.toggle("is-selected", Boolean(card.querySelector("[data-project-select]")?.checked)));
    };

    const requestJson = async (url, options = {}) => {
      const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
      const response = await fetch(url, {
        ...options,
        headers: {
          "Accept": "application/json",
          ...(options.body ? {"Content-Type": "application/json", "X-CSRFToken": decodeURIComponent(csrf)} : {}),
          ...(options.headers || {}),
        },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return response.json();
    };

    const escapeHtml = (value) => String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");

    const openDeleteModal = (items) => {
      if (!modal || !modalTitle || !modalCopy || !modalList) return;
      pendingDelete = items;
      modalTitle.textContent = items.length === 1
        ? t("delete_project_question", "Delete this project?")
        : t("delete_projects_question", `Delete ${items.length} projects?`, {count: items.length});
      modalCopy.textContent = items.length === 1
        ? t("delete_uploaded_files_copy", "This will remove the project and its uploaded files from the server.")
        : t("delete_uploaded_files_many_copy", "Selected projects and their uploaded files will be removed from the server.");
      modalList.innerHTML = items.slice(0, 5).map((item) => `<span>${escapeHtml(item.title)}</span>`).join("");
      if (items.length > 5) modalList.insertAdjacentHTML("beforeend", `<small>+${items.length - 5} ${escapeHtml(t("more", "more"))}</small>`);
      modal.hidden = false;
      document.body.classList.add("project-delete-open");
      modalConfirm?.focus();
    };

    const closeDeleteModal = (force = false) => {
      if (!modal || (!force && modalConfirm?.disabled)) return;
      modal.hidden = true;
      document.body.classList.remove("project-delete-open");
      pendingDelete = null;
    };

    const removeDeletedCards = (ids) => {
      ids.forEach((id) => {
        const card = grid.querySelector(`[data-project-id="${id}"]`);
        if (!card) return;
        card.classList.add("is-removing");
        window.setTimeout(() => {
          card.remove();
          if (empty) empty.hidden = cards().length > 0;
          updateBulk();
        }, 180);
      });
    };

    const enhanceCards = () => {
      cards().forEach((card) => {
        if (card.dataset.projectLiveBound) return;
        card.dataset.projectLiveBound = "1";
        card.querySelector("[data-project-select]")?.addEventListener("change", updateBulk);
        card.querySelector("[data-delete-project]")?.addEventListener("click", () => openDeleteModal([projectInfo(card)]));
        card.querySelector("[data-duplicate-project]")?.addEventListener("click", async (event) => {
          event.preventDefault();
          const id = event.currentTarget.dataset.duplicateProject;
          if (!id || !root.dataset.designerUrl) return;
          const data = await requestJson(`${root.dataset.apiUrl}${id}/duplicate/`, {method: "POST", body: "{}"});
          window.location.href = `${root.dataset.designerUrl}?project=${data.project.id}`;
        });
        card.querySelector("[data-project-title-text]")?.addEventListener("dblclick", () => {
          const title = card.querySelector("[data-project-title-text]");
          if (!title) return;
          const original = title.textContent.trim();
          const input = document.createElement("input");
          input.className = "video-project-title-input";
          input.value = original;
          input.maxLength = 180;
          title.replaceWith(input);
          input.focus();
          input.select();
          let done = false;
          const finish = async (save) => {
            if (done) return;
            done = true;
            const restored = document.createElement("strong");
            restored.className = "video-project-title";
            restored.dataset.projectTitleText = "";
            restored.title = t("double_click_rename", "Double-click to rename");
            restored.textContent = original;
            input.replaceWith(restored);
            card.dataset.projectLiveBound = "";
            enhanceCards();
            const next = input.value.trim() || original;
            if (!save || next === original) return;
            const data = await requestJson(`${root.dataset.apiUrl}${card.dataset.projectId}/rename/`, {method: "POST", body: JSON.stringify({title: next})});
            restored.textContent = data.project?.title || next;
            card.dataset.projectTitle = restored.textContent;
          };
          input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") finish(true);
            if (event.key === "Escape") finish(false);
          });
          input.addEventListener("blur", () => finish(true), {once: true});
        });
      });
    };

    const editorHref = (id) => {
      const base = root.dataset.editorUrl || root.dataset.designerUrl || "";
      const joiner = base.includes("?") ? "&" : "?";
      return `${base}${joiner}project=${id}`;
    };

    const setupMobileDesignProjects = () => {
      if (!root.matches("[data-design-projects]") || root.dataset.mobileDesignProjectsReady === "1") return;
      root.dataset.mobileDesignProjectsReady = "1";
      const media = window.matchMedia("(max-width: 760px)");
      const head = root.querySelector(".video-projects-head");
      const sortSelect = filters.querySelector('.project-filter-sort select[name="sort"]');
      let filterToggle = root.querySelector("[data-mobile-project-filters]");
      let backdrop = document.querySelector("[data-design-projects-mobile-backdrop]");
      let sortDropdown = filters.querySelector("[data-mobile-sort-dropdown]");

      if (head && !filterToggle) {
        filterToggle = document.createElement("button");
        filterToggle.type = "button";
        filterToggle.className = "design-project-mobile-filter-toggle";
        filterToggle.dataset.mobileProjectFilters = "";
        filterToggle.setAttribute("aria-expanded", "false");
        filterToggle.setAttribute("aria-label", t("filters", "Filters"));
        filterToggle.innerHTML = "";
        head.appendChild(filterToggle);
      }

      if (!backdrop) {
        backdrop = document.createElement("button");
        backdrop.type = "button";
        backdrop.className = "design-project-mobile-backdrop";
        backdrop.dataset.designProjectsMobileBackdrop = "";
        backdrop.setAttribute("aria-label", t("close", "Close"));
        document.body.appendChild(backdrop);
      }

      if (sortSelect && !sortDropdown) {
        sortSelect.dataset.nativeProjectSort = "";
        sortSelect.closest(".project-filter-sort")?.classList.add("has-custom-sort-dropdown");
        sortDropdown = document.createElement("div");
        sortDropdown.className = "project-sort-dropdown";
        sortDropdown.dataset.mobileSortDropdown = "";
        sortDropdown.innerHTML = `
          <button class="project-sort-trigger" type="button" data-mobile-sort-trigger aria-haspopup="listbox" aria-expanded="false">
            <span data-mobile-sort-current></span>
          </button>
          <div class="project-sort-menu" role="listbox" data-mobile-sort-menu></div>
        `;
        sortSelect.insertAdjacentElement("afterend", sortDropdown);

        const trigger = sortDropdown.querySelector("[data-mobile-sort-trigger]");
        const current = sortDropdown.querySelector("[data-mobile-sort-current]");
        const menu = sortDropdown.querySelector("[data-mobile-sort-menu]");
        const closeSort = () => {
          sortDropdown?.classList.remove("is-open");
          trigger?.setAttribute("aria-expanded", "false");
        };
        const renderSort = () => {
          if (!menu || !current) return;
          const options = Array.from(sortSelect.options);
          const selected = options.find((option) => option.value === sortSelect.value) || options[0];
          current.textContent = selected?.textContent?.trim() || "";
          menu.innerHTML = "";
          options.forEach((option) => {
            const item = document.createElement("button");
            item.type = "button";
            item.className = "project-sort-option";
            item.dataset.sortValue = option.value;
            item.setAttribute("role", "option");
            item.setAttribute("aria-selected", option.value === sortSelect.value ? "true" : "false");
            item.textContent = option.textContent.trim();
            item.addEventListener("click", () => {
              sortSelect.value = option.value;
              sortSelect.dispatchEvent(new Event("change", {bubbles: true}));
              renderSort();
              closeSort();
            });
            menu.appendChild(item);
          });
        };
        trigger?.addEventListener("click", (event) => {
          event.stopPropagation();
          if (trigger.disabled) return;
          const open = !sortDropdown.classList.contains("is-open");
          filters.querySelectorAll("[data-mobile-sort-dropdown].is-open").forEach((dropdown) => {
            if (dropdown !== sortDropdown) dropdown.classList.remove("is-open");
          });
          sortDropdown.classList.toggle("is-open", open);
          trigger.setAttribute("aria-expanded", open ? "true" : "false");
        });
        sortDropdown.addEventListener("click", (event) => event.stopPropagation());
        sortSelect.addEventListener("change", renderSort);
        document.addEventListener("click", closeSort);
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape") closeSort();
        });
        renderSort();
      }

      const closeFilters = () => {
        document.body.classList.remove("is-mobile-design-filter-open");
        filterToggle?.setAttribute("aria-expanded", "false");
        sortDropdown?.classList.remove("is-open");
        sortDropdown?.querySelector("[data-mobile-sort-trigger]")?.setAttribute("aria-expanded", "false");
      };

      const syncMode = () => {
        document.body.classList.toggle("is-mobile-design-projects", media.matches);
        if (!media.matches) closeFilters();
      };

      filterToggle?.addEventListener("click", () => {
        if (!media.matches) return;
        const open = !document.body.classList.contains("is-mobile-design-filter-open");
        document.body.classList.toggle("is-mobile-design-filter-open", open);
        filterToggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
          window.setTimeout(() => filters.querySelector("input, [data-mobile-sort-trigger], button")?.focus({preventScroll: true}), 80);
        }
      });

      backdrop.addEventListener("click", closeFilters);
      filters.addEventListener("submit", closeFilters);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeFilters();
      });

      root.addEventListener("pointerdown", (event) => {
        if (!media.matches) return;
        const card = event.target instanceof Element ? event.target.closest(".design-project-card") : null;
        if (!card) return;
        card.classList.add("is-mobile-pressed");
      }, {passive: true});

      root.addEventListener("pointerup", () => {
        if (!media.matches) return;
        root.querySelectorAll(".design-project-card.is-mobile-pressed").forEach((card) => card.classList.remove("is-mobile-pressed"));
      }, {passive: true});

      root.addEventListener("project-list:updated", () => {
        if (!media.matches) return;
        window.requestAnimationFrame(() => {
          root.querySelector("[data-project-grid]")?.scrollIntoView({block: "start", behavior: "smooth"});
        });
      });

      syncMode();
      media.addEventListener?.("change", syncMode);
    };

    const setupMobileVideoProjects = () => {
      if (!root.matches("[data-video-projects]") || root.dataset.mobileVideoProjectsReady === "1") return;
      root.dataset.mobileVideoProjectsReady = "1";
      const media = window.matchMedia("(max-width: 760px)");
      const head = root.querySelector(".video-projects-head");
      let filterToggle = root.querySelector("[data-mobile-project-filters]");
      let backdrop = document.querySelector("[data-video-projects-mobile-backdrop]");

      if (head && !filterToggle) {
        filterToggle = document.createElement("button");
        filterToggle.type = "button";
        filterToggle.className = "video-project-mobile-filter-toggle";
        filterToggle.dataset.mobileProjectFilters = "";
        filterToggle.setAttribute("aria-expanded", "false");
        filterToggle.setAttribute("aria-label", t("filters", "Filters"));
        head.appendChild(filterToggle);
      }

      if (!backdrop) {
        backdrop = document.createElement("button");
        backdrop.type = "button";
        backdrop.className = "video-project-mobile-backdrop";
        backdrop.dataset.videoProjectsMobileBackdrop = "";
        backdrop.setAttribute("aria-label", t("close", "Close"));
        document.body.appendChild(backdrop);
      }

      const closeFilters = () => {
        document.body.classList.remove("is-mobile-video-filter-open");
        filterToggle?.setAttribute("aria-expanded", "false");
      };

      const syncMode = () => {
        document.body.classList.toggle("is-mobile-video-projects", media.matches);
        if (!media.matches) closeFilters();
      };

      filterToggle?.addEventListener("click", () => {
        if (!media.matches) return;
        const open = !document.body.classList.contains("is-mobile-video-filter-open");
        document.body.classList.toggle("is-mobile-video-filter-open", open);
        filterToggle.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) window.setTimeout(() => filters.querySelector("input, select, button")?.focus({ preventScroll: true }), 80);
      });

      backdrop.addEventListener("click", closeFilters);
      filters.addEventListener("submit", closeFilters);
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") closeFilters();
      });

      root.addEventListener("pointerdown", (event) => {
        if (!media.matches) return;
        const card = event.target instanceof Element ? event.target.closest(".video-project-card") : null;
        if (!card || card.classList.contains("design-project-card")) return;
        card.classList.add("is-mobile-pressed");
      }, { passive: true });

      root.addEventListener("pointerup", () => {
        if (!media.matches) return;
        root.querySelectorAll(".video-project-card.is-mobile-pressed").forEach((card) => card.classList.remove("is-mobile-pressed"));
      }, { passive: true });

      root.addEventListener("project-list:updated", () => {
        if (!media.matches) return;
        window.requestAnimationFrame(() => root.querySelector("[data-project-grid]")?.scrollIntoView({ block: "start", behavior: "smooth" }));
      });

      syncMode();
      media.addEventListener?.("change", syncMode);
    };

    root.querySelectorAll("[data-create-project]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (root.matches("[data-music-projects]")) return;
        button.disabled = true;
        try {
          const isDesign = root.matches("[data-design-projects]");
          const title = isDesign ? t("new_design", "New design") : t("new_project", "New project");
          const state = isDesign ? {version: 2, objects: [], vectors: []} : {title, aspect: "9 / 16", trimStart: "0", trimEnd: "100"};
          const data = await requestJson(`${root.dataset.apiUrl}create/`, {
            method: "POST",
            body: JSON.stringify({title, state}),
          });
          window.location.href = editorHref(data.project.id);
        } finally {
          button.disabled = false;
        }
      });
    });

    filters.addEventListener("submit", (event) => {
      event.preventDefault();
      const url = new URL(window.location.href);
      const data = new FormData(filters);
      for (const key of Array.from(url.searchParams.keys())) url.searchParams.delete(key);
      data.forEach((value, key) => {
        const text = String(value || "").trim();
        if (text) url.searchParams.set(key, text);
      });
      load(url.toString());
    });

    root.addEventListener("click", (event) => {
      const target = event.target instanceof Element ? event.target.closest("[data-project-page]") : null;
      if (!target) return;
      event.preventDefault();
      load(target.href, target.dataset.projectPage === "next" ? "append" : "replace");
    });

    if (!root.matches("[data-music-projects]")) {
      root.querySelector("[data-clear-selection]")?.addEventListener("click", () => {
        cards().forEach((card) => {
          const input = card.querySelector("[data-project-select]");
          if (input) input.checked = false;
        });
        updateBulk();
      });

      root.querySelector("[data-delete-selected]")?.addEventListener("click", () => {
        const items = selectedCards().map(projectInfo);
        if (items.length) openDeleteModal(items);
      });
    }

    modalCancel.forEach((button) => button.addEventListener("click", closeDeleteModal));
    modalConfirm?.addEventListener("click", async () => {
      if (!pendingDelete?.length || !modalConfirm) return;
      const items = pendingDelete;
      const originalText = modalConfirm.textContent;
      modalConfirm.disabled = true;
      modalConfirm.textContent = t("deleting", "Deleting...");
      try {
        const data = items.length === 1
          ? await requestJson(`${root.dataset.apiUrl}${items[0].id}/delete/`, {method: "POST", body: "{}"})
          : await requestJson(`${root.dataset.apiUrl}delete/`, {method: "POST", body: JSON.stringify({ids: items.map((item) => item.id)})});
        closeDeleteModal(true);
        removeDeletedCards(data.deleted_ids || items.map((item) => item.id));
      } finally {
        modalConfirm.disabled = false;
        modalConfirm.textContent = originalText;
      }
    });
    enhanceCards();
    updateBulk();
    setupSortDropdown();
    setupMobileDesignProjects();
    setupMobileVideoProjects();
  });
})();
