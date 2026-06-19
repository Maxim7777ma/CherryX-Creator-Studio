(() => {
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
    document.addEventListener("click", (event) => {
      if (!switcher.contains(event.target)) {
        switcher.classList.remove("is-open");
        button.setAttribute("aria-expanded", "false");
      }
    });
  });

  const root = document.querySelector("[data-music-projects]");
  if (!root) return;

  const i18n = window.CX_MUSIC_MESSAGES || {};
  const t = (key, fallback, vars = {}) => {
    let value = i18n[key] || fallback || key;
    Object.entries(vars).forEach(([name, replacement]) => {
      value = value.replaceAll(`{${name}}`, String(replacement));
    });
    return value;
  };

  const apiUrl = root.dataset.apiUrl;
  const editorUrl = root.dataset.editorUrl || "/app/music-editor/";
  const bulkBar = root.querySelector("[data-project-bulk]");
  const selectedCount = root.querySelector("[data-selected-count]");
  const totalCount = root.querySelector("[data-project-total]");
  const clearSelection = root.querySelector("[data-clear-selection]");
  const deleteSelected = root.querySelector("[data-delete-selected]");
  const grid = root.querySelector("[data-project-grid]");
  const emptyState = root.querySelector("[data-project-empty]");
  const filters = root.querySelector("[data-project-filters]");
  const modal = document.querySelector("[data-delete-modal]");
  const modalTitle = modal?.querySelector("[data-modal-title]");
  const modalCopy = modal?.querySelector("[data-modal-copy]");
  const modalList = modal?.querySelector("[data-modal-list]");
  const modalConfirm = modal?.querySelector("[data-modal-confirm]");
  const modalCancel = modal?.querySelectorAll("[data-modal-cancel]") || [];
  let pendingDelete = null;
  let knownTotal = Number(totalCount?.textContent || 0) || 0;
  let previewAudio = null;
  let activePreviewPlayer = null;

  const csrfToken = (() => {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  })();

  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? {"Content-Type": "application/json", "X-CSRFToken": csrfToken} : {}),
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

  const setupSortDropdown = () => {
    const sortSelect = filters?.querySelector('select[name="sort"]');
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
    menu?.setAttribute("data-project-sort-portal", "");
    if (menu) document.body.appendChild(menu);
    const positionSortMenu = () => {
      if (!trigger || !menu) return;
      const rect = trigger.getBoundingClientRect();
      const safeGap = 12;
      const menuGap = 10;
      const width = Math.min(Math.max(rect.width, 180), window.innerWidth - safeGap * 2);
      const left = Math.min(Math.max(safeGap, rect.left), window.innerWidth - width - safeGap);
      const spaceBelow = window.innerHeight - rect.bottom - safeGap - menuGap;
      const spaceAbove = rect.top - safeGap - menuGap;
      const openAbove = window.matchMedia("(max-width: 760px)").matches || spaceBelow < 190 && spaceAbove > spaceBelow;
      const maxHeight = Math.max(132, Math.min(260, openAbove ? spaceAbove : spaceBelow));
      menu.style.left = `${left}px`;
      menu.style.width = `${width}px`;
      menu.style.maxHeight = `${maxHeight}px`;
      if (openAbove) {
        menu.style.top = "auto";
        menu.style.bottom = `${Math.max(safeGap, window.innerHeight - rect.top + menuGap)}px`;
      } else {
        menu.style.top = `${Math.min(rect.bottom + menuGap, window.innerHeight - safeGap - maxHeight)}px`;
        menu.style.bottom = "auto";
      }
      menu.classList.toggle("is-above", openAbove);
    };
    const closeSort = () => {
      sortDropdown.classList.remove("is-open");
      menu?.classList.remove("is-open", "is-above");
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
      menu?.classList.toggle("is-open", open);
      trigger.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) positionSortMenu();
    });
    sortDropdown.addEventListener("click", (event) => event.stopPropagation());
    menu?.addEventListener("click", (event) => event.stopPropagation());
    sortSelect.addEventListener("change", renderSort);
    document.addEventListener("click", closeSort);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeSort();
    });
    window.addEventListener("resize", () => {
      if (sortDropdown.classList.contains("is-open")) positionSortMenu();
    });
    window.addEventListener("scroll", () => {
      if (sortDropdown.classList.contains("is-open")) positionSortMenu();
    }, {passive: true});
    renderSort();
  };

  const setupMobileProjectFilters = () => {
    if (!filters || root.dataset.mobileMusicProjectsReady === "1") return;
    root.dataset.mobileMusicProjectsReady = "1";
    const media = window.matchMedia("(max-width: 760px)");
    const head = root.querySelector(".music-projects-head");
    let filterToggle = root.querySelector("[data-mobile-project-filters]");

    if (head && !filterToggle) {
      filterToggle = document.createElement("button");
      filterToggle.type = "button";
      filterToggle.className = "video-project-mobile-filter-toggle";
      filterToggle.dataset.mobileProjectFilters = "";
      filterToggle.setAttribute("aria-expanded", "false");
      filterToggle.setAttribute("aria-label", t("filters", "Filters"));
      const createButton = head.querySelector("[data-create-project]");
      if (createButton) createButton.before(filterToggle);
      else head.appendChild(filterToggle);
    }

    const closeFilters = () => {
      document.body.classList.remove("is-mobile-video-filter-open");
      filterToggle?.setAttribute("aria-expanded", "false");
      filters.querySelectorAll("[data-mobile-sort-dropdown].is-open").forEach((dropdown) => dropdown.classList.remove("is-open"));
      document.querySelectorAll("[data-project-sort-portal].is-open").forEach((menu) => menu.classList.remove("is-open", "is-above"));
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
      if (open) window.setTimeout(() => filters.querySelector("input, [data-mobile-sort-trigger], button")?.focus({preventScroll: true}), 80);
    });

    filters.addEventListener("submit", closeFilters);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeFilters();
    });

    syncMode();
    media.addEventListener?.("change", syncMode);
  };

  const cards = () => [...root.querySelectorAll("[data-project-id]")];
  const selectedCards = () => cards().filter((card) => card.querySelector("[data-project-select]")?.checked);
  const projectInfo = (card) => ({
    id: Number(card.dataset.projectId),
    title: card.dataset.projectTitle || card.querySelector("[data-project-title-text]")?.textContent?.trim() || t("untitled_project", "Untitled project"),
  });

  const editorHref = (id) => {
    const joiner = editorUrl.includes("?") ? "&" : "?";
    return `${editorUrl}${joiner}project=${id}`;
  };

  const updateEmptyState = () => {
    const count = cards().length;
    if (totalCount) totalCount.textContent = String(Math.max(knownTotal, count));
    if (emptyState) emptyState.hidden = count > 0;
    if (grid) grid.hidden = count === 0;
  };

  const updateBulkBar = () => {
    const count = selectedCards().length;
    if (bulkBar) bulkBar.hidden = count === 0;
    if (selectedCount) selectedCount.textContent = `${count} ${t("selected", "selected")}`;
    cards().forEach((card) => card.classList.toggle("is-selected", Boolean(card.querySelector("[data-project-select]")?.checked)));
  };

  const setSelection = (checked) => {
    cards().forEach((card) => {
      const input = card.querySelector("[data-project-select]");
      if (input) input.checked = checked;
    });
    updateBulkBar();
  };

  const closeModal = () => {
    if (!modal || modalConfirm?.disabled) return;
    modal.hidden = true;
    document.body.classList.remove("project-delete-open");
    pendingDelete = null;
  };

  const openModal = (items) => {
    if (!modal || !modalTitle || !modalCopy || !modalList) return;
    pendingDelete = items;
    const count = items.length;
    modalTitle.textContent = count === 1 ? t("delete_project_question", "Delete this project?") : t("delete_projects_question", `Delete ${count} projects?`, { count });
    modalCopy.textContent = count === 1
      ? t("delete_project_copy", "This will remove the project and its uploaded audio files from the server.")
      : t("delete_projects_copy", "Selected projects and their uploaded audio files will be removed from the server.");
    modalList.innerHTML = items.slice(0, 5).map((item) => `<span>${escapeHtml(item.title)}</span>`).join("");
    if (count > 5) modalList.insertAdjacentHTML("beforeend", `<small>+${count - 5} ${escapeHtml(t("more", "more"))}</small>`);
    modal.hidden = false;
    document.body.classList.add("project-delete-open");
    modalConfirm?.focus();
  };

  const removeDeletedCards = (ids) => {
    knownTotal = Math.max(0, knownTotal - ids.length);
    ids.forEach((id) => {
      const card = root.querySelector(`[data-project-id="${id}"]`);
      if (!card) return;
      card.classList.add("is-removing");
      window.setTimeout(() => {
        card.remove();
        updateBulkBar();
        updateEmptyState();
      }, 180);
    });
  };

  const startRename = (titleNode) => {
    const card = titleNode.closest("[data-project-id]");
    if (!card || card.classList.contains("is-editing-title")) return;
    const original = titleNode.textContent.trim();
    const input = document.createElement("input");
    input.className = "video-project-title-input";
    input.type = "text";
    input.value = original;
    input.maxLength = 180;
    input.setAttribute("aria-label", t("project_name", "Project name"));
    card.classList.add("is-editing-title");
    titleNode.replaceWith(input);
    input.focus();
    input.select();

    let closed = false;
    const finish = async (save) => {
      if (closed) return;
      closed = true;
      const nextTitle = input.value.trim() || original;
      const restored = document.createElement("strong");
      restored.className = "video-project-title";
      restored.dataset.projectTitleText = "";
      restored.title = t("double_click_rename", "Double-click to rename");
      restored.textContent = original;
      input.replaceWith(restored);
      card.classList.remove("is-editing-title");
      restored.addEventListener("dblclick", () => startRename(restored));
      if (!save || nextTitle === original) return;
      card.classList.add("is-renaming");
      try {
        const data = await requestJson(`${apiUrl}${card.dataset.projectId}/rename/`, {
          method: "POST",
          body: JSON.stringify({title: nextTitle}),
        });
        const savedTitle = data.project?.title || nextTitle;
        restored.textContent = savedTitle;
        card.dataset.projectTitle = savedTitle;
      } finally {
        card.classList.remove("is-renaming");
      }
    };

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        finish(true);
      }
      if (event.key === "Escape") {
        event.preventDefault();
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(true));
  };

  root.querySelectorAll("[data-create-project]").forEach((button) => button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      const data = await requestJson(`${apiUrl}create/`, {
        method: "POST",
        body: JSON.stringify({title: t("new_beat", "New beat"), state: {title: t("new_beat", "New beat"), bpm: 120}}),
      });
      window.location.href = editorHref(data.project.id);
    } finally {
      button.disabled = false;
    }
  }));

  root.querySelectorAll("[data-project-select]").forEach((input) => input.addEventListener("change", updateBulkBar));
  root.querySelectorAll("[data-project-title-text]").forEach((titleNode) => {
    titleNode.addEventListener("dblclick", () => startRename(titleNode));
  });
  clearSelection?.addEventListener("click", () => setSelection(false));
  deleteSelected?.addEventListener("click", () => {
    const items = selectedCards().map(projectInfo);
    if (items.length) openModal(items);
  });
  root.querySelectorAll("[data-delete-project]").forEach((button) => {
    button.addEventListener("click", () => {
      const card = button.closest("[data-project-id]");
      if (card) openModal([projectInfo(card)]);
    });
  });

  const previewTitle = (player) => {
    const card = player?.closest?.("[data-project-id]");
    return card ? projectInfo(card).title : t("untitled_project", "Untitled project");
  };

  const resetPreviewPlayer = (player = activePreviewPlayer) => {
    if (!player) return;
    player.classList.remove("is-playing", "is-loading");
    player.setAttribute("aria-pressed", "false");
    player.setAttribute("aria-label", `${t("play", "Play")}: ${previewTitle(player)}`);
  };

  const stopPreview = () => {
    if (previewAudio) {
      previewAudio.pause();
      previewAudio.currentTime = 0;
    }
    resetPreviewPlayer();
    activePreviewPlayer = null;
  };

  const playPreview = async (player) => {
    const url = player.dataset.previewUrl || "";
    if (!url) {
      player.classList.add("is-empty");
      player.title = t("no_audio_preview", "No audio files in this project");
      return;
    }
    if (activePreviewPlayer === player && previewAudio && !previewAudio.paused) {
      previewAudio.pause();
      resetPreviewPlayer(player);
      activePreviewPlayer = null;
      return;
    }
    resetPreviewPlayer();
    if (!previewAudio) {
      previewAudio = new Audio();
      previewAudio.preload = "metadata";
      previewAudio.addEventListener("ended", stopPreview);
      previewAudio.addEventListener("pause", () => {
        if (previewAudio?.ended) return;
        resetPreviewPlayer(activePreviewPlayer);
      });
      previewAudio.addEventListener("play", () => {
        activePreviewPlayer?.classList.remove("is-loading");
        activePreviewPlayer?.classList.add("is-playing");
        activePreviewPlayer?.setAttribute("aria-pressed", "true");
      });
    } else {
      previewAudio.pause();
    }
    activePreviewPlayer = player;
    player.classList.add("is-loading");
    player.setAttribute("aria-pressed", "false");
    player.setAttribute("aria-label", `${t("pause", "Pause")}: ${previewTitle(player)}`);
    if (previewAudio.src !== new URL(url, window.location.href).href) previewAudio.src = url;
    try {
      await previewAudio.play();
    } catch (error) {
      console.warn("Music project preview failed", error);
      resetPreviewPlayer(player);
      activePreviewPlayer = null;
    }
  };

  const preparePreviewPlayer = (player) => {
    if (!player.dataset.previewUrl) {
      player.classList.add("is-empty");
      player.title = t("no_audio_preview", "No audio files in this project");
    }
    player.setAttribute("aria-pressed", "false");
    player.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      event.stopPropagation();
      playPreview(player);
    });
  };

  root.querySelectorAll("[data-project-preview-player]").forEach(preparePreviewPlayer);
  root.addEventListener("click", (event) => {
    const player = event.target.closest("[data-project-preview-player]");
    if (!player || !root.contains(player)) return;
    event.preventDefault();
    event.stopPropagation();
    playPreview(player);
  });

  window.addEventListener("beforeunload", stopPreview);
  modalCancel.forEach((button) => button.addEventListener("click", closeModal));
  modalConfirm?.addEventListener("click", async () => {
    if (!pendingDelete?.length || !modalConfirm) return;
    const items = pendingDelete;
    modalConfirm.disabled = true;
    modalConfirm.textContent = t("deleting", "Deleting...");
    try {
      const data = items.length === 1
        ? await requestJson(`${apiUrl}${items[0].id}/delete/`, {method: "POST", body: "{}"})
        : await requestJson(`${apiUrl}delete/`, {method: "POST", body: JSON.stringify({ids: items.map((item) => item.id)})});
      const deletedIds = data.deleted_ids || items.map((item) => item.id);
      modal.hidden = true;
      document.body.classList.remove("project-delete-open");
      pendingDelete = null;
      removeDeletedCards(deletedIds);
    } finally {
      modalConfirm.disabled = false;
      modalConfirm.textContent = t("delete", "Delete");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && modal && !modal.hidden) closeModal();
  });

  updateBulkBar();
  updateEmptyState();
  setupSortDropdown();
  setupMobileProjectFilters();
})();
