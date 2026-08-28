# Agent notes

- Conventional commits (`feat`, `fix`, `test`, `chore`, `docs`).
- Do not commit `*.db` or `instance/database.db`.
- Leave the Flask process running after testing. Restart only via the existing `flask-dev` / `python main.py` session; do not `pkill -f`.
- Local run: `FLASK_DEBUG=1 SEED_DEMO=1 python main.py` on http://127.0.0.1:5000.
- Tests: `python -m unittest tests.test_booking`.
- Prefer writing results in chat; do not record demo videos unless asked.
