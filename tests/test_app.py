import unittest
import io
import json
import pandas as pd
from app import app

class CatFlipTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def upload_sample_csv(self):
        csv_data = "Nombre,Edad,Ciudad,Ventas\nAlice,30,Madrid,100\nBob,25,Barcelona,200\nCharlie,35,Madrid,150\n"
        return self.app.post(
            '/upload',
            data={'file': (io.BytesIO(csv_data.encode('utf-8')), 'data.csv')},
            content_type='multipart/form-data'
        )

    def test_upload_csv(self):
        response = self.upload_sample_csv()
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertIn('columns', data['data'])
        self.assertEqual(data['data']['columns'], ['Nombre', 'Edad', 'Ciudad', 'Ventas'])

    def test_operation_filter(self):
        self.upload_sample_csv()
        response = self.app.post(
            '/operation',
            json={
                'operation': 'filter',
                'params': {'column': 'Ciudad', 'operator': '==', 'value': 'Madrid'}
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']['data']), 2)

    def test_operation_rename_and_drop_column(self):
        self.upload_sample_csv()
        response = self.app.post(
            '/operation',
            json={
                'operation': 'rename_column',
                'params': {'old_name': 'Edad', 'new_name': 'Years'}
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('Years', data['data']['columns'])

        response = self.app.post(
            '/operation',
            json={
                'operation': 'drop_column',
                'params': {'column': 'Years'}
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertNotIn('Years', data['data']['columns'])

    def test_undo(self):
        self.upload_sample_csv()
        self.app.post(
            '/operation',
            json={
                'operation': 'drop_column',
                'params': {'column': 'Ciudad'}
            }
        )
        response = self.app.post('/undo')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('Ciudad', data['data']['columns'])

    def test_stats(self):
        self.upload_sample_csv()
        response = self.app.get('/stats')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn('stats', data)
        self.assertIn('Ciudad', data['stats'])
        self.assertEqual(data['stats']['Ciudad']['nulls'], 0)

    def test_export_and_script(self):
        self.upload_sample_csv()
        res_export = self.app.post('/export', json={'format': 'csv', 'filename': 'test'})
        self.assertEqual(res_export.status_code, 200)

        res_script = self.app.post('/export_script', json={'filename': 'pipeline'})
        self.assertEqual(res_script.status_code, 200)
        self.assertIn(b'import pandas as pd', res_script.data)

if __name__ == '__main__':
    unittest.main()
