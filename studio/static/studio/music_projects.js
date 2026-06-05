(() => {
  document.querySelectorAll(".language-switcher").forEach((switcher) => {
    const button = switcher.querySelector(".language-current");
    if (!button) return;
    switcher.addEventListener("click", (event) => event.stopPropagation());
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = switcher.classList.toggle("is-open");
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
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
  const modal = document.querySelector("[data-delete-modal]");
  const modalTitle = modal?.querySelector("[data-modal-title]");
  const modalCopy = modal?.querySelector("[data-modal-copy]");
  const modalList = modal?.querySelector("[data-modal-list]");
  const modalConfirm = modal?.querySelector("[data-modal-confirm]");
  const modalCancel = modal?.querySelectorAll("[data-modal-cancel]") || [];
  let pendingDelete = null;

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
    if (totalCount) totalCount.textContent = String(count);
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
})();
