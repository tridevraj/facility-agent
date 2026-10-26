import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["FACILITY_AGENT"] = "rule"
os.environ.pop("ANTHROPIC_API_KEY", None)

from app import create_app  # noqa: E402


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE_URL": f"sqlite:///{tmp_path/'t.db'}"})


@pytest.fixture()
def client(app):
    return app.test_client()


def submit(client, text, requester="Tester"):
    r = client.post("/api/requests", json={"text": text, "requester": requester})
    return r.status_code, r.get_json()
