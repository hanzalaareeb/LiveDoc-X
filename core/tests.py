from django.test import TestCase


class HealthApiTests(TestCase):
    def test_health_check_is_public(self):
        response = self.client.get("/api/v1/core/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "core OK"})
