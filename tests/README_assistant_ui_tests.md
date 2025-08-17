Assistant V2 UI Tests
======================

Playwright-based end-to-end tests (pytest-playwright) covering:
1. Minimize / expand panel
2. Enter key send behavior
3. Typing indicator lifecycle
4. Scroll anchor behavior when scrolled up

Prerequisites
-------------
1. Install new dependencies:
   pip install -r requirements.txt
2. Install Playwright browsers (once):
   playwright install --with-deps
3. Run the Flask app (must be reachable):
   export FLASK_ENV=testing
   flask run

Environment Variables
---------------------
APP_BASE_URL (default http://localhost:5001)
DISABLE_PLAYWRIGHT=1 to skip these tests.

Run Only UI Tests
-----------------
pytest -k assistant_v2_ui -vv

Run All Including UI
--------------------
pytest -vv

Troubleshooting
---------------
If tests hang waiting for AI response, backend endpoint may be slow/unavailable. You can mock responses or provide a lightweight fixture page with assistant markup.
