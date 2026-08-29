document.addEventListener("click", (event) => {
  const target = event.target;

  if (event.target.closest("#recalc-all")) {
    document.querySelectorAll(".block-body").forEach((el) => {
      window.htmx.trigger(el, "refresh");
    });
    return;
  }

  if (target.classList.contains("card-toggle")) {
    const card = target.closest(".card");
    if (!card) return;
    const more = card.querySelector(".more");
    if (!more) return;
    const hiddenNow = more.hasAttribute("hidden");
    if (hiddenNow) {
      more.removeAttribute("hidden");
      target.textContent = "afficher moins";
    } else {
      more.setAttribute("hidden", "");
      target.textContent = `afficher plus (${target.dataset.count})`;
    }
  }
});
