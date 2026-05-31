(function () {
  const root = (window.OfflineGISModules = window.OfflineGISModules || {});
  const mapCesium = (root.mapCesium = root.mapCesium || {});

  function parseBoolean(value, fallbackValue) {
    if (typeof value === "boolean") {
      return value;
    }
    if (value === "true") {
      return true;
    }
    if (value === "false") {
      return false;
    }
    return Boolean(fallbackValue);
  }

  mapCesium.interactionHandlers = {
    parseBoolean: parseBoolean,
  };
})();
