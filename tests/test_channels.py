"""
Unit Tests -- Channel and Help Systems
Author: Jordan Koch (GitHub: kochj23)

Tests channel CRUD, membership, and the help topic system.
"""
import pytest
import pytest_asyncio

from backend.engine.channels import ChannelManager, HelpManager
from backend.models import Channel, ChannelMembership, HelpTopic


class TestChannelManager:

    @pytest.mark.asyncio
    async def test_get_channel_by_name(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("Public")
        assert ch is not None
        assert ch.name == "Public"

    @pytest.mark.asyncio
    async def test_get_channel_by_alias(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("pub")
        assert ch is not None
        assert ch.name == "Public"

    @pytest.mark.asyncio
    async def test_get_channel_not_found(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("NonExistent")
        assert ch is None

    @pytest.mark.asyncio
    async def test_create_channel(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.create_channel(
            name="TestChannel",
            owner_id=1,
            alias="test",
            description="A test channel.",
        )
        assert ch.name == "TestChannel"
        assert ch.alias == "test"
        # Owner should be auto-joined
        assert await mgr.is_member(ch.id, 1) is True

    @pytest.mark.asyncio
    async def test_join_channel(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("Public")
        result = await mgr.join_channel(ch.id, 10)
        assert result is True
        assert await mgr.is_member(ch.id, 10) is True

    @pytest.mark.asyncio
    async def test_join_channel_already_member(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("Public")
        await mgr.join_channel(ch.id, 10)
        result = await mgr.join_channel(ch.id, 10)
        assert result is False  # Already a member

    @pytest.mark.asyncio
    async def test_leave_channel(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("Public")
        await mgr.join_channel(ch.id, 10)
        result = await mgr.leave_channel(ch.id, 10)
        assert result is True
        assert await mgr.is_member(ch.id, 10) is False

    @pytest.mark.asyncio
    async def test_leave_channel_not_member(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        ch = await mgr.get_channel_by_name("Public")
        result = await mgr.leave_channel(ch.id, 10)
        assert result is False

    @pytest.mark.asyncio
    async def test_list_all_channels(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        channels = await mgr.list_all_channels()
        assert len(channels) >= 1
        names = [c.name for c in channels]
        assert "Public" in names

    @pytest.mark.asyncio
    async def test_format_channel_list(self, seeded_session):
        mgr = ChannelManager(seeded_session)
        output = await mgr.format_channel_list(10)
        assert "Public" in output
        assert "Available" in output or "Joined" in output


class TestHelpManager:

    @pytest.mark.asyncio
    async def test_get_topic(self, seeded_session):
        mgr = HelpManager(seeded_session)
        topic = await mgr.get_topic("help")
        assert topic is not None
        assert "HELP" in topic.content

    @pytest.mark.asyncio
    async def test_get_topic_by_alias(self, seeded_session):
        mgr = HelpManager(seeded_session)
        topic = await mgr.get_topic("?")
        assert topic is not None

    @pytest.mark.asyncio
    async def test_get_topic_not_found(self, seeded_session):
        mgr = HelpManager(seeded_session)
        topic = await mgr.get_topic("nonexistent_garbage_xyz")
        assert topic is None

    @pytest.mark.asyncio
    async def test_format_help_no_topic(self, seeded_session):
        mgr = HelpManager(seeded_session)
        output = await mgr.format_help(None)
        assert "Categories" in output

    @pytest.mark.asyncio
    async def test_format_help_specific_topic(self, seeded_session):
        mgr = HelpManager(seeded_session)
        output = await mgr.format_help("help")
        assert "HELP" in output
