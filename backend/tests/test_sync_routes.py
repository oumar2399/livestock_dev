"""Keep synchronous database work off the ASGI event loop."""

import inspect
from threading import get_ident
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.v1 import activity, alerts, animals, auth, devices, telemetry
from app.core import dependencies
from app.db.database import get_db


@pytest.mark.parametrize("module", [activity, alerts, animals, auth, devices, telemetry])
def test_database_routes_are_synchronous(module):
    for route in module.router.routes:
        if isinstance(route, APIRoute):
            assert not inspect.iscoroutinefunction(route.endpoint), route.path
    assert inspect.iscoroutinefunction(telemetry.read_binary_body)


def test_real_auth_dependency_and_handler_run_outside_event_loop(monkeypatch):
    threads = {}

    class Query:
        def filter(self, *_args):
            return self

        def first(self):
            threads["query"] = get_ident()
            return SimpleNamespace(id=1)

    monkeypatch.setattr(dependencies, "decode_token", lambda _: {"sub": "1", "type": "access"})
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: SimpleNamespace(query=lambda _: Query())

    async def mark_event_loop():
        threads["loop"] = get_ident()

    @app.get("/probe", dependencies=[Depends(mark_event_loop)])
    def probe(user=Depends(dependencies.get_current_user)):
        threads["route"] = get_ident()
        return {"id": user.id}

    with TestClient(app) as client:
        response = client.get("/probe", headers={"Authorization": "Bearer test"})
    assert response.status_code == 200
    assert threads["loop"] != threads["query"]
    assert threads["loop"] != threads["route"]
