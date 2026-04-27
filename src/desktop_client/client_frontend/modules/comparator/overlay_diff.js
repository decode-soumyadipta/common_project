(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const comparator = (root.comparator = root.comparator || {});

  function normalizeDividerPosition(rawValue) {
    if (!Number.isFinite(rawValue)) {
      return 0.5;
    }
    return Math.max(0.0, Math.min(1.0, Number(rawValue)));
  }

  comparator.overlayDiff = {
    normalizeDividerPosition: normalizeDividerPosition,
  };
})();
