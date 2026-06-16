const jobs = new Map();
const polling = new Set();
const ACTIVE_TAB_KEY = "studio.activeTab";
const RESUME_STEP_KEY = "studio.resumeStep";
const JOB_FILTER_KEY = "studio.jobFilter";
const JOB_FORM_DRAFT_PREFIX = "studio.jobFormDraft.";
const DESIGN_MODE_KEY = "studio.designerMode";
const DESIGN_STORAGE_KEY = "studio.designBoard";
const DESIGN_STORAGE_KEY_V2 = "studio.designBoard.v2";
const DESIGN_HISTORY_LIMIT = 80;
const DESIGN_WIDTH = 9000;
const DESIGN_HEIGHT = 6400;
const DESIGN_GRID = 8;
const DESIGN_COLOR_PALETTE = ["#0f172a", "#2563eb", "#0891b2", "#16a34a", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#ffffff", "#e2e8f0", "#94a3b8", "transparent"];
const DESIGN_FRAME_PRESETS = {
  iphone: { label: "iPhone", w: 393, h: 852 },
  iphone_max: { label: "iPhone Pro Max", w: 430, h: 932 },
  android: { label: "Android", w: 360, h: 800 },
  pixel: { label: "Pixel", w: 412, h: 915 },
  ipad: { label: "iPad", w: 820, h: 1180 },
  tablet: { label: "Tablet", w: 768, h: 1024 },
  desktop: { label: "Desktop", w: 1440, h: 1024 },
  desktop_hd: { label: "Desktop HD", w: 1920, h: 1080 },
  laptop: { label: "Laptop", w: 1366, h: 768 },
  macbook: { label: "MacBook", w: 1512, h: 982 },
  presentation: { label: "Slides", w: 1920, h: 1080 },
  watch: { label: "Watch", w: 184, h: 224 },
  a4: { label: "A4", w: 794, h: 1123 },
  letter: { label: "Letter", w: 816, h: 1056 },
  instagram: { label: "Instagram", w: 1080, h: 1080 },
  story: { label: "Story", w: 1080, h: 1920 },
  youtube: { label: "YouTube", w: 1280, h: 720 },
  cover: { label: "Cover", w: 1500, h: 500 },
};
const i18n = loadAppMessages();

renderInitialJobs();
setupFileFields();
setupFormatPickers();
setupCustomSelects();
setupResumeWizards();
setupLanguageSwitchers();
setupSubscriptionDrawer();
setupAccountPanel();
setupDesignerModes();
setupJobFormDrafts();
setupSubtitleStylePickers();
setupJobFilters();
setupOriginalityChecker();
setupMobileWorkspace();
restoreActiveTab();

document.querySelectorAll(".tab[data-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    activateTab(button.dataset.tab);
  });
});

document.querySelectorAll(".job-form").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type='submit']");
    const originalText = button ? button.textContent : "";
    if (button) {
      button.disabled = true;
      button.textContent = i18n.starting || "Starting";
    }

    try {
      const response = await fetch(form.dataset.endpoint, {
        method: "POST",
        body: new FormData(form),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || i18n.task_failed || "Task did not start");
      }
      renderJob(payload.job);
      pollJob(payload.job.id);
    } catch (error) {
      renderJob({
        id: `error-${Date.now()}`,
        title: i18n.launch_error || "Launch error",
        status: "failed",
        progress: 100,
        message: i18n.error || "Error",
        error: error.message || String(error),
        outputs: [],
      });
    } finally {
      if (button) {
        button.disabled = false;
        button.textContent = originalText;
      }
    }
  });
});

function setupLanguageSwitchers() {
  document.querySelectorAll(".language-switcher").forEach((switcher) => {
    if (switcher.dataset.languageSwitcherBound === "1") return;
    const button = switcher.querySelector(".language-current");
    if (!button) return;
    switcher.dataset.languageSwitcherBound = "1";
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
    switcher.addEventListener("click", (event) => {
      event.stopPropagation();
    });
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
}

function setupSubscriptionDrawer() {
  const drawer = document.querySelector("[data-subscription-drawer]");
  const openButton = document.querySelector("[data-subscription-open]");
  if (!drawer || !openButton) return;
  const closeButtons = drawer.querySelectorAll("[data-subscription-close]");
  const setOpen = (open) => {
    drawer.hidden = !open;
    document.body.classList.toggle("subscription-drawer-open", open);
    openButton.setAttribute("aria-expanded", open ? "true" : "false");
  };
  openButton.addEventListener("click", () => setOpen(drawer.hidden));
  closeButtons.forEach((button) => button.addEventListener("click", () => setOpen(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !drawer.hidden) setOpen(false);
  });
}

function setupAccountPanel() {
  const panel = document.querySelector("[data-account-panel]");
  const button = document.querySelector("[data-account-panel-toggle]");
  if (!panel || !button) return;
  const setOpen = (open) => {
    panel.classList.toggle("is-open", open);
    document.body.classList.toggle("is-mobile-account-open", open);
    button.setAttribute("aria-expanded", open ? "true" : "false");
  };
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(!panel.classList.contains("is-open"));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setOpen(false);
  });
}

function setupMobileWorkspace() {
  const media = window.matchMedia("(max-width: 760px)");
  const jobsPanel = document.querySelector(".jobs-panel");
  const jobsToggle = document.querySelector("[data-mobile-jobs-toggle]");
  const accountPanel = document.querySelector("[data-account-panel]");
  const accountToggle = document.querySelector("[data-account-panel-toggle]");
  const settingsShortcut = document.querySelector(".account-settings-shortcut, .account-settings-link");
  const accountLanguageSwitcher = document.querySelector(".account-panel-content .language-switcher");
  const accountLanguageButton = accountLanguageSwitcher?.querySelector(".language-current");
  let mobileLanguageModal = null;

  const closeMobileLanguageModal = () => {
    if (!mobileLanguageModal) return;
    const modalToRemove = mobileLanguageModal;
    mobileLanguageModal.classList.remove("is-open");
    document.body.classList.remove("is-mobile-language-open");
    accountLanguageButton?.setAttribute("aria-expanded", "false");
    mobileLanguageModal = null;
    window.setTimeout(() => {
      modalToRemove.remove();
    }, 180);
  };

  const openMobileLanguageModal = () => {
    if (!accountLanguageSwitcher || !accountLanguageButton || !media.matches) return;
    closeMobileLanguageModal();
    const modal = document.createElement("div");
    modal.className = "mobile-language-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const backdrop = document.createElement("button");
    backdrop.className = "mobile-language-backdrop";
    backdrop.type = "button";
    backdrop.setAttribute("aria-label", "Close language selector");
    backdrop.addEventListener("click", closeMobileLanguageModal);

    const form = document.createElement("form");
    form.className = "mobile-language-panel";
    form.method = accountLanguageSwitcher.method || "post";
    form.action = accountLanguageSwitcher.action;

    const handle = document.createElement("span");
    handle.className = "mobile-language-handle";
    handle.setAttribute("aria-hidden", "true");
    form.appendChild(handle);

    accountLanguageSwitcher.querySelectorAll('input[type="hidden"]').forEach((input) => {
      form.appendChild(input.cloneNode(true));
    });
    accountLanguageSwitcher.querySelectorAll(".language-menu button").forEach((button) => {
      const clone = button.cloneNode(true);
      clone.classList.toggle("is-active", button.classList.contains("is-active"));
      form.appendChild(clone);
    });

    modal.append(backdrop, form);
    document.body.appendChild(modal);
    mobileLanguageModal = modal;
    document.body.classList.add("is-mobile-language-open");
    accountLanguageButton.setAttribute("aria-expanded", "true");
    window.requestAnimationFrame(() => modal.classList.add("is-open"));
  };

  const setMobile = () => {
    document.body.classList.toggle("is-mobile-workspace", media.matches);
    if (!media.matches) {
      setJobsOpen(false);
      document.body.classList.remove("is-mobile-account-open");
      closeMobileLanguageModal();
    }
  };

  const setJobsOpen = (open) => {
    document.body.classList.toggle("is-mobile-jobs-open", open);
    if (jobsToggle) jobsToggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      accountPanel?.classList.remove("is-open");
      document.body.classList.remove("is-mobile-account-open");
      accountToggle?.setAttribute("aria-expanded", "false");
    }
  };

  jobsToggle?.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    if (!media.matches) return;
    setJobsOpen(!document.body.classList.contains("is-mobile-jobs-open"));
  });

  settingsShortcut?.addEventListener("click", (event) => {
    if (!media.matches || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault();
    settingsShortcut.classList.add("is-spinning");
    window.setTimeout(() => {
      window.location.href = settingsShortcut.href;
    }, 260);
  });

  accountLanguageButton?.addEventListener("click", (event) => {
    if (!media.matches) return;
    event.preventDefault();
    event.stopPropagation();
    event.stopImmediatePropagation();
    openMobileLanguageModal();
  }, { capture: true });

  document.addEventListener("click", (event) => {
    if (!media.matches || !(event.target instanceof Element)) return;
    if (document.body.classList.contains("is-mobile-jobs-open") && !event.target.closest(".jobs-panel") && !event.target.closest("[data-mobile-jobs-toggle]")) {
      setJobsOpen(false);
    }
    if (document.body.classList.contains("is-mobile-account-open") && !event.target.closest("[data-account-panel]") && !event.target.closest(".mobile-language-modal")) {
      accountPanel?.classList.remove("is-open");
      document.body.classList.remove("is-mobile-account-open");
      accountToggle?.setAttribute("aria-expanded", "false");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!media.matches || event.key !== "Escape") return;
    setJobsOpen(false);
    accountPanel?.classList.remove("is-open");
    document.body.classList.remove("is-mobile-account-open");
    closeMobileLanguageModal();
    accountToggle?.setAttribute("aria-expanded", "false");
  });

  if (typeof media.addEventListener === "function") {
    media.addEventListener("change", setMobile);
  } else {
    media.addListener(setMobile);
  }
  setMobile();
}

function setupJobFormDrafts() {
  document.querySelectorAll(".job-form").forEach((form, index) => {
    const key = `${JOB_FORM_DRAFT_PREFIX}${form.id || form.dataset.endpoint || index}`;
    let draft = {};
    try {
      draft = JSON.parse(localStorage.getItem(key) || "{}");
    } catch {
      draft = {};
    }

    const controls = [...form.querySelectorAll("input, select, textarea")].filter((control) => {
      return control.name && control.type !== "file" && (control.type !== "hidden" || control.matches("[data-subtitle-style-input]")) && control.name !== "csrfmiddlewaretoken";
    });

    controls.forEach((control) => {
      if (!(control.name in draft)) return;
      if (control.type === "checkbox") {
        control.checked = Boolean(draft[control.name]);
        return;
      }
      if (control.type === "radio") {
        control.checked = String(control.value) === String(draft[control.name]);
        return;
      }
      control.value = draft[control.name];
    });

    const save = () => {
      const next = {};
      controls.forEach((control) => {
        if (control.type === "checkbox") {
          next[control.name] = control.checked;
          return;
        }
        if (control.type === "radio") {
          if (control.checked) next[control.name] = control.value;
          return;
        }
        next[control.name] = control.value;
      });
      localStorage.setItem(key, JSON.stringify(next));
    };

    controls.forEach((control) => {
      control.addEventListener("input", save);
      control.addEventListener("change", save);
    });
  });
}

function setupJobFilters() {
  const wrapper = document.querySelector("[data-job-filters]");
  if (!wrapper) return;
  const saved = localStorage.getItem(JOB_FILTER_KEY) || "all";
  wrapper.querySelectorAll("[data-job-filter]").forEach((button) => {
    const active = button.dataset.jobFilter === saved;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", active ? "true" : "false");
    button.addEventListener("click", () => {
      localStorage.setItem(JOB_FILTER_KEY, button.dataset.jobFilter || "all");
      wrapper.querySelectorAll("[data-job-filter]").forEach((item) => {
        const isActive = item === button;
        item.classList.toggle("is-active", isActive);
        item.setAttribute("aria-pressed", isActive ? "true" : "false");
      });
      updateJobsPanel();
    });
  });
}

function setupFormatPickers() {
  document.querySelectorAll("[data-format-picker]").forEach((picker) => {
    const input = picker.querySelector("[data-format-input]");
    const current = picker.querySelector("[data-format-current]");
    const menu = picker.querySelector("[data-format-menu]");
    const buttons = [...picker.querySelectorAll("[data-format-value]")];
    const groups = [...picker.querySelectorAll("[data-format-group]")];
    if (!input || !current || !menu || !buttons.length) return;

    document.body.appendChild(menu);

    const selectFormat = (button) => {
      if (!button || button.hidden) return;
      input.value = button.dataset.formatValue || "";
      buttons.forEach((item) => item.classList.toggle("is-selected", item === button));
      const label = button.textContent.trim();
      const group = button.dataset.formatKind === "video" ? i18n.video || "Video" : i18n.images || "Images";
      current.innerHTML = `<b>${escapeHtml(label)}</b><small>${escapeHtml(group)}</small>`;
      picker.classList.remove("is-open");
      menu.classList.remove("is-open");
      current.setAttribute("aria-expanded", "false");
    };

    const positionMenu = () => {
      const rect = current.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 260), Math.max(260, window.innerWidth - 24));
      const left = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - width - 12));
      const spaceBelow = window.innerHeight - rect.bottom - 12;
      const spaceAbove = rect.top - 12;
      const desiredHeight = Math.min(360, Math.max(menu.scrollHeight, 220));
      const availableHeight = Math.max(180, Math.min(360, Math.max(spaceBelow, spaceAbove) - 8));
      const openAbove = spaceBelow < Math.min(desiredHeight, 280) && spaceAbove > spaceBelow;
      const top = openAbove
        ? Math.max(12, rect.top - Math.min(desiredHeight, availableHeight) - 8)
        : Math.min(rect.bottom + 8, window.innerHeight - Math.min(desiredHeight, availableHeight) - 12);
      menu.style.width = `${width}px`;
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      menu.style.maxHeight = `${availableHeight}px`;
    };

    picker.setFormatKind = (kind) => {
      const normalized = kind === "video" ? "video" : "image";
      groups.forEach((group) => {
        group.hidden = group.dataset.formatGroup !== normalized;
      });
      const active = buttons.find((button) => button.dataset.formatKind === normalized && button.dataset.formatValue === input.value);
      selectFormat(active || buttons.find((button) => button.dataset.formatKind === normalized));
    };

    current.setAttribute("aria-expanded", "false");
    current.addEventListener("click", () => {
      const open = picker.classList.toggle("is-open");
      menu.classList.toggle("is-open", open);
      current.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) positionMenu();
    });
    buttons.forEach((button) => button.addEventListener("click", () => selectFormat(button)));
    document.addEventListener("click", (event) => {
      if (!picker.contains(event.target) && !menu.contains(event.target)) {
        picker.classList.remove("is-open");
        menu.classList.remove("is-open");
        current.setAttribute("aria-expanded", "false");
      }
    });
    window.addEventListener("resize", () => {
      if (picker.classList.contains("is-open")) positionMenu();
    });
    window.addEventListener("scroll", () => {
      if (picker.classList.contains("is-open")) positionMenu();
    }, true);
  });
}

function setupCustomSelects() {
  document.querySelectorAll("[data-custom-select]").forEach((picker) => {
    const input = picker.querySelector("[data-custom-select-input]");
    const current = picker.querySelector("[data-custom-select-current]");
    const menu = picker.querySelector("[data-custom-select-menu]");
    const buttons = [...picker.querySelectorAll("[data-custom-select-value]")];
    if (!input || !current || !menu || !buttons.length) return;

    document.body.appendChild(menu);

    const positionMenu = () => {
      const rect = current.getBoundingClientRect();
      const width = Math.min(Math.max(rect.width, 260), Math.max(260, window.innerWidth - 24));
      const left = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - width - 12));
      const menuHeight = Math.min(300, Math.max(menu.scrollHeight, 120));
      const below = window.innerHeight - rect.bottom - 12;
      const above = rect.top - 12;
      const openAbove = below < menuHeight && above > below;
      const top = openAbove ? Math.max(12, rect.top - menuHeight - 8) : Math.min(rect.bottom + 8, window.innerHeight - menuHeight - 12);
      menu.style.width = `${width}px`;
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      menu.style.maxHeight = `${Math.max(140, Math.min(300, Math.max(below, above) - 8))}px`;
    };

    const close = () => {
      picker.classList.remove("is-open");
      menu.classList.remove("is-open");
      current.setAttribute("aria-expanded", "false");
    };

    const choose = (button) => {
      input.value = button.dataset.customSelectValue || "";
      buttons.forEach((item) => item.classList.toggle("is-selected", item === button));
      current.innerHTML = `<b>${escapeHtml((button.querySelector("b") || button).textContent.trim())}</b><small>YouTube</small>`;
      close();
    };

    current.addEventListener("click", () => {
      const open = !picker.classList.contains("is-open");
      picker.classList.toggle("is-open", open);
      menu.classList.toggle("is-open", open);
      current.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) positionMenu();
    });
    buttons.forEach((button) => button.addEventListener("click", () => choose(button)));
    document.addEventListener("click", (event) => {
      if (!picker.contains(event.target) && !menu.contains(event.target)) close();
    });
    window.addEventListener("resize", () => {
      if (picker.classList.contains("is-open")) positionMenu();
    });
    window.addEventListener("scroll", () => {
      if (picker.classList.contains("is-open")) positionMenu();
    }, true);
  });
}

function setupSubtitleStylePickers() {
  document.querySelectorAll("[data-subtitle-style-picker]").forEach((picker) => {
    const input = picker.querySelector("[data-subtitle-style-input]");
    const current = picker.querySelector("[data-subtitle-style-current]");
    const menu = picker.querySelector("[data-subtitle-style-menu]");
    const cards = [...picker.querySelectorAll("[data-subtitle-style-value]")];
    if (!input || !current || !menu || !cards.length) return;

    const close = () => {
      picker.classList.remove("is-open");
      current.setAttribute("aria-expanded", "false");
    };

    const choose = (card, animate = true) => {
      const value = card.dataset.subtitleStyleValue || "pop";
      const swatch = card.querySelector(".subtitle-style-swatch")?.cloneNode(true);
      const title = card.querySelector(".subtitle-style-copy b")?.textContent?.trim() || value;
      const hint = card.querySelector(".subtitle-style-copy small")?.textContent?.trim() || "";
      input.value = value;
      cards.forEach((item) => item.classList.toggle("is-selected", item === card));
      current.replaceChildren(
        swatch || Object.assign(document.createElement("span"), { className: `subtitle-style-swatch is-${value}`, textContent: title }),
        Object.assign(document.createElement("span"), {
          innerHTML: `<b>${escapeHtml(title)}</b><small>${escapeHtml(hint)}</small>`,
        }),
      );
      if (animate) {
        current.classList.remove("is-pulse");
        void current.offsetWidth;
        current.classList.add("is-pulse");
      }
      close();
      input.dispatchEvent(new Event("change", { bubbles: true }));
    };

    const selected = cards.find((card) => card.dataset.subtitleStyleValue === input.value) || cards[0];
    choose(selected, false);

    current.addEventListener("click", () => {
      const open = !picker.classList.contains("is-open");
      picker.classList.toggle("is-open", open);
      current.setAttribute("aria-expanded", open ? "true" : "false");
    });
    cards.forEach((card) => {
      card.querySelector("[data-subtitle-style-choice]")?.addEventListener("click", () => choose(card));
      card.querySelector("[data-subtitle-style-details]")?.addEventListener("click", () => choose(card, false));
    });
    document.addEventListener("click", (event) => {
      if (!picker.contains(event.target)) close();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") close();
    });
  });
}

function loadAppMessages() {
  const script = document.getElementById("app-messages");
  if (!script) return {};
  try {
    return JSON.parse(script.textContent || "{}");
  } catch {
    return {};
  }
}

function setupFileFields() {
  document.querySelectorAll(".file-field input[type='file']").forEach((input) => {
    const field = input.closest(".file-field");
    const dropzone = field.querySelector(".file-dropzone");
    input.addEventListener("change", () => updatePreview(input));

    ["dragenter", "dragover"].forEach((eventName) => {
      field.addEventListener(eventName, (event) => {
        event.preventDefault();
        field.classList.add("is-dragging");
      });
    });
    ["dragleave", "drop"].forEach((eventName) => {
      field.addEventListener(eventName, (event) => {
        event.preventDefault();
        field.classList.remove("is-dragging");
      });
    });
    field.addEventListener("drop", (event) => {
      const files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      input.files = files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    if (dropzone) {
      dropzone.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          input.click();
        }
      });
      dropzone.tabIndex = 0;
    }
  });
}

function setupOriginalityChecker() {
  document.querySelectorAll("[data-originality-form]").forEach((form) => {
    const panel = form.closest(".tool-panel");
    const result = panel ? panel.querySelector("[data-originality-result]") : null;
    const button = form.querySelector("button[type='submit']");
    const textInput = form.querySelector("[data-originality-text]");
    const fileInput = form.querySelector("input[type='file']");
    if (!result) return;

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const hasText = Boolean(textInput && textInput.value.trim());
      const hasFile = Boolean(fileInput && fileInput.files && fileInput.files.length);
      if (!hasText && !hasFile) {
        renderOriginalityError(result, i18n.originality_empty || "Paste text or upload a document.");
        return;
      }
      const originalText = button ? button.textContent : "";
      if (button) {
        button.disabled = true;
        button.textContent = i18n.originality_checking || "Checking";
      }
      result.hidden = false;
      result.classList.remove("is-error");
      result.innerHTML = `<div class="originality-loading"><span></span><b>${escapeHtml(i18n.originality_checking || "Checking")}</b></div>`;
      try {
        const response = await fetch(form.dataset.endpoint, {
          method: "POST",
          body: new FormData(form),
          headers: {
            "X-CSRFToken": csrfToken(),
            "X-Requested-With": "XMLHttpRequest",
          },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || i18n.task_failed || "Task failed");
        }
        if (payload.job) renderJob(payload.job);
        renderOriginalityAnalysis(result, payload.analysis || {}, payload.job || null);
      } catch (error) {
        renderOriginalityError(result, error.message || String(error));
      } finally {
        if (button) {
          button.disabled = false;
          button.textContent = originalText;
        }
      }
    });
  });
}

function renderOriginalityAnalysis(container, analysis, job = null) {
  const overall = analysis.overall || {};
  const source = analysis.source || {};
  const metrics = Array.isArray(analysis.metrics) ? analysis.metrics : [];
  const highlights = Array.isArray(analysis.highlights) ? analysis.highlights : [];
  const segments = Array.isArray(analysis.segments) ? analysis.segments : [];
  const check = analysis.check && typeof analysis.check === "object" ? analysis.check : {};
  const score = Math.max(0, Math.min(100, Number(overall.score || 0)));
  const scoreDeg = Math.round(score * 36) / 10;
  const markedSegments = segments.filter((segment) => segment && segment.severity && segment.severity !== "none" && Array.isArray(segment.issues) && segment.issues.length);
  const mapMarkup = markedSegments.length
    ? markedSegments.map(renderOriginalitySegment).join(" ")
    : `<div class="originality-map-empty"><strong>${escapeHtml(i18n.originality_no_issues || "No issues found.")}</strong><span>${escapeHtml(i18n.originality_open_report || i18n.originality_full_report || "Open report for details.")}</span></div>`;
  const meta = [
    source.name,
    source.kind_label,
    source.words !== undefined ? `${source.words} ${i18n.originality_words || "words"}` : "",
    source.sentences !== undefined ? `${source.sentences} ${i18n.originality_sentences || "sentences"}` : "",
  ].filter(Boolean);
  const jobLink = job && job.detail_url ? `<a class="originality-report-link" href="${escapeHtml(job.detail_url)}" data-icon="external-link">${escapeHtml(i18n.originality_open_report || i18n.open || "Open report")}</a>` : "";
  container.hidden = false;
  container.classList.remove("is-error");
  container.innerHTML = `
    <div class="originality-overview">
      <div class="originality-score is-${toneClass(overall.tone)}" style="--score-deg:${scoreDeg}deg">
        <strong>${score}</strong>
        <span>/100</span>
      </div>
      <div>
        <small>${escapeHtml(overall.label || i18n.originality_score || "Integrity score")}</small>
        <h3>${escapeHtml(meta.join(" · "))}</h3>
        ${jobLink}
      </div>
    </div>
    <div class="originality-metrics" aria-label="${escapeHtml(i18n.originality_metrics || "Metrics")}">
      ${metrics.map(renderOriginalityMetric).join("")}
    </div>
    <div class="originality-check-meta">
      <span>${escapeHtml(check.mode_label || "Local")}</span>
      <span>${escapeHtml(String(check.price_cherryx || 5))} CherryX</span>
      <span>${escapeHtml(String(check.web_queries_limit || 0))} web probes</span>
      <span>${escapeHtml(check.web_status || "local")}</span>
    </div>
    <div class="originality-analysis-grid">
      <section class="originality-highlight-list">
        <h3>${escapeHtml(i18n.originality_metrics || "Metrics")}</h3>
        ${highlights.map(renderOriginalityHighlight).join("")}
      </section>
      <section class="originality-text-map">
        <h3>${escapeHtml(i18n.originality_highlights || "Marked fragments")}</h3>
        <div>${mapMarkup}</div>
      </section>
    </div>
  `;
}

function renderOriginalityMetric(metric) {
  const score = Number(metric.score || 0);
  return `
    <article class="originality-metric is-${toneClass(metric.tone)}">
      <div>
        <strong>${escapeHtml(metric.label || "")}</strong>
        <small>${escapeHtml(metric.detail || "")}</small>
      </div>
      <b>${score}</b>
      <i aria-hidden="true"><span style="width:${Math.max(0, Math.min(100, score))}%"></span></i>
    </article>
  `;
}

function renderOriginalityHighlight(item) {
  return `
    <article class="originality-highlight is-${toneClass(item.tone)}">
      <span>${escapeHtml(item.label || "")}</span>
      <b>${Number(item.count || 0)}</b>
    </article>
  `;
}

function renderOriginalitySegment(segment) {
  const severity = toneClass(segment.severity);
  const text = escapeHtml(segment.text || "");
  const issues = Array.isArray(segment.issues) ? segment.issues.filter(Boolean).join(" · ") : "";
  if (severity === "none" || !issues) {
    return `<span>${text}</span>`;
  }
  return `<mark class="is-${severity}" title="${escapeHtml(issues)}">${text}<small>${escapeHtml(issues)}</small></mark>`;
}

function renderOriginalityError(container, message) {
  container.hidden = false;
  container.classList.add("is-error");
  container.innerHTML = `<div class="originality-error">${escapeHtml(message || i18n.error || "Error")}</div>`;
}

function toneClass(value) {
  return ["good", "warn", "bad", "medium", "high", "none"].includes(value) ? value : "none";
}

function setupResumeWizards() {
  document.querySelectorAll("[data-wizard-form]").forEach((form) => {
    const steps = [...form.querySelectorAll(".resume-step")];
    const buttons = [...form.querySelectorAll("[data-step-target]")];
    const prev = form.querySelector("[data-step-prev]");
    const next = form.querySelector("[data-step-next]");
    let index = Number(localStorage.getItem(RESUME_STEP_KEY) || 0);

    const show = (target) => {
      index = Math.max(0, Math.min(steps.length - 1, target));
      localStorage.setItem(RESUME_STEP_KEY, String(index));
      steps.forEach((step, stepIndex) => step.classList.toggle("is-active", stepIndex === index));
      buttons.forEach((button) => button.classList.toggle("is-active", Number(button.dataset.stepTarget) === index));
      if (prev) prev.disabled = index === 0;
      if (next) next.hidden = index === steps.length - 1;
    };

    buttons.forEach((button) => {
      button.addEventListener("click", () => show(Number(button.dataset.stepTarget || 0)));
    });
    if (prev) prev.addEventListener("click", () => show(index - 1));
    if (next) next.addEventListener("click", () => show(index + 1));
    setupTemplatePicker(form);
    show(index);
  });
}

function setupDesignerModes() {
  document.querySelectorAll("[data-designer-launch]").forEach((launcher) => {
    launcher.addEventListener("click", (event) => {
      event.preventDefault();
      if (launcher.classList.contains("is-launching")) return;
      launcher.classList.add("is-active", "is-launching");
      launcher.setAttribute("aria-pressed", "true");
      window.setTimeout(() => {
        window.location.href = launcher.getAttribute("href") || "/app/designer/";
      }, 2000);
    });
  });
  document.querySelectorAll("[data-workspace-launch]").forEach((launcher) => {
    launcher.addEventListener("click", (event) => {
      event.preventDefault();
      if (launcher.classList.contains("is-launching")) return;
      launcher.classList.remove("is-active");
      launcher.classList.add("is-launching", "is-switching-off");
      launcher.setAttribute("aria-pressed", "false");
      window.setTimeout(() => {
        window.location.href = launcher.getAttribute("href") || "/app/";
      }, 1000);
    });
  });

  const panels = [...document.querySelectorAll("[data-designer-mode]")];
  if (!panels.length) return;

  panels.forEach((panel) => setupDesignerPanel(panel));

  const toggles = [...document.querySelectorAll("[data-designer-toggle]")];
  const closeButtons = [...document.querySelectorAll("[data-designer-close]")];
  const toggle = toggles[0];
  const panel = document.querySelector("[data-designer-mode]");
  if (!toggle || !panel) return;

  const setOpen = (open) => {
    const layout = panel.closest(".layout");
    panel.classList.toggle("is-open", open);
    if (layout) layout.classList.toggle("is-designer-mode", open);
    document.body.classList.toggle("is-designer-workspace", open && Boolean(layout));
    toggles.forEach((item) => {
      item.classList.toggle("is-active", open);
      item.setAttribute("aria-pressed", open ? "true" : "false");
    });
    localStorage.setItem(DESIGN_MODE_KEY, open ? "1" : "0");
    window.dispatchEvent(new CustomEvent("designer:viewport-change"));
  };

  toggles.forEach((item) => {
    item.addEventListener("click", () => setOpen(!panel.classList.contains("is-open")));
  });
  closeButtons.forEach((item) => {
    item.addEventListener("click", () => setOpen(false));
  });
  setOpen(localStorage.getItem(DESIGN_MODE_KEY) === "1");
}

function setupDesignerPanel(panel) {
  return setupDesignerPanelV2(panel);

  const shell = panel.querySelector("[data-design-shell]");
  const plane = panel.querySelector("[data-design-plane]");
  const vectorLayer = panel.querySelector("[data-design-vector-layer]");
  const tools = [...panel.querySelectorAll("[data-design-tool]")];
  const photoInput = panel.querySelector("[data-design-photo]");
  const fillInput = panel.querySelector("[data-design-fill]");
  const strokeInput = panel.querySelector("[data-design-stroke]");
  const brushInput = panel.querySelector("[data-design-brush]");
  const brushValue = panel.querySelector("[data-design-brush-value]");
  const zoomValue = panel.querySelector("[data-design-zoom-value]");
  const zoomButtons = [...panel.querySelectorAll("[data-design-zoom]")];
  const presetButtons = [...panel.querySelectorAll("[data-frame-preset]")];
  const penModeButtons = [...panel.querySelectorAll("[data-pen-mode]")];
  const commandButtons = [...panel.querySelectorAll("[data-design-command]")];
  const layersList = panel.querySelector("[data-design-layers]");
  const clearButton = panel.querySelector("[data-design-action='clear']");
  if (!shell || !plane || !vectorLayer) return;

  let tool = "select";
  let selectedId = "";
  let selectedIds = new Set();
  let dragState = null;
  let drawState = null;
  let pointDragState = null;
  let resizeState = null;
  let rotateState = null;
  let marqueeState = null;
  let panState = null;
  let zoom = 1;
  let planeWidth = DESIGN_WIDTH;
  let planeHeight = DESIGN_HEIGHT;
  let penMode = "pen";
  let spaceDown = false;
  let state = loadDesignState();

  const snap = (value) => Math.round(value / DESIGN_GRID) * DESIGN_GRID;

  const save = () => {
    try {
      state.zoom = zoom;
      localStorage.setItem(DESIGN_STORAGE_KEY, JSON.stringify(state));
    } catch {
      return;
    }
  };

  const applyZoom = (nextZoom, center = null, persist = true) => {
    const previousZoom = zoom;
    zoom = clamp(Number(nextZoom) || 1, 0.18, 3);
    plane.style.transform = `scale(${zoom})`;
    if (zoomValue) zoomValue.textContent = `${Math.round(zoom * 100)}%`;
    if (center && previousZoom !== zoom) {
      const factor = zoom / previousZoom;
      shell.scrollLeft = (shell.scrollLeft + center.x) * factor - center.x;
      shell.scrollTop = (shell.scrollTop + center.y) * factor - center.y;
    }
    if (persist) save();
  };

  const fitZoom = () => {
    const availableWidth = Math.max(320, shell.clientWidth - 120);
    const availableHeight = Math.max(260, shell.clientHeight - 120);
    applyZoom(Math.min(1, availableWidth / 1440, availableHeight / 900), null, false);
    save();
    requestAnimationFrame(() => {
      shell.scrollLeft = Math.max(0, (shell.scrollWidth - shell.clientWidth) / 2);
      shell.scrollTop = Math.max(0, (shell.scrollHeight - shell.clientHeight) / 2);
    });
  };

  const render = () => {
    plane.querySelectorAll(".design-object").forEach((item) => item.remove());
    plane.querySelectorAll(".design-marquee").forEach((item) => item.remove());
    renderStrokes();
    state.objects.forEach((object) => {
      const element = document.createElement(object.type === "text" ? "div" : "article");
      element.className = `design-object is-${object.type}${selectedIds.has(object.id) ? " is-selected" : ""}`;
      element.dataset.designId = object.id;
      element.dataset.size = object.type === "frame" ? `${Math.round(object.w)} x ${Math.round(object.h)}` : "";
      element.style.left = `${object.x}px`;
      element.style.top = `${object.y}px`;
      element.style.width = `${object.w}px`;
      element.style.height = `${object.h}px`;
      element.style.setProperty("--object-fill", object.fill || "#ffffff");
      element.style.setProperty("--object-stroke", object.stroke || "#2563eb");

      if (object.type === "image") {
        const image = document.createElement("img");
        image.src = object.src || "";
        image.alt = "";
        element.appendChild(image);
      } else if (object.type === "text") {
        element.contentEditable = "true";
        element.spellcheck = false;
        element.textContent = object.text || i18n.canvas_text || "Text";
        element.addEventListener("input", () => {
          object.text = element.textContent || "";
          save();
        });
      }

      if (object.id === selectedId) {
        ["nw", "ne", "sw", "se"].forEach((corner) => {
          const handle = document.createElement("span");
          handle.className = `design-resize-handle is-${corner}`;
          handle.dataset.resizeCorner = corner;
          handle.addEventListener("pointerdown", (event) => {
            const point = stagePoint(event, plane);
            resizeState = {
              id: object.id,
              corner,
              startX: point.x,
              startY: point.y,
              x: object.x,
              y: object.y,
              w: object.w,
              h: object.h,
            };
            event.preventDefault();
            event.stopPropagation();
          });
          element.appendChild(handle);
        });
      }

      element.addEventListener("pointerdown", (event) => {
        if (tool !== "select" || spaceDown || event.button === 1) return;
        if (event.shiftKey) {
          toggleSelection(object.id);
        } else if (!selectedIds.has(object.id)) {
          selectOnly(object.id);
        }
        plane.querySelectorAll(".design-object").forEach((item) => item.classList.toggle("is-selected", selectedIds.has(item.dataset.designId)));
        const point = stagePoint(event, plane);
        dragState = selectionDragState(point);
        if (element.setPointerCapture) element.setPointerCapture(event.pointerId);
        event.preventDefault();
      });
      plane.appendChild(element);
      });
    renderLayers();
  };

  const renderStrokes = () => {
    vectorLayer.innerHTML = "";
    state.strokes.forEach((stroke) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.classList.add("design-vector-stroke");
      if (selectedIds.has(stroke.id)) path.classList.add("is-selected");
      path.dataset.strokeId = stroke.id;
      path.setAttribute("d", smoothPath(stroke.points));
      path.setAttribute("stroke", stroke.color || "#2563eb");
      path.setAttribute("stroke-width", String(stroke.width || 5));
      path.setAttribute("opacity", stroke.mode === "marker" ? "0.38" : "1");
      path.addEventListener("pointerdown", (event) => {
        if (tool !== "select" || spaceDown || event.button === 1) return;
        if (event.shiftKey) {
          toggleSelection(stroke.id);
        } else if (!selectedIds.has(stroke.id)) {
          selectOnly(stroke.id);
        }
        const point = stagePoint(event, plane);
        dragState = selectionDragState(point);
        event.preventDefault();
        render();
      });
      vectorLayer.appendChild(path);

      if (stroke.id === selectedId) {
        stroke.points.forEach((point, index) => {
          const control = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          control.classList.add("design-vector-point");
          control.dataset.strokeId = stroke.id;
          control.dataset.pointIndex = String(index);
          control.setAttribute("cx", String(point.x));
          control.setAttribute("cy", String(point.y));
          control.setAttribute("r", "7");
          control.addEventListener("pointerdown", (event) => {
            pointDragState = { id: stroke.id, index };
            event.preventDefault();
            event.stopPropagation();
          });
          vectorLayer.appendChild(control);
        });
      }
    });
  };

  const setTool = (nextTool) => {
    tool = nextTool || "select";
    const isPlacingTool = ["frame", "text", "shape-rect", "shape-ellipse", "shape-line", "shape-arrow", "draw"].includes(tool);
    tools.forEach((button) => button.classList.toggle("is-active", button.dataset.designTool === tool));
    plane.classList.toggle("is-drawing", tool === "draw");
    plane.classList.toggle("is-placing", isPlacingTool);
    shell.classList.toggle("is-pannable", tool === "pan" || spaceDown);
    if (document.body.classList.contains("is-mobile-designer")) {
      shell.style.touchAction = tool === "pan" ? "pan-x pan-y" : "none";
    } else {
      shell.style.touchAction = "";
    }
    renderInspector();
  };

  const selectOnly = (id) => {
    selectedId = id || "";
    selectedIds = new Set(id ? [id] : []);
  };

  const toggleSelection = (id) => {
    if (!id) return;
    if (selectedIds.has(id)) {
      selectedIds.delete(id);
      if (selectedId === id) selectedId = selectedIds.values().next().value || "";
    } else {
      selectedIds.add(id);
      selectedId = id;
    }
  };

  const selectionDragState = (point) => ({
    kind: "selection",
    startX: point.x,
    startY: point.y,
    objects: state.objects.filter((item) => selectedIds.has(item.id)).map((item) => ({ id: item.id, x: item.x, y: item.y })),
    strokes: state.strokes.filter((item) => selectedIds.has(item.id)).map((item) => ({ id: item.id, points: item.points.map((point) => ({ ...point })) })),
  });

  const renderLayers = () => {
    if (!layersList) return;
    const layers = [
      ...state.objects.map((item) => ({ id: item.id, type: item.type, label: item.name || item.text || item.type })),
      ...state.strokes.map((item) => ({ id: item.id, type: "stroke", label: item.name || (item.mode === "marker" ? "Marker" : "Pen") })),
    ].reverse();
    layersList.innerHTML = layers
      .map((layer) => `
        <div class="designer-layer-row ${selectedIds.has(layer.id) ? "is-selected" : ""}" data-layer-id="${escapeHtml(layer.id)}">
          <button type="button" data-layer-pick="${escapeHtml(layer.id)}"><span>${escapeHtml(layer.type)}</span></button>
          <input value="${escapeHtml(layer.label)}" data-layer-name="${escapeHtml(layer.id)}">
        </div>
      `)
      .join("");
    layersList.querySelectorAll("[data-layer-pick]").forEach((button) => {
      button.addEventListener("click", (event) => {
        if (event.shiftKey) toggleSelection(button.dataset.layerPick || "");
        else selectOnly(button.dataset.layerPick || "");
        render();
      });
    });
    layersList.querySelectorAll("[data-layer-name]").forEach((input) => {
      input.addEventListener("change", () => {
        renameLayer(input.dataset.layerName || "", input.value);
      });
    });
  };

  const renameLayer = (id, name) => {
    const target = state.objects.find((item) => item.id === id) || state.strokes.find((item) => item.id === id);
    if (!target) return;
    target.name = name.trim() || target.type || "Layer";
    save();
    renderLayers();
  };

  const renderMarquee = () => {
    plane.querySelectorAll(".design-marquee").forEach((item) => item.remove());
    if (!marqueeState) return;
    const x = Math.min(marqueeState.startX, marqueeState.currentX);
    const y = Math.min(marqueeState.startY, marqueeState.currentY);
    const w = Math.abs(marqueeState.currentX - marqueeState.startX);
    const h = Math.abs(marqueeState.currentY - marqueeState.startY);
    const element = document.createElement("div");
    element.className = "design-marquee";
    element.style.left = `${x}px`;
    element.style.top = `${y}px`;
    element.style.width = `${w}px`;
    element.style.height = `${h}px`;
    plane.appendChild(element);
  };

  const renderGuides = (guides = []) => {
    plane.querySelectorAll(".design-guide").forEach((item) => item.remove());
    guides.forEach((guide) => {
      const element = document.createElement("div");
      element.className = `design-guide is-${guide.axis}`;
      if (guide.axis === "x") element.style.left = `${guide.value}px`;
      if (guide.axis === "y") element.style.top = `${guide.value}px`;
      plane.appendChild(element);
    });
  };

  const setTargetFrame = (id = "") => {
    if (targetFrameId === id) return;
    const previous = targetFrameId;
    targetFrameId = id || "";
    if (previous) {
      const element = plane.querySelector(`[data-design-id="${CSS.escape(previous)}"]`);
      if (element) element.classList.remove("is-drop-target");
    }
    if (targetFrameId) {
      const element = plane.querySelector(`[data-design-id="${CSS.escape(targetFrameId)}"]`);
      if (element) element.classList.add("is-drop-target");
    }
  };

  const updateImageElement = (object) => {
    if (!object || object.type !== "image") return;
    const image = plane.querySelector(`[data-design-id="${CSS.escape(object.id)}"] .design-image-content`);
    if (!image) return;
    const placement = imagePlacementForObject(object);
    image.style.left = `${placement.x}px`;
    image.style.top = `${placement.y}px`;
    image.style.width = `${placement.w}px`;
    image.style.height = `${placement.h}px`;
  };

  const smartSnapObject = (object, ignoreIds = selectedIds) => {
    const guides = [];
    const candidates = state.objects.filter((item) => !ignoreIds.has(item.id));
    const threshold = 6;
    const movingX = [object.x, object.x + object.w / 2, object.x + object.w];
    const movingY = [object.y, object.y + object.h / 2, object.y + object.h];
    candidates.forEach((candidate) => {
      const candidateX = [candidate.x, candidate.x + candidate.w / 2, candidate.x + candidate.w];
      const candidateY = [candidate.y, candidate.y + candidate.h / 2, candidate.y + candidate.h];
      movingX.forEach((value, index) => {
        candidateX.forEach((target) => {
          if (Math.abs(value - target) <= threshold) {
            object.x += target - value;
            guides.push({ axis: "x", value: target });
            movingX[index] = target;
          }
        });
      });
      movingY.forEach((value, index) => {
        candidateY.forEach((target) => {
          if (Math.abs(value - target) <= threshold) {
            object.y += target - value;
            guides.push({ axis: "y", value: target });
            movingY[index] = target;
          }
        });
      });
    });
    return guides.slice(0, 4);
  };

  const viewportCenter = (width = 0, height = 0) => {
    const shellRect = shell.getBoundingClientRect();
    const planeRect = plane.getBoundingClientRect();
    return {
      x: ((shellRect.left + shell.clientWidth / 2 - planeRect.left) / planeRect.width) * DESIGN_WIDTH - width / 2,
      y: ((shellRect.top + shell.clientHeight / 2 - planeRect.top) / planeRect.height) * DESIGN_HEIGHT - height / 2,
    };
  };

  tools.forEach((button) => {
    button.addEventListener("click", () => {
      const nextTool = button.dataset.designTool || "select";
      setTool(nextTool);
      if (nextTool === "frame") addDesignObject("frame");
      if (nextTool === "text") addDesignObject("text");
    });
  });

  const addDesignObject = (type, extra = {}) => {
    const count = state.objects.length;
    const object = {
      id: `object-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type,
      w: type === "text" ? 260 : 390,
      h: type === "text" ? 86 : 844,
      fill: fillInput ? fillInput.value : "#ffffff",
      stroke: strokeInput ? strokeInput.value : "#2563eb",
      text: i18n.canvas_text || "Text",
      name: type === "frame" ? "Frame" : type === "image" ? "Image" : "Text",
      ...extra,
    };
    const center = viewportCenter(object.w, object.h);
    object.x = Number.isFinite(extra.x) ? extra.x : center.x + (count % 4) * 18;
    object.y = Number.isFinite(extra.y) ? extra.y : center.y + (count % 5) * 18;
    object.x = snap(object.x);
    object.y = snap(object.y);
    object.w = snap(object.w);
    object.h = snap(object.h);
    state.objects.push(object);
    selectOnly(object.id);
    setTool("select");
    render();
    save();
  };

  plane.addEventListener("pointerdown", (event) => {
    updateLastCanvasPoint(event);
    const isEmptyCanvasTarget = event.target === plane || event.target === vectorLayer;
    if (!isEmptyCanvasTarget && tool === "select") return;
    if (spaceDown || event.button === 1) return;
    if (tool === "draw") {
      if (event.button !== 0) return;
      const point = stagePoint(event, plane);
      const stroke = {
        id: `stroke-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name: penMode === "marker" ? "Marker" : "Pen",
        points: [point],
        color: strokeInput ? strokeInput.value : "#2563eb",
        width: Number(brushInput ? brushInput.value : 5),
        mode: penMode,
      };
      state.strokes.push(stroke);
      selectOnly(stroke.id);
      drawState = { id: stroke.id };
      render();
      event.preventDefault();
      return;
    }
    if (tool === "select") {
      const point = stagePoint(event, plane);
      marqueeState = { startX: point.x, startY: point.y, currentX: point.x, currentY: point.y };
      if (!event.shiftKey) selectOnly("");
      render();
      renderMarquee();
    }
  });

  plane.addEventListener("pointermove", (event) => {
    updateLastCanvasPoint(event);
    if (cropDragState) {
      const object = objectById(cropDragState.id);
      if (object && object.type === "image") {
        const dx = (event.clientX - cropDragState.startX) / zoom;
        const dy = (event.clientY - cropDragState.startY) / zoom;
        object.imageCrop = {
          ...(object.imageCrop || { x: 0, y: 0, scale: 1 }),
          x: cropDragState.crop.x + dx,
          y: cropDragState.crop.y + dy,
        };
        updateImageElement(object);
      }
      return;
    }
    if (cropScaleState) {
      const object = objectById(cropScaleState.id);
      if (object && object.type === "image") {
        const crop = cropScaleState.crop || { x: 0, y: 0, scale: 1 };
        const naturalW = Math.max(1, Number(object.naturalW || object.w || 1));
        const naturalH = Math.max(1, Number(object.naturalH || object.h || 1));
        const oldScale = Math.max(0.05, Number(crop.scale || 1));
        const delta = ((event.clientX - cropScaleState.startX) + (event.clientY - cropScaleState.startY)) / 280;
        const nextScale = clamp(oldScale * Math.exp(delta), 0.05, 20);
        const anchor = { x: object.w / 2, y: object.h / 2 };
        const ratioX = (anchor.x - crop.x) / (naturalW * oldScale);
        const ratioY = (anchor.y - crop.y) / (naturalH * oldScale);
        object.imageCrop = {
          x: anchor.x - ratioX * naturalW * nextScale,
          y: anchor.y - ratioY * naturalH * nextScale,
          scale: nextScale,
        };
        object.imageFit = "crop";
        updateImageElement(object);
      }
      return;
    }
    if (drawState && tool === "draw") {
      const point = stagePoint(event, plane);
      const stroke = state.strokes.find((item) => item.id === drawState.id);
      if (stroke) {
        const last = stroke.points[stroke.points.length - 1];
        if (!last || Math.hypot(point.x - last.x, point.y - last.y) > 3) {
          stroke.points.push(point);
          renderStrokes();
        }
      }
      return;
    }
    if (pointDragState) {
      const stroke = state.strokes.find((item) => item.id === pointDragState.id);
      const point = stagePoint(event, plane);
      if (stroke && stroke.points[pointDragState.index]) {
        stroke.points[pointDragState.index] = point;
        renderStrokes();
      }
      return;
    }
    if (marqueeState) {
      const point = stagePoint(event, plane);
      marqueeState.currentX = point.x;
      marqueeState.currentY = point.y;
      renderMarquee();
      return;
    }
    if (resizeState) {
      const object = state.objects.find((item) => item.id === resizeState.id);
      if (!object) return;
      const point = stagePoint(event, plane);
      const dx = point.x - resizeState.startX;
      const dy = point.y - resizeState.startY;
      if (resizeState.corner.includes("e")) object.w = Math.max(32, resizeState.w + dx);
      if (resizeState.corner.includes("s")) object.h = Math.max(32, resizeState.h + dy);
      if (resizeState.corner.includes("w")) {
          object.x = resizeState.x + dx;
          object.w = Math.max(32, resizeState.w - dx);
        }
        if (resizeState.corner.includes("n")) {
          object.y = resizeState.y + dy;
          object.h = Math.max(32, resizeState.h - dy);
        }
      object.x = snap(object.x);
      object.y = snap(object.y);
      object.w = snap(object.w);
      object.h = snap(object.h);
      renderGuides(smartSnapObject(object, new Set([object.id])));
      render();
      return;
    }
    if (!dragState) return;
    const point = stagePoint(event, plane);
    if (dragState.kind === "selection") {
      const dx = point.x - dragState.startX;
      const dy = point.y - dragState.startY;
      dragState.objects.forEach((item) => {
        const object = state.objects.find((object) => object.id === item.id);
        if (object) {
          object.x = snap(item.x + dx);
          object.y = snap(item.y + dy);
          if (dragState.objects.length === 1) renderGuides(smartSnapObject(object));
        }
      });
      dragState.strokes.forEach((item) => {
        const stroke = state.strokes.find((stroke) => stroke.id === item.id);
        if (stroke) {
          stroke.points = item.points.map((point) => ({ x: point.x + dx, y: point.y + dy }));
        }
      });
      render();
      return;
    }
    const object = state.objects.find((item) => item.id === dragState.id);
    if (!object) return;
    object.x = dragState.x + point.x - dragState.startX;
    object.y = dragState.y + point.y - dragState.startY;
    render();
  });

  plane.addEventListener("pointerup", () => {
    renderGuides();
    if (marqueeState) {
      const rect = normalizedRect(marqueeState);
      const picked = [
        ...state.objects.filter((item) => rectsIntersect(rect, item)).map((item) => item.id),
        ...state.strokes.filter((item) => strokeIntersectsRect(item, rect)).map((item) => item.id),
      ];
      picked.forEach((id) => selectedIds.add(id));
      selectedId = picked[picked.length - 1] || selectedId;
      marqueeState = null;
      render();
    }
    if (drawState || dragState || pointDragState || resizeState) save();
    drawState = null;
    dragState = null;
    pointDragState = null;
    resizeState = null;
  });

  const beginPan = (event) => {
    panState = { x: event.clientX, y: event.clientY, left: shell.scrollLeft, top: shell.scrollTop };
    shell.classList.add("is-panning");
    shell.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  shell.addEventListener("pointerdown", (event) => {
    const canPan = tool === "pan" || spaceDown || event.button === 1;
    if (canPan) {
      beginPan(event);
      return;
    }
    const target = event.target instanceof Element ? event.target : null;
    if (!target || plane.contains(target) || target.closest(".designer-zoom-controls")) return;
    if (event.button !== 0) return;
    if (["frame", "text", "shape-rect", "shape-ellipse", "shape-line", "shape-arrow"].includes(tool)) {
      const point = stagePoint(event, plane);
      if (tool === "frame") addDesignObject("frame", {}, point);
      if (tool === "text") addDesignObject("text", {}, point);
      if (tool === "shape-rect") addDesignObject("shape", { shape: "rect", name: "Rectangle" }, point);
      if (tool === "shape-ellipse") addDesignObject("shape", { shape: "ellipse", name: "Ellipse" }, point);
      if (tool === "shape-line") addDesignObject("shape", { shape: "line", name: "Line" }, point);
      if (tool === "shape-arrow") addDesignObject("shape", { shape: "arrow", name: "Arrow" }, point);
      event.preventDefault();
      return;
    }
    if (tool === "draw") {
      const point = stagePoint(event, plane);
      const vector = normalizeDesignVector({
        id: `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name: penMode === "marker" ? "Marker" : "Vector",
        points: [point],
        color: strokeInput ? strokeInput.value : "#2563eb",
        width: Number(brushInput ? brushInput.value : 5),
        mode: penMode,
        parentId: (findTopFrameAt(point.x, point.y) || {}).id || "",
      });
      state.vectors.push(vector);
      selectOnly(vector.id);
      drawState = { id: vector.id };
      if (shell.setPointerCapture) shell.setPointerCapture(event.pointerId);
      render();
      event.preventDefault();
    }
  });

  shell.addEventListener("pointermove", (event) => {
    if (panState) {
      shell.scrollLeft = panState.left - (event.clientX - panState.x);
      shell.scrollTop = panState.top - (event.clientY - panState.y);
      return;
    }
    if (event.target instanceof Element && plane.contains(event.target)) return;
    if (drawState && tool === "draw") {
      const point = stagePoint(event, plane);
      const vector = vectorById(drawState.id);
      if (vector) {
        const last = vector.points[vector.points.length - 1];
        if (!last || Math.hypot(point.x - last.x, point.y - last.y) > 3) {
          vector.points.push(normalizeDesignPoint(point));
          renderVectors();
        }
      }
    }
  });

  shell.addEventListener("pointerup", () => {
    if (drawState) commit();
    drawState = null;
    panState = null;
    shell.classList.remove("is-panning");
  });

  shell.addEventListener("wheel", (event) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const direction = event.deltaY > 0 ? -1 : 1;
    applyZoom(zoom + direction * 0.08, { x: event.clientX - shell.getBoundingClientRect().left, y: event.clientY - shell.getBoundingClientRect().top });
  }, { passive: false });

  document.addEventListener("keydown", (event) => {
    if (isTypingTarget(event.target)) return;
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
      deleteSelection();
      event.preventDefault();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d" && selectedId) {
      duplicateSelection();
      event.preventDefault();
      return;
    }
    if (event.code !== "Space" || isTypingTarget(event.target)) return;
    spaceDown = true;
    shell.classList.add("is-pannable");
    event.preventDefault();
  });

  document.addEventListener("keyup", (event) => {
    if (event.code !== "Space") return;
    spaceDown = false;
    shell.classList.toggle("is-pannable", tool === "pan");
  });

  [fillInput, strokeInput].forEach((input) => {
    if (!input) return;
    input.addEventListener("input", () => {
      const object = state.objects.find((item) => item.id === selectedId);
      if (!object) return;
      if (input === fillInput) object.fill = input.value;
      if (input === strokeInput) object.stroke = input.value;
      render();
      save();
    });
  });

  const deleteSelection = () => {
    state.objects = state.objects.filter((item) => !selectedIds.has(item.id));
    state.strokes = state.strokes.filter((item) => !selectedIds.has(item.id));
    selectOnly("");
    render();
    save();
  };

  const duplicateSelection = () => {
    const nextSelection = [];
    state.objects.filter((item) => selectedIds.has(item.id)).forEach((object) => {
      const copy = { ...object, id: `object-${Date.now()}-${Math.random().toString(16).slice(2)}`, x: object.x + 32, y: object.y + 32 };
      state.objects.push(copy);
      nextSelection.push(copy.id);
    });
    state.strokes.filter((item) => selectedIds.has(item.id)).forEach((stroke) => {
      const copy = {
        ...stroke,
        id: `stroke-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        points: stroke.points.map((point) => ({ x: point.x + 32, y: point.y + 32 })),
      };
      state.strokes.push(copy);
      nextSelection.push(copy.id);
    });
    selectedIds = new Set(nextSelection);
    selectedId = nextSelection[nextSelection.length - 1] || "";
    render();
    save();
  };

  const groupSelection = () => {
    if (selectedIds.size < 2) return;
    const selectedObjects = state.objects.filter((item) => selectedIds.has(item.id));
    if (!selectedObjects.length) return;
    const box = boundsForObjects(selectedObjects);
    const group = {
      id: `object-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: "group",
      name: "Group",
      x: box.x,
      y: box.y,
      w: box.w,
      h: box.h,
      fill: "transparent",
      stroke: strokeInput ? strokeInput.value : "#2563eb",
      children: selectedObjects.map((item) => item.id),
    };
    state.objects.push(group);
    selectOnly(group.id);
    render();
    save();
  };

  const ungroupSelection = () => {
    const groups = state.objects.filter((item) => selectedIds.has(item.id) && item.type === "group");
    if (!groups.length) return;
    state.objects = state.objects.filter((item) => !groups.some((group) => group.id === item.id));
    selectedIds = new Set(groups.flatMap((group) => group.children || []));
    selectedId = selectedIds.values().next().value || "";
    render();
    save();
  };

  const exportSelection = (format) => {
    const frames = state.objects.filter((item) => selectedIds.has(item.id) && (item.type === "frame" || item.type === "group"));
    const targets = frames.length ? frames : state.objects.filter((item) => selectedIds.has(item.id));
    targets.forEach((frame, index) => exportFrame(frame, format, index));
  };

  const exportFrame = (frame, format, index = 0) => {
    if (!frame) return;
    const svg = buildExportSvg(frame, state);
    const suffix = index ? `-${index + 1}` : "";
    if (format === "svg") {
      downloadBlob(new Blob([svg], { type: "image/svg+xml" }), `${cleanFileName(frame.name || frame.type)}${suffix}.svg`);
      return;
    }
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(frame.w));
      canvas.height = Math.max(1, Math.round(frame.h));
      const ctx = canvas.getContext("2d");
      ctx.drawImage(image, 0, 0);
      canvas.toBlob((blob) => {
        if (blob) downloadBlob(blob, `${cleanFileName(frame.name || frame.type)}${suffix}.png`);
      }, "image/png");
    };
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  };

  commandButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const command = button.dataset.designCommand;
      if (command === "group") groupSelection();
      if (command === "ungroup") ungroupSelection();
      if (command === "export-svg") exportSelection("svg");
      if (command === "export-png") exportSelection("png");
    });
  });

  if (photoInput) {
    photoInput.addEventListener("change", () => {
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;
      addImageFile(file);
      photoInput.value = "";
    });
  }

  const addImageFile = (file) => {
    if (!file || !String(file.type || "").startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const image = new Image();
      image.onload = () => {
        const maxWidth = 620;
        const maxHeight = 460;
        const ratio = Math.min(1, maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
        addDesignObject("image", {
          src: String(reader.result || ""),
          w: Math.max(120, Math.round(image.naturalWidth * ratio)),
          h: Math.max(90, Math.round(image.naturalHeight * ratio)),
        });
      };
      image.src = String(reader.result || "");
    };
    reader.readAsDataURL(file);
  };

  document.addEventListener("paste", (event) => {
    const items = [...(event.clipboardData && event.clipboardData.items ? event.clipboardData.items : [])];
    if (!isTypingTarget(event.target) && pasteDesignClipboardAt(lastCanvasPoint)) {
      event.preventDefault();
      return;
    }
    const imageItem = items.find((item) => String(item.type || "").startsWith("image/"));
    if (!imageItem) return;
    const file = imageItem.getAsFile();
    if (!file) return;
    addImageFile(file);
    event.preventDefault();
  });

  if (brushInput && brushValue) {
    const updateBrushValue = () => {
      brushValue.textContent = `${brushInput.value} px`;
    };
    brushInput.addEventListener("input", updateBrushValue);
    updateBrushValue();
  }

  penModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      penMode = button.dataset.penMode || "pen";
      penModeButtons.forEach((item) => item.classList.toggle("is-active", item === button));
    });
  });

  presetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const preset = DESIGN_FRAME_PRESETS[button.dataset.framePreset || ""];
      if (!preset) return;
      const index = state.objects.length;
      addDesignObject("frame", {
        x: 140 + (index % 3) * 44,
        y: 110 + (index % 4) * 34,
        w: Math.min(preset.w, DESIGN_WIDTH - 180),
        h: Math.min(preset.h, DESIGN_HEIGHT - 160),
        text: preset.label,
      });
    });
  });

  zoomButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.designZoom;
      if (action === "fit") fitZoom();
      if (action === "in") applyZoom(zoom + 0.1, { x: shell.clientWidth / 2, y: shell.clientHeight / 2 });
      if (action === "out") applyZoom(zoom - 0.1, { x: shell.clientWidth / 2, y: shell.clientHeight / 2 });
    });
  });

  window.addEventListener("designer:viewport-change", () => {
    requestAnimationFrame(() => {
      applyZoom(zoom, null, false);
      if (!state.didFit) fitZoom();
    });
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      state = { objects: [], strokes: [], drawing: "", zoom };
      selectedId = "";
      render();
      save();
    });
  }

  vectorLayer.setAttribute("viewBox", `0 0 ${DESIGN_WIDTH} ${DESIGN_HEIGHT}`);
  plane.style.width = `${DESIGN_WIDTH}px`;
  plane.style.height = `${DESIGN_HEIGHT}px`;
  zoom = clamp(Number(state.zoom) || 1, 0.18, 3);
  applyZoom(zoom, null, false);
  render();
  if (!state.didFit) {
    state.didFit = true;
    fitZoom();
    save();
  }
}

function setupDesignerPanelV2(panel) {
  const projectDataNode = document.getElementById("current-design-project");
  const projectConfigNode = document.getElementById("design-project-config");
  const currentDesignProject = projectDataNode ? JSON.parse(projectDataNode.textContent || "null") : null;
  const projectConfig = projectConfigNode ? JSON.parse(projectConfigNode.textContent || "{}") : {};
  const shell = panel.querySelector("[data-design-shell]");
  const plane = panel.querySelector("[data-design-plane]");
  const vectorLayer = panel.querySelector("[data-design-vector-layer]");
  const tools = [...panel.querySelectorAll("[data-design-tool]")];
  const photoInput = panel.querySelector("[data-design-photo]");
  const fillInput = panel.querySelector("[data-design-fill]");
  const strokeInput = panel.querySelector("[data-design-stroke]");
  const brushInput = panel.querySelector("[data-design-brush]");
  const brushValue = panel.querySelector("[data-design-brush-value]");
  const zoomValue = panel.querySelector("[data-design-zoom-value]");
  const zoomButtons = [...panel.querySelectorAll("[data-design-zoom]")];
  const presetButtons = [...panel.querySelectorAll("[data-frame-preset]")];
  const penModeButtons = [...panel.querySelectorAll("[data-pen-mode]")];
  const commandButtons = [...panel.querySelectorAll("[data-design-command]")];
  const layersList = panel.querySelector("[data-design-layers]");
  const layerPanel = panel.querySelector("[data-design-layer-panel]");
  const inspector = panel.querySelector("[data-design-inspector]");
  const selectionCount = panel.querySelector("[data-design-selection-count]");
  const layerCount = panel.querySelector("[data-design-layer-count]");
  const clearButton = panel.querySelector("[data-design-action='clear']");
  const projectTitle = panel.querySelector("[data-design-project-title]");
  const pageTitle = document.querySelector("[data-design-page-title]");
  const saveStatus = panel.querySelector("[data-design-save-status]");
  const saveRetry = panel.querySelector("[data-design-save-retry]");
  const storageBadge = panel.querySelector("[data-design-storage-badge]");
  const importDraftButton = panel.querySelector("[data-design-import-draft]");
  if (!shell || !plane || !vectorLayer) return;

  let projectId = currentDesignProject && currentDesignProject.id ? String(currentDesignProject.id) : "";
  let projectStorageText = currentDesignProject?.storage_text || "0 B";
  let saveTimer = 0;
  let saving = false;
  let saveFailed = false;
  let dirty = false;
  let didInitialRender = false;
  const readOnly = Boolean(currentDesignProject && currentDesignProject.can_edit === false);
  let tool = "select";
  let selectedId = "";
  let selectedIds = new Set();
  let dragState = null;
  let drawState = null;
  let pointDragState = null;
  let resizeState = null;
  let rotateState = null;
  let marqueeState = null;
  let panState = null;
  let zoom = 1;
  let penMode = "pen";
  let vectorEdit = false;
  let spaceDown = false;
  let layerDragId = "";
  let contextPoint = null;
  let lastCanvasPoint = null;
  let designClipboard = null;
  let cropEditId = "";
  let cropDragState = null;
  let cropScaleState = null;
  let targetFrameId = "";
  let state = normalizeDesignStateV2(currentDesignProject?.state || loadDesignStateV2());
  let history = [designSnapshot(state)];
  let historyIndex = 0;
  if (currentDesignProject?.title) state.title = currentDesignProject.title;
  if (importDraftButton) importDraftButton.hidden = Boolean(projectId) || !hasLocalDesignDraft();

  const snap = (value) => Math.round(value / DESIGN_GRID) * DESIGN_GRID;
  const objects = () => state.objects || [];
  const vectors = () => state.vectors || [];
  const objectById = (id) => objects().find((item) => item.id === id);
  const vectorById = (id) => vectors().find((item) => item.id === id);
  const selectedObject = () => objectById(selectedId);
  const selectedVector = () => vectorById(selectedId);
  const selectedLayer = () => selectedObject() || selectedVector();
  const isLayerSelected = (id) => selectedIds.has(id);

  const updatePlaneSize = () => {
    const zoomSafe = Math.max(zoom, 0.03);
    planeWidth = Math.max(DESIGN_WIDTH, Math.ceil((shell.scrollLeft + shell.clientWidth) / zoomSafe));
    planeHeight = Math.max(DESIGN_HEIGHT, Math.ceil((shell.scrollTop + shell.clientHeight) / zoomSafe));
    plane.style.width = `${planeWidth}px`;
    plane.style.height = `${planeHeight}px`;
    vectorLayer.setAttribute("viewBox", `0 0 ${planeWidth} ${planeHeight}`);
  };

  const stagePoint = (event) => {
    const rect = plane.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * planeWidth,
      y: ((event.clientY - rect.top) / rect.height) * planeHeight,
    };
  };

  const persist = () => {
    try {
      state.version = 2;
      state.zoom = zoom;
      state.title = state.title || projectTitle?.textContent?.trim() || currentDesignProject?.title || "New design";
      localStorage.setItem(DESIGN_STORAGE_KEY_V2, JSON.stringify(state));
    } catch {
      return;
    }
  };

  const csrfToken = () => {
    const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  };

  const jsonRequest = async (url, options = {}) => {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Accept": "application/json",
        ...(options.body && !(options.body instanceof FormData) ? {"Content-Type": "application/json"} : {}),
        ...(options.method && options.method !== "GET" ? {"X-CSRFToken": csrfToken()} : {}),
        ...(options.headers || {}),
      },
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  };

  const setSaveStatus = (text, failed = false) => {
    if (saveStatus) {
      saveStatus.textContent = text;
      saveStatus.classList.toggle("is-error", failed);
    }
    if (saveRetry) saveRetry.hidden = !failed;
  };

  const syncProjectChrome = () => {
    const title = state.title || currentDesignProject?.title || "New design";
    if (projectTitle && !projectTitle.querySelector("input")) projectTitle.textContent = title;
    if (pageTitle) pageTitle.textContent = title;
    if (storageBadge) storageBadge.textContent = projectStorageText || "0 B";
  };

  const savedTime = () => new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  const ensureDesignProject = async () => {
    if (projectId) return projectId;
    const data = await jsonRequest(`${projectConfig.apiUrl}create/`, {
      method: "POST",
      body: JSON.stringify({ title: state.title || "New design", state }),
    });
    projectId = String(data.project.id);
    projectStorageText = data.project.storage_text || projectStorageText;
    window.history.replaceState({}, "", `${window.location.pathname}?project=${projectId}`);
    syncProjectChrome();
    if (importDraftButton) importDraftButton.hidden = true;
    return projectId;
  };

  const uploadDesignAsset = async (file) => {
    if (readOnly) throw new Error(i18n.view_only || "View only");
    await ensureDesignProject();
    const form = new FormData();
    form.append("file", file);
    const data = await jsonRequest(`${projectConfig.apiUrl}${projectId}/assets/`, { method: "POST", body: form });
    projectStorageText = data.project?.storage_text || projectStorageText;
    syncProjectChrome();
    return data.asset;
  };

  const dataUrlToFile = async (dataUrl, name = "image.png") => {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    return new File([blob], name, { type: blob.type || "image/png" });
  };

  const migrateEmbeddedImages = async () => {
    for (const object of objects()) {
      if (object.type !== "image" || object.assetId || !String(object.src || "").startsWith("data:image/")) continue;
      if (String(object.src).startsWith("data:image/svg")) continue;
      try {
        const asset = await uploadDesignAsset(await dataUrlToFile(object.src, `${object.name || "image"}.png`));
        object.assetId = asset.id;
        object.src = asset.preview_url;
        object.name = object.name || asset.name || "Image";
      } catch {
        // Local data URLs stay as fallback if migration fails.
      }
    }
  };

  const generateDesignPreview = async () => {
    const frame = objects().find((item) => item.type === "frame") || objects()[0];
    if (!frame) return "";
    try {
      const svg = buildExportSvgV2(frame, state);
      const image = new Image();
      image.crossOrigin = "anonymous";
      const loaded = new Promise((resolve, reject) => {
        image.onload = resolve;
        image.onerror = reject;
      });
      image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
      await loaded;
      const canvas = document.createElement("canvas");
      const ratio = Math.min(1, 720 / Math.max(1, frame.w), 480 / Math.max(1, frame.h));
      canvas.width = Math.max(240, Math.round(frame.w * ratio));
      canvas.height = Math.max(160, Math.round(frame.h * ratio));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      return canvas.toDataURL("image/jpeg", 0.78);
    } catch {
      return "";
    }
  };

  const saveProject = async () => {
    if (!projectConfig.apiUrl || readOnly) return;
    try {
      saving = true;
      clearTimeout(saveTimer);
      setSaveStatus(i18n.saving || "Saving...");
      await ensureDesignProject();
      await migrateEmbeddedImages();
      const preview = await generateDesignPreview();
      const data = await jsonRequest(`${projectConfig.apiUrl}${projectId}/save/`, {
        method: "POST",
        body: JSON.stringify({ title: state.title || "New design", state, preview }),
      });
      projectStorageText = data.project?.storage_text || projectStorageText;
      dirty = false;
      saveFailed = false;
      syncProjectChrome();
      setSaveStatus(`${i18n.saved || "Saved"} ${savedTime()}`);
    } catch {
      saveFailed = true;
      setSaveStatus(i18n.save_failed || "Save failed", true);
    } finally {
      saving = false;
    }
  };

  const scheduleProjectSave = () => {
    if (!didInitialRender || !projectConfig.apiUrl || readOnly) return;
    dirty = true;
    saveFailed = false;
    setSaveStatus(i18n.saving || "Saving...");
    clearTimeout(saveTimer);
    saveTimer = window.setTimeout(saveProject, 600);
  };

  const pushHistory = () => {
    const snapshot = designSnapshot(state);
    if (history[historyIndex] === snapshot) {
      persist();
      return;
    }
    history = history.slice(0, historyIndex + 1);
    history.push(snapshot);
    if (history.length > DESIGN_HISTORY_LIMIT) history.shift();
    historyIndex = history.length - 1;
    persist();
    scheduleProjectSave();
  };

  const commit = () => {
    normalizeDesignStateV2(state);
    pushHistory();
    render();
  };

  const restoreHistory = (direction) => {
    const nextIndex = historyIndex + direction;
    if (nextIndex < 0 || nextIndex >= history.length) return;
    historyIndex = nextIndex;
    state = normalizeDesignStateV2(JSON.parse(history[historyIndex]));
    selectedIds = new Set([...selectedIds].filter((id) => objectById(id) || vectorById(id)));
    selectedId = selectedIds.has(selectedId) ? selectedId : selectedIds.values().next().value || "";
    persist();
    render();
  };

  const stageToClientPoint = (point) => {
    const rect = plane.getBoundingClientRect();
    return {
      x: rect.left + (point.x / planeWidth) * rect.width,
      y: rect.top + (point.y / planeHeight) * rect.height,
    };
  };

  const applyZoom = (nextZoom, center = null, shouldPersist = true) => {
    const previousZoom = zoom;
    const shellRect = shell.getBoundingClientRect();
    const clientAnchor = center
      ? { x: shellRect.left + center.x, y: shellRect.top + center.y }
      : null;
    const stageAnchor = clientAnchor
      ? stagePoint({ clientX: clientAnchor.x, clientY: clientAnchor.y }, plane)
      : null;
    zoom = clamp(Number(nextZoom) || 1, 0.03, 5);
    updatePlaneSize();
    plane.style.transform = `scale(${zoom})`;
    if (zoomValue) zoomValue.textContent = `${Math.round(zoom * 100)}%`;
    if (clientAnchor && stageAnchor && previousZoom !== zoom) {
      const correctScroll = () => {
        const nextClient = stageToClientPoint(stageAnchor);
        shell.scrollLeft += nextClient.x - clientAnchor.x;
        shell.scrollTop += nextClient.y - clientAnchor.y;
      };
      correctScroll();
      requestAnimationFrame(correctScroll);
    }
    if (shouldPersist) persist();
  };

  const fitZoom = () => {
    const target = { x: 0, y: 0, w: DESIGN_WIDTH, h: DESIGN_HEIGHT };
    const availableWidth = Math.max(360, shell.clientWidth - 64);
    const availableHeight = Math.max(280, shell.clientHeight - 64);
    const nextZoom = Math.min(1, Math.max(0.03, Math.min(availableWidth / target.w, availableHeight / target.h)));
    applyZoom(nextZoom, null, false);
    requestAnimationFrame(() => {
      shell.scrollLeft = Math.max(0, plane.offsetLeft + (target.x + target.w / 2) * zoom - shell.clientWidth / 2);
      shell.scrollTop = Math.max(0, plane.offsetTop + (target.y + target.h / 2) * zoom - shell.clientHeight / 2);
      persist();
    });
  };

  const render = () => {
    plane.querySelectorAll(".design-object, .design-marquee, .design-guide").forEach((item) => item.remove());
    renderVectors();
    const hasParent = new Set(objects().map((item) => item.id));
    objects()
      .filter((object) => !object.parentId || !hasParent.has(object.parentId))
      .forEach((object) => renderObject(object, null, plane));
    renderLayers();
    renderInspector();
    syncColorInputs();
  };

  const renderObject = (object, parentObject, parentElement) => {
    if (object.hidden) return null;
    const element = document.createElement(object.type === "text" ? "div" : "article");
    element.className = [
      "design-object",
      `is-${object.type}`,
      object.shape ? `is-${object.shape}` : "",
      object.clipContent ? "is-clipping" : "",
      object.locked ? "is-locked" : "",
      isLayerSelected(object.id) ? "is-selected" : "",
      object.id === targetFrameId ? "is-drop-target" : "",
      object.type === "image" && object.id === cropEditId ? "is-cropping" : "",
    ].filter(Boolean).join(" ");
    element.dataset.designId = object.id;
    element.dataset.size = object.type === "frame" ? `${Math.round(object.w)} x ${Math.round(object.h)}` : "";
    element.style.left = `${object.x - (parentObject ? parentObject.x : 0)}px`;
    element.style.top = `${object.y - (parentObject ? parentObject.y : 0)}px`;
    element.style.width = `${object.w}px`;
    element.style.height = `${object.h}px`;
    element.style.opacity = String(object.opacity ?? 1);
    element.style.transform = `rotate(${Number(object.rotation || 0)}deg)`;
    element.style.setProperty("--object-fill", object.fill || "transparent");
    element.style.setProperty("--object-stroke", object.stroke || "#2563eb");
    element.style.setProperty("--object-radius", `${object.cornerRadius ?? 10}px`);

    if (object.type === "image") {
      ensureImageCropDefaults(object);
      const placement = imagePlacementForObject(object);
      const viewport = document.createElement("div");
      viewport.className = "design-image-viewport";
      const image = document.createElement("img");
      image.className = "design-image-content";
      image.src = object.src || "";
      image.alt = object.name || "";
      image.style.left = `${placement.x}px`;
      image.style.top = `${placement.y}px`;
      image.style.width = `${placement.w}px`;
      image.style.height = `${placement.h}px`;
      image.addEventListener("load", () => {
        if ((!object.naturalW || !object.naturalH) && image.naturalWidth && image.naturalHeight) {
          object.naturalW = image.naturalWidth;
          object.naturalH = image.naturalHeight;
          ensureImageCropDefaults(object);
          persist();
          render();
        }
      }, { once: true });
      viewport.appendChild(image);
      element.appendChild(viewport);
      if (object.id === cropEditId) {
        const handle = document.createElement("span");
        handle.className = "design-crop-scale-handle";
        handle.addEventListener("pointerdown", (event) => {
          cropScaleState = {
            id: object.id,
            startX: event.clientX,
            startY: event.clientY,
            crop: { ...(object.imageCrop || { x: 0, y: 0, scale: 1 }) },
          };
          if (element.setPointerCapture) element.setPointerCapture(event.pointerId);
          event.preventDefault();
          event.stopPropagation();
        });
        element.appendChild(handle);
      }
    } else if (object.type === "text") {
      element.contentEditable = object.locked ? "false" : "true";
      element.spellcheck = false;
      element.textContent = object.text || i18n.canvas_text || "Text";
      element.style.fontSize = `${object.fontSize || 22}px`;
      element.style.fontWeight = String(object.fontWeight || 800);
      element.style.fontFamily = object.fontFamily || "Arial, sans-serif";
      element.style.textAlign = object.textAlign || "left";
      element.style.lineHeight = String(object.lineHeight || 1.15);
      element.style.letterSpacing = `${Number(object.letterSpacing || 0)}px`;
      element.style.background = object.fill && object.fill !== "transparent" ? object.fill : "transparent";
      element.style.webkitTextStroke = `${Number(object.textStrokeWidth || 0)}px ${object.textStroke || "transparent"}`;
      if (object.textGradient) {
        element.style.color = "transparent";
        element.style.backgroundImage = `linear-gradient(90deg, ${object.gradientStart || object.stroke || "#2563eb"}, ${object.gradientEnd || "#ec4899"})`;
        element.style.webkitBackgroundClip = "text";
        element.style.backgroundClip = "text";
      }
      element.addEventListener("input", () => {
        object.text = element.textContent || "";
        object.name = object.name || object.text.slice(0, 24) || "Text";
        persist();
        renderLayers();
      });
      element.addEventListener("blur", () => {
        object.text = element.textContent || "";
        object.name = object.name || object.text.slice(0, 24) || "Text";
        pushHistory();
      });
      element.addEventListener("dblclick", (event) => {
        if (object.locked) return;
        element.focus();
        placeCaretAtEnd(element);
        event.stopPropagation();
      });
    } else if (object.type === "shape") {
      renderShapeElement(element, object);
    }

    if (object.id === selectedId && !object.locked) {
      ["nw", "ne", "sw", "se"].forEach((corner) => {
        const handle = document.createElement("span");
        handle.className = `design-resize-handle is-${corner}`;
        handle.dataset.resizeCorner = corner;
        handle.addEventListener("pointerdown", (event) => {
          const point = stagePoint(event, plane);
          resizeState = {
            id: object.id,
            corner,
            startX: point.x,
            startY: point.y,
            object: cloneDesignObject(object),
            children: childSnapshotsForFrame(object),
          };
          event.preventDefault();
          event.stopPropagation();
        });
        element.appendChild(handle);
      });
      const rotateHandle = document.createElement("span");
      rotateHandle.className = "design-rotate-handle";
      rotateHandle.addEventListener("pointerdown", (event) => {
        const center = { x: object.x + object.w / 2, y: object.y + object.h / 2 };
        const point = stagePoint(event, plane);
        rotateState = {
          id: object.id,
          center,
          startAngle: Math.atan2(point.y - center.y, point.x - center.x),
          rotation: Number(object.rotation || 0),
        };
        event.preventDefault();
        event.stopPropagation();
      });
      element.appendChild(rotateHandle);
    }

    element.addEventListener("pointerdown", (event) => {
      if (tool !== "select" || spaceDown || event.button === 1) return;
      if (object.type === "image" && cropEditId === object.id && !event.target.closest(".design-resize-handle") && !event.target.closest(".design-crop-scale-handle")) {
        cropDragState = {
          id: object.id,
          startX: event.clientX,
          startY: event.clientY,
          crop: { ...(object.imageCrop || { x: 0, y: 0, scale: 1 }) },
        };
        if (element.setPointerCapture) element.setPointerCapture(event.pointerId);
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (object.type === "text" && selectedId === object.id && event.detail >= 2) {
        element.focus();
        placeCaretAtEnd(element);
        event.stopPropagation();
        return;
      }
      if (object.type === "text" && selectedId === object.id && event.target === element) {
        element.focus();
        return;
      }
      if (object.type === "image" && selectedId === object.id && event.detail >= 2) {
        startImageCrop(object);
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.shiftKey) toggleSelection(object.id);
      else if (!selectedIds.has(object.id)) selectOnly(object.id);
      if (!object.locked) {
        const point = stagePoint(event, plane);
        dragState = selectionDragState(point);
        if (element.setPointerCapture) element.setPointerCapture(event.pointerId);
      }
      event.preventDefault();
      event.stopPropagation();
      render();
    });

    if (object.type === "image") {
      element.addEventListener("dblclick", (event) => {
        if (object.locked) return;
        startImageCrop(object);
        event.preventDefault();
        event.stopPropagation();
      });
    }
    if (object.type === "shape") {
      element.addEventListener("dblclick", (event) => {
        if (object.locked) return;
        convertShapeToVector(object);
        event.preventDefault();
        event.stopPropagation();
      });
    }

    parentElement.appendChild(element);
    objects()
      .filter((child) => child.parentId === object.id)
      .forEach((child) => renderObject(child, object, element));
    return element;
  };

  const renderShapeElement = (element, object) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("design-shape-svg");
    svg.setAttribute("viewBox", `0 0 ${Math.max(1, object.w)} ${Math.max(1, object.h)}`);
    svg.setAttribute("preserveAspectRatio", "none");
    const fill = object.fill || "transparent";
    const stroke = object.stroke || "#2563eb";
    const width = Math.max(0, Number(object.strokeWidth ?? 2));
    if (object.shape === "ellipse") {
      const ellipse = document.createElementNS("http://www.w3.org/2000/svg", "ellipse");
      ellipse.setAttribute("cx", String(object.w / 2));
      ellipse.setAttribute("cy", String(object.h / 2));
      ellipse.setAttribute("rx", String(Math.max(1, object.w / 2 - width / 2)));
      ellipse.setAttribute("ry", String(Math.max(1, object.h / 2 - width / 2)));
      ellipse.setAttribute("fill", fill);
      ellipse.setAttribute("stroke", stroke);
      ellipse.setAttribute("stroke-width", String(width));
      svg.appendChild(ellipse);
    } else if (object.shape === "line" || object.shape === "arrow") {
      if (object.shape === "arrow") {
        const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
        const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
        marker.setAttribute("id", `${object.id}-arrow`);
        marker.setAttribute("viewBox", "0 0 10 10");
        marker.setAttribute("refX", "9");
        marker.setAttribute("refY", "5");
        marker.setAttribute("markerWidth", "7");
        marker.setAttribute("markerHeight", "7");
        marker.setAttribute("orient", "auto-start-reverse");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
        path.setAttribute("fill", stroke);
        marker.appendChild(path);
        defs.appendChild(marker);
        svg.appendChild(defs);
      }
      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", "8");
      line.setAttribute("y1", String(object.h / 2));
      line.setAttribute("x2", String(Math.max(10, object.w - 8)));
      line.setAttribute("y2", String(object.h / 2));
      line.setAttribute("stroke", stroke);
      line.setAttribute("stroke-width", String(width));
      line.setAttribute("stroke-linecap", "round");
      if (object.shape === "arrow") line.setAttribute("marker-end", `url(#${object.id}-arrow)`);
      svg.appendChild(line);
    } else {
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(width / 2));
      rect.setAttribute("y", String(width / 2));
      rect.setAttribute("width", String(Math.max(1, object.w - width)));
      rect.setAttribute("height", String(Math.max(1, object.h - width)));
      rect.setAttribute("rx", String(object.cornerRadius ?? 10));
      rect.setAttribute("fill", fill);
      rect.setAttribute("stroke", stroke);
      rect.setAttribute("stroke-width", String(width));
      svg.appendChild(rect);
    }
    element.appendChild(svg);
  };

  const renderVectors = () => {
    vectorLayer.innerHTML = "";
    const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
    objects().filter((item) => item.type === "frame" && item.clipContent && !item.hidden).forEach((frame) => {
      const clip = document.createElementNS("http://www.w3.org/2000/svg", "clipPath");
      clip.setAttribute("id", `${frame.id}-clip`);
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", String(frame.x));
      rect.setAttribute("y", String(frame.y));
      rect.setAttribute("width", String(frame.w));
      rect.setAttribute("height", String(frame.h));
      clip.appendChild(rect);
      defs.appendChild(clip);
    });
    vectorLayer.appendChild(defs);

    vectors().forEach((vector) => {
      if (vector.hidden) return;
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.classList.add("design-vector-stroke");
      if (isLayerSelected(vector.id)) path.classList.add("is-selected");
      if (vector.locked) path.classList.add("is-locked");
      path.dataset.vectorId = vector.id;
      path.setAttribute("d", vectorPathV2(vector.points, vector.closed));
      path.setAttribute("stroke", vector.color || "#2563eb");
      path.setAttribute("stroke-width", String(vector.width ?? 5));
      path.setAttribute("opacity", String((vector.opacity ?? 1) * (vector.mode === "marker" ? 0.38 : 1)));
      if (vector.parentId) {
        const parent = objectById(vector.parentId);
        if (parent && parent.clipContent) path.setAttribute("clip-path", `url(#${parent.id}-clip)`);
      }
      path.addEventListener("pointerdown", (event) => {
        if (tool !== "select" || spaceDown || event.button === 1) return;
        if (event.shiftKey) toggleSelection(vector.id);
        else if (!selectedIds.has(vector.id)) selectOnly(vector.id);
        if (!vector.locked) dragState = selectionDragState(stagePoint(event, plane));
        event.preventDefault();
        event.stopPropagation();
        render();
      });
      vectorLayer.appendChild(path);

      if (vector.id === selectedId && vectorEdit) renderVectorControls(vector);
    });
  };

  const renderVectorControls = (vector) => {
    vector.points.forEach((point, index) => {
      [["in", point.in], ["out", point.out]].forEach(([handle, handlePoint]) => {
        if (!handlePoint) return;
        const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
        line.classList.add("design-vector-handle-line");
        line.setAttribute("x1", String(point.x));
        line.setAttribute("y1", String(point.y));
        line.setAttribute("x2", String(handlePoint.x));
        line.setAttribute("y2", String(handlePoint.y));
        vectorLayer.appendChild(line);
        const control = vectorControlCircle(handlePoint.x, handlePoint.y, "handle");
        control.addEventListener("pointerdown", (event) => {
          pointDragState = { id: vector.id, index, handle };
          event.preventDefault();
          event.stopPropagation();
        });
        vectorLayer.appendChild(control);
      });
      const anchor = vectorControlCircle(point.x, point.y, "anchor");
      anchor.addEventListener("dblclick", (event) => {
        insertVectorPointAfter(vector, index);
        event.preventDefault();
        event.stopPropagation();
      });
      anchor.addEventListener("pointerdown", (event) => {
        pointDragState = { id: vector.id, index, handle: "anchor" };
        event.preventDefault();
        event.stopPropagation();
      });
      vectorLayer.appendChild(anchor);
    });
  };

  const vectorControlCircle = (x, y, type) => {
    const control = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    control.classList.add("design-vector-point", `is-${type}`);
    control.setAttribute("cx", String(x));
    control.setAttribute("cy", String(y));
    control.setAttribute("r", type === "anchor" ? "3.8" : "3");
    return control;
  };

  const convertShapeToVector = (object) => {
    if (!object || object.type !== "shape") return;
    const points = shapePointsForVector(object);
    if (points.length < 2) return;
    const vector = normalizeDesignVector({
      id: `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      name: `${object.name || object.shape || "Shape"} path`,
      points,
      closed: object.shape !== "line" && object.shape !== "arrow",
      color: object.stroke || "#2563eb",
      width: Number(object.strokeWidth ?? 2),
      opacity: object.opacity ?? 1,
      parentId: object.parentId || "",
    });
    state.objects = objects().filter((item) => item.id !== object.id);
    state.vectors.push(vector);
    selectOnly(vector.id);
    vectorEdit = true;
    commit();
  };

  const shapePointsForVector = (object) => {
    const x = Number(object.x || 0);
    const y = Number(object.y || 0);
    const w = Math.max(1, Number(object.w || 1));
    const h = Math.max(1, Number(object.h || 1));
    if (object.shape === "line" || object.shape === "arrow") {
      return [
        normalizeDesignPoint({ x: x + 8, y: y + h / 2 }),
        normalizeDesignPoint({ x: x + w - 8, y: y + h / 2 }),
      ];
    }
    if (object.shape === "ellipse") {
      const cx = x + w / 2;
      const cy = y + h / 2;
      const rx = w / 2;
      const ry = h / 2;
      const k = 0.5522847498;
      return [
        normalizeDesignPoint({ x: cx, y, in: { x: cx - rx * k, y }, out: { x: cx + rx * k, y } }),
        normalizeDesignPoint({ x: x + w, y: cy, in: { x: x + w, y: cy - ry * k }, out: { x: x + w, y: cy + ry * k } }),
        normalizeDesignPoint({ x: cx, y: y + h, in: { x: cx + rx * k, y: y + h }, out: { x: cx - rx * k, y: y + h } }),
        normalizeDesignPoint({ x, y: cy, in: { x, y: cy + ry * k }, out: { x, y: cy - ry * k } }),
      ];
    }
    if (object.shape === "triangle") {
      return [
        normalizeDesignPoint({ x: x + w / 2, y }),
        normalizeDesignPoint({ x: x + w, y: y + h }),
        normalizeDesignPoint({ x, y: y + h }),
      ];
    }
    return [
      normalizeDesignPoint({ x, y }),
      normalizeDesignPoint({ x: x + w, y }),
      normalizeDesignPoint({ x: x + w, y: y + h }),
      normalizeDesignPoint({ x, y: y + h }),
    ];
  };

  const insertVectorPointAfter = (vector, index) => {
    if (!vector || !Array.isArray(vector.points) || vector.points.length < 2) return;
    const nextIndex = index + 1 < vector.points.length ? index + 1 : (vector.closed ? 0 : -1);
    if (nextIndex < 0) return;
    const current = vector.points[index];
    const next = vector.points[nextIndex];
    if (!current || !next) return;
    const point = normalizeDesignPoint({
      x: (current.x + next.x) / 2,
      y: (current.y + next.y) / 2,
    });
    vector.points.splice(index + 1, 0, point);
    commit();
  };

  const setTool = (nextTool) => {
    tool = nextTool || "select";
    const isPlacingTool = ["frame", "text", "shape-rect", "shape-ellipse", "shape-line", "shape-arrow", "draw"].includes(tool);
    tools.forEach((button) => button.classList.toggle("is-active", button.dataset.designTool === tool));
    plane.classList.toggle("is-drawing", tool === "draw");
    plane.classList.toggle("is-placing", isPlacingTool);
    shell.classList.toggle("is-pannable", tool === "pan" || spaceDown);
    renderInspector();
  };

  const selectOnly = (id) => {
    selectedId = id || "";
    selectedIds = new Set(id ? [id] : []);
    vectorEdit = vectorById(selectedId) ? vectorEdit : false;
    if (cropEditId && cropEditId !== selectedId) cropEditId = "";
  };

  const toggleSelection = (id) => {
    if (!id) return;
    if (selectedIds.has(id)) {
      selectedIds.delete(id);
      if (selectedId === id) selectedId = selectedIds.values().next().value || "";
    } else {
      selectedIds.add(id);
      selectedId = id;
    }
    vectorEdit = vectorById(selectedId) ? vectorEdit : false;
  };

  const selectionDragState = (point) => {
    const dragObjectIds = new Set();
    selectedIds.forEach((id) => {
      const object = objectById(id);
      if (!object || object.locked) return;
      dragObjectIds.add(object.id);
      if (object.type === "frame" || object.type === "group") {
        collectDescendantObjectIds(object.id).forEach((childId) => dragObjectIds.add(childId));
      }
    });
    const dragVectorIds = new Set();
    selectedIds.forEach((id) => {
      const vector = vectorById(id);
      if (vector && !vector.locked) dragVectorIds.add(id);
      const object = objectById(id);
      if (object && (object.type === "frame" || object.type === "group")) {
        vectors().filter((item) => item.parentId === object.id && !item.locked).forEach((item) => dragVectorIds.add(item.id));
      }
    });
    return {
      kind: "selection",
      startX: point.x,
      startY: point.y,
      objects: [...dragObjectIds].map((id) => {
        const object = objectById(id);
        return object ? { id, x: object.x, y: object.y } : null;
      }).filter(Boolean),
      vectors: [...dragVectorIds].map((id) => {
        const vector = vectorById(id);
        return vector ? { id, points: vector.points.map((item) => cloneDesignPoint(item)) } : null;
      }).filter(Boolean),
    };
  };

  const renderLayers = () => {
    if (!layersList) return;
    const objectIds = new Set(objects().map((item) => item.id));
    const rows = [];
    const childrenFor = (parentId) => [
      ...objects().filter((item) => (item.parentId || "") === parentId),
      ...vectors().filter((item) => (item.parentId || "") === parentId),
    ];
    const pushRows = (parentId, depth) => {
      childrenFor(parentId).slice().reverse().forEach((layer) => {
        rows.push(layerRow(layer, depth));
        if (layer.type === "frame" || layer.type === "group") pushRows(layer.id, depth + 1);
      });
    };
    pushRows("", 0);
    objects().filter((item) => item.parentId && !objectIds.has(item.parentId)).forEach((item) => rows.push(layerRow(item, 0)));
    if (layerCount) layerCount.textContent = String(objects().length + vectors().length);
    layersList.innerHTML = `
      <div class="designer-layer-toolbar">
        <button type="button" data-layer-command="group">${escapeHtml(i18n.group || "Group")}</button>
        <button type="button" data-layer-command="ungroup">${escapeHtml(i18n.ungroup || "Ungroup")}</button>
        <button type="button" data-layer-command="duplicate">${escapeHtml(i18n.duplicate || "Duplicate")}</button>
        <button type="button" data-layer-command="delete">${escapeHtml(i18n.delete || "Delete")}</button>
        <button type="button" data-layer-command="up">${escapeHtml(i18n.up || "Up")}</button>
        <button type="button" data-layer-command="down">${escapeHtml(i18n.down || "Down")}</button>
      </div>
      <div class="designer-layer-list">
        ${rows.length ? rows.join("") : `<p class="designer-empty-layer">${escapeHtml(i18n.no_layers || "No layers yet")}</p>`}
      </div>
    `;

    layersList.querySelectorAll("[data-layer-command]").forEach((button) => {
      button.addEventListener("click", () => {
        const command = button.dataset.layerCommand || "";
        if (command === "group") groupSelection();
        if (command === "ungroup") ungroupSelection();
        if (command === "duplicate") duplicateSelection();
        if (command === "delete") deleteSelection();
        if (command === "up") reorderSelectionStack(1);
        if (command === "down") reorderSelectionStack(-1);
      });
    });

    layersList.querySelectorAll("[data-layer-pick]").forEach((button) => {
      button.addEventListener("click", (event) => {
        if (event.shiftKey) toggleSelection(button.dataset.layerPick || "");
        else selectOnly(button.dataset.layerPick || "");
        render();
      });
    });
    layersList.querySelectorAll("[data-layer-name]").forEach((input) => {
      input.addEventListener("change", () => {
        renameLayer(input.dataset.layerName || "", input.value);
      });
    });
    layersList.querySelectorAll("[data-layer-toggle]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const target = getLayer(button.dataset.layerId || "");
        if (!target) return;
        target[button.dataset.layerToggle || "hidden"] = !target[button.dataset.layerToggle || "hidden"];
        event.stopPropagation();
        commit();
      });
    });
    layersList.querySelectorAll(".designer-layer-row").forEach((row) => {
      row.addEventListener("dragstart", (event) => {
        layerDragId = row.dataset.layerId || "";
        event.dataTransfer.effectAllowed = "move";
      });
      row.addEventListener("dragover", (event) => {
        event.preventDefault();
        row.classList.add("is-drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("is-drop-target"));
      row.addEventListener("drop", (event) => {
        event.preventDefault();
        row.classList.remove("is-drop-target");
        reorderLayer(layerDragId, row.dataset.layerId || "");
      });
    });
  };

  const layerRow = (layer, depth) => {
    const label = layer.name || layer.text || layer.shape || layer.type || "Layer";
    const type = layer.points ? "vector" : layer.type;
    return `
      <div class="designer-layer-row ${isLayerSelected(layer.id) ? "is-selected" : ""} ${layer.hidden ? "is-hidden" : ""}" draggable="true" data-layer-id="${escapeHtml(layer.id)}" style="--depth:${depth}">
        <button type="button" data-layer-toggle="hidden" data-layer-active="${layer.hidden ? "1" : "0"}" data-layer-id="${escapeHtml(layer.id)}" aria-label="${escapeHtml(i18n.hide || "Hide")}"></button>
        <button type="button" data-layer-toggle="locked" data-layer-active="${layer.locked ? "1" : "0"}" data-layer-id="${escapeHtml(layer.id)}" aria-label="${escapeHtml(i18n.lock || "Lock")}"></button>
        <button type="button" data-layer-pick="${escapeHtml(layer.id)}"><span>${escapeHtml(type)}</span></button>
        <input value="${escapeHtml(label)}" data-layer-name="${escapeHtml(layer.id)}">
      </div>
    `;
  };

  const renderInspector = () => {
    if (!inspector) return;
    const selection = [...selectedIds];
    const canvasLabel = i18n.canvas || "Canvas";
    if (selectionCount) {
      if (!selection.length) selectionCount.textContent = tool === "draw" ? (i18n.pen || "Pen") : canvasLabel;
      else if (selection.length === 1) selectionCount.textContent = (selectedLayer() && (selectedLayer().name || selectedLayer().type)) || "Layer";
      else selectionCount.textContent = `${selection.length} ${i18n.layers || "Layers"}`;
    }
    if (!selection.length) {
      if (tool === "draw") {
        inspector.innerHTML = `
          <section class="designer-inspector-section">
            <span>${escapeHtml(i18n.pen || "Pen")}</span>
            ${colorField("color", i18n.stroke || "Stroke", strokeInput ? strokeInput.value : "#2563eb")}
            ${numberField("width", i18n.brush || "Brush", brushInput ? brushInput.value : 5)}
            <div class="designer-segmented" data-pen-mode-proxy>
              <button class="${penMode === "pen" ? "is-active" : ""}" type="button" data-pen-proxy="pen">${escapeHtml(i18n.pen || "Pen")}</button>
              <button class="${penMode === "marker" ? "is-active" : ""}" type="button" data-pen-proxy="marker">${escapeHtml(i18n.marker || "Marker")}</button>
            </div>
          </section>
        `;
        bindDefaultToolFields();
        return;
      }
      inspector.innerHTML = `
        <section class="designer-inspector-section is-empty">
          <span>${escapeHtml(canvasLabel)}</span>
          <div class="designer-selection-actions">
            <button type="button" data-design-tool-proxy="frame">${escapeHtml(i18n.frame || "Frame")}</button>
            <button type="button" data-design-tool-proxy="text">${escapeHtml(i18n.text || "Text")}</button>
            <button type="button" data-design-tool-proxy="shape-rect">${escapeHtml(i18n.rectangle || "Rectangle")}</button>
            <button type="button" data-design-tool-proxy="draw">${escapeHtml(i18n.pen || "Pen")}</button>
          </div>
        </section>
      `;
      inspector.querySelectorAll("[data-design-tool-proxy]").forEach((button) => {
        button.addEventListener("click", () => {
          const match = tools.find((toolButton) => toolButton.dataset.designTool === button.dataset.designToolProxy);
          if (match) match.click();
        });
      });
      return;
    }
    if (selection.length > 1) {
      inspector.innerHTML = `
        <section class="designer-inspector-section">
          <span>${selection.length} ${escapeHtml(i18n.layers || "Layers")}</span>
          <div class="designer-selection-actions">
            <button type="button" data-design-command="group">${escapeHtml(i18n.group || "Group")}</button>
            <button type="button" data-design-command="align-left">${escapeHtml(i18n.left || "Left")}</button>
            <button type="button" data-design-command="align-center">${escapeHtml(i18n.center || "Center")}</button>
            <button type="button" data-design-command="align-right">${escapeHtml(i18n.right || "Right")}</button>
            <button type="button" data-design-command="align-top">${escapeHtml(i18n.top || "Top")}</button>
            <button type="button" data-design-command="align-middle">${escapeHtml(i18n.middle || "Middle")}</button>
            <button type="button" data-design-command="align-bottom">${escapeHtml(i18n.bottom || "Bottom")}</button>
            <button type="button" data-design-command="distribute-horizontal">${escapeHtml(i18n.distribute || "Distribute")} X</button>
            <button type="button" data-design-command="distribute-vertical">${escapeHtml(i18n.distribute || "Distribute")} Y</button>
            <button type="button" data-design-command="export-png">PNG</button>
            <button type="button" data-design-command="export-svg">SVG</button>
            <button type="button" data-inspect-action="delete">${escapeHtml(i18n.delete || "Delete")}</button>
          </div>
        </section>
      `;
      bindInspectorActions();
      return;
    }
    const object = selectedObject();
    const vector = selectedVector();
    if (object) renderObjectInspector(object);
    if (vector) renderVectorInspector(vector);
  };

  const renderObjectInspector = (object) => {
    const isFrame = object.type === "frame";
    const isText = object.type === "text";
    const isShape = object.type === "shape";
    const isImage = object.type === "image";
    inspector.innerHTML = `
      <section class="designer-inspector-section">
        <span>${escapeHtml(object.type)} · ${escapeHtml(object.name || object.shape || "Layer")}</span>
        <div class="designer-inspector-grid">
          ${numberField("x", "X", object.x)}
          ${numberField("y", "Y", object.y)}
          ${numberField("w", "W", object.w)}
          ${numberField("h", "H", object.h)}
          ${numberField("rotation", i18n.rotation || "Rotate", object.rotation || 0)}
        </div>
        ${rangeField("opacity", i18n.opacity || "Opacity", object.opacity ?? 1, 0, 1, 0.05)}
      </section>
      <section class="designer-inspector-section">
        <span>${escapeHtml(i18n.arrange || "Arrange")}</span>
        <div class="designer-command-grid is-compact">
          <button type="button" data-design-command="align-left">${escapeHtml(i18n.left || "Left")}</button>
          <button type="button" data-design-command="align-center">${escapeHtml(i18n.center || "Center")}</button>
          <button type="button" data-design-command="align-right">${escapeHtml(i18n.right || "Right")}</button>
          <button type="button" data-design-command="align-top">${escapeHtml(i18n.top || "Top")}</button>
          <button type="button" data-design-command="align-middle">${escapeHtml(i18n.middle || "Middle")}</button>
          <button type="button" data-design-command="align-bottom">${escapeHtml(i18n.bottom || "Bottom")}</button>
        </div>
      </section>
      <section class="designer-inspector-section is-style-grid">
        <span>${escapeHtml(i18n.style || "Style")}</span>
        ${!isText ? colorField("fill", i18n.fill || "Fill", object.fill || "#ffffff") : ""}
        ${!isText ? colorField("stroke", i18n.stroke || "Stroke", object.stroke || "#2563eb") : ""}
        ${!isText ? numberField("strokeWidth", i18n.stroke_width || "Stroke width", object.strokeWidth || 2) : ""}
        ${isShape && object.shape === "rect" ? `${numberField("cornerRadius", i18n.radius || "Radius", object.cornerRadius || 10)}` : ""}
      </section>
      ${isText ? textInspectorMarkup(object) : ""}
      ${isImage ? imageInspectorMarkup(object) : ""}
      ${object.parentId ? constraintsMarkup(object) : ""}
      ${isFrame ? frameInspectorMarkup(object) : ""}
    `;
    bindInspectorFields(object);
    bindInspectorActions();
    if (isText) bindTextInspectorActions(object);
  };

  const renderVectorInspector = (vector) => {
    inspector.innerHTML = `
      <section class="designer-inspector-section">
        <span>Vector · ${escapeHtml(vector.name || "Pen")}</span>
        ${colorField("color", i18n.stroke || "Stroke", vector.color || "#2563eb")}
        ${numberField("width", i18n.brush || "Brush", vector.width || 5)}
        ${rangeField("opacity", i18n.opacity || "Opacity", vector.opacity ?? 1, 0, 1, 0.05)}
        <label class="designer-check"><input type="checkbox" data-inspect-field="closed" ${vector.closed ? "checked" : ""}> ${escapeHtml(i18n.close_path || "Close path")}</label>
        <button class="designer-mini-action" type="button" data-inspect-action="vector-edit">${escapeHtml(vectorEdit ? (i18n.done || "Done") : (i18n.edit_points || "Edit points"))}</button>
        <small>${vector.points.length} ${escapeHtml(i18n.points || "points")}</small>
      </section>
    `;
    bindInspectorFields(vector);
    bindInspectorActions();
    const editButton = inspector.querySelector("[data-inspect-action='vector-edit']");
    if (editButton) {
      editButton.addEventListener("click", () => {
        vectorEdit = !vectorEdit;
        if (vectorEdit) ensureVectorHandles(vector);
        render();
      });
    }
  };

  const numberField = (field, label, value) => `
    <label class="designer-field">
      <span>${escapeHtml(label)}</span>
      <input type="number" ${field === "lineHeight" ? 'step="0.05"' : ""} data-inspect-field="${escapeHtml(field)}" value="${field === "lineHeight" ? Number(value || 1.15).toFixed(2) : Math.round(Number(value) || 0)}">
    </label>
  `;

  const rangeField = (field, label, value, min, max, step) => `
    <label class="designer-field">
      <span>${escapeHtml(label)} <output>${Math.round(Number(value) * 100)}%</output></span>
      <input type="range" min="${min}" max="${max}" step="${step}" value="${Number(value)}" data-inspect-field="${escapeHtml(field)}">
    </label>
  `;

  const colorField = (field, label, value) => {
    const fallback = field === "fill" ? "#ffffff" : "#2563eb";
    const normalized = normalizeDesignerColor(value, fallback);
    const nativeColor = safeColor(normalized, fallback);
    const palette = DESIGN_COLOR_PALETTE.map((color) => {
      const picked = normalizeDesignerColor(color, fallback) === normalized;
      const title = color === "transparent" ? (i18n.none || "None") : color.toUpperCase();
      return `<button class="${picked ? "is-active" : ""}" type="button" data-color-preset="${escapeHtml(field)}" data-color-value="${escapeHtml(color)}" style="--swatch:${escapeHtml(color)}" title="${escapeHtml(title)}" aria-label="${escapeHtml(title)}"></button>`;
    }).join("");
    return `
      <label class="designer-field designer-color-field" data-color-field="${escapeHtml(field)}" style="--field-color:${escapeHtml(normalized === "transparent" ? "transparent" : nativeColor)}">
        <span class="designer-color-title">
          <span>${escapeHtml(label)}</span>
          <button type="button" data-color-close title="${escapeHtml(i18n.close || "Close")}" aria-label="${escapeHtml(i18n.close || "Close")}"></button>
        </span>
        <div class="designer-color-control">
          <input class="designer-color-native" type="color" value="${escapeHtml(nativeColor)}" data-inspect-field="${escapeHtml(field)}" data-color-native="true">
          <input class="designer-color-code" type="text" value="${escapeHtml(normalized)}" data-inspect-field="${escapeHtml(field)}" data-color-code="true" spellcheck="false" inputmode="text">
        </div>
        <div class="designer-color-palette">${palette}</div>
      </label>
    `;
  };

  const syncInspectorColorControls = (field, value) => {
    const normalized = normalizeDesignerColor(value, field === "fill" ? "#ffffff" : "#2563eb");
    const nativeColor = safeColor(normalized, field === "fill" ? "#ffffff" : "#2563eb");
    inspector.querySelectorAll(`[data-color-field="${field}"]`).forEach((control) => {
      control.style.setProperty("--field-color", normalized === "transparent" ? "transparent" : nativeColor);
      const native = control.querySelector("[data-color-native]");
      const code = control.querySelector("[data-color-code]");
      if (native) native.value = nativeColor;
      if (code) code.value = normalized;
      control.querySelectorAll("[data-color-value]").forEach((button) => {
        button.classList.toggle("is-active", normalizeDesignerColor(button.dataset.colorValue || "", nativeColor) === normalized);
      });
    });
  };

  const bindColorPalettes = (onPick) => {
    inspector.querySelectorAll("[data-color-close]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const field = button.closest(".designer-color-field");
        if (field) field.classList.add("is-palette-closed");
        event.preventDefault();
        event.stopPropagation();
      });
    });
    inspector.querySelectorAll(".designer-color-control").forEach((control) => {
      control.addEventListener("click", () => {
        const field = control.closest(".designer-color-field");
        if (field) field.classList.remove("is-palette-closed");
      });
    });
    inspector.querySelectorAll("[data-color-preset]").forEach((button) => {
      button.addEventListener("click", () => {
        const field = button.dataset.colorPreset || "";
        const value = normalizeDesignerColor(button.dataset.colorValue || "", field === "fill" ? "#ffffff" : "#2563eb");
        syncInspectorColorControls(field, value);
        onPick(field, value);
      });
    });
  };

  const bindDefaultToolFields = () => {
    inspector.querySelectorAll("[data-inspect-field]").forEach((input) => {
      input.addEventListener(input.type === "range" || input.type === "color" ? "input" : "change", () => {
        const field = input.dataset.inspectField || "";
        if (field === "color" && strokeInput) {
          const value = normalizeDesignerColor(input.value, strokeInput.value || "#2563eb");
          strokeInput.value = safeColor(value, strokeInput.value || "#2563eb");
          syncInspectorColorControls(field, value);
        }
        if (field === "width" && brushInput && brushValue) {
          brushInput.value = String(clamp(Number(input.value) || 5, Number(brushInput.min || 1), Number(brushInput.max || 80)));
          brushValue.textContent = `${brushInput.value} px`;
        }
      });
    });
    bindColorPalettes((field, value) => {
      if (field === "color" && strokeInput) strokeInput.value = safeColor(value, strokeInput.value || "#2563eb");
    });
    inspector.querySelectorAll("[data-pen-proxy]").forEach((button) => {
      button.addEventListener("click", () => {
        const mode = button.dataset.penProxy || "pen";
        const source = penModeButtons.find((item) => item.dataset.penMode === mode);
        if (source) source.click();
        renderInspector();
      });
    });
  };

  const bindInspectorActions = () => {
    inspector.querySelectorAll("[data-design-command]").forEach((button) => {
      button.addEventListener("click", () => runDesignCommand(button.dataset.designCommand || ""));
    });
    inspector.querySelectorAll("[data-inspect-action]").forEach((button) => {
      button.addEventListener("click", () => {
        const action = button.dataset.inspectAction || "";
        if (action === "duplicate") duplicateSelection();
        if (action === "delete") deleteSelection();
        if (action === "replace-image") replaceImageLayer(selectedObject());
        if (action === "crop-image") {
          const object = selectedObject();
          if (object && object.type === "image") {
            if (cropEditId === object.id) stopImageCrop();
            else startImageCrop(object);
          }
        }
        if (action === "reset-crop") resetImageCrop(selectedObject());
        if (action === "detach-frame") {
          const object = selectedObject();
          if (object) {
            object.parentId = "";
            commit();
          }
        }
      });
    });
    inspector.querySelectorAll("[data-image-fit]").forEach((button) => {
      button.addEventListener("click", () => setImageFit(selectedObject(), button.dataset.imageFit || "fill"));
    });
  };

  const frameInspectorMarkup = (frame) => `
    <section class="designer-inspector-section">
      <span>${escapeHtml(i18n.frame || "Frame")}</span>
      <label class="designer-check"><input type="checkbox" data-inspect-field="clipContent" ${frame.clipContent ? "checked" : ""}> ${escapeHtml(i18n.clip_content || "Clip content")}</label>
      <label class="designer-field">
        <span>${escapeHtml(i18n.auto_layout || "Auto layout")}</span>
        <select data-inspect-field="layoutMode">
          ${selectOption("off", i18n.off || "Off", frame.layoutMode)}
          ${selectOption("vertical", i18n.vertical || "Vertical", frame.layoutMode)}
          ${selectOption("horizontal", i18n.horizontal || "Horizontal", frame.layoutMode)}
        </select>
      </label>
      <div class="designer-inspector-grid">
        ${numberField("gap", i18n.gap || "Gap", frame.gap || 12)}
        ${numberField("padding", i18n.padding || "Padding", frame.padding || 16)}
      </div>
      <label class="designer-field">
        <span>${escapeHtml(i18n.align || "Align")}</span>
        <select data-inspect-field="align">
          ${selectOption("start", i18n.start || "Start", frame.align)}
          ${selectOption("center", i18n.center || "Center", frame.align)}
          ${selectOption("end", i18n.end || "End", frame.align)}
          ${selectOption("stretch", i18n.stretch || "Stretch", frame.align)}
        </select>
      </label>
    </section>
  `;

  const imageInspectorMarkup = (object) => `
    <section class="designer-inspector-section">
      <span>${escapeHtml(i18n.image || "Image")}</span>
      <div class="designer-segmented is-grid">
        ${["fill", "fit", "crop", "original"].map((fit) => `<button class="${object.imageFit === fit ? "is-active" : ""}" type="button" data-image-fit="${fit}">${escapeHtml(fit === "original" ? "1:1" : fit[0].toUpperCase() + fit.slice(1))}</button>`).join("")}
      </div>
      <div class="designer-selection-actions">
        <button type="button" data-inspect-action="replace-image">${escapeHtml(i18n.replace || "Replace")}</button>
        <button type="button" data-inspect-action="crop-image">${escapeHtml(cropEditId === object.id ? (i18n.done || "Done") : (i18n.crop || "Crop"))}</button>
        <button type="button" data-inspect-action="reset-crop">${escapeHtml(i18n.reset || "Reset")}</button>
        ${object.parentId ? `<button type="button" data-inspect-action="detach-frame">${escapeHtml(i18n.detach || "Detach")}</button>` : ""}
      </div>
      <small>${Math.round(Number(object.naturalW || 0))} x ${Math.round(Number(object.naturalH || 0))}</small>
    </section>
  `;

  const textInspectorMarkup = (object) => `
    <section class="designer-inspector-section is-text-tools">
      <span>${escapeHtml(i18n.text || "Text")}</span>
      <label class="designer-field">
        <span>${escapeHtml(i18n.font || "Font")}</span>
        <select data-inspect-field="fontFamily">
          ${selectOption("Arial, sans-serif", "Arial", object.fontFamily)}
          ${selectOption("Inter, Arial, sans-serif", "Inter", object.fontFamily)}
          ${selectOption("Georgia, serif", "Georgia", object.fontFamily)}
          ${selectOption("'Times New Roman', serif", "Times", object.fontFamily)}
          ${selectOption("'Courier New', monospace", "Mono", object.fontFamily)}
          ${selectOption("Impact, Haettenschweiler, sans-serif", "Impact", object.fontFamily)}
        </select>
      </label>
      <div class="designer-inspector-grid">
        ${numberField("fontSize", i18n.font_size || "Size", object.fontSize || 22)}
        ${numberField("fontWeight", i18n.weight || "Weight", object.fontWeight || 800)}
        ${numberField("lineHeight", i18n.line_height || "Line", object.lineHeight || 1.15)}
        ${numberField("letterSpacing", i18n.spacing || "Space", object.letterSpacing || 0)}
      </div>
      <div class="designer-icon-segment" aria-label="${escapeHtml(i18n.align || "Align")}">
        <button class="${object.textAlign === "left" ? "is-active" : ""}" type="button" data-text-align="left" data-align-icon="left" title="${escapeHtml(i18n.left || "Left")}"></button>
        <button class="${object.textAlign === "center" ? "is-active" : ""}" type="button" data-text-align="center" data-align-icon="center" title="${escapeHtml(i18n.center || "Center")}"></button>
        <button class="${object.textAlign === "right" ? "is-active" : ""}" type="button" data-text-align="right" data-align-icon="right" title="${escapeHtml(i18n.right || "Right")}"></button>
      </div>
      ${colorField("stroke", i18n.text_color || "Text color", object.stroke || "#2563eb")}
      ${colorField("fill", i18n.background || "Background", object.fill || "transparent")}
      ${colorField("textStroke", i18n.outline || "Outline", object.textStroke || "transparent")}
      ${numberField("textStrokeWidth", i18n.outline_size || "Outline size", object.textStrokeWidth || 0)}
    </section>
    <section class="designer-inspector-section is-text-tools">
      <span>${escapeHtml(i18n.gradient || "Gradient")}</span>
      <label class="designer-check"><input type="checkbox" data-inspect-field="textGradient" ${object.textGradient ? "checked" : ""}> ${escapeHtml(i18n.enable || "Enable")}</label>
      ${colorField("gradientStart", i18n.start || "Start", object.gradientStart || object.stroke || "#2563eb")}
      ${colorField("gradientEnd", i18n.end || "End", object.gradientEnd || "#ec4899")}
    </section>
  `;

  const bindTextInspectorActions = (object) => {
    inspector.querySelectorAll("[data-text-align]").forEach((button) => {
      button.addEventListener("click", () => {
        object.textAlign = button.dataset.textAlign || "left";
        commit();
      });
    });
  };

  const constraintsMarkup = (object) => `
    <section class="designer-inspector-section">
      <span>${escapeHtml(i18n.constraints || "Constraints")}</span>
      <label class="designer-field">
        <span>${escapeHtml(i18n.horizontal || "Horizontal")}</span>
        <select data-inspect-field="constraintH">
          ${selectOption("left", i18n.left || "Left", object.constraints && object.constraints.h)}
          ${selectOption("right", i18n.right || "Right", object.constraints && object.constraints.h)}
          ${selectOption("leftRight", i18n.left_right || "Left & right", object.constraints && object.constraints.h)}
          ${selectOption("center", i18n.center || "Center", object.constraints && object.constraints.h)}
        </select>
      </label>
      <label class="designer-field">
        <span>${escapeHtml(i18n.vertical || "Vertical")}</span>
        <select data-inspect-field="constraintV">
          ${selectOption("top", i18n.top || "Top", object.constraints && object.constraints.v)}
          ${selectOption("bottom", i18n.bottom || "Bottom", object.constraints && object.constraints.v)}
          ${selectOption("topBottom", i18n.top_bottom || "Top & bottom", object.constraints && object.constraints.v)}
          ${selectOption("center", i18n.center || "Center", object.constraints && object.constraints.v)}
        </select>
      </label>
    </section>
  `;

  const selectOption = (value, label, selected) => `<option value="${escapeHtml(value)}" ${selected === value ? "selected" : ""}>${escapeHtml(label)}</option>`;

  const bindInspectorFields = (target) => {
    inspector.querySelectorAll("[data-inspect-field]").forEach((input) => {
      const update = () => {
        const field = input.dataset.inspectField || "";
        const oldFrame = target.type === "frame" ? cloneDesignObject(target) : null;
        const childSnapshots = target.type === "frame" ? childSnapshotsForFrame(target) : [];
        const value = input.type === "checkbox" ? input.checked : input.value;
        if (["x", "y", "w", "h", "fontSize", "cornerRadius", "gap", "padding", "width"].includes(field)) {
          target[field] = field === "w" || field === "h" ? Math.max(8, snap(Number(value) || 0)) : Number(value) || 0;
          if (field === "width" && target.points && brushInput && brushValue) {
            brushInput.value = String(clamp(Number(value) || 1, Number(brushInput.min || 1), Number(brushInput.max || 80)));
            brushValue.textContent = `${brushInput.value} px`;
          }
        } else if (["fontWeight", "letterSpacing", "textStrokeWidth"].includes(field)) {
          target[field] = Math.max(0, Number(value) || 0);
        } else if (field === "lineHeight") {
          target.lineHeight = clamp(Number(value) || 1.15, 0.8, 3);
        } else if (field === "fontFamily") {
          target.fontFamily = value || "Arial, sans-serif";
        } else if (field === "rotation") {
          target.rotation = normalizeAngle(Number(value) || 0);
        } else if (["fill", "stroke", "color", "textStroke", "gradientStart", "gradientEnd"].includes(field)) {
          const colorValue = normalizeDesignerColor(value, target[field] || (field === "fill" ? "#ffffff" : "#2563eb"));
          target[field] = colorValue;
          if (field === "fill" && fillInput) fillInput.value = safeColor(colorValue, fillInput.value || "#ffffff");
          if ((field === "stroke" || field === "color") && strokeInput) strokeInput.value = safeColor(colorValue, strokeInput.value || "#2563eb");
          syncInspectorColorControls(field, colorValue);
        } else if (field === "strokeWidth") {
          target.strokeWidth = Math.max(0, Number(value) || 0);
        } else if (field === "opacity") {
          target.opacity = clamp(Number(value), 0, 1);
        } else if (field === "clipContent" || field === "closed" || field === "textGradient") {
          target[field] = Boolean(value);
        } else if (field === "layoutMode" || field === "align") {
          target[field] = value;
        } else if (field === "constraintH") {
          target.constraints = { ...(target.constraints || {}), h: value };
        } else if (field === "constraintV") {
          target.constraints = { ...(target.constraints || {}), v: value };
        }
        if (target.type === "frame" && oldFrame) applyResizeChildren(target, oldFrame, childSnapshots);
        if (target.type === "frame") applyAutoLayout(target);
        commit();
      };
      input.addEventListener(input.type === "range" || input.type === "color" ? "input" : "change", update);
    });
    bindColorPalettes((field, value) => {
      if (!["fill", "stroke", "color", "textStroke", "gradientStart", "gradientEnd"].includes(field)) return;
      const colorValue = normalizeDesignerColor(value, target[field] || (field === "fill" ? "#ffffff" : "#2563eb"));
      target[field] = colorValue;
      if (field === "fill" && fillInput) fillInput.value = safeColor(colorValue, fillInput.value || "#ffffff");
      if ((field === "stroke" || field === "color") && strokeInput) strokeInput.value = safeColor(colorValue, strokeInput.value || "#2563eb");
      syncInspectorColorControls(field, colorValue);
      commit();
    });
  };

  const syncColorInputs = () => {
    const layer = selectedLayer();
    if (!layer) return;
    if (fillInput && layer.fill) fillInput.value = safeColor(layer.fill, fillInput.value);
    if (strokeInput) strokeInput.value = safeColor(layer.stroke || layer.color || "#2563eb", strokeInput.value);
  };

  const getLayer = (id) => objectById(id) || vectorById(id);

  const renameLayer = (id, name) => {
    const target = getLayer(id);
    if (!target) return;
    target.name = name.trim() || target.type || "Layer";
    commit();
  };

  const reorderLayer = (dragId, targetId) => {
    if (!dragId || !targetId || dragId === targetId) return;
    const draggedObject = objectById(dragId);
    const targetObject = objectById(targetId);
    const draggedVector = vectorById(dragId);
    const targetLayer = getLayer(targetId);
    if (!targetLayer || (targetObject && isDescendantObject(targetObject.id, dragId))) return;
    const nextParent = targetObject && targetObject.type === "frame" ? targetObject.id : (targetLayer.parentId || "");
    if (draggedObject) {
      draggedObject.parentId = nextParent;
      state.objects = state.objects.filter((item) => item.id !== dragId);
      const index = Math.max(0, state.objects.findIndex((item) => item.id === targetId));
      state.objects.splice(index === -1 ? state.objects.length : index, 0, draggedObject);
    }
    if (draggedVector) draggedVector.parentId = nextParent;
    layerDragId = "";
    commit();
  };

  const reorderSelectionStack = (direction) => {
    if (!selectedIds.size) return;
    const moveInStack = (items) => {
      const next = [...items];
      const indexes = next
        .map((item, index) => selectedIds.has(item.id) ? index : -1)
        .filter((index) => index >= 0);
      const ordered = direction > 0 ? indexes.slice().reverse() : indexes;
      ordered.forEach((index) => {
        const targetIndex = index + direction;
        if (targetIndex < 0 || targetIndex >= next.length || selectedIds.has(next[targetIndex].id)) return;
        [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      });
      return next;
    };
    state.objects = moveInStack(objects());
    state.vectors = moveInStack(vectors());
    commit();
  };

  const renderMarquee = () => {
    plane.querySelectorAll(".design-marquee").forEach((item) => item.remove());
    if (!marqueeState) return;
    const x = Math.min(marqueeState.startX, marqueeState.currentX);
    const y = Math.min(marqueeState.startY, marqueeState.currentY);
    const w = Math.abs(marqueeState.currentX - marqueeState.startX);
    const h = Math.abs(marqueeState.currentY - marqueeState.startY);
    const element = document.createElement("div");
    element.className = "design-marquee";
    element.style.left = `${x}px`;
    element.style.top = `${y}px`;
    element.style.width = `${w}px`;
    element.style.height = `${h}px`;
    plane.appendChild(element);
  };

  const renderGuides = (guides = []) => {
    plane.querySelectorAll(".design-guide").forEach((item) => item.remove());
    guides.forEach((guide) => {
      const element = document.createElement("div");
      element.className = `design-guide is-${guide.axis}`;
      if (guide.axis === "x") element.style.left = `${guide.value}px`;
      if (guide.axis === "y") element.style.top = `${guide.value}px`;
      plane.appendChild(element);
    });
  };

  const setTargetFrame = (id = "") => {
    if (targetFrameId === id) return;
    const previous = targetFrameId;
    targetFrameId = id || "";
    if (previous) {
      const element = plane.querySelector(`[data-design-id="${cssEscape(previous)}"]`);
      if (element) element.classList.remove("is-drop-target");
    }
    if (targetFrameId) {
      const element = plane.querySelector(`[data-design-id="${cssEscape(targetFrameId)}"]`);
      if (element) element.classList.add("is-drop-target");
    }
  };

  const updateImageElement = (object) => {
    if (!object || object.type !== "image") return;
    const image = plane.querySelector(`[data-design-id="${cssEscape(object.id)}"] .design-image-content`);
    if (!image) return;
    const placement = imagePlacementForObject(object);
    image.style.left = `${placement.x}px`;
    image.style.top = `${placement.y}px`;
    image.style.width = `${placement.w}px`;
    image.style.height = `${placement.h}px`;
  };

  const smartSnapObject = (object, ignoreIds = selectedIds) => {
    const guides = [];
    const candidates = objects().filter((item) => !ignoreIds.has(item.id) && !item.hidden);
    const threshold = 6;
    const movingX = [object.x, object.x + object.w / 2, object.x + object.w];
    const movingY = [object.y, object.y + object.h / 2, object.y + object.h];
    candidates.forEach((candidate) => {
      const candidateX = [candidate.x, candidate.x + candidate.w / 2, candidate.x + candidate.w];
      const candidateY = [candidate.y, candidate.y + candidate.h / 2, candidate.y + candidate.h];
      movingX.forEach((value, index) => {
        candidateX.forEach((target) => {
          if (Math.abs(value - target) <= threshold) {
            object.x += target - value;
            movingX[index] = target;
            guides.push({ axis: "x", value: target });
          }
        });
      });
      movingY.forEach((value, index) => {
        candidateY.forEach((target) => {
          if (Math.abs(value - target) <= threshold) {
            object.y += target - value;
            movingY[index] = target;
            guides.push({ axis: "y", value: target });
          }
        });
      });
    });
    return guides.slice(0, 4);
  };

  const viewportCenter = (width = 0, height = 0) => {
    const shellRect = shell.getBoundingClientRect();
    const planeRect = plane.getBoundingClientRect();
    return {
      x: ((shellRect.left + shell.clientWidth / 2 - planeRect.left) / planeRect.width) * DESIGN_WIDTH - width / 2,
      y: ((shellRect.top + shell.clientHeight / 2 - planeRect.top) / planeRect.height) * DESIGN_HEIGHT - height / 2,
    };
  };

  const updateLastCanvasPoint = (event) => {
    const point = stagePoint(event, plane);
    lastCanvasPoint = {
      x: clamp(point.x, 0, planeWidth - 80),
      y: clamp(point.y, 0, planeHeight - 80),
    };
    return lastCanvasPoint;
  };

  const selectedClipboardLayers = () => {
    const objectIds = new Set();
    selectedIds.forEach((id) => {
      const object = objectById(id);
      if (!object) return;
      objectIds.add(id);
      if (object.type === "frame" || object.type === "group") {
        collectDescendantObjectIds(id).forEach((childId) => objectIds.add(childId));
      }
    });
    const vectorIds = new Set([...selectedIds].filter((id) => vectorById(id)));
    vectors().forEach((vector) => {
      if (vector.parentId && objectIds.has(vector.parentId)) vectorIds.add(vector.id);
    });
    return {
      objects: objects().filter((item) => objectIds.has(item.id)).map(cloneDesignObject),
      vectors: vectors().filter((item) => vectorIds.has(item.id)).map(cloneDesignVector),
    };
  };

  const copySelection = () => {
    const payload = selectedClipboardLayers();
    if (!payload.objects.length && !payload.vectors.length) return false;
    const bounds = boundsForLayersV2(payload.objects, payload.vectors);
    designClipboard = { ...payload, bounds };
    return true;
  };

  const pasteDesignClipboardAt = (point = null) => {
    if (!designClipboard || (!designClipboard.objects.length && !designClipboard.vectors.length)) return false;
    const basePoint = point || lastCanvasPoint || viewportCenter(designClipboard.bounds.w, designClipboard.bounds.h);
    const dx = snap(basePoint.x - designClipboard.bounds.x);
    const dy = snap(basePoint.y - designClipboard.bounds.y);
    const idMap = new Map();
    const nextSelection = [];
    designClipboard.objects.forEach((source) => {
      idMap.set(source.id, `object-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    });
    designClipboard.vectors.forEach((source) => {
      idMap.set(source.id, `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`);
    });
    designClipboard.objects.forEach((source) => {
      const copy = cloneDesignObject(source);
      copy.id = idMap.get(source.id);
      copy.x = snap(copy.x + dx);
      copy.y = snap(copy.y + dy);
      copy.parentId = idMap.get(source.parentId) || "";
      state.objects.push(copy);
      nextSelection.push(copy.id);
    });
    designClipboard.vectors.forEach((source) => {
      const copy = cloneDesignVector(source);
      copy.id = idMap.get(source.id);
      copy.parentId = idMap.get(source.parentId) || "";
      copy.points = copy.points.map((item) => moveDesignPoint(item, dx, dy));
      state.vectors.push(copy);
      nextSelection.push(copy.id);
    });
    selectedIds = new Set(nextSelection);
    selectedId = nextSelection[nextSelection.length - 1] || "";
    commit();
    return true;
  };

  const focusTextLayer = (id) => {
    requestAnimationFrame(() => {
      const element = [...plane.querySelectorAll("[data-design-id]")].find((item) => item.dataset.designId === id);
      if (!element || !(element instanceof HTMLElement)) return;
      element.focus({ preventScroll: true });
      const range = document.createRange();
      range.selectNodeContents(element);
      const selection = window.getSelection();
      if (!selection) return;
      selection.removeAllRanges();
      selection.addRange(range);
    });
  };

  const addDesignObject = (type, extra = {}, point = null) => {
    const defaults = objectDefaultsFor(type, extra.shape);
    const object = normalizeDesignObject({
      id: `object-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type,
      ...defaults,
      fill: fillInput ? fillInput.value : defaults.fill,
      stroke: strokeInput ? strokeInput.value : defaults.stroke,
      ...extra,
    });
    const position = point || viewportCenter(object.w, object.h);
    object.x = snap(Number.isFinite(extra.x) ? extra.x : position.x);
    object.y = snap(Number.isFinite(extra.y) ? extra.y : position.y);
    if (object.type !== "frame" && object.type !== "group") {
      if (point) assignParent(object, point);
      else assignParent(object);
    }
    state.objects.push(object);
    const parent = object.parentId ? objectById(object.parentId) : null;
    if (parent) applyAutoLayout(parent);
    selectOnly(object.id);
    setTool("select");
    commit();
    if (object.type === "text") focusTextLayer(object.id);
  };

  const addImageFile = async (file, point = null) => {
    if (readOnly) return;
    if (!file) return;
    if (file.type === "image/svg+xml" || file.name.toLowerCase().endsWith(".svg")) {
      const reader = new FileReader();
      reader.onload = () => addSvgText(String(reader.result || ""), point);
      reader.readAsText(file);
      return;
    }
    if (!String(file.type || "").startsWith("image/")) return;
    try {
      const asset = await uploadDesignAsset(file);
      addImageSource(asset.preview_url, point, { assetId: asset.id, name: asset.name || file.name || "Image" });
    } catch {
      const reader = new FileReader();
      reader.onload = () => addImageSource(String(reader.result || ""), point, { name: file.name || "Image" });
      reader.readAsDataURL(file);
    }
  };

  const addImageSource = (src, point = null, extra = {}) => {
    const image = new Image();
    image.onload = () => {
      const maxWidth = 620;
      const maxHeight = 460;
      const ratio = Math.min(1, maxWidth / image.naturalWidth, maxHeight / image.naturalHeight);
      addDesignObject("image", {
        src,
        w: Math.max(120, Math.round(image.naturalWidth * ratio)),
        h: Math.max(90, Math.round(image.naturalHeight * ratio)),
        naturalW: image.naturalWidth,
        naturalH: image.naturalHeight,
        imageFit: "fill",
        name: "Image",
        ...extra,
      }, point ? { x: point.x, y: point.y } : null);
    };
    image.src = src;
  };

  const addSvgText = (svgText, point = null) => {
    const src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svgText)}`;
    addImageSource(src, point);
  };

  const addTextLayer = (text, point = null) => {
    addDesignObject("text", {
      text: text.trim().slice(0, 2000) || i18n.canvas_text || "Text",
      name: text.trim().slice(0, 28) || "Text",
    }, point);
  };

  const startImageCrop = (object) => {
    if (!object || object.type !== "image") return;
    ensureImageCropFromFit(object);
    object.imageFit = "crop";
    cropEditId = object.id;
    selectOnly(object.id);
    persist();
    render();
  };

  const stopImageCrop = () => {
    cropEditId = "";
    render();
  };

  const setImageFit = (object, fit) => {
    if (!object || object.type !== "image") return;
    const nextFit = ["fill", "fit", "crop", "original"].includes(fit) ? fit : "fill";
    if (nextFit === "crop") ensureImageCropFromFit(object);
    if (nextFit === "original") {
      object.imageCrop = {
        x: Math.round((object.w - Math.max(1, Number(object.naturalW || object.w))) / 2),
        y: Math.round((object.h - Math.max(1, Number(object.naturalH || object.h))) / 2),
        scale: 1,
      };
    }
    object.imageFit = nextFit;
    cropEditId = nextFit === "crop" ? object.id : "";
    commit();
  };

  const resetImageCrop = (object) => {
    if (!object || object.type !== "image") return;
    object.imageFit = "fill";
    object.imageCrop = { x: 0, y: 0, scale: 1 };
    cropEditId = "";
    commit();
  };

  const replaceImageLayer = (object) => {
    if (!object || object.type !== "image") return;
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      if (!file || !String(file.type || "").startsWith("image/")) return;
      const applySource = (src, asset = null) => {
        const image = new Image();
        image.onload = () => {
          object.src = src;
          if (asset) {
            object.assetId = asset.id;
            object.name = asset.name || object.name;
          }
          object.naturalW = image.naturalWidth;
          object.naturalH = image.naturalHeight;
          resetImageCrop(object);
        };
        image.src = src;
      };
      try {
        const asset = await uploadDesignAsset(file);
        applySource(asset.preview_url, asset);
      } catch {
        const reader = new FileReader();
        reader.onload = () => applySource(String(reader.result || ""));
        reader.readAsDataURL(file);
      }
    }, { once: true });
    input.click();
  };

  const contextMenu = document.createElement("div");
  contextMenu.className = "designer-context-menu";
  contextMenu.hidden = true;
  contextMenu.innerHTML = `
    <button type="button" data-designer-context-action="paste">
      <b>${escapeHtml(i18n.paste || "Paste")}</b>
      <span>${escapeHtml(i18n.clipboard || "Text, image or SVG")}</span>
    </button>
    <hr>
    <button type="button" data-designer-context-action="copy">
      <b>${escapeHtml(i18n.copy || "Copy")}</b>
      <span>Ctrl C</span>
    </button>
    <button type="button" data-designer-context-action="duplicate">
      <b>${escapeHtml(i18n.duplicate || "Duplicate")}</b>
      <span>Ctrl D</span>
    </button>
    <button type="button" data-designer-context-action="delete">
      <b>${escapeHtml(i18n.delete || "Delete")}</b>
      <span>Del</span>
    </button>
    <hr data-image-context>
    <button type="button" data-image-context data-designer-context-action="crop-image">
      <b>${escapeHtml(i18n.crop || "Crop")}</b>
      <span>${escapeHtml(i18n.image || "Image")}</span>
    </button>
    <button type="button" data-image-context data-designer-context-action="reset-crop">
      <b>${escapeHtml(i18n.reset || "Reset")}</b>
      <span>${escapeHtml(i18n.crop || "Crop")}</span>
    </button>
    <button type="button" data-image-context data-designer-context-action="replace-image">
      <b>${escapeHtml(i18n.replace || "Replace")}</b>
      <span>${escapeHtml(i18n.image || "Image")}</span>
    </button>
    <button type="button" data-image-context data-designer-context-action="detach-frame">
      <b>${escapeHtml(i18n.detach || "Detach")}</b>
      <span>${escapeHtml(i18n.frame || "Frame")}</span>
    </button>
    <small data-designer-context-status></small>
  `;
  document.body.appendChild(contextMenu);
  const contextStatus = contextMenu.querySelector("[data-designer-context-status]");

  const hideContextMenu = () => {
    contextMenu.hidden = true;
    if (contextStatus) contextStatus.textContent = "";
  };

  const setContextStatus = (message) => {
    if (contextStatus) contextStatus.textContent = message || "";
  };

  const positionContextMenu = (event) => {
    contextMenu.hidden = false;
    contextMenu.style.left = "0px";
    contextMenu.style.top = "0px";
    const rect = contextMenu.getBoundingClientRect();
    const left = clamp(event.clientX, 8, window.innerWidth - rect.width - 8);
    const top = clamp(event.clientY, 8, window.innerHeight - rect.height - 8);
    contextMenu.style.left = `${left}px`;
    contextMenu.style.top = `${top}px`;
  };

  const pointFromContextEvent = (event) => {
    return updateLastCanvasPoint(event);
  };

  const pasteClipboardAt = async (point) => {
    if (pasteDesignClipboardAt(point)) return;
    const basePoint = point || viewportCenter(260, 160);
    let pasted = false;
    let offset = 0;
    const nextPoint = () => {
      const step = offset++;
      return { x: basePoint.x + step * 28, y: basePoint.y + step * 28 };
    };
    setContextStatus(i18n.loading || "Reading clipboard...");

    const pasteText = (text) => {
      const clean = String(text || "").trim();
      if (!clean) return false;
      if (clean.startsWith("<svg")) addSvgText(clean, nextPoint());
      else addTextLayer(clean, nextPoint());
      return true;
    };

    try {
      if (navigator.clipboard && navigator.clipboard.read) {
        const items = await navigator.clipboard.read();
        for (const item of items) {
          const imageType = item.types.find((type) => type.startsWith("image/"));
          if (imageType) {
            const blob = await item.getType(imageType);
            const extension = imageType.split("/")[1] || "png";
            addImageFile(new File([blob], `clipboard.${extension}`, { type: imageType }), nextPoint());
            pasted = true;
            continue;
          }
          const svgType = item.types.find((type) => type.includes("svg"));
          if (svgType) {
            const blob = await item.getType(svgType);
            const text = await blob.text();
            if (pasteText(text)) pasted = true;
            continue;
          }
          const htmlType = item.types.find((type) => type === "text/html");
          if (htmlType) {
            const html = await (await item.getType(htmlType)).text();
            const svgMatch = html.match(/<svg[\s\S]*<\/svg>/i);
            if (svgMatch && pasteText(svgMatch[0])) {
              pasted = true;
              continue;
            }
          }
          const textType = item.types.find((type) => type === "text/plain");
          if (textType) {
            const text = await (await item.getType(textType)).text();
            if (pasteText(text)) pasted = true;
          }
        }
      }
      if (!pasted && navigator.clipboard && navigator.clipboard.readText) {
        pasted = pasteText(await navigator.clipboard.readText());
      }
    } catch {
      try {
        if (navigator.clipboard && navigator.clipboard.readText) {
          pasted = pasteText(await navigator.clipboard.readText());
        }
      } catch {
        pasted = false;
      }
    }

    if (pasted) {
      hideContextMenu();
      return;
    }
    setContextStatus(i18n.clipboard_empty || "Clipboard is empty or blocked");
  };

  const assignParent = (layer, anchorPoint = null) => {
    const box = layer.points ? vectorBoundsV2(layer) : layer;
    const center = anchorPoint || { x: box.x + box.w / 2, y: box.y + box.h / 2 };
    const parent = findTopFrameAt(center.x, center.y, layer.id);
    layer.parentId = parent ? parent.id : "";
    if (parent && !layer.constraints) layer.constraints = { h: "left", v: "top" };
  };

  const applyAutoLayout = (frame) => {
    if (!frame || frame.type !== "frame" || frame.layoutMode === "off") return;
    const children = objects().filter((item) => item.parentId === frame.id && !item.hidden && !item.locked);
    const padding = Number(frame.padding || 0);
    const gap = Number(frame.gap || 0);
    let cursor = padding;
    children.forEach((child) => {
      if (frame.layoutMode === "vertical") {
        child.y = frame.y + cursor;
        if (frame.align === "center") child.x = frame.x + frame.w / 2 - child.w / 2;
        else if (frame.align === "end") child.x = frame.x + frame.w - padding - child.w;
        else child.x = frame.x + padding;
        if (frame.align === "stretch") {
          child.x = frame.x + padding;
          child.w = Math.max(24, frame.w - padding * 2);
        }
        cursor += child.h + gap;
      } else if (frame.layoutMode === "horizontal") {
        child.x = frame.x + cursor;
        if (frame.align === "center") child.y = frame.y + frame.h / 2 - child.h / 2;
        else if (frame.align === "end") child.y = frame.y + frame.h - padding - child.h;
        else child.y = frame.y + padding;
        if (frame.align === "stretch") {
          child.y = frame.y + padding;
          child.h = Math.max(24, frame.h - padding * 2);
        }
        cursor += child.w + gap;
      }
      child.x = snap(child.x);
      child.y = snap(child.y);
    });
  };

  const childSnapshotsForFrame = (frame) => {
    if (!frame || frame.type !== "frame") return [];
    return [
      ...objects().filter((item) => item.parentId === frame.id).map((item) => ({ kind: "object", id: item.id, object: cloneDesignObject(item) })),
      ...vectors().filter((item) => item.parentId === frame.id).map((item) => ({ kind: "vector", id: item.id, vector: cloneDesignVector(item) })),
    ];
  };

  const applyResizeChildren = (frame, oldFrame, childSnapshots) => {
    if (!frame || frame.type !== "frame" || frame.layoutMode !== "off") return;
    const nextBoxFor = (source, constraints) => {
      const left = source.x - oldFrame.x;
      const right = oldFrame.x + oldFrame.w - (source.x + source.w);
      const top = source.y - oldFrame.y;
      const bottom = oldFrame.y + oldFrame.h - (source.y + source.h);
      const next = { x: source.x, y: source.y, w: source.w, h: source.h };
      if (constraints.h === "right") next.x = frame.x + frame.w - right - next.w;
      else if (constraints.h === "leftRight") {
        next.x = frame.x + left;
        next.w = Math.max(24, frame.w - left - right);
      } else if (constraints.h === "center") next.x = frame.x + frame.w / 2 - next.w / 2;
      else next.x = frame.x + left;
      if (constraints.v === "bottom") next.y = frame.y + frame.h - bottom - next.h;
      else if (constraints.v === "topBottom") {
        next.y = frame.y + top;
        next.h = Math.max(24, frame.h - top - bottom);
      } else if (constraints.v === "center") next.y = frame.y + frame.h / 2 - next.h / 2;
      else next.y = frame.y + top;
      return next;
    };
    childSnapshots.forEach((snapshot) => {
      if (snapshot.kind === "object") {
        const child = objectById(snapshot.id);
        if (!child || child.locked) return;
        const source = snapshot.object;
        const next = nextBoxFor(source, source.constraints || { h: "left", v: "top" });
        child.x = snap(next.x);
        child.y = snap(next.y);
        child.w = snap(next.w);
        child.h = snap(next.h);
        return;
      }
      if (snapshot.kind === "vector") {
        const vector = vectorById(snapshot.id);
        if (!vector || vector.locked) return;
        const sourceVector = snapshot.vector;
        const sourceBox = vectorBoundsV2(sourceVector);
        const next = nextBoxFor({ ...sourceBox, constraints: sourceVector.constraints }, sourceVector.constraints || { h: "left", v: "top" });
        const scaleX = sourceBox.w ? next.w / sourceBox.w : 1;
        const scaleY = sourceBox.h ? next.h / sourceBox.h : 1;
        const transformPoint = (point) => ({
          ...point,
          x: next.x + (point.x - sourceBox.x) * scaleX,
          y: next.y + (point.y - sourceBox.y) * scaleY,
          in: point.in ? { x: next.x + (point.in.x - sourceBox.x) * scaleX, y: next.y + (point.in.y - sourceBox.y) * scaleY } : null,
          out: point.out ? { x: next.x + (point.out.x - sourceBox.x) * scaleX, y: next.y + (point.out.y - sourceBox.y) * scaleY } : null,
        });
        vector.points = sourceVector.points.map(transformPoint);
      }
    });
  };

  const findTopFrameAt = (x, y, ignoreId = "") => {
    return objects().slice().reverse().find((item) => item.type === "frame" && item.id !== ignoreId && !item.hidden && !isDescendantObject(item.id, ignoreId) && x >= item.x && x <= item.x + item.w && y >= item.y && y <= item.y + item.h);
  };

  const collectDescendantObjectIds = (parentId) => {
    const found = [];
    objects().filter((item) => item.parentId === parentId).forEach((child) => {
      found.push(child.id);
      found.push(...collectDescendantObjectIds(child.id));
    });
    return found;
  };

  const isDescendantObject = (id, parentId) => {
    let current = objectById(id);
    while (current && current.parentId) {
      if (current.parentId === parentId) return true;
      current = objectById(current.parentId);
    }
    return false;
  };

  const deleteSelection = () => {
    const objectIds = new Set(selectedIds);
    selectedIds.forEach((id) => collectDescendantObjectIds(id).forEach((childId) => objectIds.add(childId)));
    state.objects = objects().filter((item) => !objectIds.has(item.id));
    state.vectors = vectors().filter((item) => !selectedIds.has(item.id) && !objectIds.has(item.parentId || ""));
    selectOnly("");
    commit();
  };

  const duplicateSelection = () => {
    const nextSelection = [];
    const idMap = new Map();
    objects().filter((item) => selectedIds.has(item.id)).forEach((object) => {
      const copy = cloneDesignObject(object);
      copy.id = `object-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      copy.x += 32;
      copy.y += 32;
      copy.parentId = object.parentId && selectedIds.has(object.parentId) ? idMap.get(object.parentId) || object.parentId : object.parentId;
      idMap.set(object.id, copy.id);
      state.objects.push(copy);
      nextSelection.push(copy.id);
    });
    vectors().filter((item) => selectedIds.has(item.id)).forEach((vector) => {
      const copy = cloneDesignVector(vector);
      copy.id = `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`;
      copy.points = copy.points.map((point) => moveDesignPoint(point, 32, 32));
      state.vectors.push(copy);
      nextSelection.push(copy.id);
    });
    selectedIds = new Set(nextSelection);
    selectedId = nextSelection[nextSelection.length - 1] || "";
    commit();
  };

  const groupSelection = () => {
    const selectedObjects = objects().filter((item) => selectedIds.has(item.id));
    const selectedVectors = vectors().filter((item) => selectedIds.has(item.id));
    const selectedLayers = [...selectedObjects, ...selectedVectors];
    if (selectedLayers.length < 2) return;
    const box = boundsForLayersV2(selectedObjects, selectedVectors);
    const commonParent = selectedLayers.every((item) => item.parentId === selectedLayers[0].parentId) ? selectedLayers[0].parentId : "";
    const group = normalizeDesignObject({
      id: `object-${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type: "group",
      name: "Group",
      x: box.x,
      y: box.y,
      w: box.w,
      h: box.h,
      parentId: commonParent,
      fill: "transparent",
      stroke: strokeInput ? strokeInput.value : "#2563eb",
      children: selectedLayers.map((item) => item.id),
    });
    selectedObjects.forEach((item) => {
      item.parentId = group.id;
    });
    selectedVectors.forEach((item) => {
      item.parentId = group.id;
    });
    state.objects.push(group);
    selectOnly(group.id);
    commit();
  };

  const ungroupSelection = () => {
    const groups = objects().filter((item) => selectedIds.has(item.id) && item.type === "group");
    if (!groups.length) return;
    groups.forEach((group) => {
      objects().filter((item) => item.parentId === group.id).forEach((child) => {
        child.parentId = group.parentId || "";
      });
      vectors().filter((item) => item.parentId === group.id).forEach((child) => {
        child.parentId = group.parentId || "";
      });
    });
    state.objects = objects().filter((item) => !groups.some((group) => group.id === item.id));
    selectedIds = new Set(groups.flatMap((group) => group.children || []));
    selectedId = selectedIds.values().next().value || "";
    commit();
  };

  const selectedMovableLayers = () => [
    ...objects().filter((item) => selectedIds.has(item.id) && !item.locked && !item.hidden),
    ...vectors().filter((item) => selectedIds.has(item.id) && !item.locked && !item.hidden),
  ];

  const layerBounds = (layer) => layer.points ? vectorBoundsV2(layer) : layer;

  const moveLayerBy = (layer, dx, dy) => {
    if (!dx && !dy) return;
    if (layer.points) {
      layer.points = layer.points.map((point) => moveDesignPoint(point, dx, dy));
      return;
    }
    layer.x = snap(layer.x + dx);
    layer.y = snap(layer.y + dy);
  };

  const alignmentReferenceBounds = (layers) => {
    if (!layers.length) return null;
    if (layers.length > 1) {
      const objectLayers = layers.filter((item) => !item.points);
      const vectorLayers = layers.filter((item) => item.points);
      return boundsForLayersV2(objectLayers, vectorLayers);
    }
    const layer = layers[0];
    const parent = layer.parentId ? objectById(layer.parentId) : null;
    if (parent) return parent;
    return layerBounds(layer);
  };

  const alignSelection = (mode) => {
    const layers = selectedMovableLayers();
    const reference = alignmentReferenceBounds(layers);
    if (!reference) return;
    layers.forEach((layer) => {
      const box = layerBounds(layer);
      let dx = 0;
      let dy = 0;
      if (mode === "left") dx = reference.x - box.x;
      if (mode === "center") dx = reference.x + reference.w / 2 - (box.x + box.w / 2);
      if (mode === "right") dx = reference.x + reference.w - (box.x + box.w);
      if (mode === "top") dy = reference.y - box.y;
      if (mode === "middle") dy = reference.y + reference.h / 2 - (box.y + box.h / 2);
      if (mode === "bottom") dy = reference.y + reference.h - (box.y + box.h);
      moveLayerBy(layer, dx, dy);
    });
    commit();
  };

  const distributeSelection = (axis) => {
    const layers = selectedMovableLayers()
      .map((layer) => ({ layer, box: layerBounds(layer) }))
      .sort((a, b) => axis === "x" ? a.box.x - b.box.x : a.box.y - b.box.y);
    if (layers.length < 3) return;
    const first = layers[0].box;
    const last = layers[layers.length - 1].box;
    const totalSize = layers.reduce((sum, item) => sum + (axis === "x" ? item.box.w : item.box.h), 0);
    const span = axis === "x" ? (last.x + last.w - first.x) : (last.y + last.h - first.y);
    const gap = (span - totalSize) / (layers.length - 1);
    let cursor = axis === "x" ? first.x + first.w + gap : first.y + first.h + gap;
    layers.slice(1, -1).forEach((item) => {
      if (axis === "x") {
        moveLayerBy(item.layer, cursor - item.box.x, 0);
        cursor += item.box.w + gap;
      } else {
        moveLayerBy(item.layer, 0, cursor - item.box.y);
        cursor += item.box.h + gap;
      }
    });
    commit();
  };

  const exportSelection = (format) => {
    const targets = [
      ...objects().filter((item) => selectedIds.has(item.id)),
      ...vectors().filter((item) => selectedIds.has(item.id)),
    ];
    if (!targets.length) return;
    const frameTargets = targets.filter((item) => item.type === "frame" || item.type === "group");
    (frameTargets.length ? frameTargets : targets).forEach((target, index) => exportLayer(target, format, index));
  };

  const exportLayer = (target, format, index = 0) => {
    const svg = buildExportSvgV2(target, state);
    const bounds = target.points ? vectorBoundsV2(target) : target;
    const suffix = index ? `-${index + 1}` : "";
    const fileName = `${cleanFileName(target.name || target.type || "export")}${suffix}`;
    if (format === "svg") {
      downloadBlob(new Blob([svg], { type: "image/svg+xml" }), `${fileName}.svg`);
      return;
    }
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(bounds.w));
      canvas.height = Math.max(1, Math.round(bounds.h));
      const ctx = canvas.getContext("2d");
      ctx.drawImage(image, 0, 0);
      canvas.toBlob((blob) => {
        if (blob) downloadBlob(blob, `${fileName}.png`);
      }, "image/png");
    };
    image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  };

  const runDesignCommand = (command) => {
    if (command === "group") groupSelection();
    if (command === "ungroup") ungroupSelection();
    if (command === "align-left") alignSelection("left");
    if (command === "align-center") alignSelection("center");
    if (command === "align-right") alignSelection("right");
    if (command === "align-top") alignSelection("top");
    if (command === "align-middle") alignSelection("middle");
    if (command === "align-bottom") alignSelection("bottom");
    if (command === "distribute-horizontal") distributeSelection("x");
    if (command === "distribute-vertical") distributeSelection("y");
    if (command === "export-svg") exportSelection("svg");
    if (command === "export-png") exportSelection("png");
  };

  tools.forEach((button) => {
    button.addEventListener("click", () => {
      const nextTool = button.dataset.designTool || "select";
      setTool(nextTool);
    });
  });

  plane.addEventListener("pointerdown", (event) => {
    const isEmptyCanvasTarget = event.target === plane || event.target === vectorLayer;
    if (!isEmptyCanvasTarget && tool === "select") return;
    if (spaceDown || event.button === 1) return;
    if (event.button !== 0) return;
    if (["frame", "text", "shape-rect", "shape-ellipse", "shape-line", "shape-arrow"].includes(tool)) {
      const point = stagePoint(event, plane);
      if (tool === "frame") addDesignObject("frame", {}, point);
      if (tool === "text") addDesignObject("text", {}, point);
      if (tool === "shape-rect") addDesignObject("shape", { shape: "rect", name: "Rectangle" }, point);
      if (tool === "shape-ellipse") addDesignObject("shape", { shape: "ellipse", name: "Ellipse" }, point);
      if (tool === "shape-line") addDesignObject("shape", { shape: "line", name: "Line" }, point);
      if (tool === "shape-arrow") addDesignObject("shape", { shape: "arrow", name: "Arrow" }, point);
      event.preventDefault();
      return;
    }
    if (tool === "draw") {
      if (event.button !== 0) return;
      const point = stagePoint(event, plane);
      const vector = normalizeDesignVector({
        id: `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`,
        name: penMode === "marker" ? "Marker" : "Vector",
        points: [point],
        color: strokeInput ? strokeInput.value : "#2563eb",
        width: Number(brushInput ? brushInput.value : 5),
        mode: penMode,
        parentId: (findTopFrameAt(point.x, point.y) || {}).id || "",
      });
      state.vectors.push(vector);
      selectOnly(vector.id);
      drawState = { id: vector.id };
      if (plane.setPointerCapture) plane.setPointerCapture(event.pointerId);
      render();
      event.preventDefault();
      return;
    }
    if (tool === "select") {
      const point = stagePoint(event, plane);
      marqueeState = { startX: point.x, startY: point.y, currentX: point.x, currentY: point.y };
      if (!event.shiftKey) selectOnly("");
      render();
      renderMarquee();
    }
  });

  plane.addEventListener("pointermove", (event) => {
    if (cropDragState) {
      const object = objectById(cropDragState.id);
      if (object && object.type === "image") {
        const dx = (event.clientX - cropDragState.startX) / zoom;
        const dy = (event.clientY - cropDragState.startY) / zoom;
        object.imageCrop = {
          ...(object.imageCrop || { x: 0, y: 0, scale: 1 }),
          x: cropDragState.crop.x + dx,
          y: cropDragState.crop.y + dy,
        };
        object.imageFit = "crop";
        updateImageElement(object);
      }
      return;
    }
    if (cropScaleState) {
      const object = objectById(cropScaleState.id);
      if (object && object.type === "image") {
        const crop = cropScaleState.crop || { x: 0, y: 0, scale: 1 };
        const naturalW = Math.max(1, Number(object.naturalW || object.w || 1));
        const naturalH = Math.max(1, Number(object.naturalH || object.h || 1));
        const oldScale = Math.max(0.05, Number(crop.scale || 1));
        const delta = ((event.clientX - cropScaleState.startX) + (event.clientY - cropScaleState.startY)) / 280;
        const nextScale = clamp(oldScale * Math.exp(delta), 0.05, 20);
        const anchor = { x: object.w / 2, y: object.h / 2 };
        const ratioX = (anchor.x - crop.x) / (naturalW * oldScale);
        const ratioY = (anchor.y - crop.y) / (naturalH * oldScale);
        object.imageCrop = {
          x: anchor.x - ratioX * naturalW * nextScale,
          y: anchor.y - ratioY * naturalH * nextScale,
          scale: nextScale,
        };
        object.imageFit = "crop";
        updateImageElement(object);
      }
      return;
    }
    if (drawState && tool === "draw") {
      const point = stagePoint(event, plane);
      const vector = vectorById(drawState.id);
      if (vector) {
        const last = vector.points[vector.points.length - 1];
        if (!last || Math.hypot(point.x - last.x, point.y - last.y) > 3) {
          vector.points.push(normalizeDesignPoint(point));
          renderVectors();
        }
      }
      return;
    }
    if (pointDragState) {
      const vector = vectorById(pointDragState.id);
      const point = stagePoint(event, plane);
      if (vector && vector.points[pointDragState.index]) {
        const target = vector.points[pointDragState.index];
        if (pointDragState.handle === "anchor") {
          const dx = point.x - target.x;
          const dy = point.y - target.y;
          vector.points[pointDragState.index] = moveDesignPoint(target, dx, dy);
        } else {
          target[pointDragState.handle] = { x: point.x, y: point.y };
        }
        renderVectors();
      }
      return;
    }
    if (rotateState) {
      const object = objectById(rotateState.id);
      if (!object) return;
      const point = stagePoint(event, plane);
      const angle = Math.atan2(point.y - rotateState.center.y, point.x - rotateState.center.x);
      let nextRotation = rotateState.rotation + ((angle - rotateState.startAngle) * 180) / Math.PI;
      if (event.shiftKey) nextRotation = Math.round(nextRotation / 15) * 15;
      object.rotation = normalizeAngle(nextRotation);
      render();
      return;
    }
    if (marqueeState) {
      const point = stagePoint(event, plane);
      marqueeState.currentX = point.x;
      marqueeState.currentY = point.y;
      renderMarquee();
      return;
    }
    if (resizeState) {
      const object = objectById(resizeState.id);
      if (!object) return;
      const point = stagePoint(event, plane);
      const dx = point.x - resizeState.startX;
      const dy = point.y - resizeState.startY;
      const source = resizeState.object;
      object.x = source.x;
      object.y = source.y;
      object.w = source.w;
      object.h = source.h;
      if (resizeState.corner.includes("e")) object.w = Math.max(24, source.w + dx);
      if (resizeState.corner.includes("s")) object.h = Math.max(24, source.h + dy);
      if (resizeState.corner.includes("w")) {
        object.x = source.x + dx;
        object.w = Math.max(24, source.w - dx);
      }
      if (resizeState.corner.includes("n")) {
        object.y = source.y + dy;
        object.h = Math.max(24, source.h - dy);
      }
      object.x = snap(object.x);
      object.y = snap(object.y);
      object.w = snap(object.w);
      object.h = snap(object.h);
      if (object.type === "frame") applyResizeChildren(object, source, resizeState.children);
      renderGuides(smartSnapObject(object, new Set([object.id])));
      render();
      return;
    }
    if (!dragState) return;
    const point = stagePoint(event, plane);
    dragState.currentPoint = point;
    const dx = point.x - dragState.startX;
    const dy = point.y - dragState.startY;
    const hoverFrame = findTopFrameAt(point.x, point.y, selectedId);
    const hoverParentId = (hoverFrame && hoverFrame.id) || "";
    setTargetFrame(hoverParentId);
    dragState.objects.forEach((item) => {
      const object = objectById(item.id);
      if (!object || object.locked) return;
      object.x = snap(item.x + dx);
      object.y = snap(item.y + dy);
      if (object.type !== "frame" && object.type !== "group") {
        object.parentId = hoverParentId;
        if (hoverParentId && !object.constraints) object.constraints = { h: "left", v: "top" };
      }
      if (dragState.objects.length === 1) renderGuides(smartSnapObject(object));
    });
    dragState.vectors.forEach((item) => {
      const vector = vectorById(item.id);
      if (!vector || vector.locked) return;
      vector.points = item.points.map((sourcePoint) => moveDesignPoint(sourcePoint, dx, dy));
      vector.parentId = hoverParentId;
    });
    render();
  });

  plane.addEventListener("pointerup", () => {
    renderGuides();
    const activeCropId = (cropDragState && cropDragState.id) || (cropScaleState && cropScaleState.id) || "";
    if (marqueeState) {
      const rect = normalizedRect(marqueeState);
      const picked = [
        ...objects().filter((item) => !item.hidden && rectsIntersect(rect, item)).map((item) => item.id),
        ...vectors().filter((item) => !item.hidden && vectorIntersectsRectV2(item, rect)).map((item) => item.id),
      ];
      if (!picked.length) selectOnly("");
      picked.forEach((id) => selectedIds.add(id));
      selectedId = picked[picked.length - 1] || selectedId;
      marqueeState = null;
      render();
    }
    if (drawState || dragState || pointDragState || resizeState || rotateState || cropDragState || cropScaleState) {
      if (dragState) {
        dragState.objects.forEach((item) => {
          const object = objectById(item.id);
          if (object && object.type !== "frame" && object.type !== "group") assignParent(object, dragState.currentPoint || null);
        });
        dragState.vectors.forEach((item) => {
          const vector = vectorById(item.id);
          if (vector) assignParent(vector, dragState.currentPoint || null);
        });
      }
      if (activeCropId) {
        selectOnly(activeCropId);
        cropEditId = activeCropId;
      }
      commit();
    }
    drawState = null;
    dragState = null;
    pointDragState = null;
    resizeState = null;
    rotateState = null;
    cropDragState = null;
    cropScaleState = null;
    setTargetFrame("");
  });

  const beginPan = (event) => {
    panState = { x: event.clientX, y: event.clientY, left: shell.scrollLeft, top: shell.scrollTop };
    shell.classList.add("is-panning");
    if (shell.setPointerCapture) shell.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  shell.addEventListener("pointerdown", (event) => {
    const canPan = tool === "pan" || spaceDown || event.button === 1;
    if (!canPan) return;
    beginPan(event);
  });

  shell.addEventListener("pointermove", (event) => {
    updateLastCanvasPoint(event);
    if (!panState) return;
    shell.scrollLeft = panState.left - (event.clientX - panState.x);
    shell.scrollTop = panState.top - (event.clientY - panState.y);
  });

  shell.addEventListener("pointerup", () => {
    panState = null;
    shell.classList.remove("is-panning");
  });

  shell.addEventListener("wheel", (event) => {
    if (event.ctrlKey || event.metaKey) {
      event.preventDefault();
      const shellRect = shell.getBoundingClientRect();
      const speed = event.deltaMode === 1 ? 0.045 : 0.0018;
      const nextZoom = zoom * Math.exp(-event.deltaY * speed);
      applyZoom(nextZoom, { x: event.clientX - shellRect.left, y: event.clientY - shellRect.top });
      return;
    }
    event.preventDefault();
    if (event.shiftKey) shell.scrollLeft += event.deltaY + event.deltaX;
    else {
      shell.scrollLeft += event.deltaX;
      shell.scrollTop += event.deltaY;
    }
  }, { passive: false });

  shell.addEventListener("contextmenu", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (!target || target.closest(".designer-zoom-controls")) return;
    event.preventDefault();
    contextPoint = pointFromContextEvent(event);
    const objectElement = target.closest("[data-design-id]");
    const vectorElement = target.closest("[data-vector-id]");
    const targetId = objectElement ? objectElement.dataset.designId : (vectorElement ? vectorElement.dataset.vectorId : "");
    if (targetId && !selectedIds.has(targetId)) {
      selectOnly(targetId);
      render();
    }
    const activeImage = selectedObject();
    const showImageActions = Boolean(activeImage && activeImage.type === "image");
    contextMenu.querySelectorAll("[data-image-context]").forEach((item) => {
      item.hidden = !showImageActions;
    });
    contextMenu.querySelectorAll("[data-designer-context-action='copy'], [data-designer-context-action='duplicate'], [data-designer-context-action='delete']").forEach((button) => {
      button.disabled = !selectedId;
    });
    setContextStatus("");
    positionContextMenu(event);
  });

  contextMenu.addEventListener("click", async (event) => {
    const button = event.target instanceof Element ? event.target.closest("[data-designer-context-action]") : null;
    if (!button || button.disabled) return;
    const action = button.dataset.designerContextAction || "";
    if (action === "paste") {
      await pasteClipboardAt(contextPoint);
      return;
    }
    if (action === "copy") copySelection();
    if (action === "duplicate") duplicateSelection();
    if (action === "delete") deleteSelection();
    if (action === "crop-image") startImageCrop(selectedObject());
    if (action === "reset-crop") resetImageCrop(selectedObject());
    if (action === "replace-image") replaceImageLayer(selectedObject());
    if (action === "detach-frame") {
      const object = selectedObject();
      if (object) {
        object.parentId = "";
        commit();
      }
    }
    hideContextMenu();
  });

  document.addEventListener("click", (event) => {
    if (!contextMenu.hidden && event.target instanceof Node && !contextMenu.contains(event.target)) hideContextMenu();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") hideContextMenu();
  });
  shell.addEventListener("scroll", hideContextMenu);
  shell.addEventListener("scroll", updatePlaneSize);

  document.addEventListener("keydown", (event) => {
    if (readOnly) return;
    const key = event.key.toLowerCase();
    const code = event.code || "";
    const formTarget = event.target instanceof Element ? event.target.closest("input, textarea, select") : null;
    if (!formTarget && (event.ctrlKey || event.metaKey) && (key === "c" || code === "KeyC") && selectedId) {
      copySelection();
      event.preventDefault();
      return;
    }
    if (!formTarget && (event.ctrlKey || event.metaKey) && (key === "v" || code === "KeyV")) {
      pasteDesignClipboardAt(lastCanvasPoint) || pasteClipboardAt(lastCanvasPoint);
      event.preventDefault();
      return;
    }
    if (isTypingTarget(event.target)) return;
    if ((event.ctrlKey || event.metaKey) && key === "z") {
      restoreHistory(event.shiftKey ? 1 : -1);
      event.preventDefault();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "y") {
      restoreHistory(1);
      event.preventDefault();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "d" && selectedId) {
      duplicateSelection();
      event.preventDefault();
      return;
    }
    if ((event.key === "Delete" || event.key === "Backspace") && selectedId) {
      deleteSelection();
      event.preventDefault();
      return;
    }
    if (event.key === "Enter" && selectedVector()) {
      vectorEdit = true;
      ensureVectorHandles(selectedVector());
      render();
      event.preventDefault();
      return;
    }
    if (event.key === "Escape" && vectorEdit) {
      vectorEdit = false;
      render();
      event.preventDefault();
      return;
    }
    if (event.key === "0") {
      fitZoom();
      event.preventDefault();
      return;
    }
    if (event.key === "1") {
      applyZoom(1, { x: shell.clientWidth / 2, y: shell.clientHeight / 2 });
      event.preventDefault();
      return;
    }
    if (event.code !== "Space") return;
    spaceDown = true;
    shell.classList.add("is-pannable");
    event.preventDefault();
  });

  document.addEventListener("keyup", (event) => {
    if (event.code !== "Space") return;
    spaceDown = false;
    shell.classList.toggle("is-pannable", tool === "pan");
  });

  [fillInput, strokeInput].forEach((input) => {
    if (!input) return;
    input.addEventListener("input", () => {
      selectedIds.forEach((id) => {
        const object = objectById(id);
        const vector = vectorById(id);
        if (object && !object.locked) {
          if (input === fillInput) object.fill = input.value;
          if (input === strokeInput) object.stroke = input.value;
        }
        if (vector && !vector.locked && input === strokeInput) vector.color = input.value;
      });
      commit();
    });
  });

  commandButtons.forEach((button) => {
    button.addEventListener("click", () => runDesignCommand(button.dataset.designCommand || ""));
  });

  if (layerPanel && inspector) {
    const syncLayerPanelState = () => {
      inspector.classList.toggle("is-layers-open", layerPanel.open);
    };
    layerPanel.addEventListener("toggle", syncLayerPanelState);
    syncLayerPanelState();
  }

  if (photoInput) {
    photoInput.addEventListener("change", () => {
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;
      addImageFile(file);
      photoInput.value = "";
    });
  }

  shell.addEventListener("dragover", (event) => {
    event.preventDefault();
    shell.classList.add("is-dropping");
    const point = stagePoint(event, plane);
    setTargetFrame((findTopFrameAt(point.x, point.y) || {}).id || "");
  });
  shell.addEventListener("dragleave", () => {
    shell.classList.remove("is-dropping");
    setTargetFrame("");
  });
  shell.addEventListener("drop", (event) => {
    event.preventDefault();
    shell.classList.remove("is-dropping");
    const point = stagePoint(event, plane);
    setTargetFrame("");
    const files = [...(event.dataTransfer && event.dataTransfer.files ? event.dataTransfer.files : [])];
    if (files.length) {
      files.forEach((file, index) => addImageFile(file, { x: point.x + index * 24, y: point.y + index * 24 }));
      return;
    }
    const text = event.dataTransfer ? event.dataTransfer.getData("text/plain") : "";
    if (text) addTextLayer(text, point);
  });

  document.addEventListener("paste", (event) => {
    const items = [...(event.clipboardData && event.clipboardData.items ? event.clipboardData.items : [])];
    const imageItem = items.find((item) => String(item.type || "").startsWith("image/"));
    if (imageItem) {
      const file = imageItem.getAsFile();
      if (file) {
        addImageFile(file, lastCanvasPoint);
        event.preventDefault();
      }
      return;
    }
    const text = event.clipboardData ? event.clipboardData.getData("text/plain") : "";
    if (!text || isTypingTarget(event.target)) return;
    if (text.trim().startsWith("<svg")) addSvgText(text, lastCanvasPoint);
    else addTextLayer(text, lastCanvasPoint);
    event.preventDefault();
  });

  if (brushInput && brushValue) {
    const updateBrushValue = () => {
      brushValue.textContent = `${brushInput.value} px`;
    };
    brushInput.addEventListener("input", updateBrushValue);
    updateBrushValue();
  }

  penModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      penMode = button.dataset.penMode || "pen";
      penModeButtons.forEach((item) => item.classList.toggle("is-active", item === button));
    });
  });

  presetButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const preset = DESIGN_FRAME_PRESETS[button.dataset.framePreset || ""];
      if (!preset) return;
      addDesignObject("frame", {
        w: Math.min(preset.w, DESIGN_WIDTH - 240),
        h: Math.min(preset.h, DESIGN_HEIGHT - 200),
        name: preset.label,
        text: preset.label,
      });
    });
  });

  zoomButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.designZoom;
      if (action === "fit") fitZoom();
      if (action === "in") applyZoom(zoom + 0.1, { x: shell.clientWidth / 2, y: shell.clientHeight / 2 });
      if (action === "out") applyZoom(zoom - 0.1, { x: shell.clientWidth / 2, y: shell.clientHeight / 2 });
    });
  });

  if (clearButton) {
    clearButton.addEventListener("click", () => {
      state = normalizeDesignStateV2({ version: 2, objects: [], vectors: [], zoom });
      selectedId = "";
      selectedIds = new Set();
      vectorEdit = false;
      commit();
    });
  }

  const startProjectTitleEdit = () => {
    if (readOnly) return;
    if (!projectTitle || projectTitle.querySelector("input")) return;
    const original = projectTitle.textContent.trim() || "New design";
    const input = document.createElement("input");
    input.className = "designer-project-title-input";
    input.value = original;
    input.maxLength = 180;
    projectTitle.textContent = "";
    projectTitle.append(input);
    input.focus();
    input.select();
    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const next = input.value.trim() || original;
      projectTitle.textContent = save ? next : original;
      state.title = save ? next : original;
      syncProjectChrome();
      if (save && next !== original) {
        scheduleProjectSave();
        try {
          await ensureDesignProject();
          const data = await jsonRequest(`${projectConfig.apiUrl}${projectId}/rename/`, { method: "POST", body: JSON.stringify({ title: next }) });
          state.title = data.project?.title || next;
          syncProjectChrome();
        } catch {
          setSaveStatus(i18n.save_failed || "Save failed", true);
        }
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

  projectTitle?.addEventListener("dblclick", startProjectTitleEdit);
  saveRetry?.addEventListener("click", saveProject);
  importDraftButton?.addEventListener("click", () => {
    state = loadDesignStateV2();
    state.title = state.title || "Imported design";
    history = [designSnapshot(state)];
    historyIndex = 0;
    selectedId = "";
    selectedIds = new Set();
    render();
    scheduleProjectSave();
    importDraftButton.hidden = true;
  });
  window.addEventListener("beforeunload", (event) => {
    if (!dirty && !saving && !saveFailed) return;
    event.preventDefault();
    event.returnValue = "";
  });

  setupMobileDesignerWorkspace();

  zoom = clamp(Number(state.zoom) || 1, 0.03, 5);
  if (readOnly) {
    panel.classList.add("is-view-only");
    panel.querySelectorAll("button, input, select, textarea").forEach((control) => {
      if (control.closest(".designer-zoom-controls") || control.matches("[data-share-open]")) return;
      control.disabled = true;
    });
  }
  updatePlaneSize();
  applyZoom(zoom, null, false);
  window.addEventListener("resize", () => {
    updatePlaneSize();
  });
  render();
  syncProjectChrome();
  setSaveStatus(readOnly ? (i18n.view_only || "View only") : (projectId ? `${i18n.saved || "Saved"} ${savedTime()}` : (i18n.local_draft || "Local draft")));
  didInitialRender = true;
  if (!state.didFit) {
    state.didFit = true;
    fitZoom();
    persist();
  }

  function setupMobileDesignerWorkspace() {
    const media = window.matchMedia("(max-width: 760px)");
    const inspectorShell = panel.querySelector("[data-designer-mobile-drawer]");
    const toolbar = panel.querySelector("[data-designer-mobile-palette]");
    const storageKey = "designerMobileInspectorHeight.v2";
    let startY = 0;
    let startHeight = 0;
    const defaultHeight = () => 44;
    const maxHeight = () => Math.max(300, (window.innerHeight || 760) - 128);
    const clampHeight = (value) => Math.max(38, Math.min(maxHeight(), Math.round(Number(value) || defaultHeight())));
    const applyHeight = (value, remember = true) => {
      if (!inspectorShell) return;
      const next = clampHeight(value);
      document.documentElement.style.setProperty("--mobile-designer-inspector-height", `${next}px`);
      inspectorShell.classList.toggle("is-sheet-collapsed", next <= 50);
      if (remember) localStorage.setItem(storageKey, String(next));
    };
    const sync = () => {
      document.body.classList.toggle("is-mobile-designer", media.matches);
      if (!media.matches) return;
      applyHeight(localStorage.getItem(storageKey) || defaultHeight(), false);
      requestAnimationFrame(() => {
        updatePlaneSize();
        fitZoom();
      });
    };
    const resize = (event) => {
      if (!startHeight) return;
      applyHeight(startHeight + (startY - event.clientY));
    };
    const stopResize = () => {
      startHeight = 0;
      document.body.classList.remove("is-resizing-designer-sheet");
      window.removeEventListener("pointermove", resize);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
    };
    const startResize = (event) => {
      if (!media.matches || !inspectorShell) return;
      event.preventDefault();
      startY = event.clientY;
      startHeight = inspectorShell.getBoundingClientRect().height;
      document.body.classList.add("is-resizing-designer-sheet");
      event.currentTarget.setPointerCapture?.(event.pointerId);
      window.addEventListener("pointermove", resize);
      window.addEventListener("pointerup", stopResize, {once: true});
      window.addEventListener("pointercancel", stopResize, {once: true});
    };
    if (inspectorShell && !inspectorShell.querySelector(".designer-inspector-grip")) {
      const grip = document.createElement("button");
      grip.className = "designer-inspector-grip";
      grip.type = "button";
      grip.setAttribute("aria-label", i18n.resize_panel || "Resize panel");
      inspectorShell.prepend(grip);
      grip.addEventListener("pointerdown", startResize);
      grip.addEventListener("dblclick", () => {
        const current = inspectorShell.getBoundingClientRect().height;
        applyHeight(current <= 50 ? defaultHeight() : 38);
      });
    }
    toolbar?.querySelectorAll("[data-design-tool]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!media.matches) return;
        button.scrollIntoView({behavior: "smooth", inline: "center", block: "nearest"});
      });
    });
    media.addEventListener?.("change", sync);
    sync();
  }
}

function loadDesignStateV2() {
  try {
    const v2 = localStorage.getItem(DESIGN_STORAGE_KEY_V2);
    if (v2) return normalizeDesignStateV2(JSON.parse(v2));
    const legacy = localStorage.getItem(DESIGN_STORAGE_KEY);
    if (legacy) return normalizeDesignStateV2(JSON.parse(legacy));
  } catch {
    return normalizeDesignStateV2({});
  }
  return normalizeDesignStateV2({});
}

function hasLocalDesignDraft() {
  try {
    const raw = localStorage.getItem(DESIGN_STORAGE_KEY_V2) || localStorage.getItem(DESIGN_STORAGE_KEY) || "";
    if (!raw) return false;
    const state = normalizeDesignStateV2(JSON.parse(raw));
    return Boolean((state.objects && state.objects.length) || (state.vectors && state.vectors.length));
  } catch {
    return false;
  }
}

function normalizeDesignStateV2(input = {}) {
  const legacyStrokes = Array.isArray(input.strokes) ? input.strokes : [];
  const rawVectors = Array.isArray(input.vectors) ? input.vectors : legacyStrokes.map((stroke) => ({
    id: stroke.id,
    name: stroke.name || (stroke.mode === "marker" ? "Marker" : "Vector"),
    points: stroke.points,
    color: stroke.color,
    width: stroke.width,
    mode: stroke.mode,
  }));
  const state = {
    version: 2,
    title: input.title || "New design",
    objects: Array.isArray(input.objects) ? input.objects.map(normalizeDesignObject) : [],
    vectors: rawVectors.map(normalizeDesignVector),
    zoom: Number(input.zoom) || 1,
    didFit: Boolean(input.didFit),
  };
  const objectIds = new Set(state.objects.map((item) => item.id));
  state.objects.forEach((item) => {
    if (item.parentId && !objectIds.has(item.parentId)) item.parentId = "";
    if (item.parentId === item.id) item.parentId = "";
  });
  state.vectors.forEach((item) => {
    if (item.parentId && !objectIds.has(item.parentId)) item.parentId = "";
  });
  return state;
}

function normalizeDesignObject(input = {}) {
  const type = ["frame", "group", "text", "image", "shape"].includes(input.type) ? input.type : "frame";
  const defaults = objectDefaultsFor(type, input.shape);
  const object = {
    ...defaults,
    ...input,
    id: input.id || `object-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type,
    name: input.name || input.text || defaults.name,
    x: Number(input.x) || 0,
    y: Number(input.y) || 0,
    w: Math.max(8, Number(input.w) || defaults.w),
    h: Math.max(8, Number(input.h) || defaults.h),
    parentId: input.parentId || "",
    rotation: Number(input.rotation) || 0,
    opacity: clamp(Number(input.opacity ?? defaults.opacity ?? 1), 0, 1),
    locked: Boolean(input.locked),
    hidden: Boolean(input.hidden),
    fill: input.fill ?? defaults.fill,
    stroke: input.stroke || defaults.stroke,
    strokeWidth: Math.max(0, Number(input.strokeWidth ?? defaults.strokeWidth ?? 2)),
    cornerRadius: Math.max(0, Number(input.cornerRadius ?? defaults.cornerRadius ?? 10)),
    constraints: {
      h: (input.constraints && input.constraints.h) || "left",
      v: (input.constraints && input.constraints.v) || "top",
    },
  };
  if (object.type === "frame") {
    object.clipContent = Boolean(input.clipContent);
    object.layoutMode = ["off", "vertical", "horizontal"].includes(input.layoutMode) ? input.layoutMode : "off";
    object.gap = Math.max(0, Number(input.gap ?? 12));
    object.padding = Math.max(0, Number(input.padding ?? 16));
    object.align = ["start", "center", "end", "stretch"].includes(input.align) ? input.align : "start";
  }
  if (object.type === "text") {
    object.text = input.text || "Text";
    object.fontSize = Math.max(8, Number(input.fontSize || 22));
    object.fontWeight = Number(input.fontWeight || 800);
    object.fontFamily = input.fontFamily || "Arial, sans-serif";
    object.textAlign = ["left", "center", "right"].includes(input.textAlign) ? input.textAlign : "left";
    object.lineHeight = clamp(Number(input.lineHeight || 1.15), 0.8, 3);
    object.letterSpacing = Number(input.letterSpacing || 0);
    object.textStroke = input.textStroke || "transparent";
    object.textStrokeWidth = Math.max(0, Number(input.textStrokeWidth || 0));
    object.textGradient = Boolean(input.textGradient);
    object.gradientStart = input.gradientStart || object.stroke || "#2563eb";
    object.gradientEnd = input.gradientEnd || "#ec4899";
  }
  if (object.type === "image") {
    object.src = input.src || "";
    object.naturalW = Math.max(0, Number(input.naturalW || 0));
    object.naturalH = Math.max(0, Number(input.naturalH || 0));
    object.imageFit = ["fill", "fit", "crop", "original"].includes(input.imageFit) ? input.imageFit : "fill";
    object.imageCrop = {
      x: Number(input.imageCrop && input.imageCrop.x) || 0,
      y: Number(input.imageCrop && input.imageCrop.y) || 0,
      scale: Math.max(0.05, Number(input.imageCrop && input.imageCrop.scale || 1)),
    };
  }
  if (object.type === "shape") object.shape = ["rect", "ellipse", "line", "arrow"].includes(input.shape) ? input.shape : "rect";
  if (object.type === "group") object.children = Array.isArray(input.children) ? input.children : [];
  return object;
}

function objectDefaultsFor(type, shape = "") {
  if (type === "text") {
    return { name: "Text", w: 260, h: 86, fill: "transparent", stroke: "#0f172a", opacity: 1, fontSize: 22, fontWeight: 800, fontFamily: "Arial, sans-serif", textAlign: "left", lineHeight: 1.15, letterSpacing: 0, textStroke: "transparent", textStrokeWidth: 0, textGradient: false, gradientStart: "#2563eb", gradientEnd: "#ec4899" };
  }
  if (type === "image") {
    return { name: "Image", w: 320, h: 240, fill: "#f8fafc", stroke: "#2563eb", opacity: 1, naturalW: 0, naturalH: 0, imageFit: "fill", imageCrop: { x: 0, y: 0, scale: 1 } };
  }
  if (type === "shape") {
    const isLine = shape === "line" || shape === "arrow";
    return { name: shape || "Shape", w: isLine ? 360 : 260, h: isLine ? 72 : 180, fill: isLine ? "transparent" : "#ffffff", stroke: "#2563eb", opacity: 1, strokeWidth: 2, cornerRadius: 12 };
  }
  if (type === "group") {
    return { name: "Group", w: 320, h: 220, fill: "transparent", stroke: "#60a5fa", opacity: 1 };
  }
  return { name: "Frame", w: 390, h: 844, fill: "#ffffff", stroke: "#2563eb", opacity: 1, strokeWidth: 2, cornerRadius: 10 };
}

function normalizeDesignVector(input = {}) {
  const points = Array.isArray(input.points) ? input.points.map(normalizeDesignPoint).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y)) : [];
  return {
    id: input.id || `vector-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    type: "vector",
    name: input.name || "Vector",
    points,
    closed: Boolean(input.closed),
    color: input.color || input.stroke || "#2563eb",
    width: Math.max(1, Number(input.width || 5)),
    mode: input.mode === "marker" ? "marker" : "pen",
    parentId: input.parentId || "",
    opacity: clamp(Number(input.opacity ?? 1), 0, 1),
    locked: Boolean(input.locked),
    hidden: Boolean(input.hidden),
  };
}

function normalizeDesignPoint(input = {}) {
  const point = {
    x: Number(input.x) || 0,
    y: Number(input.y) || 0,
    in: input.in ? { x: Number(input.in.x) || 0, y: Number(input.in.y) || 0 } : null,
    out: input.out ? { x: Number(input.out.x) || 0, y: Number(input.out.y) || 0 } : null,
  };
  return point;
}

function cloneDesignObject(object) {
  return normalizeDesignObject(JSON.parse(JSON.stringify(object)));
}

function cloneDesignVector(vector) {
  return normalizeDesignVector(JSON.parse(JSON.stringify(vector)));
}

function cloneDesignPoint(point) {
  return normalizeDesignPoint(JSON.parse(JSON.stringify(point)));
}

function designSnapshot(state) {
  return JSON.stringify(normalizeDesignStateV2(JSON.parse(JSON.stringify(state || {}))));
}

function safeColor(value, fallback = "#2563eb") {
  const color = normalizeDesignerColor(value, fallback);
  return /^#[0-9a-f]{6}$/i.test(color) ? color : fallback;
}

function normalizeDesignerColor(value, fallback = "#2563eb") {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return fallback;
  if (raw === "transparent" || raw === "none") return "transparent";
  const shortHex = raw.match(/^#([0-9a-f]{3})$/i);
  if (shortHex) return `#${shortHex[1].split("").map((char) => char + char).join("")}`;
  const longHex = raw.match(/^#([0-9a-f]{6})$/i);
  if (longHex) return `#${longHex[1]}`;
  const rgb = raw.match(/^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+)\s*)?\)$/i);
  if (rgb) {
    const alpha = rgb[4] === undefined ? 1 : clamp(Number(rgb[4]), 0, 1);
    if (alpha === 0) return "transparent";
    const toHex = (channel) => clamp(Math.round(Number(channel) || 0), 0, 255).toString(16).padStart(2, "0");
    return `#${toHex(rgb[1])}${toHex(rgb[2])}${toHex(rgb[3])}`;
  }
  return fallback;
}

function ensureImageCropDefaults(object) {
  if (!object || object.type !== "image") return object;
  object.naturalW = Math.max(0, Number(object.naturalW || 0));
  object.naturalH = Math.max(0, Number(object.naturalH || 0));
  object.imageFit = ["fill", "fit", "crop", "original"].includes(object.imageFit) ? object.imageFit : "fill";
  const crop = object.imageCrop && typeof object.imageCrop === "object" ? object.imageCrop : {};
  object.imageCrop = {
    x: Number(crop.x) || 0,
    y: Number(crop.y) || 0,
    scale: Math.max(0.05, Number(crop.scale || 1)),
  };
  return object;
}

function imagePlacementForObject(object) {
  ensureImageCropDefaults(object);
  const layerW = Math.max(1, Number(object.w || 1));
  const layerH = Math.max(1, Number(object.h || 1));
  const naturalW = Math.max(1, Number(object.naturalW || layerW));
  const naturalH = Math.max(1, Number(object.naturalH || layerH));
  const crop = object.imageCrop || { x: 0, y: 0, scale: 1 };
  const fit = object.imageFit || "fill";
  let scale = Math.max(0.05, Number(crop.scale || 1));
  if (fit === "fit") scale = Math.min(layerW / naturalW, layerH / naturalH);
  else if (fit === "fill") scale = Math.max(layerW / naturalW, layerH / naturalH);
  else if (fit === "original") scale = Math.max(0.05, Number(crop.scale || 1));
  const width = naturalW * scale;
  const height = naturalH * scale;
  const centered = fit === "fill" || fit === "fit";
  return {
    x: centered ? (layerW - width) / 2 : Number(crop.x || 0),
    y: centered ? (layerH - height) / 2 : Number(crop.y || 0),
    w: width,
    h: height,
    scale,
  };
}

function ensureImageCropFromFit(object) {
  if (!object || object.type !== "image") return;
  ensureImageCropDefaults(object);
  const placement = imagePlacementForObject({ ...object, imageFit: object.imageFit === "crop" ? "fill" : object.imageFit });
  object.imageCrop = {
    x: placement.x,
    y: placement.y,
    scale: placement.scale,
  };
}

function moveDesignPoint(point, dx, dy) {
  return {
    ...point,
    x: point.x + dx,
    y: point.y + dy,
    in: point.in ? { x: point.in.x + dx, y: point.in.y + dy } : null,
    out: point.out ? { x: point.out.x + dx, y: point.out.y + dy } : null,
  };
}

function ensureVectorHandles(vector) {
  if (!vector || !Array.isArray(vector.points)) return;
  vector.points.forEach((point, index) => {
    const prev = vector.points[index - 1];
    const next = vector.points[index + 1];
    const source = prev || next;
    const target = next || prev;
    if (!source || !target) return;
    const dx = target.x - source.x;
    const dy = target.y - source.y;
    const length = Math.max(1, Math.hypot(dx, dy));
    const handle = Math.min(96, length / 5);
    if (!point.in) point.in = { x: point.x - (dx / length) * handle, y: point.y - (dy / length) * handle };
    if (!point.out) point.out = { x: point.x + (dx / length) * handle, y: point.y + (dy / length) * handle };
  });
}

function vectorPathV2(points = [], closed = false) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const point = points[index];
    if (prev.out || point.in) {
      const c1 = prev.out || prev;
      const c2 = point.in || point;
      path += ` C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${point.x} ${point.y}`;
    } else {
      path += ` L ${point.x} ${point.y}`;
    }
  }
  if (closed && points.length > 2) {
    const prev = points[points.length - 1];
    const point = points[0];
    if (prev.out || point.in) {
      const c1 = prev.out || prev;
      const c2 = point.in || point;
      path += ` C ${c1.x} ${c1.y} ${c2.x} ${c2.y} ${point.x} ${point.y}`;
    }
    return `${path} Z`;
  }
  return path;
}

function vectorBoundsV2(vector) {
  const points = Array.isArray(vector.points) ? vector.points : [];
  if (!points.length) return { x: 0, y: 0, w: 1, h: 1 };
  const all = points.flatMap((point) => [point, point.in, point.out].filter(Boolean));
  const left = Math.min(...all.map((point) => point.x));
  const top = Math.min(...all.map((point) => point.y));
  const right = Math.max(...all.map((point) => point.x));
  const bottom = Math.max(...all.map((point) => point.y));
  return { x: left, y: top, w: Math.max(1, right - left), h: Math.max(1, bottom - top) };
}

function vectorIntersectsRectV2(vector, rect) {
  return (vector.points || []).some((point) => point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h);
}

function boundsForLayersV2(objectLayers = [], vectorLayers = []) {
  const boxes = [
    ...objectLayers.map((item) => ({ x: item.x, y: item.y, w: item.w, h: item.h })),
    ...vectorLayers.map(vectorBoundsV2),
  ].filter((box) => Number.isFinite(box.x) && Number.isFinite(box.y));
  if (!boxes.length) return { x: 0, y: 0, w: 1, h: 1 };
  const left = Math.min(...boxes.map((item) => item.x));
  const top = Math.min(...boxes.map((item) => item.y));
  const right = Math.max(...boxes.map((item) => item.x + item.w));
  const bottom = Math.max(...boxes.map((item) => item.y + item.h));
  return { x: left, y: top, w: Math.max(1, right - left), h: Math.max(1, bottom - top) };
}

function buildExportSvgV2(target, designState = null) {
  const storage = normalizeDesignStateV2(designState || JSON.parse(localStorage.getItem(DESIGN_STORAGE_KEY_V2) || "{}"));
  const targetBounds = target.points ? vectorBoundsV2(target) : target;
  const x = Number(targetBounds.x || 0);
  const y = Number(targetBounds.y || 0);
  const w = Math.max(1, Number(targetBounds.w || 1));
  const h = Math.max(1, Number(targetBounds.h || 1));
  const objectByIdLocal = (id) => storage.objects.find((item) => item.id === id);
  const childrenOf = (id) => storage.objects.filter((item) => item.parentId === id && !item.hidden);
  const vectorsOf = (id) => storage.vectors.filter((item) => item.parentId === id && !item.hidden);
  const inBounds = (item) => {
    const box = item.points ? vectorBoundsV2(item) : item;
    return rectsIntersect({ x, y, w, h }, box);
  };
  const wrapObjectMarkup = (item, ix, iy, markup) => {
    const rotation = Number(item.rotation || 0);
    if (!rotation) return markup;
    const cx = ix + Number(item.w || 0) / 2;
    const cy = iy + Number(item.h || 0) / 2;
    return `<g transform="rotate(${rotation} ${cx} ${cy})">${markup}</g>`;
  };
  const objectMarkup = (item, originX, originY) => {
    const ix = Number(item.x || 0) - originX;
    const iy = Number(item.y || 0) - originY;
    const opacity = item.opacity ?? 1;
    if (item.type === "image" && item.src) {
      const placement = imagePlacementForObject(item);
      return wrapObjectMarkup(item, ix, iy, `<g clip-path="url(#image-clip-${escapeHtml(item.id)})" opacity="${opacity}"><image href="${escapeHtml(item.src)}" x="${ix + placement.x}" y="${iy + placement.y}" width="${placement.w}" height="${placement.h}" preserveAspectRatio="none"/></g>`);
    }
    if (item.type === "text") {
      const fill = item.textGradient ? `url(#text-gradient-${escapeHtml(item.id)})` : escapeHtml(item.stroke || "#0f172a");
      const bg = item.fill && item.fill !== "transparent" ? `<rect x="${ix}" y="${iy}" width="${item.w}" height="${item.h}" rx="${item.cornerRadius || 0}" fill="${escapeHtml(item.fill)}" opacity="${opacity}"/>` : "";
      const anchor = item.textAlign === "center" ? "middle" : (item.textAlign === "right" ? "end" : "start");
      const textX = item.textAlign === "center" ? ix + item.w / 2 : (item.textAlign === "right" ? ix + item.w - 12 : ix + 12);
      const strokeAttrs = Number(item.textStrokeWidth || 0) > 0 ? ` stroke="${escapeHtml(item.textStroke || "transparent")}" stroke-width="${item.textStrokeWidth}" paint-order="stroke fill"` : "";
      const text = `<text x="${textX}" y="${iy + Number(item.fontSize || 22) + 8}" fill="${fill}" font-size="${item.fontSize || 22}" font-family="${escapeHtml(item.fontFamily || "Arial, sans-serif")}" font-weight="${item.fontWeight || 800}" text-anchor="${anchor}" letter-spacing="${Number(item.letterSpacing || 0)}" opacity="${opacity}"${strokeAttrs}>${escapeHtml(item.text || "")}</text>`;
      return wrapObjectMarkup(item, ix, iy, `${bg}${text}`);
    }
    if (item.type === "shape") return wrapObjectMarkup(item, ix, iy, shapeMarkupV2(item, ix, iy));
    const rect = `<rect x="${ix}" y="${iy}" width="${item.w}" height="${item.h}" rx="${item.cornerRadius ?? 10}" fill="${escapeHtml(item.fill || "transparent")}" stroke="${escapeHtml(item.stroke || "#2563eb")}" stroke-width="${item.strokeWidth ?? 2}" opacity="${opacity}"/>`;
    const children = [...childrenOf(item.id).map((child) => objectMarkup(child, originX, originY)), ...vectorsOf(item.id).map((vector) => vectorMarkupV2(vector, originX, originY))].join("");
    if (item.clipContent) {
      return wrapObjectMarkup(item, ix, iy, `<g clip-path="url(#clip-${escapeHtml(item.id)})">${rect}${children}</g>`);
    }
    return wrapObjectMarkup(item, ix, iy, `${rect}${children}`);
  };
  const vectorMarkupV2 = (vector, originX, originY) => {
    const moved = vector.points.map((point) => ({
      ...point,
      x: point.x - originX,
      y: point.y - originY,
      in: point.in ? { x: point.in.x - originX, y: point.in.y - originY } : null,
      out: point.out ? { x: point.out.x - originX, y: point.out.y - originY } : null,
    }));
    return `<path d="${vectorPathV2(moved, vector.closed)}" fill="none" stroke="${escapeHtml(vector.color || "#2563eb")}" stroke-width="${vector.width ?? 5}" stroke-linecap="round" stroke-linejoin="round" opacity="${(vector.opacity ?? 1) * (vector.mode === "marker" ? 0.38 : 1)}"/>`;
  };
  const clipDefs = storage.objects
    .filter((item) => item.clipContent)
    .map((item) => `<clipPath id="clip-${escapeHtml(item.id)}"><rect x="${item.x - x}" y="${item.y - y}" width="${item.w}" height="${item.h}"/></clipPath>`)
    .join("");
  const imageClipDefs = storage.objects
    .filter((item) => item.type === "image" && item.src)
    .map((item) => `<clipPath id="image-clip-${escapeHtml(item.id)}"><rect x="${item.x - x}" y="${item.y - y}" width="${item.w}" height="${item.h}" rx="${item.cornerRadius || 0}"/></clipPath>`)
    .join("");
  const textGradientDefs = storage.objects
    .filter((item) => item.type === "text" && item.textGradient)
    .map((item) => `<linearGradient id="text-gradient-${escapeHtml(item.id)}" x1="0%" y1="0%" x2="100%" y2="0%"><stop offset="0%" stop-color="${escapeHtml(item.gradientStart || item.stroke || "#2563eb")}"/><stop offset="100%" stop-color="${escapeHtml(item.gradientEnd || "#ec4899")}"/></linearGradient>`)
    .join("");
  let body = "";
  if (target.points) {
    body = vectorMarkupV2(target, x, y);
  } else if (target.type === "frame" || target.type === "group") {
    const background = target.type === "frame" ? `<rect width="100%" height="100%" fill="${escapeHtml(target.fill || "#ffffff")}"/>` : "";
    const children = childrenOf(target.id).map((child) => objectMarkup(child, x, y)).join("");
    const childVectors = vectorsOf(target.id).map((vector) => vectorMarkupV2(vector, x, y)).join("");
    const looseVectors = storage.vectors.filter((vector) => !vector.parentId && inBounds(vector)).map((vector) => vectorMarkupV2(vector, x, y)).join("");
    body = `${background}${children}${childVectors}${looseVectors}`;
  } else {
    body = objectMarkup(target, x, y);
    const parent = target.parentId ? objectByIdLocal(target.parentId) : null;
    if (parent && parent.type === "frame") body = objectMarkup(target, x, y);
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><defs><marker id="export-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#2563eb"/></marker>${clipDefs}${imageClipDefs}${textGradientDefs}</defs>${body}</svg>`;
}

function shapeMarkupV2(item, ix, iy) {
  const fill = escapeHtml(item.fill || "transparent");
  const stroke = escapeHtml(item.stroke || "#2563eb");
  const strokeWidth = item.strokeWidth ?? 2;
  const opacity = item.opacity ?? 1;
  if (item.shape === "ellipse") {
    return `<ellipse cx="${ix + item.w / 2}" cy="${iy + item.h / 2}" rx="${Math.max(1, item.w / 2 - strokeWidth / 2)}" ry="${Math.max(1, item.h / 2 - strokeWidth / 2)}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" opacity="${opacity}"/>`;
  }
  if (item.shape === "line" || item.shape === "arrow") {
    return `<line x1="${ix + 8}" y1="${iy + item.h / 2}" x2="${ix + item.w - 8}" y2="${iy + item.h / 2}" stroke="${stroke}" stroke-width="${strokeWidth}" stroke-linecap="round" opacity="${opacity}" ${item.shape === "arrow" ? 'marker-end="url(#export-arrow)"' : ""}/>`;
  }
  return `<rect x="${ix}" y="${iy}" width="${item.w}" height="${item.h}" rx="${item.cornerRadius ?? 10}" fill="${fill}" stroke="${stroke}" stroke-width="${strokeWidth}" opacity="${opacity}"/>`;
}

function loadDesignState() {
  try {
    const parsed = JSON.parse(localStorage.getItem(DESIGN_STORAGE_KEY) || "{}");
    return {
      objects: Array.isArray(parsed.objects) ? parsed.objects : [],
      strokes: Array.isArray(parsed.strokes) ? parsed.strokes : [],
      drawing: typeof parsed.drawing === "string" ? parsed.drawing : "",
      zoom: Number(parsed.zoom) || 1,
      didFit: Boolean(parsed.didFit),
    };
  } catch {
    return { objects: [], strokes: [], drawing: "", zoom: 1, didFit: false };
  }
}

function stagePoint(event, surface) {
  const rect = surface.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * DESIGN_WIDTH,
    y: ((event.clientY - rect.top) / rect.height) * DESIGN_HEIGHT,
  };
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeAngle(value) {
  const angle = Number(value) || 0;
  return Math.round(((angle % 360) + 360) % 360);
}

function isTypingTarget(target) {
  const element = target instanceof Element ? target : null;
  return Boolean(element && (element.closest("input, textarea, select") || element.isContentEditable));
}

function placeCaretAtEnd(element) {
  if (!element || !window.getSelection || !document.createRange) return;
  const range = document.createRange();
  range.selectNodeContents(element);
  range.collapse(false);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

function normalizedRect(rect) {
  const x = Math.min(rect.startX, rect.currentX);
  const y = Math.min(rect.startY, rect.currentY);
  return {
    x,
    y,
    w: Math.abs(rect.currentX - rect.startX),
    h: Math.abs(rect.currentY - rect.startY),
  };
}

function rectsIntersect(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function strokeIntersectsRect(stroke, rect) {
  return stroke.points.some((point) => point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h);
}

function smoothPath(points) {
  if (!points.length) return "";
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`;
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let index = 1; index < points.length - 1; index += 1) {
    const midX = (points[index].x + points[index + 1].x) / 2;
    const midY = (points[index].y + points[index + 1].y) / 2;
    path += ` Q ${points[index].x} ${points[index].y} ${midX} ${midY}`;
  }
  const last = points[points.length - 1];
  path += ` L ${last.x} ${last.y}`;
  return path;
}

function boundsForObjects(objects) {
  const left = Math.min(...objects.map((item) => item.x));
  const top = Math.min(...objects.map((item) => item.y));
  const right = Math.max(...objects.map((item) => item.x + item.w));
  const bottom = Math.max(...objects.map((item) => item.y + item.h));
  return { x: left, y: top, w: right - left, h: bottom - top };
}

function cleanFileName(value) {
  return String(value || "export").replace(/[\\/:*?"<>|]+/g, "-").trim() || "export";
}

function downloadBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function buildExportSvg(frame, designState = null) {
  const storage = designState || JSON.parse(localStorage.getItem(DESIGN_STORAGE_KEY) || "{}");
  const objects = Array.isArray(storage.objects) ? storage.objects : [];
  const strokes = Array.isArray(storage.strokes) ? storage.strokes : [];
  const x = Number(frame.x || 0);
  const y = Number(frame.y || 0);
  const w = Math.max(1, Number(frame.w || 1));
  const h = Math.max(1, Number(frame.h || 1));
  const inFrame = (item) => item.x >= x && item.y >= y && item.x <= x + w && item.y <= y + h;
  const objectMarkup = objects
    .filter((item) => item.id !== frame.id && inFrame(item))
    .map((item) => {
      const ix = Number(item.x || 0) - x;
      const iy = Number(item.y || 0) - y;
      if (item.type === "image" && item.src) {
        return `<image href="${escapeHtml(item.src)}" x="${ix}" y="${iy}" width="${item.w}" height="${item.h}" preserveAspectRatio="xMidYMid slice"/>`;
      }
      if (item.type === "text") {
        return `<text x="${ix + 12}" y="${iy + 32}" fill="${escapeHtml(item.stroke || "#0f172a")}" font-size="22" font-family="Arial, sans-serif" font-weight="800">${escapeHtml(item.text || "")}</text>`;
      }
      return `<rect x="${ix}" y="${iy}" width="${item.w}" height="${item.h}" rx="10" fill="${escapeHtml(item.fill || "transparent")}" stroke="${escapeHtml(item.stroke || "#2563eb")}" stroke-width="2"/>`;
    })
    .join("");
  const strokeMarkup = strokes
    .filter((stroke) => stroke.points.some((point) => point.x >= x && point.x <= x + w && point.y >= y && point.y <= y + h))
    .map((stroke) => `<path d="${smoothPath(stroke.points.map((point) => ({ x: point.x - x, y: point.y - y })))}" fill="none" stroke="${escapeHtml(stroke.color || "#2563eb")}" stroke-width="${stroke.width || 5}" stroke-linecap="round" stroke-linejoin="round" opacity="${stroke.mode === "marker" ? "0.38" : "1"}"/>`)
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><rect width="100%" height="100%" fill="${escapeHtml(frame.fill || "#ffffff")}"/>${objectMarkup}${strokeMarkup}</svg>`;
}

function activateTab(target, options = {}) {
  if (!target) return;
  const shouldReveal = options.reveal !== false;
  localStorage.setItem(ACTIVE_TAB_KEY, target);
  document.querySelectorAll(".tab").forEach((item) => item.classList.toggle("is-active", item.dataset.tab === target));
  document.querySelectorAll(".tool-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${target}`);
  });
  if (shouldReveal) scrollActiveMobileTool();
}

function scrollActiveMobileTool() {
  if (!window.matchMedia("(max-width: 760px)").matches) return;
  const panel = document.querySelector(".tool-panel.is-active");
  if (!panel) return;
  panel.classList.remove("is-mobile-panel-enter");
  void panel.offsetWidth;
  panel.classList.add("is-mobile-panel-enter");
  window.requestAnimationFrame(() => {
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

function restoreActiveTab() {
  const requested = new URLSearchParams(window.location.search).get("tool");
  if (requested && document.getElementById(`tab-${requested}`)) {
    activateTab(requested, { reveal: false });
    return;
  }
  const saved = localStorage.getItem(ACTIVE_TAB_KEY);
  if (saved && document.getElementById(`tab-${saved}`)) {
    activateTab(saved, { reveal: false });
  }
}

function setupTemplatePicker(form) {
  const select = form.querySelector("[data-template-select]");
  const picker = form.querySelector("[data-template-picker]");
  if (!select || !picker) return;
  const buttons = [...picker.querySelectorAll("[data-template-value]")];
  const choose = (value) => {
    select.value = value;
    buttons.forEach((button) => button.classList.toggle("is-selected", button.dataset.templateValue === value));
  };
  buttons.forEach((button) => button.addEventListener("click", () => choose(button.dataset.templateValue)));
  choose(select.value || (buttons[0] && buttons[0].dataset.templateValue));
}

document.addEventListener("click", async (event) => {
  const actionToggle = event.target.closest("[data-job-actions-toggle]");
  if (actionToggle) {
    event.preventDefault();
    const actions = actionToggle.closest("[data-job-actions]");
    const open = !actions?.classList.contains("is-open");
    closeJobActionMenus(actions);
    if (actions) {
      actions.classList.toggle("is-open", open);
      actionToggle.setAttribute("aria-expanded", open ? "true" : "false");
    }
    return;
  }

  if (!event.target.closest("[data-job-actions]")) {
    closeJobActionMenus();
  }

  const deleteButton = event.target.closest("[data-delete-url]");
  if (deleteButton) {
    event.preventDefault();
    const card = deleteButton.closest("[data-job-id]");
    const jobId = card ? card.dataset.jobId : "";
    closeJobActionMenus();
    const confirmed = await confirmJobDelete(card);
    if (!confirmed) return;
    const deleteLabel = deleteButton.querySelector("span");
    const originalText = deleteLabel ? deleteLabel.textContent : deleteButton.textContent;
    deleteButton.disabled = true;
    if (deleteLabel) deleteLabel.textContent = i18n.deleting || "Deleting";
    else deleteButton.textContent = i18n.deleting || "Deleting";
    try {
      const response = await fetch(deleteButton.dataset.deleteUrl, {
        method: "POST",
        headers: {
          "X-CSRFToken": csrfToken(),
          "X-Requested-With": "XMLHttpRequest",
        },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || i18n.delete_failed || "Could not delete task");
      }
      if (jobId) {
        jobs.delete(jobId);
        polling.delete(jobId);
      }
      card?.remove();
      updateJobsPanel();
      if (payload.account_stats) updateAccountStats(payload.account_stats);
    } catch (error) {
      deleteButton.disabled = false;
      if (deleteLabel) deleteLabel.textContent = originalText;
      else deleteButton.textContent = originalText;
      window.alert(error.message || String(error));
    }
    return;
  }

  const button = event.target.closest("[data-repeat-url]");
  if (!button) return;
  event.preventDefault();
  closeJobActionMenus();
  const repeatLabel = button.querySelector("span");
  const originalText = repeatLabel ? repeatLabel.textContent : button.textContent;
  button.disabled = true;
  if (repeatLabel) repeatLabel.textContent = i18n.repeating || "Repeating";
  else button.textContent = i18n.repeating || "Repeating";
  try {
    const response = await fetch(button.dataset.repeatUrl, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || i18n.repeat_failed || "Could not repeat task");
    }
    renderJob(payload.job);
    pollJob(payload.job.id);
  } catch (error) {
    renderJob({
      id: `error-${Date.now()}`,
      title: i18n.repeat_error || "Repeat error",
      status: "failed",
      progress: 100,
      message: i18n.error || "Error",
      error: error.message || String(error),
      outputs: [],
    });
  } finally {
    button.disabled = false;
    if (repeatLabel) repeatLabel.textContent = originalText;
    else button.textContent = originalText;
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeJobActionMenus();
});

function updateAccountStats(stats) {
  Object.entries(stats || {}).forEach(([key, value]) => {
    const node = document.querySelector(`[data-account-stat="${cssEscape(key)}"]`);
      if (node) node.textContent = String(value);
  });
  const storageBar = document.querySelector(".storage-card i b");
  if (storageBar && stats.storage_percent !== undefined) {
    storageBar.style.width = `${Number(stats.storage_percent || 0)}%`;
  }
}

function renderInitialJobs() {
  const element = document.getElementById("initial-jobs");
  if (!element || !element.textContent.trim()) return;
  try {
    const initialJobs = JSON.parse(element.textContent);
    [...initialJobs].reverse().forEach((job) => {
      renderJob(job);
      if (job.status === "queued" || job.status === "running") {
        pollJob(job.id);
      }
    });
  } catch {
    return;
  }
}

function updatePreview(input) {
  const field = input.closest(".file-field");
  const meta = field ? field.querySelector(".file-meta") : null;
  const preview = document.getElementById(input.dataset.preview);
  if (!preview) return;
  if (preview.dataset.objectUrl) {
    URL.revokeObjectURL(preview.dataset.objectUrl);
    delete preview.dataset.objectUrl;
  }
  preview.classList.remove("is-document-preview", "is-pdf-preview", "is-text-preview", "is-card-preview");
  preview.innerHTML = "";

  const file = input.files && input.files[0];
  if (!file) {
    if (field) field.classList.remove("is-ready");
    if (meta) meta.textContent = i18n.file_not_selected || "No file selected";
    preview.innerHTML = `<span>${escapeHtml(i18n.preview_file || "File preview")}</span>`;
    return;
  }

  if (field) field.classList.add("is-ready");
  updateCompatibleFormats(input, file);
  if (meta) {
    meta.innerHTML = `
      <strong>${escapeHtml(file.name)}</strong>
      <small>${escapeHtml(readableSize(file.size))}${file.type ? ` · ${escapeHtml(file.type)}` : ""}</small>
    `;
  }

  const url = URL.createObjectURL(file);
  preview.dataset.objectUrl = url;
  if (file.type.startsWith("image/")) {
    const image = document.createElement("img");
    image.src = url;
    image.alt = file.name;
    preview.appendChild(image);
    return;
  }
  if (file.type.startsWith("video/")) {
    const video = document.createElement("video");
    video.src = url;
    video.controls = true;
    video.muted = true;
    video.playsInline = true;
    preview.appendChild(video);
    return;
  }
  if (isPdfFile(file)) {
    preview.classList.add("is-document-preview", "is-pdf-preview");
    const frame = document.createElement("iframe");
    frame.src = `${url}#toolbar=0&navpanes=0`;
    frame.title = file.name;
    preview.appendChild(frame);
    return;
  }
  if (isTextPreviewFile(file)) {
    preview.classList.add("is-document-preview", "is-text-preview");
    const reader = new FileReader();
    const pre = document.createElement("pre");
    pre.textContent = i18n.loading || "Loading";
    preview.appendChild(pre);
    reader.addEventListener("load", () => {
      const text = String(reader.result || "");
      pre.textContent = text.slice(0, 12000) || file.name;
      if (text.length > 12000) {
        const note = document.createElement("small");
        note.textContent = "Preview truncated. Full document will be checked.";
        preview.appendChild(note);
      }
    });
    reader.addEventListener("error", () => {
      previewDocumentCard(preview, file, "Text preview is unavailable. The document will still be processed.");
    });
    reader.readAsText(file);
    return;
  }
  if (input.dataset.documentPreviewEndpoint && isServerExtractableDocument(file)) {
    previewServerDocument(input, preview, file);
    return;
  }
  previewDocumentCard(preview, file, documentPreviewHint(file));
}

function isPdfFile(file) {
  const name = (file.name || "").toLowerCase();
  return file.type === "application/pdf" || name.endsWith(".pdf");
}

function isTextPreviewFile(file) {
  const name = (file.name || "").toLowerCase();
  const type = (file.type || "").toLowerCase();
  return type.startsWith("text/") || [".txt", ".md", ".csv", ".json", ".html", ".htm"].some((ext) => name.endsWith(ext));
}

function isServerExtractableDocument(file) {
  const name = (file.name || "").toLowerCase();
  return [".docx", ".rtf", ".doc"].some((ext) => name.endsWith(ext));
}

async function previewServerDocument(input, preview, file) {
  preview.classList.add("is-document-preview", "is-text-preview");
  preview.innerHTML = `<pre>${escapeHtml(i18n.loading || "Loading")}</pre>`;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch(input.dataset.documentPreviewEndpoint, {
      method: "POST",
      body: formData,
      headers: {
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Preview unavailable");
    }
    renderExtractedDocumentPreview(preview, {
      name: payload.name || file.name,
      words: Number(payload.words || 0),
      text: payload.text || file.name,
      type: fileExtensionLabel(file),
    });
    if (payload.truncated) {
      const note = document.createElement("small");
      note.textContent = "Preview truncated. Full document will be checked.";
      preview.appendChild(note);
    }
  } catch (error) {
    previewDocumentCard(preview, file, error.message || documentPreviewHint(file));
  }
}

function renderExtractedDocumentPreview(preview, payload) {
  preview.innerHTML = "";
  const header = document.createElement("div");
  header.className = "document-text-preview-head";
  header.innerHTML = `
    <span class="document-preview-type">${escapeHtml(payload.type || "DOC")}</span>
    <strong>${escapeHtml(payload.name || "Document")}</strong>
    <span>${Number(payload.words || 0).toLocaleString("ru-RU")} words</span>
  `;
  const page = document.createElement("article");
  page.className = "document-extracted-page";
  const paragraphs = String(payload.text || "")
    .split(/\n{2,}/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (!paragraphs.length) {
    const empty = document.createElement("p");
    empty.textContent = payload.name || "Document";
    page.appendChild(empty);
  } else {
    paragraphs.slice(0, 80).forEach((paragraph, index) => {
      const element = document.createElement(index === 0 && paragraph.length < 140 ? "h4" : "p");
      element.textContent = paragraph;
      page.appendChild(element);
    });
  }
  preview.append(header, page);
}

function documentPreviewHint(file) {
  const name = (file.name || "").toLowerCase();
  if (name.endsWith(".docx")) return "DOCX preview will be extracted during the check.";
  if (name.endsWith(".rtf")) return "RTF preview will be extracted during the check.";
  return "Preview is not available in browser. The file will still be processed.";
}

function previewDocumentCard(preview, file, hint) {
  preview.classList.add("is-document-preview", "is-card-preview");
  preview.innerHTML = `
    <article class="document-preview-card">
      <b>${escapeHtml(fileExtensionLabel(file))}</b>
      <strong>${escapeHtml(file.name || "Document")}</strong>
      <span>${escapeHtml(readableSize(file.size))}${file.type ? ` · ${escapeHtml(file.type)}` : ""}</span>
      <small>${escapeHtml(hint)}</small>
    </article>
  `;
}

function fileExtensionLabel(file) {
  const name = String(file.name || "");
  const ext = name.includes(".") ? name.split(".").pop() : "";
  return (ext || "file").slice(0, 5).toUpperCase();
}

function updateCompatibleFormats(input, file) {
  if (!input.name || input.name !== "file") return;
  const form = input.closest("form");
  const picker = form ? form.querySelector("[data-format-picker]") : null;
  if (!picker || typeof picker.setFormatKind !== "function") return;
  picker.setFormatKind(fileKind(file));
}

function fileKind(file) {
  const type = (file.type || "").toLowerCase();
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("image/")) return "image";
  const name = (file.name || "").toLowerCase();
  if (/\.(mp4|webm|mov|m4v|mkv|avi|wmv|flv)$/i.test(name)) return "video";
  return "image";
}

function readableSize(size) {
  const units = ["B", "KB", "MB", "GB"];
  let amount = Number(size || 0);
  for (const unit of units) {
    if (amount < 1024 || unit === units[units.length - 1]) {
      return unit === "B" ? `${amount} B` : `${amount.toFixed(1)} ${unit}`;
    }
    amount /= 1024;
  }
  return `${size} B`;
}

async function pollJob(jobId) {
  if (polling.has(jobId)) return;
  polling.add(jobId);

  const tick = async () => {
    if (document.hidden) {
      window.setTimeout(tick, 12000);
      return;
    }
    try {
      const response = await fetch(`/api/jobs/${jobId}/`);
      if (!response.ok) throw new Error("status");
      const payload = await response.json();
      renderJob(payload.job);
      if (payload.job.status !== "completed" && payload.job.status !== "failed") {
        window.setTimeout(tick, payload.job.status === "queued" ? 8000 : 5000);
      } else {
        polling.delete(jobId);
      }
    } catch {
      window.setTimeout(tick, 10000);
    }
  };

  window.setTimeout(tick, 1200);
}

function renderJob(job) {
  jobs.set(job.id, job);
  const list = document.getElementById("jobs-list");
  if (!list) return;

  let card = list.querySelector(`[data-job-id="${cssEscape(job.id)}"]`);
  if (!card) {
    card = document.createElement("article");
    card.dataset.jobId = job.id;
    list.prepend(card);
  }

  card.className = `job-card ${job.status === "failed" ? "is-failed" : ""}`;
  card.dataset.jobStatus = job.status || "";
  card.innerHTML = `
    <div class="job-topline">
      <p class="job-title">${escapeHtml(job.title || i18n.task || "Task")}</p>
      <div class="job-top-actions">
        <span class="job-status">${escapeHtml(statusLabel(job.status))}</span>
        ${renderJobActionMenu(job)}
      </div>
    </div>
    <p class="job-message">
      <span>${escapeHtml(job.error || job.message || "")}</span>
      ${job.eta_text && job.status !== "completed" && job.status !== "failed" ? `<small class="job-eta">${escapeHtml(job.eta_text)}</small>` : ""}
    </p>
    ${renderAiMeta(job.ai)}
    <div class="progress" aria-label="progress">
      <span style="width: ${Number(job.progress || 0)}%"></span>
    </div>
    ${renderOutputs(job.outputs || [])}
  `;
  updateJobsPanel();
}

function renderJobActionMenu(job) {
  const actions = [];
  const access = window.STUDIO_ACCESS || {};
  const hasAccess = access.hasAccess === true;
  const checkoutUrl = access.checkoutUrl || "/billing/checkout/";
  if (job.detail_url) {
    actions.push(`<a class="job-action-item" href="${escapeHtml(job.detail_url)}" data-icon="external-link"><span>${escapeHtml(i18n.open || "Open")}</span></a>`);
  }
  if (job.repeatable && job.repeat_url) {
    actions.push(`<button class="job-action-item" type="button" data-repeat-url="${escapeHtml(job.repeat_url)}" data-icon="rotate-ccw"><span>${escapeHtml(i18n.repeat || "Repeat")}</span></button>`);
  }
  if ((job.outputs || []).length && job.download_all_url) {
    const href = hasAccess ? job.download_all_url : checkoutUrl;
    actions.push(`<a class="job-action-item" href="${escapeHtml(href)}" data-icon="download"><span>${escapeHtml(hasAccess ? (i18n.download_all || "Download all") : "Checkout")}</span></a>`);
  }
  if (job.delete_url && job.status !== "queued" && job.status !== "running") {
    actions.push(`<button class="job-action-item is-danger" type="button" data-delete-url="${escapeHtml(job.delete_url)}" data-icon="trash-2"><span>${escapeHtml(i18n.delete || "Delete")}</span></button>`);
  }
  if (!actions.length) return "";
  const label = escapeHtml(i18n.actions || "Actions");
  return `
    <div class="job-action-menu" data-job-actions>
      <button class="job-action-toggle" type="button" data-job-actions-toggle data-icon="settings" aria-label="${label}" aria-expanded="false">
        <span>${label}</span>
      </button>
      <div class="job-action-popover" role="menu">
        ${actions.join("")}
      </div>
    </div>
  `;
}

function closeJobActionMenus(except) {
  document.querySelectorAll("[data-job-actions].is-open").forEach((menu) => {
    if (except && menu === except) return;
    menu.classList.remove("is-open");
    menu.querySelector("[data-job-actions-toggle]")?.setAttribute("aria-expanded", "false");
  });
}

function confirmJobDelete(card) {
  const modal = ensureJobDeleteModal();
  const title = card?.querySelector(".job-title")?.textContent?.trim() || i18n.task || "Task";
  modal.querySelector("[data-job-delete-title]").textContent = i18n.delete_task_question || "Delete this task?";
  modal.querySelector("[data-job-delete-copy]").textContent = i18n.delete_confirm || "Delete this task and its files?";
  modal.querySelector("[data-job-delete-name]").textContent = title;
  modal.hidden = false;
  document.body.classList.add("job-delete-open");
  const confirm = modal.querySelector("[data-job-delete-confirm]");
  confirm.focus();

  return new Promise((resolve) => {
    const finish = (value) => {
      modal.hidden = true;
      document.body.classList.remove("job-delete-open");
      modal.removeEventListener("click", onClick);
      document.removeEventListener("keydown", onKeydown);
      resolve(value);
    };
    const onClick = (event) => {
      if (event.target.closest("[data-job-delete-confirm]")) finish(true);
      if (event.target.closest("[data-job-delete-cancel]")) finish(false);
    };
    const onKeydown = (event) => {
      if (event.key === "Escape") finish(false);
    };
    modal.addEventListener("click", onClick);
    document.addEventListener("keydown", onKeydown);
  });
}

function ensureJobDeleteModal() {
  let modal = document.querySelector("[data-job-delete-modal]");
  if (modal) return modal;
  modal = document.createElement("div");
  modal.className = "job-delete-modal";
  modal.dataset.jobDeleteModal = "";
  modal.hidden = true;
  modal.innerHTML = `
    <div class="job-delete-backdrop" data-job-delete-cancel></div>
    <section class="job-delete-dialog" role="dialog" aria-modal="true" aria-labelledby="job-delete-title">
      <span>${escapeHtml(i18n.delete_confirmation || "Delete confirmation")}</span>
      <h2 id="job-delete-title" data-job-delete-title>${escapeHtml(i18n.delete_task_question || "Delete this task?")}</h2>
      <p data-job-delete-copy>${escapeHtml(i18n.delete_confirm || "Delete this task and its files?")}</p>
      <div class="job-delete-target">
        <small>${escapeHtml(i18n.task || "Task")}</small>
        <b data-job-delete-name></b>
      </div>
      <footer>
        <button type="button" data-job-delete-cancel>${escapeHtml(i18n.cancel || "Cancel")}</button>
        <button class="is-danger" type="button" data-job-delete-confirm>${escapeHtml(i18n.delete || "Delete")}</button>
      </footer>
    </section>
  `;
  document.body.appendChild(modal);
  return modal;
}

function updateJobsPanel() {
  const list = document.getElementById("jobs-list");
  if (!list) return;
  const empty = document.getElementById("empty-jobs");
  const counter = document.getElementById("jobs-count");
  const filter = localStorage.getItem(JOB_FILTER_KEY) || "all";
  const cards = [...list.querySelectorAll("[data-job-id]")];
  let visibleCount = 0;
  cards.forEach((card) => {
    const show = jobMatchesFilter(card.dataset.jobStatus || "", filter);
    visibleCount += show ? 1 : 0;
    card.hidden = !show || visibleCount > 5;
  });
  if (empty) empty.hidden = visibleCount > 0;
  if (counter) counter.textContent = filter === "all" ? String(jobs.size) : `${visibleCount}/${jobs.size}`;
}

function jobMatchesFilter(status, filter) {
  if (filter === "active") return status === "queued" || status === "running";
  if (filter === "completed") return status === "completed";
  if (filter === "failed") return status === "failed" || status === "cancelled";
  return true;
}

function renderOutputs(outputs) {
  if (!outputs.length) return "";
  const access = window.STUDIO_ACCESS || {};
  const hasAccess = access.hasAccess === true;
  const checkoutUrl = access.checkoutUrl || "/billing/checkout/";
  return `
    <div class="output-scroll" aria-label="Task outputs">
      <div class="output-list">
        ${outputs
          .map(
            (output) => {
              const href = hasAccess ? output.url : checkoutUrl;
              const downloadAttr = hasAccess ? " download" : "";
              return `
              <div class="output-link-wrap">
                <a class="output-link" href="${escapeHtml(href)}"${downloadAttr}>
                  <span>${escapeHtml(output.label || output.name)}</span>
                  <small>${escapeHtml(output.size_text || "")}</small>
                </a>
                ${output.can_edit_design ? `<button class="output-link" type="button" data-edit-design-url="${escapeHtml(output.edit_design_url)}"><span>${escapeHtml(i18n.edit_design || "Edit design")}</span><small>Design Mode</small></button>` : ""}
                ${output.can_edit_video ? `<button class="output-link" type="button" data-edit-video-url="${escapeHtml(output.edit_video_url)}"><span>${escapeHtml(i18n.edit_video || "Edit video")}</span><small>${escapeHtml(i18n.video_editor_nav || "Video Editor")}</small></button>` : ""}
              </div>
            `;
            },
          )
          .join("")}
      </div>
    </div>
  `;
}

function aiMetaName(name) {
  const key = `ai_${String(name || "")}`;
  return i18n[key] || String(name || "").replace(/_/g, " ");
}

function friendlyAiReason(reason) {
  const value = String(reason || "").trim();
  if (!value) return "";
  const lower = value.toLowerCase();
  const lang = String(document.documentElement.lang || "en").slice(0, 2);
  const pick = (items) => items[lang] || items.en;
  if (lower.includes("insufficient_quota") || lower.includes("insufficient quota") || lower.includes("exceeded your current quota") || lower.includes("error code: 429")) {
    return pick({
      en: "OpenAI quota is exhausted, local fallback used",
      ru: "Лимит OpenAI исчерпан, использован локальный fallback",
      uk: "Ліміт OpenAI вичерпано, використано локальний fallback",
    });
  }
  if (lower.includes("openai is not configured")) {
    return pick({
      en: "OpenAI is not configured, local fallback used",
      ru: "OpenAI не настроен, использован локальный fallback",
      uk: "OpenAI не налаштовано, використано локальний fallback",
    });
  }
  if (lower.includes("no usable") || lower.includes("returned no cues")) {
    return pick({
      en: "OpenAI returned no usable result, local fallback used",
      ru: "OpenAI не вернул подходящий результат, использован локальный fallback",
      uk: "OpenAI не повернув придатний результат, використано локальний fallback",
    });
  }
  if (lower.includes("error code:") || lower.includes("traceback") || lower.includes("{'error'") || lower.includes('"error"')) {
    return pick({
      en: "AI unavailable, local fallback used",
      ru: "AI недоступен, использован локальный fallback",
      uk: "AI недоступний, використано локальний fallback",
    });
  }
  return value.replace(/https?:\/\/\S+/g, "").replace(/\s+/g, " ").trim().slice(0, 140);
}

function renderAiMeta(ai) {
  if (!ai || typeof ai !== "object") return "";
  const items = Object.entries(ai)
    .map(([rawName, meta]) => {
      if (!meta || typeof meta !== "object") return "";
      const status = String(meta.status || "");
      const reason = friendlyAiReason(meta.fallback_reason || meta.reason || "");
      const label = status === "used" ? (i18n.ai_used || "AI used") : status === "fallback" ? (i18n.ai_fallback || "AI fallback") : (i18n.ai_unknown || "AI");
      const detailParts = [aiMetaName(rawName)];
      if (status === "used" && meta.model) detailParts.push(String(meta.model));
      const name = detailParts.filter(Boolean).join(" · ");
      return `<span class="ai-meta-chip is-${escapeHtml(status || "unknown")}" title="${escapeHtml(reason)}"><b>${escapeHtml(label)}</b><small>${escapeHtml(name.replace(/_/g, " "))}</small></span>`;
    })
    .filter(Boolean);
  return items.length ? `<div class="ai-meta-row" aria-label="AI status">${items.join("")}</div>` : "";
}

document.addEventListener("click", async (event) => {
  const button = event.target instanceof Element ? event.target.closest("[data-edit-design-url]") : null;
  if (!button || button.closest(".detail-page")) return;
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
    button.textContent = original || i18n.edit_design || "Edit design";
    button.dataset.loading = "0";
    alert(error.message || "Design import failed");
  }
});

document.addEventListener("click", async (event) => {
  const button = event.target instanceof Element ? event.target.closest("[data-edit-video-url]") : null;
  if (!button || button.closest(".detail-page")) return;
  event.preventDefault();
  if (button.dataset.loading === "1") return;
  const original = button.textContent;
  button.dataset.loading = "1";
  button.textContent = "Opening...";
  try {
    const response = await fetch(button.dataset.editVideoUrl || "", {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await response.json();
    if (!response.ok || !data.video_editor_url) throw new Error(data.error || "Video import failed");
    window.location.href = data.video_editor_url;
  } catch (error) {
    button.textContent = original || i18n.edit_video || "Edit video";
    button.dataset.loading = "0";
    alert(error.message || "Video import failed");
  }
});

function statusLabel(status) {
  return {
    queued: i18n.queued || "Queued",
    running: i18n.running || "In progress",
    completed: i18n.completed || "Done",
    failed: i18n.failed || "Failed",
    cancelled: i18n.cancelled || "Cancelled",
  }[status] || status;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }
  return String(value).replace(/["\\]/g, "\\$&");
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  if (match) return decodeURIComponent(match[1]);
  const input = document.querySelector("input[name='csrfmiddlewaretoken']");
  return input ? input.value : "";
}
