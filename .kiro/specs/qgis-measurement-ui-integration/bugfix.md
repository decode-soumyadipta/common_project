# Bugfix Requirements Document

## Introduction

This document addresses critical UI integration issues in the offline 3D GIS desktop application that prevent users from accessing measurement tools and viewing proper GIS status information. The application has implemented measurement tool functionality (distance, area, volume, viewshed, slope/aspect, shadow height) but the toolbar buttons are not properly wired to trigger these tools. Additionally, the status bar footer displays platform hardware information instead of essential GIS data like real-time cursor coordinates, CRS information, and progress indicators.

These issues significantly impact the usability of the application, as users cannot perform measurements or track their cursor position on the map - both fundamental requirements for a GIS application.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a user clicks any measurement tool button in the toolbar (Distance/Azimuth, Polygon Area, Elevation Profile, Volume Cut/Fill, Viewshed/LOS, Slope & Aspect, Shadow Height) THEN the system logs "Toolbar action: [action_label]" but does not activate the corresponding measurement mode or tool

1.2 WHEN a user clicks the "Distance / Azimuth" button THEN the system calls `_toolbar_measure_distance()` which is not fully implemented to enable interactive distance measurement mode on the map

1.3 WHEN a user clicks the "Polygon Area" button THEN the system calls `_toolbar_measure_polygon_area()` which does not exist or is not implemented to enable polygon drawing mode for area measurement

1.4 WHEN a user clicks the "Volume Cut/Fill" button THEN the system calls `_toolbar_measure_volume()` which does not exist or is not implemented to enable volume measurement mode

1.5 WHEN a user clicks the "Viewshed / LOS" button THEN the system calls `_toolbar_measure_viewshed()` which does not exist or is not implemented to enable viewshed analysis mode

1.6 WHEN a user clicks the "Slope & Aspect" button THEN the system calls `_toolbar_measure_slope_aspect()` which does not exist or is not implemented to enable slope/aspect analysis mode

1.7 WHEN a user moves their cursor over the map THEN the status bar footer displays static platform information (e.g., "GPU: Apple M2") instead of real-time geographic coordinates

1.8 WHEN the application is loading data or processing THEN the status bar does not show a progress indicator or busy status

1.9 WHEN a user views the status bar THEN it does not display the current Coordinate Reference System (CRS) being used for coordinate display

1.10 WHEN a user views the status bar THEN it does not display real-time cursor elevation information from the terrain

### Expected Behavior (Correct)

2.1 WHEN a user clicks the "Distance / Azimuth" button THEN the system SHALL enable interactive distance measurement mode, allowing the user to click two points on the map and receive distance and azimuth calculations using GDAL/pyproj for accuracy

2.2 WHEN a user clicks the "Polygon Area" button THEN the system SHALL enable polygon drawing mode, allowing the user to draw a polygon on the map and receive planimetric area, perimeter, and surface area calculations using GDAL

2.3 WHEN a user clicks the "Volume Cut/Fill" button THEN the system SHALL enable volume measurement mode, allowing the user to define a polygon and receive cut/fill volume calculations from the DEM using GDAL

2.4 WHEN a user clicks the "Viewshed / LOS" button THEN the system SHALL enable viewshed analysis mode, allowing the user to select an observer point and receive viewshed calculations from the DEM

2.5 WHEN a user clicks the "Slope & Aspect" button THEN the system SHALL enable slope/aspect analysis mode, allowing the user to select a point or area and receive slope and aspect calculations from the DEM

2.6 WHEN a user clicks the "Shadow Height" button THEN the system SHALL enable shadow height measurement mode, allowing the user to measure building or object heights using shadow analysis

2.7 WHEN a user moves their cursor over the map THEN the status bar SHALL display real-time geographic coordinates (longitude and latitude) in the format "Lon: XX.XXXXXX° Lat: YY.YYYYYY°" with configurable precision

2.8 WHEN the application is loading data or processing THEN the status bar SHALL display a pulsing indicator and "Rendering..." status message

2.9 WHEN a user views the status bar THEN it SHALL display the current CRS (e.g., "EPSG:4326") in a clearly labeled badge

2.10 WHEN a user moves their cursor over the map THEN the status bar SHALL display real-time elevation information (e.g., "Elev: 312.5 m") sampled from the terrain

2.11 WHEN measurement tools complete calculations THEN the system SHALL display results in the "Measurement Results" panel with proper formatting and units

2.12 WHEN a user clicks "Clear Last" or "Clear All" buttons THEN the system SHALL remove measurement overlays from the map and clear results from the panel

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a user clicks visualization tools (Layer Compositor, Comparator) THEN the system SHALL CONTINUE TO function correctly as they are already properly implemented

3.2 WHEN a user clicks navigation tools (Pan, Zoom In, Zoom Out, Zoom to Extent, North Arrow) THEN the system SHALL CONTINUE TO function correctly as they are already properly implemented

3.3 WHEN a user clicks file operations (Open Raster, Open DEM, Save Project, Export GeoPackage) THEN the system SHALL CONTINUE TO function correctly as they are already properly implemented

3.4 WHEN the status bar receives camera change events THEN it SHALL CONTINUE TO display map scale and heading information correctly

3.5 WHEN the status bar receives render busy events THEN it SHALL CONTINUE TO toggle the render indicator correctly

3.6 WHEN a user interacts with the control panel THEN all existing functionality (data ingest, search, display settings, activity log) SHALL CONTINUE TO work correctly

3.7 WHEN measurement tool backend functions are called programmatically THEN they SHALL CONTINUE TO return accurate results using GDAL/pyproj calculations

3.8 WHEN the application runs on different platforms (Mac/Windows) THEN cross-platform compatibility SHALL CONTINUE TO be maintained

3.9 WHEN NVIDIA GPU is available on Windows THEN GPU acceleration SHALL CONTINUE TO be utilized for rendering

3.10 WHEN the WebBridge emits mouseCoordinates signals THEN the status bar SHALL CONTINUE TO receive and process these signals correctly
