(() => {
  const modal = document.querySelector("[data-share-modal]");
  const openButton = document.querySelector("[data-share-open]");
  if (!modal || !openButton) return;

  const apiUrl = "/api/shares/";
  const form = modal.querySelector("[data-share-form]");
  const list = modal.querySelector("[data-share-list]");
  const status = modal.querySelector("[data-share-status]");
  const resourceType = modal.dataset.resourceType || "";
  const resourceId = modal.dataset.resourceId || "";
  const csrfToken = () => {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };
  const escapeHtml = (value) => String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
  const requestJson = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body ? {"Content-Type": "application/json", "X-CSRFToken": csrfToken()} : {}),
        ...(options.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  };
  const setStatus = (message, failed = false) => {
    if (!status) return;
    status.textContent = message || "";
    status.classList.toggle("is-error", failed);
  };
  const copyText = async (value) => {
    try {
      await navigator.clipboard.writeText(value);
      setStatus("Invite link copied");
    } catch {
      setStatus(value);
    }
  };
  const roleLabel = (role) => role === "editor" ? "Edit access" : "View only";
  const setRolePickerValue = (picker, role) => {
    if (!picker) return;
    picker.querySelectorAll("[data-role-option]").forEach((button) => {
      const active = button.dataset.roleOption === role;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    const hidden = picker.closest("form")?.querySelector("input[name='role']");
    if (hidden) hidden.value = role;
  };
  modal.querySelectorAll("[data-role-picker]").forEach((picker) => {
    picker.querySelectorAll("[data-role-option]").forEach((button) => {
      button.addEventListener("click", () => setRolePickerValue(picker, button.dataset.roleOption || "viewer"));
    });
  });
  const renderShares = (shares) => {
    if (!list) return;
    if (!shares.length) {
      list.innerHTML = `<p>No people invited yet</p>`;
      return;
    }
    list.innerHTML = shares.map((share) => `
      <article data-share-id="${share.id}">
        <div>
          <strong>${escapeHtml(share.email)}</strong>
          <span>${escapeHtml(share.status)} &middot; ${escapeHtml(roleLabel(share.role))}</span>
        </div>
        <div class="workspace-share-role-toggle" data-share-role>
          <button type="button" data-share-role-option="viewer" class="${share.role === "viewer" ? "is-active" : ""}" aria-pressed="${share.role === "viewer" ? "true" : "false"}">View</button>
          <button type="button" data-share-role-option="editor" class="${share.role === "editor" ? "is-active" : ""}" aria-pressed="${share.role === "editor" ? "true" : "false"}">Edit</button>
        </div>
        <button type="button" data-share-copy="${escapeHtml(share.invite_url)}">Copy</button>
        <button type="button" data-share-revoke>Revoke</button>
      </article>
    `).join("");
    list.querySelectorAll("[data-share-role-option]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (button.classList.contains("is-active")) return;
        const row = button.closest("[data-share-id]");
        const role = button.dataset.shareRoleOption || "viewer";
        const previousRole = row.querySelector("[data-share-role-option].is-active")?.dataset.shareRoleOption || "";
        try {
          row.querySelectorAll("[data-share-role-option]").forEach((entry) => {
            const active = entry === button;
            entry.classList.toggle("is-active", active);
            entry.setAttribute("aria-pressed", active ? "true" : "false");
          });
          await requestJson(`${apiUrl}${row.dataset.shareId}/role/`, {method: "POST", body: JSON.stringify({role})});
          setStatus("Role updated");
          loadShares();
        } catch (error) {
          row.querySelectorAll("[data-share-role-option]").forEach((entry) => {
            const active = entry.dataset.shareRoleOption === previousRole;
            entry.classList.toggle("is-active", active);
            entry.setAttribute("aria-pressed", active ? "true" : "false");
          });
          setStatus(error.message, true);
        }
      });
    });
    list.querySelectorAll("[data-share-copy]").forEach((button) => {
      button.addEventListener("click", () => copyText(button.dataset.shareCopy || ""));
    });
    list.querySelectorAll("[data-share-revoke]").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-share-id]");
        await requestJson(`${apiUrl}${row.dataset.shareId}/revoke/`, {method: "POST", body: "{}"});
        setStatus("Access revoked");
        loadShares();
      });
    });
  };
  const loadShares = async () => {
    if (!resourceType || !resourceId) return;
    const data = await requestJson(`${apiUrl}?resource_type=${encodeURIComponent(resourceType)}&resource_id=${encodeURIComponent(resourceId)}`);
    renderShares(data.shares || []);
  };
  const openModal = () => {
    modal.hidden = false;
    document.body.classList.add("workspace-share-open");
    setStatus("");
    loadShares().catch((error) => setStatus(error.message, true));
    modal.querySelector("input[name='email']")?.focus();
  };
  const closeModal = () => {
    modal.hidden = true;
    document.body.classList.remove("workspace-share-open");
  };

  openButton.addEventListener("click", openModal);
  modal.querySelectorAll("[data-share-close]").forEach((button) => button.addEventListener("click", closeModal));
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = {
      resource_type: resourceType,
      resource_id: Number(resourceId),
      email: form.email.value,
      role: form.querySelector("input[name='role']")?.value || "viewer",
    };
    form.querySelector("button[type='submit']").disabled = true;
    setStatus("Sending invite...");
    try {
      await requestJson(apiUrl, {method: "POST", body: JSON.stringify(payload)});
      form.reset();
      setRolePickerValue(form.querySelector("[data-role-picker]"), "viewer");
      setStatus("Invite sent");
      loadShares();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      form.querySelector("button[type='submit']").disabled = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });
})();
