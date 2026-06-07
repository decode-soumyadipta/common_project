//! lib.rs — PyO3 extension module entry point for rust_accelerators.
//!
//! This file wires together the `rasterize` and `transform` sub-modules and
//! registers their functions as a single Python extension module named
//! `rust_accelerators`.  When compiled with maturin, the resulting shared
//! library is importable from Python as:
//!
//! ```python
//! from rust_accelerators import rasterize_vectors, transform_coordinates
//! ```

use pyo3::prelude::*;

mod rasterize;
mod transform;

/// Python extension module: `rust_accelerators`
///
/// Exposes two public functions:
/// - `rasterize_vectors` — fast vector-to-raster burn using rusterize
/// - `transform_coordinates` — batch CRS transformation releasing the GIL
#[pymodule]
fn rust_accelerators(m: &Bound<'_, PyModule>) -> PyResult<()> {
    rasterize::register(m)?;
    transform::register(m)?;

    // Module-level metadata accessible from Python
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add(
        "__doc__",
        "PyO3 Rust accelerators for CPU-intensive geospatial operations \
         (vector rasterization and batch CRS transformation).",
    )?;

    Ok(())
}
