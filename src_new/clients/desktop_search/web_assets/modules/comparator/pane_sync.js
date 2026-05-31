(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const comparator = (root.comparator = root.comparator || {});

  function makePaneSyncController(deps) {
    const requestFrame = (deps && deps.requestAnimationFrame) || window.requestAnimationFrame.bind(window);
    const cancelFrame = (deps && deps.cancelAnimationFrame) || window.cancelAnimationFrame.bind(window);

    let handle = null;

    function schedule(syncFn) {
      if (handle !== null) {
        return;
      }
      handle = requestFrame(function () {
        handle = null;
        if (typeof syncFn === "function") {
          syncFn();
        }
      });
    }

    function cancel() {
      if (handle !== null) {
        cancelFrame(handle);
        handle = null;
      }
    }

    return {
      schedule: schedule,
      cancel: cancel,
      hasPendingSync: function () {
        return handle !== null;
      },
    };
  }

  comparator.paneSync = {
    makePaneSyncController: makePaneSyncController,
  };
})();
