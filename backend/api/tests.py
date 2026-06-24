from django.test import TestCase


class HealthEndpointTests(TestCase):

    def test_health_returns_200(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)

    def test_health_returns_ok_json(self):
        response = self.client.get('/api/health/')
        self.assertJSONEqual(response.content, {'status': 'ok'})
