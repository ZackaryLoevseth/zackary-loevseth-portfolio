"""Offline QA for the documented synthetic, complete 2D point-export profile.

No network access, coordinate transformation, or full GIS/schema conformance claim.
"""
import argparse
import json
import math
from pathlib import Path

FIELDS = {
    'OBJECTID': ('esriFieldTypeOID', False),
    'label': ('esriFieldTypeString', True),
    'status': ('esriFieldTypeString', False),
}


def _issue(issues, code, path, message):
    issues.append({'code': code, 'path': path, 'message': message})


def _fields_match(fields, *, nullability=False):
    if not isinstance(fields, list) or len(fields) != len(FIELDS):
        return False
    found = {}
    for field in fields:
        if not isinstance(field, dict):
            return False
        name = field.get('name')
        if not isinstance(name, str) or name in found or name not in FIELDS:
            return False
        expected_type, expected_nullable = FIELDS[name]
        if field.get('type') != expected_type:
            return False
        if (nullability or 'nullable' in field) and field.get('nullable') is not expected_nullable:
            return False
        found[name] = True
    return set(found) == set(FIELDS)


def _wkid4326(sr):
    return isinstance(sr, dict) and type(sr.get('wkid')) is int and sr['wkid'] == 4326


def _metadata_ok(metadata, issues):
    if not (isinstance(metadata, dict)
            and metadata.get('geometryType') == 'esriGeometryPoint'
            and metadata.get('objectIdField') == 'OBJECTID'
            and _wkid4326(metadata.get('spatialReference'))
            and all(flag not in metadata or metadata[flag] is False for flag in ('hasZ', 'hasM'))
            and _fields_match(metadata.get('fields'), nullability=True)):
        _issue(issues, 'metadata.contract', '$metadata',
               'Metadata must agree with the documented synthetic point-export contract.')
        return False
    return True


def _attributes(properties, issues, path, seen):
    if not isinstance(properties, dict):
        _issue(issues, 'schema.object', path, 'Attributes/properties must be an object.')
        return
    missing = set(FIELDS) - set(properties)
    extra = set(properties) - set(FIELDS)
    if missing:
        _issue(issues, 'schema.missing', path, 'Required fields missing: ' + ', '.join(sorted(missing)))
    if extra:
        _issue(issues, 'schema.extra', path, 'Unexpected attributes are outside this export contract.')
    if 'OBJECTID' in properties:
        oid = properties['OBJECTID']
        if type(oid) is not int or oid <= 0:
            _issue(issues, 'schema.id', path + '.OBJECTID', 'OBJECTID must be a positive integer, excluding bool.')
        elif oid in seen:
            _issue(issues, 'schema.duplicate_id', path + '.OBJECTID', 'OBJECTID is duplicated in this response.')
        else:
            seen.add(oid)
    if 'label' in properties and properties['label'] is not None and not isinstance(properties['label'], str):
        _issue(issues, 'schema.label', path + '.label', 'label must be a string or null.')
    if 'status' in properties and properties['status'] not in ('active', 'retired'):
        _issue(issues, 'schema.status', path + '.status', 'status must be active or retired, never null.')


def _position(position, issues, path):
    if not isinstance(position, list) or len(position) != 2:
        _issue(issues, 'coordinate.shape', path, 'This profile requires exactly two coordinates.')
        return
    for number in position:
        # All integers are finite; compare their bounds without converting huge ints to float.
        if type(number) not in (int, float) or (type(number) is float and not math.isfinite(number)):
            _issue(issues, 'coordinate.number', path, 'Coordinates must be finite numbers, excluding bool.')
            return
    lon, lat = position
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        _issue(issues, 'coordinate.bounds', path, 'Expected WGS84 longitude/latitude ranges; no CRS inference performed.')


def validate_geojson(payload, metadata):
    """Return structured profile violations for one parsed GeoJSON response."""
    issues = []
    if not _metadata_ok(metadata, issues):
        return issues
    if not isinstance(payload, dict) or payload.get('type') != 'FeatureCollection':
        _issue(issues, 'response.object', '$', 'Expected a GeoJSON FeatureCollection object.')
        return issues
    if 'crs' in payload:
        _issue(issues, 'crs.legacy', '$.crs', 'Legacy CRS declarations are outside this RFC 7946 export profile.')
    features = payload.get('features')
    if not isinstance(features, list):
        _issue(issues, 'response.features', '$.features', 'features must be an array.')
        return issues
    seen = set()
    for index, feature in enumerate(features):
        path = f'$.features[{index}]'
        if not isinstance(feature, dict) or feature.get('type') != 'Feature':
            _issue(issues, 'feature.object', path, 'Expected a GeoJSON Feature object.')
            continue
        if 'crs' in feature:
            _issue(issues, 'crs.legacy', path + '.crs', 'Legacy CRS declarations are outside this RFC 7946 export profile.')
        props = feature.get('properties')
        _attributes(props, issues, path + '.properties', seen)
        if 'id' in feature and isinstance(props, dict):
            if type(feature['id']) is not int or feature['id'] != props.get('OBJECTID'):
                _issue(issues, 'schema.feature_id', path + '.id', 'Feature id, when present, must match OBJECTID.')
        geometry = feature.get('geometry')
        if geometry is None:
            _issue(issues, 'geometry.null', path + '.geometry', 'This export contract requires non-null geometry.')
        elif not isinstance(geometry, dict) or geometry.get('type') != 'Point':
            _issue(issues, 'geometry.type', path + '.geometry', 'This export contract requires Point geometry.')
        else:
            if 'crs' in geometry:
                _issue(issues, 'crs.legacy', path + '.geometry.crs', 'Legacy CRS declarations are outside this RFC 7946 export profile.')
            _position(geometry.get('coordinates'), issues, path + '.geometry.coordinates')
    return issues


def validate_arcgis(payload, metadata):
    """Return structured profile violations for one parsed ArcGIS-style response."""
    issues = []
    if not _metadata_ok(metadata, issues):
        return issues
    if not isinstance(payload, dict):
        _issue(issues, 'response.object', '$', 'Expected an ArcGIS query response object.')
        return issues
    if not _wkid4326(payload.get('spatialReference')):
        _issue(issues, 'crs.mismatch', '$.spatialReference', 'Expected explicit wkid 4326 in this query response.')
    if any(flag in payload and payload[flag] is not False for flag in ('hasZ', 'hasM')):
        _issue(issues, 'geometry.dimensions', '$', 'hasZ and hasM must be false when supplied for this 2D profile.')
    if payload.get('geometryType') != 'esriGeometryPoint':
        _issue(issues, 'geometry.type', '$.geometryType', 'Expected esriGeometryPoint.')
    if payload.get('objectIdFieldName') != 'OBJECTID':
        _issue(issues, 'schema.object_id_field', '$.objectIdFieldName', 'Expected OBJECTID.')
    if 'exceededTransferLimit' in payload:
        flag = payload['exceededTransferLimit']
        if type(flag) is not bool:
            _issue(issues, 'response.completion_flag', '$.exceededTransferLimit', 'Completion flag must be boolean when present.')
        elif flag:
            _issue(issues, 'response.truncated', '$.exceededTransferLimit', 'Complete export expected; response is truncated.')
    features = payload.get('features')
    if not isinstance(features, list):
        _issue(issues, 'response.features', '$.features', 'features must be an array.')
        return issues
    # Esri documents omission of fields for an empty feature set.
    if not (features == [] and 'fields' not in payload) and not _fields_match(payload.get('fields')):
        _issue(issues, 'schema.fields', '$.fields', 'Returned fields must agree with the profile metadata.')
    seen = set()
    for index, feature in enumerate(features):
        path = f'$.features[{index}]'
        if not isinstance(feature, dict):
            _issue(issues, 'feature.object', path, 'Expected a feature object.')
            continue
        _attributes(feature.get('attributes'), issues, path + '.attributes', seen)
        geometry = feature.get('geometry')
        if geometry is None:
            _issue(issues, 'geometry.null', path + '.geometry', 'This export contract requires non-null geometry.')
        elif not isinstance(geometry, dict) or set(geometry) != {'x', 'y'}:
            _issue(issues, 'coordinate.shape', path + '.geometry', 'This profile requires a 2D point containing x and y only.')
        else:
            _position([geometry['x'], geometry['y']], issues, path + '.geometry')
    return issues


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('format', choices=['geojson', 'arcgis'])
    parser.add_argument('response', type=Path)
    parser.add_argument('--metadata', type=Path, default=Path(__file__).parent / 'fixtures/service-metadata.json')
    args = parser.parse_args()
    try:
        payload = json.loads(args.response.read_text())
        metadata = json.loads(args.metadata.read_text())
    except (OSError, ValueError) as exc:
        print(json.dumps({'valid': False, 'issues': [{'code': 'input.read', 'path': '$', 'message': str(exc)}]}, indent=2))
        return 2
    validator = validate_geojson if args.format == 'geojson' else validate_arcgis
    issues = validator(payload, metadata)
    print(json.dumps({'valid': not issues, 'issues': issues}, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
