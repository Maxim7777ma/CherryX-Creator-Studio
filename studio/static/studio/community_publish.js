(() => {
  const form = document.querySelector("[data-publish-form]");

  document.querySelectorAll("[data-custom-select]").forEach((select) => {
    const input = select.querySelector("[data-custom-select-input]");
    const button = select.querySelector("[data-custom-select-button]");
    const buttonLabel = button?.querySelector("[data-custom-select-label]");
    const menu = select.querySelector(".custom-select-menu");
    const options = [...select.querySelectorAll("[data-value]")];
    if (!input || !button || !menu || !options.length) return;
    const close = () => {
      select.classList.remove("is-open");
      button.setAttribute("aria-expanded", "false");
    };
    const open = () => {
      select.classList.add("is-open");
      button.setAttribute("aria-expanded", "true");
    };
    const syncLabel = () => {
      const active = options.find((option) => option.dataset.value === input.value) || options[0];
      if (!active) return;
      const label = active.dataset.label || active.textContent.trim();
      if (buttonLabel) {
        buttonLabel.textContent = label;
      } else {
        button.textContent = label;
      }
      if (active.dataset.icon) {
        button.dataset.icon = active.dataset.icon;
      } else {
        delete button.dataset.icon;
      }
      options.forEach((option) => {
        const selected = option === active;
        option.classList.toggle("is-selected", selected);
        option.setAttribute("aria-selected", selected ? "true" : "false");
      });
    };
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    menu.setAttribute("role", "listbox");
    menu.hidden = false;
    options.forEach((option) => option.setAttribute("role", "option"));
    syncLabel();
    button.addEventListener("click", () => {
      select.classList.contains("is-open") ? close() : open();
    });
    button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        open();
        (options.find((option) => option.classList.contains("is-selected")) || options[0])?.focus();
      }
    });
    options.forEach((option) => {
      option.addEventListener("click", () => {
        input.value = option.dataset.value || "";
        syncLabel();
        close();
        button.focus();
      });
      option.addEventListener("keydown", (event) => {
        const index = options.indexOf(option);
        if (event.key === "Escape") {
          close();
          button.focus();
        }
        if (event.key === "ArrowDown") {
          event.preventDefault();
          options[(index + 1) % options.length]?.focus();
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          options[(index - 1 + options.length) % options.length]?.focus();
        }
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          option.click();
        }
      });
    });
    document.addEventListener("click", (event) => {
      if (!select.contains(event.target)) close();
    });
    close();
  });

  if (!form) return;

  const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
  const usdRate = Number(form.dataset.usdRate || "0.01") || 0.01;
  const starsRate = Math.max(1, Number(form.dataset.starsRate || "10") || 10);

  document.querySelectorAll("[data-access-switch]").forEach((switcher) => {
    const input = switcher.querySelector("[data-access-input]");
    const buttons = [...switcher.querySelectorAll("button[data-value]")];
    const priceInput = document.querySelector("[data-price-input]");
    let rememberedPrice = Math.max(0, Number(priceInput?.value || "0") || 0);
    const sync = () => {
      buttons.forEach((button) => button.classList.toggle("is-active", button.dataset.value === input.value));
      const paid = input.value === "paid";
      form.classList.toggle("is-paid-work", paid);
      if (!paid && priceInput) {
        rememberedPrice = Math.max(rememberedPrice, Number(priceInput.value || "0") || 0);
        priceInput.value = "0";
        priceInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
      if (paid && priceInput && Number(priceInput.value || "0") <= 0 && rememberedPrice > 0) {
        priceInput.value = String(rememberedPrice);
        priceInput.dispatchEvent(new Event("input", { bubbles: true }));
      }
    };
    buttons.forEach((button) => {
      button.addEventListener("click", () => {
        input.value = button.dataset.value || "free";
        sync();
      });
    });
    sync();
  });

  const preview = document.querySelector("[data-publish-preview]");
  const showPreview = (file) => {
    if (!preview || !file) return;
    preview.innerHTML = "";
    preview.classList.add("has-local-preview");
    if (file.type.startsWith("image/")) {
      const image = document.createElement("img");
      image.src = URL.createObjectURL(file);
      image.alt = "";
      preview.append(image);
      const note = document.createElement("small");
      note.textContent = "Selected cover preview. This image will be used on the marketplace card.";
      preview.append(note);
      return;
    }
    if (file.type.startsWith("video/")) {
      const video = document.createElement("video");
      video.src = URL.createObjectURL(file);
      video.muted = true;
      video.controls = true;
      preview.append(video);
      const note = document.createElement("small");
      note.textContent = "Selected video preview. If you do not upload a cover, CherryX will create one from this material.";
      preview.append(note);
      return;
    }
    const fallback = document.createElement("span");
    fallback.textContent = `Selected file: ${file.name}`;
    preview.append(fallback);
  };

  document.querySelectorAll("[data-file-zone]").forEach((zone) => {
    const input = zone.querySelector("[data-file-input]");
    const name = zone.querySelector("[data-file-name]");
    input?.addEventListener("change", () => {
      const file = input.files && input.files[0];
      name.textContent = file ? file.name : "No file selected";
      zone.classList.toggle("has-file", Boolean(file));
      if (file) showPreview(file);
    });
    zone.addEventListener("dragover", (event) => {
      event.preventDefault();
      zone.classList.add("is-dragging");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
    zone.addEventListener("drop", (event) => {
      event.preventDefault();
      zone.classList.remove("is-dragging");
      if (!input || !event.dataTransfer?.files?.length) return;
      input.files = event.dataTransfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  const priceInput = document.querySelector("[data-price-input]");
  const priceOutput = document.querySelector("[data-price-usd]");
  const starsOutput = document.querySelector("[data-price-stars]");
  const syncPrice = () => {
    const value = Math.max(0, Number(priceInput?.value || "0") || 0);
    if (priceOutput) priceOutput.textContent = money.format(value * usdRate);
    if (starsOutput) starsOutput.textContent = `~${Math.max(0, Math.ceil(value / starsRate))} Stars`;
  };
  priceInput?.addEventListener("input", syncPrice);
  syncPrice();

  form.addEventListener("submit", () => {
    const button = form.querySelector("[data-publish-submit]");
    if (!button) return;
    button.classList.add("is-loading");
    button.disabled = true;
    button.textContent = "Publishing...";
  });
})();
