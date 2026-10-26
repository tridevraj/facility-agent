import os
import threading
import time

from flask import Flask

from .config_loader import load_config
from .db import make_session_factory
from .seed import seed_demo_data


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite:///facility.db")
    app.config["SEED_DEMO"] = os.environ.get("SEED_DEMO", "1") == "1"
    if test_config:
        app.config.update(test_config)

    app.fm_config = load_config(app.config.get("FACILITY_CONFIG"))
    app.session_factory = make_session_factory(app.config["DATABASE_URL"])
    if app.config["SEED_DEMO"]:
        with app.session_factory() as s:
            seed_demo_data(s)

    from .routes import bp
    app.register_blueprint(bp)

    minutes = os.environ.get("SLA_CHECK_MINUTES")
    if minutes and not app.config.get("TESTING"):
        _start_sla_thread(app, float(minutes))
    return app


def _start_sla_thread(app, minutes):
    from .sla import run_sla_check

    def loop():
        while True:
            time.sleep(minutes * 60)
            with app.session_factory() as s:
                for e in run_sla_check(s, app.fm_config):
                    app.logger.warning("SLA escalation: %s", e)

    threading.Thread(target=loop, daemon=True).start()
