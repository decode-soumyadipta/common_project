def normalize_crs(crs_value: str | None) -> str:
    if not crs_value:
        return "EPSG:4326"
    return crs_value.upper().replace("::", ":")

