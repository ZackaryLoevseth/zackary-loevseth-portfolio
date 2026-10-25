"""Additional boundaries of the existing synthetic profile; no new features."""
import copy
import json
import math
from pathlib import Path
import unittest

from qa import validate_arcgis, validate_geojson

ROOT = Path(__file__).parent


def fixture(name):
    return json.loads((ROOT / 'fixtures' / name).read_text())


class ContractBoundaries(unittest.TestCase):
    def setUp(self):
        self.metadata = fixture('service-metadata.json')

    def examples(self):
        return [('geojson', fixture('geojson-valid.json'), validate_geojson),
                ('arcgis', fixture('arcgis-valid.json'), validate_arcgis)]

    def position(self, kind, document, lon, lat):
        if kind == 'geojson':
            document['features'][0]['geometry']['coordinates'] = [lon, lat]
        else:
            document['features'][0]['geometry'] = {'x': lon, 'y': lat}

    def properties(self, kind, document):
        return document['features'][0]['properties' if kind == 'geojson' else 'attributes']

    def assert_issue(self, issues, code, path=None):
        found = [issue for issue in issues if issue['code'] == code]
        self.assertTrue(found, issues)
        if path is not None:
            self.assertIn(path, [issue['path'] for issue in found])

    def test_all_coordinate_edges_are_inclusive_for_both_formats(self):
        # Catches swapped axes, strict inequalities, or format-specific bounds.
        for kind, original, validator in self.examples():
            for lon, lat in [(-180, -90), (-180, 90), (180, -90), (180, 90), (0, 0)]:
                with self.subTest(kind=kind, lon=lon, lat=lat):
                    document = copy.deepcopy(original)
                    self.position(kind, document, lon, lat)
                    self.assertEqual(validator(document, self.metadata), [])

    def test_just_outside_each_coordinate_edge_is_rejected(self):
        # No arbitrary tolerance may admit values just outside the fixed profile.
        for kind, original, validator in self.examples():
            for lon, lat in [(-180.000001, 0), (180.000001, 0), (0, -90.000001), (0, 90.000001)]:
                with self.subTest(kind=kind, lon=lon, lat=lat):
                    document = copy.deepcopy(original)
                    self.position(kind, document, lon, lat)
                    self.assert_issue(validator(document, self.metadata), 'coordinate.bounds')

    def test_each_axis_rejects_bool_non_numbers_and_non_finite_values(self):
        # Protects both x/y and lon/lat, not only the first axis.
        for kind, original, validator in self.examples():
            for axis in [0, 1]:
                for value in [True, False, '0', None, [], {}, math.nan, math.inf, -math.inf]:
                    with self.subTest(kind=kind, axis=axis, value=value):
                        document = copy.deepcopy(original)
                        point = [0, 0]
                        point[axis] = value
                        self.position(kind, document, *point)
                        self.assert_issue(validator(document, self.metadata), 'coordinate.number')

    def test_huge_integer_coordinates_are_violations_without_float_overflow(self):
        # A float conversion of these JSON integers would raise OverflowError.
        for kind, document, validator in self.examples():
            with self.subTest(kind=kind):
                self.position(kind, document, 10 ** 400, -(10 ** 400))
                self.assert_issue(validator(document, self.metadata), 'coordinate.bounds')

    def test_missing_and_invalid_objectids_are_rejected_in_both_formats(self):
        # Catches positivity/type checks omitted from ArcGIS attributes.
        for kind, original, validator in self.examples():
            for value in [0, -1, 1.0, '1', True, False, None, [], {}]:
                with self.subTest(kind=kind, value=value):
                    document = copy.deepcopy(original)
                    self.properties(kind, document)['OBJECTID'] = value
                    self.assert_issue(validator(document, self.metadata), 'schema.id')
            document = copy.deepcopy(original)
            del self.properties(kind, document)['OBJECTID']
            self.assert_issue(validator(document, self.metadata), 'schema.missing')

    def test_duplicate_ids_are_rejected_in_both_formats(self):
        for kind, document, validator in self.examples():
            with self.subTest(kind=kind):
                self.properties(kind, document)['OBJECTID'] = 2
                self.assert_issue(validator(document, self.metadata), 'schema.duplicate_id')

    def test_required_nullable_label_and_status_enum_apply_to_both_formats(self):
        for kind, original, validator in self.examples():
            for props, expected in [
                ({'OBJECTID': 1, 'label': None, 'status': 'retired'}, None),
                ({'OBJECTID': 1, 'label': '', 'status': 'active'}, None),
                ({'OBJECTID': 1, 'status': 'active'}, 'schema.missing'),
                ({'OBJECTID': 1, 'label': 'a'}, 'schema.missing'),
                ({'OBJECTID': 1, 'label': 'a', 'status': 'ACTIVE'}, 'schema.status'),
                ({'OBJECTID': 1, 'label': 'a', 'status': None}, 'schema.status'),
                ({'OBJECTID': 1, 'label': 0, 'status': 'active'}, 'schema.label'),
                ({'OBJECTID': 1, 'label': 'a', 'status': 'active', 'extra': None}, 'schema.extra')]:
                with self.subTest(kind=kind, props=props):
                    document = copy.deepcopy(original)
                    key = 'properties' if kind == 'geojson' else 'attributes'
                    document['features'][0][key] = props
                    issues = validator(document, self.metadata)
                    if expected is None:
                        self.assertEqual(issues, [])
                    else:
                        self.assert_issue(issues, expected)

    def test_optional_geojson_id_may_be_absent_but_must_be_exact_integer_when_present(self):
        original = fixture('geojson-valid.json')
        del original['features'][0]['id']
        self.assertEqual(validate_geojson(original, self.metadata), [])
        for value in [True, 1.0, '1', None, 2]:
            with self.subTest(value=value):
                document = copy.deepcopy(original)
                document['features'][0]['id'] = value
                self.assert_issue(validate_geojson(document, self.metadata), 'schema.feature_id', '$.features[0].id')

    def test_empty_arcgis_may_omit_fields_but_nonempty_response_may_not(self):
        document = fixture('arcgis-valid.json')
        del document['fields']
        self.assert_issue(validate_arcgis(document, self.metadata), 'schema.fields')
        document['features'] = []
        self.assertEqual(validate_arcgis(document, self.metadata), [])
        document['fields'] = None
        self.assert_issue(validate_arcgis(document, self.metadata), 'schema.fields')

    def test_field_order_is_irrelevant_and_duplicate_or_unknown_definitions_fail(self):
        document = fixture('arcgis-valid.json')
        document['fields'].reverse()
        self.metadata['fields'].reverse()
        self.assertEqual(validate_arcgis(document, self.metadata), [])
        for source in ['metadata', 'response']:
            for change in ['duplicate', 'unknown', 'unhashable_name']:
                with self.subTest(source=source, change=change):
                    meta = copy.deepcopy(self.metadata)
                    response = copy.deepcopy(document)
                    fields = meta['fields'] if source == 'metadata' else response['fields']
                    if change == 'duplicate':
                        fields[1] = copy.deepcopy(fields[0])
                    else:
                        fields[0]['name'] = 'unexpected' if change == 'unknown' else []
                    self.assert_issue(validate_arcgis(response, meta), 'metadata.contract' if source == 'metadata' else 'schema.fields')

    def test_metadata_crs_and_nullability_require_exact_types_and_presence(self):
        for kind, document, validator in self.examples():
            for wkid in [True, 4326.0, '4326', None, 3857]:
                with self.subTest(kind=kind, wkid=wkid):
                    meta = copy.deepcopy(self.metadata)
                    meta['spatialReference']['wkid'] = wkid
                    self.assert_issue(validator(document, meta), 'metadata.contract')
            for value in [0, 1, None, 'false']:
                with self.subTest(kind=kind, nullable=value):
                    meta = copy.deepcopy(self.metadata)
                    meta['fields'][0]['nullable'] = value
                    self.assert_issue(validator(document, meta), 'metadata.contract')
            meta = copy.deepcopy(self.metadata)
            del meta['fields'][0]['nullable']
            self.assert_issue(validator(document, meta), 'metadata.contract')

    def test_arcgis_requires_exact_xy_point_shape_and_integer_wkid(self):
        original = fixture('arcgis-valid.json')
        for geometry in [{}, {'x': 0}, {'y': 0}, {'x': 0, 'y': 0, 'z': 0}, {'x': 0, 'y': 0, 'm': 0}, [0, 0]]:
            with self.subTest(geometry=geometry):
                document = copy.deepcopy(original)
                document['features'][0]['geometry'] = geometry
                self.assert_issue(validate_arcgis(document, self.metadata), 'coordinate.shape')
        for wkid in [True, 4326.0, '4326', None]:
            with self.subTest(wkid=wkid):
                document = copy.deepcopy(original)
                document['spatialReference']['wkid'] = wkid
                self.assert_issue(validate_arcgis(document, self.metadata), 'crs.mismatch')

    def test_absent_completion_flag_is_permitted_and_explicit_false_is_permitted(self):
        document = fixture('arcgis-valid.json')
        del document['exceededTransferLimit']
        self.assertEqual(validate_arcgis(document, self.metadata), [])
        document['exceededTransferLimit'] = False
        self.assertEqual(validate_arcgis(document, self.metadata), [])

    def test_validation_does_not_change_in_memory_response_or_metadata(self):
        # Catches normalization, sorting, pop/default insertion or repair side effects.
        for kind, original, validator in self.examples():
            for invalid in [False, True]:
                with self.subTest(kind=kind, invalid=invalid):
                    document = copy.deepcopy(original)
                    if invalid:
                        self.properties(kind, document)['status'] = None
                    before_document = copy.deepcopy(document)
                    before_meta = copy.deepcopy(self.metadata)
                    issues = validator(document, self.metadata)
                    self.assertEqual(bool(issues), invalid)
                    self.assertEqual(document, before_document)
                    self.assertEqual(self.metadata, before_meta)

    def test_legacy_crs_presence_is_rejected_on_collection_feature_and_point(self):
        # The profile rejects legacy declarations, including conflicting nested ones.
        for location, expected_path in [('collection', '$.crs'), ('feature', '$.features[0].crs'),
                                        ('point', '$.features[0].geometry.crs')]:
            for declaration in [None, {'type': 'name', 'properties': {'name': 'EPSG:3857'}}]:
                with self.subTest(location=location, declaration=declaration):
                    document = fixture('geojson-valid.json')
                    target = {'collection': document, 'feature': document['features'][0],
                              'point': document['features'][0]['geometry']}[location]
                    target['crs'] = declaration
                    self.assert_issue(validate_geojson(document, self.metadata), 'crs.legacy', expected_path)

    def test_multiple_legacy_crs_findings_have_stable_precise_paths_without_mutation(self):
        document = fixture('geojson-valid.json')
        document['crs'] = None
        document['features'][0]['crs'] = None
        document['features'][0]['geometry']['crs'] = None
        before = copy.deepcopy(document)
        first = validate_geojson(document, self.metadata)
        self.assertEqual([(i['code'], i['path']) for i in first], [
            ('crs.legacy', '$.crs'),
            ('crs.legacy', '$.features[0].crs'),
            ('crs.legacy', '$.features[0].geometry.crs'),
        ])
        self.assertEqual(validate_geojson(document, self.metadata), first)
        self.assertEqual(document, before)

    def test_metadata_geometry_and_object_id_declarations_must_match_profile(self):
        # Removing either individual declaration check must be observable.
        for kind, document, validator in self.examples():
            for key, values in [('geometryType', ['esriGeometryPolygon', None, True]),
                                ('objectIdField', ['another_id', None, True])]:
                for value in values:
                    with self.subTest(kind=kind, key=key, value=value):
                        metadata = copy.deepcopy(self.metadata)
                        metadata[key] = value
                        self.assert_issue(validator(document, metadata), 'metadata.contract')
                metadata = copy.deepcopy(self.metadata)
                del metadata[key]
                self.assert_issue(validator(document, metadata), 'metadata.contract')

    def test_arcgis_object_id_field_name_must_match_profile(self):
        for value in ['another_id', None, True, 1]:
            with self.subTest(value=value):
                document = fixture('arcgis-valid.json')
                document['objectIdFieldName'] = value
                self.assert_issue(validate_arcgis(document, self.metadata), 'schema.object_id_field', '$.objectIdFieldName')
        document = fixture('arcgis-valid.json')
        del document['objectIdFieldName']
        self.assert_issue(validate_arcgis(document, self.metadata), 'schema.object_id_field', '$.objectIdFieldName')


if __name__ == '__main__':
    unittest.main(verbosity=2)
