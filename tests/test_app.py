import unittest

from sqlalchemy import func, select

from app import create_app
from app.commands import seed_data
from app.extensions import db
from app.models import Application, ApplicationActivity, CrmTask, Notification, Tariff, TaskStatus, User


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
        self.assertIn(b"251140024698", response.data)
        self.assertIn("Рыскулова 140/4".encode(), response.data)
        self.assertIn(b"application/ld+json", response.data)
        self.assertIn(b"/sitemap.xml", self.client.get("/robots.txt").data)
        self.assertIn(b"/privacy", self.client.get("/sitemap.xml").data)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_calculator_uses_database_tariff(self):
        response = self.client.post("/api/calculate", json={
            "from": "Алматы", "to": "Астана", "transport": "auto",
            "weight": 100, "volume": 0.5,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["price"], 650000)
        self.assertEqual(response.get_json()["basis"], "Крытая фура, 20 тонн")

    def test_website_application_is_saved(self):
        before = db.session.scalar(select(func.count(Application.id)))
        notifications_before = db.session.scalar(select(func.count(Notification.id)))
        response = self.client.post("/api/applications", json={
            "name": "Тестовый клиент", "phone": "+7 700 000 00 00",
            "route": "Алматы — Астана", "message": "Паллеты, 100 кг",
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["number"].startswith("IC-"))
        after = db.session.scalar(select(func.count(Application.id)))
        self.assertEqual(after, before + 1)
        self.assertGreater(db.session.scalar(select(func.count(Notification.id))), notifications_before)
        application = db.session.scalar(select(Application).order_by(Application.created_at.desc()))
        self.assertIsNotNone(db.session.scalar(select(ApplicationActivity).where(ApplicationActivity.application_id == application.id)))
        automatic_task = db.session.scalar(select(CrmTask).where(CrmTask.application_id == application.id))
        self.assertIsNotNone(automatic_task)
        self.assertEqual(automatic_task.status, TaskStatus.OPEN)

    def test_manager_can_create_and_complete_task(self):
        self.login()
        application = db.session.scalar(select(Application).order_by(Application.id))
        admin = db.session.scalar(select(User).where(User.email == "admin@icstroy.kz"))
        response = self.client.post("/crm/applications/{}/tasks".format(application.id), data={
            "title": "Позвонить клиенту",
            "due_at": "2026-07-20T12:00",
            "assignee_id": str(admin.id),
            "notes": "Подтвердить маршрут",
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Позвонить клиенту".encode(), response.data)
        task = db.session.scalar(select(CrmTask).where(CrmTask.title == "Позвонить клиенту"))
        self.assertIsNotNone(task)
        self.assertEqual(task.status, TaskStatus.OPEN)
        notification = db.session.scalar(select(Notification).where(Notification.user_id == admin.id, Notification.application_id == application.id))
        self.assertIsNotNone(notification)
        response = self.client.post("/crm/notifications/{}/open".format(notification.id), follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(notification.is_read)
        response = self.client.post("/crm/tasks/{}/status".format(task.id), data={"status": "done"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(task.status, TaskStatus.DONE)
        self.assertEqual(self.client.get("/crm/tasks").status_code, 200)
        self.assertEqual(self.client.get("/crm/notifications").status_code, 200)

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
        self.assertEqual(self.client.get("/crm/commercial-proposal").status_code, 200)
        self.assertIn(b"251140024698", self.client.get("/crm/commercial-proposal").data)
        self.assertEqual(self.client.get("/crm/city-tariffs").status_code, 200)

    def test_admin_can_change_tariff(self):
        self.login()
        tariff = db.session.scalar(select(Tariff).where(Tariff.name == "Алматы — Караганда · Сборный груз"))
        response = self.client.post("/crm/tariffs/{}".format(tariff.id), data={
            "name": tariff.name,
            "origin": "Алматы",
            "destination": "Караганда",
            "service_type": "groupage",
            "distance_km": "1100",
            "price_per_kg": "130",
            "price_per_m3": "6000",
            "minimum_price": "0",
            "volumetric_factor": "167",
            "rounding_step": "500",
            "delivery_days_min": "3",
            "delivery_days_max": "6",
            "valid_from": tariff.valid_from.isoformat(),
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        quote = self.client.post("/api/calculate", json={
            "from": "Алматы", "to": "Караганда", "transport": "groupage",
            "weight": 100, "volume": 0.5,
        }).get_json()
        self.assertEqual(quote["price"], 13000)
        tariff.price_per_kg = 120
        db.session.commit()


if __name__ == "__main__":
    unittest.main()
