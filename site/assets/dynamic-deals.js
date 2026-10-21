// Remove stale/elapsed records even if a scheduled build fails. No network or analytics.
(() => {
  const update = () => {
    for (const section of document.querySelectorAll('#current-deals')) {
      for (const item of section.querySelectorAll('[data-hide-at]')) {
        const deadline = Date.parse(item.dataset.hideAt);
        item.hidden = !Number.isFinite(deadline) || Date.now() >= deadline;
      }
      const empty = section.querySelector('.dynamic-empty');
      if (empty) empty.hidden = !!section.querySelector('[data-hide-at]:not([hidden])');
    }
  };
  update();
  setInterval(update, 60000);
})();
