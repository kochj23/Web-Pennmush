"""
Security Tests -- Building-command permissions
Author: Jordan Koch (GitHub: kochj23)

Regression tests for a privilege escalation: @set, @describe, @destroy, @lock and @unlock had no
ownership checks, so any player could run `@set me=WIZARD` and become an admin. Players may now only
change themselves and objects they own; WIZARD/ROYAL may only be granted by staff and GOD only by God.
"""
import pytest

from backend import auth
from backend.engine.commands import CommandParser
from backend.models import DBObject


async def _setup(session):
    parser = CommandParser(session)
    player = await session.get(DBObject, 10)   # ordinary player in the Central Plaza (#2)
    god = await session.get(DBObject, 1)
    crystal = await session.get(DBObject, 5)   # God-owned thing in the plaza
    return parser, player, god, crystal


class TestSelfPromotion:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("target", ["me", "TestPlayer", "Test"])
    @pytest.mark.parametrize("flag", ["WIZARD", "wizard", "ROYAL", "GOD"])
    async def test_player_cannot_grant_staff_flags(self, seeded_session, target, flag):
        parser, player, _, _ = await _setup(seeded_session)
        result = await parser.cmd_set(player, f"{target}={flag}")
        assert "Permission denied" in result
        await seeded_session.refresh(player)
        assert not auth.is_admin(player)

    @pytest.mark.asyncio
    async def test_comma_cannot_smuggle_flags(self, seeded_session):
        parser, player, _, _ = await _setup(seeded_session)
        result = await parser.cmd_set(player, "me=DARK,WIZARD")
        assert "Invalid flag" in result
        await seeded_session.refresh(player)
        assert not auth.is_admin(player)

    @pytest.mark.asyncio
    async def test_parse_path_blocks_self_promotion(self, seeded_session):
        parser, player, _, _ = await _setup(seeded_session)
        await parser.parse(player, "@set me=WIZARD")
        await seeded_session.refresh(player)
        assert not auth.is_admin(player)

    @pytest.mark.asyncio
    async def test_player_can_set_harmless_flag_on_self(self, seeded_session):
        parser, player, _, _ = await _setup(seeded_session)
        result = await parser.cmd_set(player, "me=DARK")
        assert "Flag DARK set" in result

    @pytest.mark.asyncio
    async def test_pending_flag_not_settable(self, seeded_session):
        parser, _, god, _ = await _setup(seeded_session)
        result = await parser.cmd_set(god, "me=PENDING")
        assert "Permission denied" in result


class TestStaffGrants:

    @pytest.mark.asyncio
    async def test_god_can_grant_wizard(self, seeded_session):
        parser, player, god, _ = await _setup(seeded_session)
        god.location_id = player.location_id
        await seeded_session.commit()
        result = await parser.cmd_set(god, "TestPlayer=WIZARD")
        assert "Flag WIZARD set" in result

    @pytest.mark.asyncio
    async def test_wizard_cannot_grant_god_or_touch_god(self, seeded_session):
        parser, player, god, _ = await _setup(seeded_session)
        player.flags = "WIZARD"
        god.location_id = player.location_id
        await seeded_session.commit()
        assert "Permission denied" in await parser.cmd_set(player, "me=GOD")
        assert "Permission denied" in await parser.cmd_set(player, "One=DARK")
        assert "Permission denied" in await parser.cmd_describe(player, "One=pwned")


class TestOwnership:

    @pytest.mark.asyncio
    async def test_cannot_modify_others_objects(self, seeded_session):
        parser, player, _, crystal = await _setup(seeded_session)
        assert "Permission denied" in await parser.cmd_set(player, "crystal=DARK")
        assert "Permission denied" in await parser.cmd_set(player, "crystal=HP:1")
        assert "Permission denied" in await parser.cmd_describe(player, "crystal=mine now")
        assert "Permission denied" in await parser.cmd_describe(player, "here=mine now")
        assert "Permission denied" in await parser.cmd_lock(player, "crystal/use=#10")
        assert "Permission denied" in await parser.cmd_unlock(player, "crystal/use")
        assert "Permission denied" in await parser.cmd_destroy(player, "crystal")
        assert await seeded_session.get(DBObject, crystal.id) is not None

    @pytest.mark.asyncio
    async def test_owner_can_modify_own_objects(self, seeded_session):
        parser, player, _, crystal = await _setup(seeded_session)
        crystal.owner_id = player.id
        await seeded_session.commit()
        assert "Flag DARK set" in await parser.cmd_set(player, "crystal=DARK")
        assert "Description set" in await parser.cmd_describe(player, "crystal=Mine.")
        assert "Lock 'use' set" in await parser.cmd_lock(player, "crystal/use=#10")
        assert "removed" in await parser.cmd_unlock(player, "crystal/use")
        assert "Destroyed" in await parser.cmd_destroy(player, "crystal")

    @pytest.mark.asyncio
    async def test_player_can_describe_self(self, seeded_session):
        parser, player, _, _ = await _setup(seeded_session)
        assert "Description set" in await parser.cmd_describe(player, "me=A brave adventurer.")
