import logging
import os

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration


def scrub_event(event, hint):
    request = event.get("request", {})
    for key in ("headers", "cookies", "data", "query_string"):
        request.pop(key, None)
    event.pop("user", None)
    # SQL parameters and provider responses can contain emails or credentials.
    event.pop("breadcrumbs", None)
    for item in event.get("exception", {}).get("values", []):
        item["value"] = item.get("type", "Application error")
        for frame in item.get("stacktrace", {}).get("frames", []):
            frame.pop("vars", None)
    return event


def setup_monitoring():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if os.getenv("SENTRY_DSN"):
        sentry_sdk.init(
            dsn=os.environ["SENTRY_DSN"], environment=os.getenv("APP_ENV", "development"),
            release=os.getenv("APP_RELEASE"), send_default_pii=False,
            include_local_variables=False, traces_sample_rate=0,
            before_send=scrub_event,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )


def report_failure(component: str, error: Exception):
    logging.getLogger(component).error("operation_failed error_type=%s", type(error).__name__)
    with sentry_sdk.isolation_scope() as scope:
        scope.set_tag("component", component)
        sentry_sdk.capture_exception(error)
