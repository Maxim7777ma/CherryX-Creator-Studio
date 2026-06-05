(() => {
  const modal = document.querySelector("[data-share-modal]");
  const openButton = document.querySelector("[data-share-open]");
  if (!modal || !openButton) return;

  const apiUrl = "/api/shares/";
  const form = modal.querySelector("[data-share-form]");
  const list = modal.querySelector("[data-share-list]");
  const status = modal.querySelector("[data-share-status]");
  const latestCopy = modal.querySelector("[data-share-copy-latest]");
  const resourceTitle = modal.querySelector("[data-share-resource-title]");
  const resourceLabel = modal.querySelector("[data-share-resource-label]");
  const resourceThumb = modal.querySelector("[data-share-preview-thumb]");
  const resourceType = modal.dataset.resourceType || "";
  const resourceId = modal.dataset.resourceId || "";
  let latestInviteUrl = "";

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
    if (!value) return;
    try {
      await navigator.clipboard.writeText(value);
      setStatus("Invite link copied");
    } catch {
      setStatus(value);
    }
  };
  const roleLabel = (role) => role === "editor" ? "Can edit" : "View only";
  const statusLabel = (value) => ({
    pending: "Invite pending",
    accepted: "Accepted",
    revoked: "Revoked",
  }[value] || value || "Invite");
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
  const applyResource = (resource) => {
    if (!resource) return;
    if (resourceTitle) resourceTitle.textContent = resource.title || "Project invite";
    if (resourceLabel) resourceLabel.textContent = resource.label || "Private project link";
    if (!resourceThumb) return;
    resourceThumb.style.backgroundImage = resource.preview_url ? `url("${resource.preview_url}")` : "";
    resourceThumb.classList.toggle("has-image", Boolean(resource.preview_url));
  };
  const refreshLatestLink = (shares) => {
    const latest = shares[0];
    latestInviteUrl = latest?.invite_url || "";
    if (latestCopy) latestCopy.hidden = !latestInviteUrl;
  };

  modal.querySelectorAll("[data-role-picker]").forEach((picker) => {
    picker.querySelectorAll("[data-role-option]").forEach((button) => {
      button.addEventListener("click", () => setRolePickerValue(picker, button.dataset.roleOption || "viewer"));
    });
  });

  const postInvite = async (email, role) => requestJson(apiUrl, {
    method: "POST",
    body: JSON.stringify({
      resource_type: resourceType,
      resource_id: Number(resourceId),
      email,
      role,
    }),
  });

  const renderShares = (shares) => {
    if (!list) return;
    refreshLatestLink(shares);
    if (!shares.length) {
      list.innerHTML = `
        <p class="workspace-share-empty">
          No people invited yet. Send an invite to give a teammate view or edit access.
        </p>
      `;
      return;
    }
    list.innerHTML = shares.map((share) => `
      <article data-share-id="${share.id}" data-share-email="${escapeHtml(share.email)}" data-share-role-value="${escapeHtml(share.role)}">
        <div class="workspace-share-person">
          <strong>${escapeHtml(share.email)}</strong>
          <span>${escapeHtml(statusLabel(share.status))} · ${escapeHtml(roleLabel(share.role))} · ${escapeHtml(share.expires_label || "")}</span>
        </div>
        <div class="workspace-share-role-toggle" data-share-role>
          <button type="button" data-share-role-option="viewer" class="${share.role === "viewer" ? "is-active" : ""}" aria-pressed="${share.role === "viewer" ? "true" : "false"}">View</button>
          <button type="button" data-share-role-option="editor" class="${share.role === "editor" ? "is-active" : ""}" aria-pressed="${share.role === "editor" ? "true" : "false"}">Edit</button>
        </div>
        <button type="button" data-share-copy="${escapeHtml(share.invite_url)}">Copy</button>
        <button type="button" data-share-resend>Resend</button>
        <button class="is-danger" type="button" data-share-revoke>Revoke</button>
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
    list.querySelectorAll("[data-share-resend]").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-share-id]");
        if (!row) return;
        button.disabled = true;
        setStatus("Resending invite...");
        try {
          await postInvite(row.dataset.shareEmail || "", row.dataset.shareRoleValue || "viewer");
          setStatus("Invite resent");
          loadShares();
        } catch (error) {
          setStatus(error.message, true);
        } finally {
          button.disabled = false;
        }
      });
    });
    list.querySelectorAll("[data-share-revoke]").forEach((button) => {
      button.addEventListener("click", async () => {
        const row = button.closest("[data-share-id]");
        if (!row) return;
        const email = row.dataset.shareEmail || "this person";
        if (!window.confirm(`Revoke access for ${email}?`)) return;
        button.disabled = true;
        try {
          await requestJson(`${apiUrl}${row.dataset.shareId}/revoke/`, {method: "POST", body: "{}"});
          setStatus("Access revoked");
          loadShares();
        } catch (error) {
          setStatus(error.message, true);
        } finally {
          button.disabled = false;
        }
      });
    });
  };

  async function loadShares() {
    if (!resourceType || !resourceId) return;
    const data = await requestJson(`${apiUrl}?resource_type=${encodeURIComponent(resourceType)}&resource_id=${encodeURIComponent(resourceId)}`);
    applyResource(data.resource);
    renderShares(data.shares || []);
  }

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
  latestCopy?.addEventListener("click", () => copyText(latestInviteUrl));
  modal.querySelectorAll("[data-share-close]").forEach((button) => button.addEventListener("click", closeModal));
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    setStatus("Sending invite...");
    try {
      const payload = await postInvite(form.email.value, form.querySelector("input[name='role']")?.value || "viewer");
      form.reset();
      setRolePickerValue(form.querySelector("[data-role-picker]"), "viewer");
      setStatus("Invite sent");
      latestInviteUrl = payload.share?.invite_url || latestInviteUrl;
      await loadShares();
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });
})();
