"""
Functional Tests -- REST API Endpoints
Author: Jordan Koch (GitHub: kochj23)

Tests player registration, player retrieval, object endpoints,
room contents, stats, and health check.
"""
import pytest
import pytest_asyncio


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_endpoint(self, app_client, admin_headers):
        resp = await app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data


class TestAPIRoot:
    @pytest.mark.asyncio
    async def test_api_root(self, app_client, admin_headers):
        resp = await app_client.get("/api/", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "Web-Pennmush" in data["name"]


class TestPlayerRegistration:
    @pytest.mark.asyncio
    async def test_register_player(self, app_client, admin_headers):
        resp = await app_client.post("/api/players/register", json={
            "username": "NewPlayer",
            "password": "secret123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "NewPlayer"
        assert data["is_connected"] is False

    @pytest.mark.asyncio
    async def test_register_duplicate_username(self, app_client, admin_headers):
        await app_client.post("/api/players/register", json={
            "username": "Duplicate",
            "password": "password-one",
        })
        resp = await app_client.post("/api/players/register", json={
            "username": "Duplicate",
            "password": "password-two",
        })
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()


class TestPlayerEndpoints:
    @pytest.mark.asyncio
    async def test_get_player(self, app_client, admin_headers):
        resp = await app_client.get("/api/players/1", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["name"] == "One"

    @pytest.mark.asyncio
    async def test_get_player_not_found(self, app_client, admin_headers):
        resp = await app_client.get("/api/players/9999", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_players(self, app_client, admin_headers):
        resp = await app_client.get("/api/players", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1


class TestObjectEndpoints:
    @pytest.mark.asyncio
    async def test_get_object(self, app_client, admin_headers):
        resp = await app_client.get("/api/objects/0", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Room Zero"
        assert data["type"] == "ROOM"

    @pytest.mark.asyncio
    async def test_get_object_not_found(self, app_client, admin_headers):
        resp = await app_client.get("/api/objects/9999", headers=admin_headers)
        assert resp.status_code == 404


class TestRoomContents:
    @pytest.mark.asyncio
    async def test_get_room_contents(self, app_client, admin_headers):
        resp = await app_client.get("/api/rooms/0/contents", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_get_invalid_room_contents(self, app_client, admin_headers):
        resp = await app_client.get("/api/rooms/9999/contents", headers=admin_headers)
        assert resp.status_code == 404


class TestRoomMap:
    @pytest.mark.asyncio
    async def test_get_room_map(self, app_client, admin_headers):
        resp = await app_client.get("/api/rooms/map", params={"center_room_id": 0, "radius": 5}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data
        assert "edges" in data


class TestStats:
    @pytest.mark.asyncio
    async def test_get_stats(self, app_client, admin_headers):
        resp = await app_client.get("/api/stats", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "rooms" in data
        assert "players" in data
