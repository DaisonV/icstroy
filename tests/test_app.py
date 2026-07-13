import unittest

from sqlalchemy import func, select

from app import create_app
from app.commands import seed_data
from app.extensions import db
from app.models import Application, Tariff


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = False
    SITE_URL = "https://example.test"
    SESSION_COOKIE_SECURE = False


class IcstroyAppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app(TestConfig)
        with cls.app.app_context():
            db.create_all()
            seed_data(include_demo=True)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        self.context.pop()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.drop_all()

    def login(self):
        return self.client.post("/auth/login", data={
            "email": "admin@icstroy.kz",
            "password": "ChangeMe!2026",
        }, follow_redirects=True)

    def test_public_site_and_seo_files(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Касымова Гаухар Булатовна".encode(), response.data)
        self.assertIn(b"application/ld+json", response.data)
        self.assertIn(b"/sitemap.xml", self.client.get("/robots.txt").data)
        self.assertIn(b"/privacy", self.client.get("/sitemap.xml").data)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_calculator_uses_database_tariff(self):
        response = self.client.post("/api/calculate", json={
            "from": "Алматы", "to": "Астана", "transport": "groupage",
            "weight": 100, "volume": 0.5,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["price"], 9500)

    def test_website_application_is_saved(self):
        before = db.session.scalar(select(func.count(Application.id)))
        response = self.client.post("/api/applications", json={
            "name": "Тестовый клиент", "phone": "+7 700 000 00 00",
            "route": "Алматы — Астана", "message": "Паллеты, 100 кг",
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["number"].startswith("IC-"))
        after = db.session.scalar(select(func.count(Application.id)))
        self.assertEqual(after, before + 1)

    def test_tracking_and_crm_authentication(self):
        tracking = self.client.get("/api/tracking/IC-2048")
        self.assertEqual(tracking.status_code, 200)
        self.assertEqual(tracking.get_json()["status"], "in_transit")
        protected = self.client.get("/crm")
        self.assertEqual(protected.status_code, 302)
        self.assertIn("/auth/login", protected.location)
        logged_in = self.login()
        self.assertEqual(logged_in.status_code, 200)
        self.assertIn("Система работает".encode(), logged_in.data)
        self.assertEqual(self.client.get("/crm/shipments").status_code, 200)

    def test_admin_can_change_tariff(self):
        self.login()
        tariff = db.session.scalar(select(Tariff).where(Tariff.name == "Алматы — Астана · Сборный"))
        response = self.client.post("/crm/tariffs/{}".format(tariff.id), data={
            "name": tariff.name,
            "origin": "Алматы",
            "destination": "Астана",
            "service_type": "groupage",
            "price_per_kg": "100",
            "minimum_price": "5000",
            "volumetric_factor": "167",
            "rounding_step": "500",
            "delivery_days_min": "3",
            "delivery_days_max": "6",
            "valid_from": tariff.valid_from.isoformat(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        quote = self.client.post("/api/calculate", json={
            "from": "Алматы", "to": "Астана", "transport": "groupage",
            "weight": 100, "volume": 0.5,
        }).get_json()
        self.assertEqual(quote["price"], 10000)
        tariff.price_per_kg = 95
        db.session.commit()


if __name__ == "__main__":
    unittest.main()
