import os
import tempfile
import unittest

from website import create_app, db
from website.models import GymSession, ROLE_CLIENT, SESSION_AVAILABLE, SESSION_BOOKED, User
from werkzeug.security import generate_password_hash


class BookingRolesTest(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        self.db_path = handle.name
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + self.db_path,
            }
        )
        self.client = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()

    def tearDown(self):
        self.ctx.pop()
        os.unlink(self.db_path)

    def login(self, email, password):
        return self.client.post(
            "/login",
            data={"email": email, "password": password},
            follow_redirects=True,
        )

    def test_client_cannot_open_users(self):
        self.login("client@gym.com", "client123")
        response = self.client.get("/users")
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"You do not have access", response.data)

    def test_book_then_slot_unavailable(self):
        session = GymSession.query.filter_by(status=SESSION_AVAILABLE).first()
        self.assertIsNotNone(session)
        session_id = session.id

        self.login("client@gym.com", "client123")
        confirm = self.client.get(f"/sessions/{session_id}/confirm")
        self.assertEqual(confirm.status_code, 200)
        booked = self.client.post(f"/sessions/{session_id}/book", follow_redirects=True)
        self.assertEqual(booked.status_code, 200)
        self.assertIn(b"Session booked", booked.data)

        refreshed = db.session.get(GymSession, session_id)
        self.assertEqual(refreshed.status, SESSION_BOOKED)

        extra = User(
            email="second@gym.com",
            password=generate_password_hash("client123"),
            name_first="Second",
            name_last="Client",
            role=ROLE_CLIENT,
        )
        db.session.add(extra)
        db.session.commit()
        self.client.get("/logout")
        self.login("second@gym.com", "client123")
        again = self.client.post(f"/sessions/{session_id}/book", follow_redirects=True)
        self.assertIn(b"no longer available", again.data)

    def test_instructor_cannot_book_as_client(self):
        session = GymSession.query.filter_by(status=SESSION_AVAILABLE).first()
        self.assertIsNotNone(session)
        self.login("instructor@gym.com", "instructor123")
        response = self.client.post(f"/sessions/{session.id}/book")
        self.assertEqual(response.status_code, 403)
        refreshed = db.session.get(GymSession, session.id)
        self.assertEqual(refreshed.status, SESSION_AVAILABLE)
        self.assertIsNone(refreshed.client_id)

    def test_seeded_clients_can_be_compared_by_role(self):
        emails = ["client@gym.com", "jordan@gym.com", "riley@gym.com", "morgan@gym.com"]
        clients = User.query.filter(User.email.in_(emails)).all()
        self.assertEqual(len(clients), 4)
        self.assertTrue(all(user.role == ROLE_CLIENT for user in clients))
        self.assertEqual(User.query.filter_by(role="instructor").count(), 2)
        self.assertEqual(User.query.filter_by(role="admin").count(), 1)

        self.login("jordan@gym.com", "client123")
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn(b"Client", home.data)
        self.assertEqual(self.client.get("/users").status_code, 403)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        users_page = self.client.get("/users")
        self.assertEqual(users_page.status_code, 200)
        for email in emails + ["sam@gym.com", "instructor@gym.com"]:
            self.assertIn(email.encode(), users_page.data)
        self.assertIn(b"filterRole", users_page.data)

    def test_calendar_labels_open_slots_and_past_bookings(self):
        from datetime import datetime, timedelta

        from website.models import SESSION_BOOKED

        instructor = User.query.filter_by(email="instructor@gym.com").first()
        client = User.query.filter_by(email="client@gym.com").first()
        past_start = datetime.now().replace(minute=0, second=0, microsecond=0) - timedelta(days=2)
        db.session.add(
            GymSession(
                instructor_id=instructor.id,
                client_id=client.id,
                datetime_start=past_start,
                datetime_end=past_start + timedelta(hours=1),
                status=SESSION_BOOKED,
            )
        )
        db.session.commit()

        self.login("client@gym.com", "client123")
        page = self.client.get("/book")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Open slots", page.data)
        self.assertIn(b"No slots", page.data)
        self.assertIn(b"No bookings", page.data)
        self.assertIn(b"past-booked", page.data)
        self.assertIn(b"has-booked", page.data)
        self.assertNotIn(b">None<", page.data)

        self.assertIn(b"Previous month", page.data)
        self.assertIn(b"Next month", page.data)
        self.assertNotIn(b"month-select", page.data)
        self.assertIn(b"day-disabled", page.data)

        blocked = self.client.get("/book/2099/1/1", follow_redirects=False)
        self.assertEqual(blocked.status_code, 302)

        self.client.get("/logout")
        self.login("admin@gym.com", "admin123")
        admin_cal = self.client.get("/book")
        self.assertIn(b"month-select", admin_cal.data)
        open_empty = self.client.get("/book/2099/1/1")
        self.assertEqual(open_empty.status_code, 200)


if __name__ == "__main__":
    unittest.main()
