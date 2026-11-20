"""A request that drags is written to the server log, so a slow lesson can be traced."""
import asyncio
import logging

import main


def test_a_slow_request_is_logged_with_its_path_and_time(caplog):
    async def app(scope, receive, send):
        await asyncio.sleep(0.05)
    middleware = main.SlowRequests(app)
    middleware.SLOW = 0.01
    with caplog.at_level(logging.WARNING, logger="homeschooling.slow"):
        asyncio.run(middleware({"type": "http", "method": "POST", "path": "/api/tutor/sessions/s/activity-events",
                                "client": ("192.168.0.20", 5000)}, None, None))
    assert "POST /api/tutor/sessions/s/activity-events from 192.168.0.20" in caplog.text


def test_a_quick_request_is_not_logged(caplog):
    async def app(scope, receive, send):
        return None
    with caplog.at_level(logging.WARNING, logger="homeschooling.slow"):
        asyncio.run(main.SlowRequests(app)({"type": "http", "method": "GET", "path": "/api/session"}, None, None))
    assert "Slow request" not in caplog.text
