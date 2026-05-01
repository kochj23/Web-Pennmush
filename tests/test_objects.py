"""
Unit Tests -- Object Manager
Author: Jordan Koch (GitHub: kochj23)

Tests object creation, retrieval, attribute management, flags, and movement.
"""
import pytest
import pytest_asyncio

from backend.engine.objects import ObjectManager
from backend.models import DBObject, ObjectType, Attribute


class TestObjectManager:

    @pytest.mark.asyncio
    async def test_get_object(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        room = await mgr.get_object(0)
        assert room is not None
        assert room.name == "Room Zero"

    @pytest.mark.asyncio
    async def test_get_object_not_found(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        obj = await mgr.get_object(9999)
        assert obj is None

    @pytest.mark.asyncio
    async def test_get_object_by_name(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        player = await mgr.get_object_by_name("TestPlayer")
        assert player is not None
        assert player.type == ObjectType.PLAYER

    @pytest.mark.asyncio
    async def test_get_object_by_name_with_location(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        crystal = await mgr.get_object_by_name("crystal", location_id=2)
        assert crystal is not None
        assert crystal.name == "magic crystal"

    @pytest.mark.asyncio
    async def test_get_object_by_name_wrong_location(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        result = await mgr.get_object_by_name("crystal", location_id=0)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_object(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        obj = await mgr.create_object(
            name="New Widget",
            obj_type=ObjectType.THING,
            owner_id=1,
            location_id=2,
            description="Shiny.",
        )
        assert obj.id is not None
        assert obj.name == "New Widget"
        assert obj.type == ObjectType.THING

    @pytest.mark.asyncio
    async def test_set_and_get_attribute(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        attr = await mgr.set_attribute(5, "MAGIC", "fire")
        assert attr.name == "MAGIC"
        assert attr.value == "fire"

        fetched = await mgr.get_attribute(5, "magic")  # case-insensitive via upper()
        assert fetched is not None
        assert fetched.value == "fire"

    @pytest.mark.asyncio
    async def test_update_existing_attribute(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        await mgr.set_attribute(5, "POWER", "99")
        attr = await mgr.get_attribute(5, "POWER")
        assert attr.value == "99"

    @pytest.mark.asyncio
    async def test_get_all_attributes(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        attrs = await mgr.get_all_attributes(5)
        assert len(attrs) >= 1
        names = [a.name for a in attrs]
        assert "POWER" in names

    @pytest.mark.asyncio
    async def test_move_object(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        # Move crystal from Central Plaza (2) to Room Zero (0)
        result = await mgr.move_object(5, 0)
        assert result is True
        crystal = await mgr.get_object(5)
        assert crystal.location_id == 0

    @pytest.mark.asyncio
    async def test_move_nonexistent_object(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        result = await mgr.move_object(9999, 0)
        assert result is False

    @pytest.mark.asyncio
    async def test_move_to_nonexistent_location(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        result = await mgr.move_object(5, 9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_contents(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        contents = await mgr.get_contents(2)
        ids = [obj.id for obj in contents]
        # TestPlayer (10) and crystal (5) are in Central Plaza
        assert 5 in ids
        assert 10 in ids

    @pytest.mark.asyncio
    async def test_get_exits(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        exits = await mgr.get_exits(0)
        assert len(exits) >= 1
        names = [e.name for e in exits]
        assert "portal" in names

    @pytest.mark.asyncio
    async def test_get_players_in_room(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        players = await mgr.get_players_in_room(2)
        assert len(players) >= 1
        names = [p.name for p in players]
        assert "TestPlayer" in names

    @pytest.mark.asyncio
    async def test_delete_object(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        result = await mgr.delete_object(5)
        assert result is True
        crystal = await mgr.get_object(5)
        assert crystal.type == ObjectType.GARBAGE

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        result = await mgr.delete_object(9999)
        assert result is False

    @pytest.mark.asyncio
    async def test_has_flag(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        god = await mgr.get_object(1)
        assert mgr.has_flag(god, "GOD") is True
        assert mgr.has_flag(god, "WIZARD") is True
        assert mgr.has_flag(god, "NONEXISTENT") is False

    @pytest.mark.asyncio
    async def test_add_flag(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        player = await mgr.get_object(10)
        mgr.add_flag(player, "BUILDER")
        assert mgr.has_flag(player, "BUILDER") is True

    @pytest.mark.asyncio
    async def test_add_duplicate_flag(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        god = await mgr.get_object(1)
        original_flags = god.flags
        mgr.add_flag(god, "GOD")
        assert god.flags.count("GOD") == original_flags.count("GOD")

    @pytest.mark.asyncio
    async def test_remove_flag(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        god = await mgr.get_object(1)
        mgr.remove_flag(god, "ROYAL")
        assert mgr.has_flag(god, "ROYAL") is False
        assert mgr.has_flag(god, "GOD") is True  # other flags untouched

    @pytest.mark.asyncio
    async def test_has_flag_empty_flags(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        player = await mgr.get_object(10)
        assert mgr.has_flag(player, "WIZARD") is False

    @pytest.mark.asyncio
    async def test_get_object_info(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        info = await mgr.get_object_info(5)
        assert info["name"] == "magic crystal"
        assert info["type"] == "THING"
        assert len(info["attributes"]) >= 1

    @pytest.mark.asyncio
    async def test_get_object_info_not_found(self, seeded_session):
        mgr = ObjectManager(seeded_session)
        info = await mgr.get_object_info(9999)
        assert info == {}
