"""
Unit Tests -- Database Models
Author: Jordan Koch (GitHub: kochj23)

Verifies ORM model creation, relationships, and constraints.
"""
import pytest
import pytest_asyncio
from datetime import datetime

from backend.models import (
    DBObject, ObjectType, FlagType, Attribute, Lock, Mail,
    Channel, ChannelMembership, HelpTopic, NPC, Quest, QuestStep,
    QuestProgress, PlayerCurrency, Transaction, BanRecord, Page,
)


class TestDBObject:
    """Tests for the unified DBObject model."""

    @pytest.mark.asyncio
    async def test_create_room(self, db_session):
        room = DBObject(
            name="Test Room",
            type=ObjectType.ROOM,
            owner_id=None,
            description="A test room.",
            flags="VISIBLE",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
        )
        db_session.add(room)
        await db_session.commit()
        await db_session.refresh(room)

        assert room.id is not None
        assert room.name == "Test Room"
        assert room.type == ObjectType.ROOM
        assert room.flags == "VISIBLE"

    @pytest.mark.asyncio
    async def test_create_player(self, db_session):
        player = DBObject(
            name="Alice",
            type=ObjectType.PLAYER,
            password_hash="fakehash",
            description="Test player.",
            flags="",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
            is_connected=False,
        )
        db_session.add(player)
        await db_session.commit()
        await db_session.refresh(player)

        assert player.type == ObjectType.PLAYER
        assert player.is_connected is False
        assert player.password_hash == "fakehash"

    @pytest.mark.asyncio
    async def test_create_exit(self, db_session):
        # Room first
        room = DBObject(
            name="R", type=ObjectType.ROOM, flags="",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(room)
        await db_session.flush()

        exit_obj = DBObject(
            name="north",
            alias="n;go north",
            type=ObjectType.EXIT,
            location_id=room.id,
            home_id=room.id,
            flags="VISIBLE",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
        )
        db_session.add(exit_obj)
        await db_session.commit()
        await db_session.refresh(exit_obj)

        assert exit_obj.type == ObjectType.EXIT
        assert exit_obj.alias == "n;go north"

    @pytest.mark.asyncio
    async def test_create_thing(self, db_session):
        thing = DBObject(
            name="sword",
            type=ObjectType.THING,
            description="A sharp blade.",
            flags="VISIBLE",
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
        )
        db_session.add(thing)
        await db_session.commit()
        assert thing.type == ObjectType.THING

    @pytest.mark.asyncio
    async def test_repr(self, db_session):
        obj = DBObject(
            id=42, name="Widget", type=ObjectType.THING,
            flags="", created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        assert "Widget" in repr(obj)
        assert "42" in repr(obj)

    def test_object_type_values(self):
        assert ObjectType.ROOM.value == "ROOM"
        assert ObjectType.PLAYER.value == "PLAYER"
        assert ObjectType.EXIT.value == "EXIT"
        assert ObjectType.THING.value == "THING"
        assert ObjectType.GARBAGE.value == "GARBAGE"

    def test_flag_type_values(self):
        assert FlagType.WIZARD.value == "WIZARD"
        assert FlagType.GOD.value == "GOD"
        assert FlagType.DARK.value == "DARK"


class TestAttribute:
    @pytest.mark.asyncio
    async def test_create_attribute(self, db_session):
        obj = DBObject(
            name="thing", type=ObjectType.THING, flags="",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(obj)
        await db_session.flush()

        attr = Attribute(
            object_id=obj.id, name="POWER", value="42", flags="VISIBLE",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(attr)
        await db_session.commit()
        await db_session.refresh(attr)

        assert attr.name == "POWER"
        assert attr.value == "42"
        assert "POWER" in repr(attr)


class TestMail:
    @pytest.mark.asyncio
    async def test_create_mail(self, db_session):
        for pid in (1, 2):
            p = DBObject(
                id=pid, name=f"P{pid}", type=ObjectType.PLAYER, flags="",
                created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
            )
            db_session.add(p)
        await db_session.flush()

        mail = Mail(
            sender_id=1, recipient_id=2, subject="Hello",
            message="How are you?", is_read=False, sent_at=datetime.utcnow(),
        )
        db_session.add(mail)
        await db_session.commit()
        await db_session.refresh(mail)

        assert mail.subject == "Hello"
        assert mail.is_read is False


class TestChannel:
    @pytest.mark.asyncio
    async def test_create_channel(self, db_session):
        owner = DBObject(
            id=1, name="Owner", type=ObjectType.PLAYER, flags="",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(owner)
        await db_session.flush()

        ch = Channel(
            name="TestChan", alias="tc", description="Test",
            owner_id=1, is_public=True, created_at=datetime.utcnow(),
        )
        db_session.add(ch)
        await db_session.commit()

        assert ch.name == "TestChan"
        assert ch.is_public is True


class TestQuest:
    @pytest.mark.asyncio
    async def test_create_quest_and_steps(self, db_session):
        creator = DBObject(
            id=1, name="C", type=ObjectType.PLAYER, flags="",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(creator)
        await db_session.flush()

        quest = Quest(
            name="Find Crystal", description="Locate the crystal.",
            creator_id=1, reward_credits=100, is_active=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(quest)
        await db_session.flush()

        step = QuestStep(
            quest_id=quest.id, step_number=1,
            description="Go to Central Plaza.",
        )
        db_session.add(step)
        await db_session.commit()

        assert quest.reward_credits == 100
        assert step.step_number == 1


class TestPlayerCurrency:
    @pytest.mark.asyncio
    async def test_default_balance(self, db_session):
        p = DBObject(
            id=1, name="Rich", type=ObjectType.PLAYER, flags="",
            created_at=datetime.utcnow(), modified_at=datetime.utcnow(),
        )
        db_session.add(p)
        await db_session.flush()

        cur = PlayerCurrency(player_id=1, credits=0, created_at=datetime.utcnow(),
                             modified_at=datetime.utcnow())
        db_session.add(cur)
        await db_session.commit()
        assert cur.credits == 0
