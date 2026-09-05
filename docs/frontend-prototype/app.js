/* Static design-board controller only. No backend calls or production behavior. */
(() => {
  const validRoutes = new Set(["home", "cases", "workspace", "analysis", "reviews", "settings"]);
  const params = new URLSearchParams(window.location.search);

  function showRoute(route, updateUrl = true) {
    const next = validRoutes.has(route) ? route : "home";
    document.body.dataset.route = next;
    document.querySelectorAll("[data-page]").forEach((page) => {
      page.classList.toggle("is-visible", page.dataset.page === next);
    });
    document.querySelectorAll("[data-route]").forEach((item) => {
      if (item.classList.contains("nav-link")) item.classList.toggle("is-active", item.dataset.route === next);
    });
    if (updateUrl) {
      const url = new URL(window.location.href);
      url.searchParams.set("page", next);
      history.replaceState({}, "", url);
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }

  function showToast(message) {
    const toast = document.querySelector(".toast");
    toast.querySelector("p").textContent = `${message}（视觉原型示意）`;
    toast.classList.add("is-visible");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => toast.classList.remove("is-visible"), 1800);
  }

  document.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => showRoute(button.dataset.route));
  });
  document.querySelectorAll("[data-open-route]").forEach((card) => {
    card.addEventListener("click", () => showRoute(card.dataset.openRoute));
  });
  document.querySelectorAll("[data-demo]").forEach((button) => {
    button.addEventListener("click", () => showToast(button.dataset.demo));
  });

  document.querySelectorAll("[data-settings-target]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-settings-target]").forEach((item) => item.classList.toggle("is-active", item === button));
      document.querySelectorAll("[data-settings-panel]").forEach((panel) => panel.classList.toggle("is-visible", panel.dataset.settingsPanel === button.dataset.settingsTarget));
    });
  });

  document.querySelectorAll("[data-theme-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      document.body.dataset.theme = button.dataset.themeChoice;
      document.querySelectorAll("[data-theme-choice]").forEach((item) => item.classList.toggle("is-selected", item === button));
    });
  });

  document.querySelectorAll('input[name="nav-layout"]').forEach((input) => {
    input.addEventListener("change", () => {
      document.body.dataset.nav = input.value;
      document.querySelectorAll(".layout-choice").forEach((choice) => choice.classList.toggle("is-selected", choice.contains(input)));
      showToast(input.value === "side" ? "工作区侧栏已启用，首页仍保持无侧栏" : "已切换为顶部导航");
    });
  });

  document.querySelectorAll("[data-density-choice]").forEach((button) => {
    button.addEventListener("click", () => {
      document.body.dataset.density = button.dataset.densityChoice;
      document.querySelectorAll("[data-density-choice]").forEach((item) => item.classList.toggle("is-active", item === button));
    });
  });

  const initialTheme = params.get("theme");
  if (["aurora", "ember", "tide"].includes(initialTheme)) document.body.dataset.theme = initialTheme;
  document.querySelectorAll("[data-theme-choice]").forEach((item) => item.classList.toggle("is-selected", item.dataset.themeChoice === document.body.dataset.theme));

  const navMode = params.get("nav") === "side" ? "side" : "top";
  document.body.dataset.nav = navMode;
  const navInput = document.querySelector(`input[name="nav-layout"][value="${navMode}"]`);
  if (navInput) {
    navInput.checked = true;
    document.querySelectorAll(".layout-choice").forEach((choice) => choice.classList.toggle("is-selected", choice.contains(navInput)));
  }

  showRoute(params.get("page") || "home", false);
})();
