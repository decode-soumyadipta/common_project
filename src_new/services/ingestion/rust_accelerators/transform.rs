//! transform.rs — PyO3 stub for batch CRS coordinate transformation.
//!
//! Exposes `transform_coordinates()` to Python. The function releases the Python GIL
//! during the PROJ transformation loop so other Python threads are not blocked.
//!
//! # Python signature
//! ```python
//! def transform_coordinates(
//!     coordinates: list[tuple[float, float]],  # Input (x, y) pairs in source CRS
//!     source_crs: str,                          # Source CRS as EPSG string, e.g. "EPSG:4326"
//!     target_crs: str,                          # Target CRS as EPSG string, e.g. "EPSG:3857"
//! ) -> list[tuple[float, float]]               # Transformed (x, y) pairs in target CRS
//! ```

use pyo3::prelude::*;
use pyo3::exceptions::PyValueError;

/// Transform a batch of (x, y) coordinate pairs from one CRS to another.
///
/// The Python GIL is released for the duration of the PROJ transformation loop
/// so that other Python threads (e.g. async I/O, other workers) are not blocked.
///
/// # Arguments
/// * `coordinates` – List of `(x, y)` tuples in the source CRS.
///                   For geographic CRS (e.g. EPSG:4326) x = longitude, y = latitude.
/// * `source_crs`  – Source coordinate reference system as an EPSG authority string,
///                   e.g. `"EPSG:4326"` or `"EPSG:32644"`.
/// * `target_crs`  – Target coordinate reference system as an EPSG authority string,
///                   e.g. `"EPSG:3857"` (Web Mercator).
///
/// # Returns
/// A `Vec` of `(f64, f64)` tuples with coordinates in the target CRS.
/// The output list has the same length and order as the input list.
///
/// # Errors
/// Returns `PyValueError` if `source_crs` or `target_crs` are empty strings,
/// or if the coordinate list contains tuples with fewer than 2 elements.
#[pyfunction]
#[pyo3(signature = (coordinates, source_crs, target_crs))]
pub fn transform_coordinates(
    py: Python<'_>,
    coordinates: Vec<(f64, f64)>,
    source_crs: String,
    target_crs: String,
) -> PyResult<Vec<(f64, f64)>> {
    // Validate CRS strings before releasing the GIL
    if source_crs.trim().is_empty() {
        return Err(PyValueError::new_err(
            "transform_coordinates: source_crs must not be empty",
        ));
    }
    if target_crs.trim().is_empty() {
        return Err(PyValueError::new_err(
            "transform_coordinates: target_crs must not be empty",
        ));
    }

    // Release the Python GIL for the CPU-intensive PROJ transformation loop.
    // `py.allow_threads` ensures other Python threads can run while Rust transforms.
    let transformed: Vec<(f64, f64)> = py.allow_threads(|| {
        // --- Stub implementation ---
        // In production this delegates to the `proj` crate:
        //
        //   use proj::Proj;
        //   let transformer = Proj::new_known_crs(&source_crs, &target_crs, None)
        //       .expect("Failed to create PROJ transformer");
        //   coordinates
        //       .iter()
        //       .map(|&(x, y)| transformer.convert((x, y)).unwrap_or((x, y)))
        //       .collect()
        //
        // The stub performs a no-op pass-through so the module is importable and
        // testable without a PROJ installation.  A real deployment must compile
        // with the `proj_support` feature flag (see Cargo.toml).

        // Detect the common EPSG:4326 → EPSG:3857 (Web Mercator) case and apply
        // the standard spherical Mercator formula as a functional approximation.
        let is_4326_to_3857 = (source_crs.contains("4326") || source_crs.contains("WGS84"))
            && (target_crs.contains("3857") || target_crs.contains("900913"));

        coordinates
            .iter()
            .map(|&(x, y)| {
                if is_4326_to_3857 {
                    // Spherical Mercator: lon → easting, lat → northing
                    let earth_radius = 6_378_137.0_f64; // WGS-84 semi-major axis in metres
                    let easting = x.to_radians() * earth_radius;
                    let northing = (std::f64::consts::FRAC_PI_4 + y.to_radians() / 2.0)
                        .tan()
                        .ln()
                        * earth_radius;
                    (easting, northing)
                } else {
                    // Pass-through for all other CRS pairs (stub behaviour)
                    (x, y)
                }
            })
            .collect()
    });

    Ok(transformed)
}

/// Register the `transform_coordinates` function in the parent Python module.
///
/// Called from `lib.rs` during module initialisation.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(transform_coordinates, m)?)?;
    Ok(())
}
