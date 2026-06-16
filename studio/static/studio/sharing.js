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
  let revokeCandidate = "";

  const appMessages = (() => {
    try {
      return JSON.parse(document.getElementById("app-messages")?.textContent || "{}");
    } catch {
      return {};
    }
  })();

  const messages = {
    copied: "Invite link copied",
    roleUpdated: "Role updated",
    invitePending: "Invite pending",
    accepted: "Accepted",
    revoked: "Revoked",
    invite: "Invite",
    canEdit: "Can edit",
    viewOnly: "View only",
    empty: "No people invited yet. Send an invite to give a teammate view or edit access.",
    resending: "Resending invite...",
    resent: "Invite resent",
    revokeReady: "Click Revoke again to remove access.",
    revokeProgress: "Revoking access...",
    revokedAccess: "Access revoked",
    sending: "Sending invite...",
    sent: "Invite sent",
    copy: "Copy",
    resend: "Resend",
    revoke: "Revoke",
    view: "View",
    edit: "Edit",
    daysLeft: "days left",
    expiresToday: "Expires today",
  };
  Object.entries({
    copied: appMessages.invite_link_copied,
    roleUpdated: appMessages.role_updated,
    invitePending: appMessages.invite_pending,
    accepted: appMessages.accepted,
    revoked: appMessages.revoked,
    canEdit: appMessages.can_edit,
    viewOnly: appMessages.view_only,
    empty: appMessages.no_invites_yet,
    resending: appMessages.resending_invite,
    resent: appMessages.invite_resent,
    revokeReady: appMessages.revoke_ready,
    revokeProgress: appMessages.revoking_access,
    revokedAccess: appMessages.access_revoked,
    sending: appMessages.sending_invite,
    sent: appMessages.invite_sent,
    copy: appMessages.copy,
    resend: appMessages.resend,
    revoke: appMessages.revoke,
    view: appMessages.view,
    edit: appMessages.edit,
  }).forEach(([key, value]) => {
    if (value) messages[key] = value;
  });

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
      setStatus(messages.copied);
    } catch {
      setStatus(value);
    }
  };

  const roleLabel = (role) => role === "editor" ? messages.canEdit : messages.viewOnly;
  const statusLabel = (value) => ({
    pending: messages.invitePending,
    accepted: messages.accepted,
    revoked: messages.revoked,
  }[value] || value || messages.invite);

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
      list.innerHTML = `<p class="workspace-share-empty">${escapeHtml(messages.empty)}</p>`;
      return;
    }

    list.innerHTML = shares.map((share) => {
      const meta = [statusLabel(share.status), roleLabel(share.role), share.expires_label || ""].filter(Boolean).join(" - ");
      return `
        <article class="is-${escapeHtml(share.status || "pending")}" data-share-id="${share.id}" data-share-email="${escapeHtml(share.email)}" data-share-role-value="${escapeHtml(share.role)}">
          <div class="workspace-share-person">
            <strong>${escapeHtml(share.email)}</strong>
            <span>${escapeHtml(meta)}</span>
          </div>
          <div class="workspace-share-role-toggle" data-share-role>
            <button type="button" data-share-role-option="viewer" class="${share.role === "viewer" ? "is-active" : ""}" aria-pressed="${share.role === "viewer" ? "true" : "false"}">${escapeHtml(messages.view)}</button>
            <button type="button" data-share-role-option="editor" class="${share.role === "editor" ? "is-active" : ""}" aria-pressed="${share.role === "editor" ? "true" : "false"}">${escapeHtml(messages.edit)}</button>
          </div>
          <button type="button" data-share-copy="${escapeHtml(share.invite_url)}">${escapeHtml(messages.copy)}</button>
          <button type="button" data-share-resend>${escapeHtml(messages.resend)}</button>
          <button class="is-danger" type="button" data-share-revoke>${escapeHtml(messages.revoke)}</button>
        </article>
      `;
    }).join("");

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
          setStatus(messages.roleUpdated);
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
        setStatus(messages.resending);
        try {
          await postInvite(row.dataset.shareEmail || "", row.dataset.shareRoleValue || "viewer");
          setStatus(messages.resent);
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
        const shareId = row.dataset.shareId || "";
        if (revokeCandidate !== shareId) {
          revokeCandidate = shareId;
          list.querySelectorAll("[data-share-revoke]").forEach((entry) => entry.classList.remove("is-confirming"));
          button.classList.add("is-confirming");
          setStatus(messages.revokeReady);
          window.setTimeout(() => {
            if (revokeCandidate === shareId) {
              revokeCandidate = "";
              button.classList.remove("is-confirming");
            }
          }, 4500);
          return;
        }
        button.disabled = true;
        row.classList.add("is-revoking");
        setStatus(messages.revokeProgress);
        try {
          await requestJson(`${apiUrl}${row.dataset.shareId}/revoke/`, {method: "POST", body: "{}"});
          revokeCandidate = "";
          setStatus(messages.revokedAccess);
          loadShares();
        } catch (error) {
          setStatus(error.message, true);
        } finally {
          button.disabled = false;
          row.classList.remove("is-revoking");
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

  modal.querySelectorAll("[data-role-picker]").forEach((picker) => {
    picker.querySelectorAll("[data-role-option]").forEach((button) => {
      button.addEventListener("click", () => setRolePickerValue(picker, button.dataset.roleOption || "viewer"));
    });
  });

  const openModal = () => {
    modal.hidden = false;
    document.body.classList.add("workspace-share-open");
    revokeCandidate = "";
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
    setStatus(messages.sending);
    try {
      const payload = await postInvite(form.email.value, form.querySelector("input[name='role']")?.value || "viewer");
      form.reset();
      setRolePickerValue(form.querySelector("[data-role-picker]"), "viewer");
      setStatus(messages.sent);
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
