# Local GIS data QA utility

A Python standard-library utility tested on synthetic GeoJSON and ArcGIS-style point responses. It checks a small, explicit export profile and emits JSON findings. No network or external package is required. Tested with Python 3.14.6 on macOS.

## Run

From this folder:

```sh
python3 -B demo.py
python3 -B -m unittest -v
python3 -B qa.py geojson fixtures/geojson-valid.json
python3 -B qa.py arcgis fixtures/arcgis-wrong-crs.json
```

The test suite has 46 test methods. The demo runs seven saved cases under two Python hash seeds and checks expected findings and unchanged inputs. Three cases are accepted and four deliberately rejected. The in-range axis-swap example is accepted to show the limit of coordinate bounds.

Validator exit codes: 0 passes this profile; 1 reports profile violations; 2 indicates an input-read/JSON error or argument-usage error. File/JSON errors are structured JSON; argument-usage errors use argparse stderr. The demo exits 0 when all expected outcomes and preservation checks pass, including expected rejections. It writes no output files.

## Fixed contract

- WGS84 longitude/latitude is assumed, with explicit integer WKID 4326 in service metadata and the ArcGIS-style response. Coordinates must be exactly two finite numbers within longitude [-180,180] and latitude [-90,90]; booleans are rejected.
- Attributes are exactly OBJECTID (unique positive integer), label (required string or null), and status (active or retired, never null). An optional GeoJSON id must be an integer matching OBJECTID.
- Geometry must be a non-null Point. Legacy crs members are rejected on GeoJSON collections, features and points. Service metadata and ArcGIS response hasZ/hasM flags must be absent or false. ArcGIS point geometry contains x and y only.
- Field definitions agree with the fixed schema. Metadata nullability is required; explicit response nullability must agree. An empty ArcGIS feature set may omit fields.
- Explicit exceededTransferLimit true is rejected. Absence or false is accepted by this profile and does not prove the export is complete.

## Limits

This is a local synthetic-fixture-tested demonstrator. It does not establish actual CRS, positional accuracy, correct axis order, scientific validity, export completeness or production readiness. The formats are checked independently against fixed metadata, not compared against one another.

It is not a complete GeoJSON or Esri validator: GeoJSON normally permits null geometry and more geometry types. No reprojection, polygon topology, live-service integration, arbitrary metadata validation, duplicate JSON-key detection, file locking or oversized/deep-input protection is provided. Stable output and input preservation have been tested on the supplied cases; cross-platform operating-system error text is not promised.

Format references: [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946) and [Esri query documentation](https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer/). Those references do not imply full conformance.
