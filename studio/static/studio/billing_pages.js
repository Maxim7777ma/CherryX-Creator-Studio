(() => {
  const CHECKOUT_STATE_KEY = "cherryx.checkout.state.v1";

  const readCheckoutState = () => {
    try {
      return JSON.parse(localStorage.getItem(CHECKOUT_STATE_KEY) || "{}") || {};
    } catch (error) {
      return {};
    }
  };

  const writeCheckoutState = (patch) => {
    try {
      localStorage.setItem(CHECKOUT_STATE_KEY, JSON.stringify({...readCheckoutState(), ...patch}));
    } catch (error) {
      // Local storage can be disabled; checkout still works without persistence.
    }
  };

  const bindLanguageSwitchers = () => {
    if (window.CXLanguageSwitcherReady) return;
    document.querySelectorAll(".language-switcher").forEach((switcher) => {
      const button = switcher.querySelector(".language-current");
      if (!button || switcher.dataset.billingBound === "1" || switcher.dataset.languageSwitcherBound === "1") return;
      switcher.dataset.billingBound = "1";
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
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        const open = switcher.classList.toggle("is-open");
        button.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) positionMenu();
      });
      switcher.addEventListener("click", (event) => event.stopPropagation());
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
  };

  const bindPasswordToggles = () => {
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
      const input = button.closest(".checkout-input-wrap")?.querySelector("input");
      if (!input || button.dataset.billingBound === "1") return;
      button.dataset.billingBound = "1";
      button.addEventListener("click", () => {
        const hidden = input.type === "password";
        input.type = hidden ? "text" : "password";
        button.dataset.icon = hidden ? "eye-off" : "eye";
        button.setAttribute("aria-label", hidden ? button.dataset.hideLabel : button.dataset.showLabel);
      });
    });
  };

  const bindPlanPicker = () => {
    const buttons = Array.from(document.querySelectorAll(".plan-button"));
    const planInput = document.getElementById("id_plan");
    if (!buttons.length || !planInput) return;

    const dueInput = document.getElementById("id_due");
    const total = document.getElementById("payment-total");
    const due = document.getElementById("payment-due");
    const list = document.getElementById("payment-list");
    const credit = document.getElementById("payment-credit");
    const badge = document.getElementById("summary-badge");
    const title = document.getElementById("summary-title");
    const copy = document.getElementById("summary-copy");

    const selectPlan = (button, persist = true) => {
      buttons.forEach((item) => {
        item.classList.remove("is-selected");
        item.setAttribute("aria-pressed", "false");
      });
      button.classList.add("is-selected");
      button.setAttribute("aria-pressed", "true");
      planInput.value = button.dataset.plan || "";
      if (dueInput) dueInput.value = button.dataset.dueCents || "";
      const dueText = button.dataset.due || button.dataset.price || "";
      if (total) total.textContent = dueText;
      if (due) due.textContent = dueText;
      if (list) list.textContent = button.dataset.list || button.dataset.price || "";
      if (credit) credit.textContent = button.dataset.credit || "0$";
      if (badge) badge.textContent = button.dataset.badge || "";
      if (title) title.textContent = `${button.dataset.name || ""} - ${button.dataset.priceLabel || ""}`.trim();
      if (copy) copy.textContent = button.dataset.headline || "";
      if (persist) writeCheckoutState({plan: button.dataset.plan || ""});
      if (persist && window.matchMedia("(max-width: 760px)").matches) {
        button.closest(".checkout-plan-option")?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
          inline: "center",
        });
      }
    };

    buttons.forEach((button) => {
      if (button.dataset.billingBound === "1") return;
      button.dataset.billingBound = "1";
      button.addEventListener("click", () => selectPlan(button));
    });

    const savedPlan = readCheckoutState().plan;
    const savedButton = savedPlan ? buttons.find((button) => button.dataset.plan === savedPlan) : null;
    if (savedButton) selectPlan(savedButton, false);
  };

  const bindCheckoutWizard = () => {
    const wizard = document.querySelector("[data-checkout-wizard]");
    if (!wizard || wizard.dataset.billingWizardBound === "1") return;
    wizard.dataset.billingWizardBound = "1";
    const form = wizard.querySelector("#checkout-form");
    const steps = Array.from(wizard.querySelectorAll("[data-checkout-step]"));
    const tabs = Array.from(wizard.querySelectorAll("[data-checkout-step-tab]"));
    if (!form || !steps.length) return;
    let current = 1;
    let emailCheckController = null;

    const field = (name) => form.querySelector(`[name="${name}"]`);

    const fieldShell = (input) => input?.closest(".field");
    const fieldError = (input) => input ? fieldShell(input)?.querySelector(`[data-field-error="${input.name}"]`) : null;
    const setFieldError = (input, message = "") => {
      if (!input) return;
      const shell = fieldShell(input);
      const error = fieldError(input);
      shell?.classList.toggle("has-error", Boolean(message));
      input.setAttribute("aria-invalid", message ? "true" : "false");
      if (error) {
        error.textContent = message;
        error.hidden = !message;
      }
    };
    const focusInvalid = (input) => {
      if (!input) return;
      input.focus({preventScroll: true});
      fieldShell(input)?.scrollIntoView({behavior: "smooth", block: "center"});
    };

    const accountFields = [field("name"), field("email"), field("password"), field("password_confirm")].filter(Boolean);
    const savedState = readCheckoutState();
    if (savedState.name && field("name")) field("name").value = savedState.name;
    if (savedState.email && field("email")) field("email").value = savedState.email;
    accountFields.forEach((input) => {
      input.addEventListener("input", () => {
        setFieldError(input);
        if (input.name === "name" || input.name === "email") {
          writeCheckoutState({[input.name]: input.value});
        }
      });
      input.addEventListener("blur", () => {
        if (fieldError(input)?.textContent) validateAccountStep(false);
      });
    });

    const validateAccountStep = async (checkEmail = true) => {
      const name = field("name");
      const email = field("email");
      const password = field("password");
      const confirm = field("password_confirm");

      setFieldError(name);
      setFieldError(email);
      setFieldError(password);
      setFieldError(confirm);

      const cleanName = (name?.value || "").trim().replace(/\s+/g, " ");
      if (name && !cleanName) {
        setFieldError(name, wizard.dataset.nameRequiredError || "Enter your name");
      } else if (name && (cleanName.length < 2 || cleanName.length > 90)) {
        setFieldError(name, wizard.dataset.nameError || "Name must be 2 to 90 characters");
      }

      const emailValue = (email?.value || "").trim().toLowerCase();
      const emailLooksReal = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(emailValue);
      if (email && !emailValue) {
        setFieldError(email, wizard.dataset.emailRequiredError || "Enter your email");
      } else if (email && !emailLooksReal) {
        setFieldError(email, wizard.dataset.emailError || "Enter a real email address");
      }

      const passwordValue = password?.value || "";
      const strongPassword = passwordValue.length >= 8 && /[A-Za-zА-Яа-яІіЇїЄєҐґ]/.test(passwordValue) && /\d/.test(passwordValue);
      if (password && !passwordValue) {
        setFieldError(password, wizard.dataset.passwordRequiredError || "Enter a password");
      } else if (password && !strongPassword) {
        setFieldError(password, wizard.dataset.passwordError || "Use 8+ characters with letters and numbers");
      }

      if (confirm && !confirm.value) {
        setFieldError(confirm, wizard.dataset.passwordConfirmRequiredError || "Repeat the password");
      } else if (confirm && passwordValue && confirm.value && passwordValue !== confirm.value) {
        setFieldError(confirm, wizard.dataset.passwordMatchError || "Passwords do not match");
      }

      let invalid = accountFields.find((input) => fieldError(input)?.textContent);
      if (invalid) {
        focusInvalid(invalid);
        return false;
      }

      if (checkEmail && email && emailValue && wizard.dataset.emailCheckUrl) {
        emailCheckController?.abort();
        emailCheckController = new AbortController();
        try {
          const url = `${wizard.dataset.emailCheckUrl}?email=${encodeURIComponent(emailValue)}`;
          const response = await fetch(url, {headers: {"Accept": "application/json"}, signal: emailCheckController.signal});
          if (response.ok) {
            const data = await response.json();
            if (data.exists) {
              setFieldError(email, wizard.dataset.emailExistsError || "An account with this email already exists");
              focusInvalid(email);
              return false;
            }
          }
        } catch (error) {
          if (error.name === "AbortError") return false;
        }
      }

      return true;
    };

    const stepFieldsValid = async (stepNumber) => {
      if (stepNumber === 2) return validateAccountStep();
      const step = wizard.querySelector(`[data-checkout-step="${stepNumber}"]`);
      if (!step) return true;
      return true;
    };

    const showStep = (stepNumber, reveal = true) => {
      current = Math.max(1, Math.min(steps.length, Number(stepNumber) || 1));
      writeCheckoutState({step: current});
      steps.forEach((step) => {
        const active = Number(step.dataset.checkoutStep) === current;
        step.hidden = !active;
        step.classList.toggle("is-active", active);
      });
      tabs.forEach((tab) => {
        const active = Number(tab.dataset.checkoutStepTab) === current;
        tab.classList.toggle("is-active", active);
        tab.setAttribute("aria-current", active ? "step" : "false");
      });
      if (reveal && window.matchMedia("(max-width: 760px)").matches) {
        wizard.scrollIntoView({behavior: "smooth", block: "start"});
      }
    };

    tabs.forEach((tab) => {
      tab.addEventListener("click", async () => {
        const target = Number(tab.dataset.checkoutStepTab) || 1;
        if (target > current && current === 1 && target > 2) {
          showStep(2);
          return;
        }
        if (target > current && current === 2 && !(await stepFieldsValid(2))) return;
        showStep(target);
      });
    });

    wizard.querySelectorAll("[data-checkout-next]").forEach((button) => {
      button.addEventListener("click", async () => {
        if (current === 2 && !(await stepFieldsValid(2))) return;
        showStep(current + 1);
      });
    });

    wizard.querySelectorAll("[data-checkout-back]").forEach((button) => {
      button.addEventListener("click", () => showStep(current - 1));
    });

    const savedStep = Math.max(1, Math.min(steps.length, Number(readCheckoutState().step) || 1));
    showStep(savedStep, false);
  };

  const bindPricingRail = () => {
    const rail = document.querySelector(".pricing-page .pricing-grid");
    if (!rail) return;
    const target = rail.querySelector(".price-card.is-focused") || rail.querySelector(".price-card.is-current");
    if (!target || !window.matchMedia("(max-width: 760px)").matches) return;
    requestAnimationFrame(() => {
      rail.scrollTo({
        left: Math.max(0, target.offsetLeft - rail.offsetLeft - 14),
        behavior: "smooth",
      });
    });
  };

  bindLanguageSwitchers();
  bindPasswordToggles();
  bindPlanPicker();
  bindCheckoutWizard();
  bindPricingRail();
})();
