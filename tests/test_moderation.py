"""
Unit Tests -- Moderation System
Author: Jordan Koch (GitHub: kochj23)

Tests ban, unban, is_banned (including expiry), and ban listing.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta

from backend.engine.moderation import ModerationManager
from backend.models import DBObject, BanRecord


class TestModerationManager:

    @pytest.mark.asyncio
    async def test_ban_player(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        ban = await mgr.ban_player(10, 1, "Spamming")
        assert ban.player_id == 10
        assert ban.is_active is True

        # Check BANNED flag
        player = await seeded_session.get(DBObject, 10)
        assert "BANNED" in player.flags

    @pytest.mark.asyncio
    async def test_ban_with_duration(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        ban = await mgr.ban_player(10, 1, "Temp ban", duration_days=7)
        assert ban.expires_at is not None

    @pytest.mark.asyncio
    async def test_is_banned(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        await mgr.ban_player(10, 1, "Bad behavior")
        is_banned, ban = await mgr.is_banned(10)
        assert is_banned is True
        assert ban is not None

    @pytest.mark.asyncio
    async def test_is_not_banned(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        is_banned, ban = await mgr.is_banned(10)
        assert is_banned is False
        assert ban is None

    @pytest.mark.asyncio
    async def test_unban_player(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        await mgr.ban_player(10, 1, "Temp issue")
        result = await mgr.unban_player(10)
        assert result is True

        is_banned, _ = await mgr.is_banned(10)
        assert is_banned is False

        # BANNED flag should be removed
        player = await seeded_session.get(DBObject, 10)
        assert "BANNED" not in (player.flags or "")

    @pytest.mark.asyncio
    async def test_unban_not_banned(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        result = await mgr.unban_player(10)
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_ban_auto_clears(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        ban = await mgr.ban_player(10, 1, "Short ban", duration_days=1)
        # Manually set expiry to the past
        ban.expires_at = datetime.utcnow() - timedelta(days=1)
        await seeded_session.commit()

        is_banned, _ = await mgr.is_banned(10)
        assert is_banned is False

    @pytest.mark.asyncio
    async def test_list_active_bans(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        await mgr.ban_player(10, 1, "Reason A")
        bans = await mgr.list_active_bans()
        assert len(bans) >= 1

    @pytest.mark.asyncio
    async def test_format_ban_list_empty(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        output = await mgr.format_ban_list()
        assert "No active" in output

    @pytest.mark.asyncio
    async def test_format_ban_list_with_bans(self, seeded_session):
        mgr = ModerationManager(seeded_session)
        await mgr.ban_player(10, 1, "Spamming")
        output = await mgr.format_ban_list()
        assert "Active Bans" in output
        assert "Spamming" in output
