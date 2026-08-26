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


if __name__ == "__main__":
    unittest.main()
