"""
Unit Tests -- Command Parser
Author: Jordan Koch (GitHub: kochj23)

Tests the main command parser and a selection of critical command handlers.
"""
import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock

from backend.engine.commands import CommandParser
from backend.models import DBObject, ObjectType


class TestCommandParser:

    @pytest.mark.asyncio
    async def test_empty_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.parse(player, "")
        assert result == ""

    @pytest.mark.asyncio
    async def test_whitespace_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.parse(player, "   ")
        assert result == ""

    @pytest.mark.asyncio
    async def test_unknown_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.parse(player, "xyzzy")
        assert "Huh?" in result

    @pytest.mark.asyncio
    async def test_look_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_look(player, "")
        assert "Central Plaza" in result

    @pytest.mark.asyncio
    async def test_look_at_object(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_look(player, "crystal")
        assert "crystal" in result.lower()

    @pytest.mark.asyncio
    async def test_look_at_nonexistent(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_look(player, "unicorn")
        assert "don't see" in result.lower()

    @pytest.mark.asyncio
    async def test_examine_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_examine(player, "crystal")
        assert "magic crystal" in result.lower()
        assert "POWER" in result

    @pytest.mark.asyncio
    async def test_examine_empty(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_examine(player, "")
        assert "Examine what?" in result

    @pytest.mark.asyncio
    async def test_say_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_say(player, "Hello world")
        assert 'You say, "Hello world"' in result

    @pytest.mark.asyncio
    async def test_say_empty(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_say(player, "")
        assert "Say what?" in result

    @pytest.mark.asyncio
    async def test_say_shortcut(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.parse(player, '"Hello')
        assert "You say" in result

    @pytest.mark.asyncio
    async def test_pose_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_pose(player, "waves")
        assert "TestPlayer waves" in result

    @pytest.mark.asyncio
    async def test_pose_shortcut(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.parse(player, ":dances")
        assert "TestPlayer dances" in result

    @pytest.mark.asyncio
    async def test_inventory_empty(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_inventory(player, "")
        assert "aren't carrying" in result.lower()

    @pytest.mark.asyncio
    async def test_get_object(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_get(player, "crystal")
        assert "pick up" in result.lower()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_get(player, "unicorn")
        assert "don't see" in result.lower()

    @pytest.mark.asyncio
    async def test_create_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_create(player, "shiny gem")
        assert "Created" in result

    @pytest.mark.asyncio
    async def test_create_invalid_name(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_create(player, "<script>evil</script>")
        assert "Cannot create" in result

    @pytest.mark.asyncio
    async def test_dig_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_dig(player, "Secret Chamber")
        assert "Dug" in result

    @pytest.mark.asyncio
    async def test_describe_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_describe(player, "here=A beautiful plaza.")
        assert "Description set" in result

    @pytest.mark.asyncio
    async def test_describe_xss_rejected(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_describe(player, "here=<script>alert(1)</script>")
        assert "Cannot set" in result

    @pytest.mark.asyncio
    async def test_who_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_who(player, "")
        assert "Connected Players" in result or "TestPlayer" in result

    @pytest.mark.asyncio
    async def test_stats_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_stats(player, "")
        assert "Statistics" in result

    @pytest.mark.asyncio
    async def test_help_command(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_help(player, "")
        assert "Categories" in result or "Help" in result

    @pytest.mark.asyncio
    async def test_go_empty(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_go(player, "")
        assert "Go where?" in result

    @pytest.mark.asyncio
    async def test_destroy_player_rejected(self, seeded_session):
        parser = CommandParser(seeded_session)
        god = await seeded_session.get(DBObject, 1)
        god.location_id = 2
        await seeded_session.commit()

        result = await parser.cmd_destroy(god, "TestPlayer")
        assert "can't destroy" in result.lower()


class TestCommandParserModeration:
    """Tests that moderation commands enforce permissions."""

    @pytest.mark.asyncio
    async def test_ban_requires_wizard(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_ban(player, "One=testing")
        assert "Permission denied" in result

    @pytest.mark.asyncio
    async def test_kick_requires_wizard(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_kick(player, "One")
        assert "Permission denied" in result

    @pytest.mark.asyncio
    async def test_muzzle_requires_wizard(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_muzzle(player, "One")
        assert "Permission denied" in result

    @pytest.mark.asyncio
    async def test_economy_grant_requires_wizard(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_economy_grant(player, "One=1000")
        assert "Permission denied" in result

    @pytest.mark.asyncio
    async def test_quest_create_requires_wizard(self, seeded_session):
        parser = CommandParser(seeded_session)
        player = await seeded_session.get(DBObject, 10)
        result = await parser.cmd_quest_create(player, "Test=Desc")
        assert "Permission denied" in result
