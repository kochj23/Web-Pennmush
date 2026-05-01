"""
Unit Tests -- Mail and Page Systems
Author: Jordan Koch (GitHub: kochj23)

Tests mail send/receive/read/delete and page send/history.
"""
import pytest
import pytest_asyncio

from backend.engine.mail import MailManager
from backend.engine.pages import PageManager
from backend.models import Mail, Page


class TestMailManager:

    @pytest.mark.asyncio
    async def test_send_mail(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Hello", "How are you?")
        assert mail.id is not None
        assert mail.sender_id == 1
        assert mail.recipient_id == 10
        assert mail.is_read is False

    @pytest.mark.asyncio
    async def test_get_inbox(self, seeded_session):
        mgr = MailManager(seeded_session)
        await mgr.send_mail(1, 10, "Msg1", "Body1")
        await mgr.send_mail(1, 10, "Msg2", "Body2")
        inbox = await mgr.get_inbox(10)
        assert len(inbox) == 2

    @pytest.mark.asyncio
    async def test_get_inbox_unread_only(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Read Me", "Content")
        await mgr.read_mail(mail.id, 10)
        await mgr.send_mail(1, 10, "Unread", "Content2")
        unread = await mgr.get_inbox(10, unread_only=True)
        assert len(unread) == 1
        assert unread[0].subject == "Unread"

    @pytest.mark.asyncio
    async def test_read_mail(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Test", "Body")
        read = await mgr.read_mail(mail.id, 10)
        assert read is not None
        assert read.is_read is True

    @pytest.mark.asyncio
    async def test_read_mail_wrong_player(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Private", "Secret")
        result = await mgr.read_mail(mail.id, 1)  # Wrong recipient
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_mail(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Delete Me", "Gone")
        result = await mgr.delete_mail(mail.id, 10)
        assert result is True
        inbox = await mgr.get_inbox(10)
        assert len(inbox) == 0

    @pytest.mark.asyncio
    async def test_delete_mail_wrong_player(self, seeded_session):
        mgr = MailManager(seeded_session)
        mail = await mgr.send_mail(1, 10, "Stay", "Protected")
        result = await mgr.delete_mail(mail.id, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_unread_count(self, seeded_session):
        mgr = MailManager(seeded_session)
        await mgr.send_mail(1, 10, "A", "a")
        await mgr.send_mail(1, 10, "B", "b")
        count = await mgr.get_unread_count(10)
        assert count == 2

    @pytest.mark.asyncio
    async def test_format_mail_list_empty(self, seeded_session):
        mgr = MailManager(seeded_session)
        output = await mgr.format_mail_list([])
        assert "No mail" in output


class TestPageManager:

    @pytest.mark.asyncio
    async def test_send_page(self, seeded_session):
        mgr = PageManager(seeded_session)
        page = await mgr.send_page(1, 10, "Hey there!")
        assert page.id is not None
        assert page.message == "Hey there!"

    @pytest.mark.asyncio
    async def test_get_recent_pages(self, seeded_session):
        mgr = PageManager(seeded_session)
        await mgr.send_page(1, 10, "Msg1")
        await mgr.send_page(10, 1, "Reply")
        pages = await mgr.get_recent_pages(10)
        assert len(pages) == 2

    @pytest.mark.asyncio
    async def test_mark_as_read(self, seeded_session):
        mgr = PageManager(seeded_session)
        page = await mgr.send_page(1, 10, "Read me")
        result = await mgr.mark_as_read(page.id, 10)
        assert result is True

    @pytest.mark.asyncio
    async def test_mark_as_read_wrong_player(self, seeded_session):
        mgr = PageManager(seeded_session)
        page = await mgr.send_page(1, 10, "Private")
        result = await mgr.mark_as_read(page.id, 1)
        assert result is False

    @pytest.mark.asyncio
    async def test_format_page_history_empty(self, seeded_session):
        mgr = PageManager(seeded_session)
        output = await mgr.format_page_history(10)
        assert "No recent" in output

    @pytest.mark.asyncio
    async def test_format_page_history(self, seeded_session):
        mgr = PageManager(seeded_session)
        await mgr.send_page(1, 10, "Hello")
        output = await mgr.format_page_history(10)
        assert "Recent Pages" in output
