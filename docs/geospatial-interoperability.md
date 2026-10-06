# Geospatial interoperability

StageMesh may use geospatial data to plan, visualize, and qualify location-aware
shows. This guidance is informed by USGS MapIO's grid-oriented handling of
spatial data and its interoperability with common grid and raster ecosystems.

Reference: [USGS MapIO](https://github.com/usgs/MapIO)

## Boundary

Geospatial layers are planning and visualization inputs by default. A map point,
raster cell, or transformed coordinate must not directly arm a physical output,
robot, pyro channel, or lighting universe. Any transition from a map-derived
intent to a show action requires an explicit, auditable authorization step.

## Layer and coordinate contract

Every imported layer should retain, at minimum:

- coordinate reference system and axis order;
- origin, bounds, cell spacing, dimensions, and units;
- acquisition timestamp, source, version, and provenance;
- nodata/uncertainty semantics and any resampling method;
- the mapping from source coordinates to StageMesh show-space coordinates.

Keep the source grid immutable. Derived layers should record their parent layer,
transform, and processing version so that a rehearsal can be reproduced after a
map or calibration update.

## Safe interoperability

Adapters may support grid and raster data exchanged through formats or tools in
the MapIO ecosystem, including GDAL/ESRI-style grids, GMT grids, HDF-backed
data, and earthquake or hazard products such as ShakeMap. Import should be
bounded by file size, cell count, numeric range, and supported CRS. Unsupported
metadata must be reported rather than silently discarded.

Coordinate conversion should validate bounds, axis order, units, antimeridian
behavior, polar edge cases, and loss of precision. A failed transform produces
an unavailable planning layer, never a best-effort physical command.

## Qualification scenarios

1. Load a small synthetic grid and verify dimensions, bounds, CRS, units, and
   nodata behavior.
2. Transform known control points into show space and compare against expected
   tolerances.
3. Select and blend layers while preserving provenance and reporting the
   resampling method.
4. Exercise stale, malformed, unsupported, and out-of-bounds inputs; confirm
   they remain visible as diagnostics and cannot arm outputs.
5. Reopen a saved plan and verify that the same source versions and transforms
   reproduce the same planning coordinates.

## StageMesh implementation boundary

The first implementation should expose read-only layer metadata, validation
results, and preview overlays. Physical output drivers remain independently
armed and should consume only explicit show events with their own timing,
authorization, and interlock checks.
