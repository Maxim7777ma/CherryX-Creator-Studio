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

  const body = document.body;
  const nameInput = document.querySelector("input[name='name']");
  const profileName = document.querySelector(".profile-preview strong");
  const originalName = profileName?.textContent || "";
  const avatarInput = document.querySelector("input[name='avatar_file']");
  const avatarUrlInput = document.querySelector("input[name='avatar_url']");
  const cropDataInput = document.querySelector("input[name='avatar_crop_data']");
  const modal = document.getElementById("avatar-crop-modal");
  const canvas = document.getElementById("avatar-crop-canvas");
  const zoom = document.getElementById("avatar-crop-zoom");
  const apply = document.getElementById("avatar-crop-apply");
  const cancel = document.getElementById("avatar-crop-cancel");
  const previews = document.querySelectorAll(".profile-preview-avatar, .photo-upload-surface img");

  const applyThemePreview = () => {
    const checked = document.querySelector("input[name='theme_mode']:checked");
    const mode = checked?.value || "light";
    body.classList.remove("theme-light", "theme-dark", "theme-soft");
    body.classList.add(`theme-${mode}`);
  };

  const applyAccentPreview = () => {
    const checked = document.querySelector("input[name='accent_color']:checked");
    const color = checked?.value || body.style.getPropertyValue("--raw-accent") || "#2563eb";
    body.style.setProperty("--blue", color);
    body.style.setProperty("--teal", color);
    body.style.setProperty("--raw-accent", color);
  };

  nameInput?.addEventListener("input", () => {
    if (profileName) profileName.textContent = nameInput.value.trim() || originalName;
  });

  avatarUrlInput?.addEventListener("input", () => {
    const value = avatarUrlInput.value.trim();
    if (!value) return;
    previews.forEach((preview) => {
      preview.src = value;
    });
  });

  document.querySelectorAll("input[name='theme_mode']").forEach((input) => {
    input.addEventListener("change", applyThemePreview);
  });
  document.querySelectorAll("input[name='accent_color']").forEach((input) => {
    input.addEventListener("change", applyAccentPreview);
  });

  if (!avatarInput || !cropDataInput || !modal || !canvas || !zoom || !apply || !cancel) return;

  const ctx = canvas.getContext("2d");
  const image = new Image();
  let offsetX = 0;
  let offsetY = 0;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;

  const draw = () => {
    if (!image.width || !image.height) return;
    const scale = Number(zoom.value || 1);
    const base = Math.max(canvas.width / image.width, canvas.height / image.height);
    const width = image.width * base * scale;
    const height = image.height * base * scale;
    const x = (canvas.width - width) / 2 + offsetX;
    const y = (canvas.height - height) / 2 + offsetY;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0b1220";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, x, y, width, height);
  };

  avatarInput.addEventListener("change", () => {
    const file = avatarInput.files && avatarInput.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      image.onload = () => {
        offsetX = 0;
        offsetY = 0;
        zoom.value = "1";
        modal.hidden = false;
        draw();
      };
      image.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

  zoom.addEventListener("input", draw);
  canvas.addEventListener("pointerdown", (event) => {
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    offsetX += event.clientX - lastX;
    offsetY += event.clientY - lastY;
    lastX = event.clientX;
    lastY = event.clientY;
    draw();
  });
  canvas.addEventListener("pointerup", () => {
    dragging = false;
  });
  cancel.addEventListener("click", () => {
    modal.hidden = true;
    avatarInput.value = "";
  });
  apply.addEventListener("click", () => {
    const data = canvas.toDataURL("image/jpeg", 0.92);
    cropDataInput.value = data;
    previews.forEach((preview) => {
      preview.src = data;
    });
    modal.hidden = true;
  });
})();
