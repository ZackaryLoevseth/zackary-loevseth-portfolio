"""Behavioral tests: each invalid input protects a data-contract boundary."""
import copy
import json
import math
from pathlib import Path
import unittest

from qa import validate_geojson, validate_arcgis

ROOT = Path(__file__).parent


def read(name):
    return json.loads((ROOT / 'fixtures' / name).read_text())


class ResponseQA(unittest.TestCase):
    def setUp(self):
        self.metadata = read('service-metadata.json')
        self.geo = read('geojson-valid.json')
        self.arc = read('arcgis-valid.json')

    def codes(self, issues):
        self.assertTrue(all(set(i) == {'code', 'path', 'message'} for i in issues))
        return {i['code'] for i in issues}

    def test_valid_responses_and_nullable_label_pass(self):
        self.assertEqual(validate_geojson(self.geo, self.metadata), [])
        self.assertEqual(validate_arcgis(self.arc, self.metadata), [])

    def test_bounds_are_inclusive(self):
        self.geo['features'][0]['geometry']['coordinates'] = [-180, 90]
        self.assertEqual(validate_geojson(self.geo, self.metadata), [])

    def test_axis_swap_within_bounds_is_not_detectable(self):
        self.assertEqual(validate_geojson(read('geojson-axis-swap-undetectable.json'), self.metadata), [])

    def test_projected_values_fail_geographic_contract(self):
        self.assertIn('coordinate.bounds', self.codes(validate_geojson(read('geojson-projected-coordinates.json'), self.metadata)))

    def test_null_geometry_is_profile_violation(self):
        self.assertIn('geometry.null', self.codes(validate_geojson(read('geojson-null-geometry.json'), self.metadata)))

    def test_missing_nullable_field_differs_from_present_null(self):
        del self.geo['features'][1]['properties']['label']
        self.assertIn('schema.missing', self.codes(validate_geojson(self.geo, self.metadata)))

    def test_required_status_null_is_rejected(self):
        self.geo['features'][0]['properties']['status'] = None
        self.assertIn('schema.status', self.codes(validate_geojson(self.geo, self.metadata)))

    def test_unknown_field_and_wrong_label_type_are_rejected(self):
        props = self.geo['features'][0]['properties']
        props['extra'] = 'unexpected'
        props['label'] = 7
        self.assertTrue({'schema.extra', 'schema.label'} <= self.codes(validate_geojson(self.geo, self.metadata)))

    def test_boolean_and_duplicate_ids_are_rejected(self):
        for value, expected in [(True, 'schema.id'), (2, 'schema.duplicate_id')]:
            with self.subTest(value=value):
                doc = copy.deepcopy(self.geo)
                doc['features'][0]['properties']['OBJECTID'] = value
                self.assertIn(expected, self.codes(validate_geojson(doc, self.metadata)))

    def test_feature_id_must_agree_with_objectid(self):
        self.geo['features'][0]['id'] = 999
        self.assertIn('schema.feature_id', self.codes(validate_geojson(self.geo, self.metadata)))

    def test_geometry_type_and_position_dimensions_are_enforced(self):
        for geom, code in [({'type':'LineString','coordinates':[[0,0],[1,1]]},'geometry.type'),({'type':'Point','coordinates':[0]},'coordinate.shape'),({'type':'Point','coordinates':[0,0,100]},'coordinate.shape')]:
            with self.subTest(geom=geom):
                self.geo['features'][0]['geometry'] = geom
                self.assertIn(code, self.codes(validate_geojson(self.geo, self.metadata)))

    def test_non_numeric_and_non_finite_coordinates_are_rejected(self):
        for value in [True, '38', None, math.nan, math.inf, -math.inf]:
            with self.subTest(value=value):
                self.geo['features'][0]['geometry']['coordinates'] = [value, 0]
                self.assertIn('coordinate.number', self.codes(validate_geojson(self.geo, self.metadata)))

    def test_legacy_crs_member_is_profile_violation(self):
        self.geo['crs'] = {'type':'name','properties':{'name':'EPSG:3857'}}
        self.assertIn('crs.legacy', self.codes(validate_geojson(self.geo, self.metadata)))

    def test_arcgis_wrong_crs_and_truncation_are_rejected(self):
        self.assertIn('crs.mismatch', self.codes(validate_arcgis(read('arcgis-wrong-crs.json'), self.metadata)))
        self.assertIn('response.truncated', self.codes(validate_arcgis(read('arcgis-truncated.json'), self.metadata)))

    def test_arcgis_schema_and_geometry_type_drift_are_rejected(self):
        self.arc['fields'][0]['type'] = 'esriFieldTypeString'
        self.arc['geometryType'] = 'esriGeometryPolygon'
        codes = self.codes(validate_arcgis(self.arc, self.metadata))
        self.assertTrue({'schema.fields','geometry.type'} <= codes)

    def test_arcgis_null_and_missing_geometry_are_rejected(self):
        self.arc['features'][0]['geometry'] = None
        del self.arc['features'][1]['geometry']
        self.assertIn('geometry.null', self.codes(validate_arcgis(self.arc, self.metadata)))

    def test_arcgis_boolean_completion_flag_is_required_when_present(self):
        for value in [0, 'false', None, []]:
            with self.subTest(value=value):
                self.arc['exceededTransferLimit'] = value
                self.assertIn('response.completion_flag', self.codes(validate_arcgis(self.arc, self.metadata)))

    def test_bad_metadata_is_reported_without_crash(self):
        for meta in [None, [], {'spatialReference':None}, dict(self.metadata, fields=[None]), dict(self.metadata, spatialReference={'wkid':3857})]:
            with self.subTest(meta=meta):
                self.assertIn('metadata.contract', self.codes(validate_geojson(self.geo, meta)))

    def test_malformed_json_shapes_are_reported_without_crash(self):
        for document in [None, [], 5, {'type':'FeatureCollection','features':None}, {'type':'FeatureCollection','features':[None]}, {'type':'FeatureCollection','features':[{'type':'Feature','properties':[],'geometry':[]}] }]:
            with self.subTest(document=document):
                self.assertTrue(validate_geojson(document, self.metadata))
        for document in [None, [], {'features':None}, dict(self.arc, features=[None]), dict(self.arc, fields=[None]), dict(self.arc, spatialReference=[])]:
            with self.subTest(document=document):
                self.assertTrue(validate_arcgis(document, self.metadata))

    def test_explicit_returned_field_nullability_must_match_metadata(self):
        self.arc['fields'][1]['nullable'] = False
        self.assertIn('schema.fields', self.codes(validate_arcgis(self.arc, self.metadata)))
        self.arc['fields'][1]['nullable'] = True
        self.assertEqual(validate_arcgis(self.arc, self.metadata), [])

    def test_explicit_z_or_m_flags_must_agree_with_2d_profile(self):
        for flag in ['hasZ', 'hasM']:
            for value in [True, 1, 'false', None]:
                with self.subTest(flag=flag, value=value):
                    meta = copy.deepcopy(self.metadata)
                    meta[flag] = value
                    self.assertIn('metadata.contract', self.codes(validate_geojson(self.geo, meta)))
                    arc = copy.deepcopy(self.arc)
                    arc[flag] = value
                    self.assertIn('geometry.dimensions', self.codes(validate_arcgis(arc, self.metadata)))
            self.metadata[flag] = False
            self.arc[flag] = False
        self.assertEqual(validate_arcgis(self.arc, self.metadata), [])

    def test_empty_complete_responses_are_valid(self):
        self.geo['features'] = []
        self.arc['features'] = []
        self.assertEqual(validate_geojson(self.geo, self.metadata), [])
        self.assertEqual(validate_arcgis(self.arc, self.metadata), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
