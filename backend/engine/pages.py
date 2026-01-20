"""
Web-Pennmush Page System
Author: Jordan Koch (GitHub: kochj23)

Direct messaging system for real-time player communication.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Page, DBObject
from typing import List, Optional
from datetime import datetime


class PageManager:
    """Manages direct messages (pages) between players"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_page(
        self,
        from_player_id: int,
        to_player_id: int,
        message: str
    ) -> Page:
        """Send a page to another player"""
        page = Page(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            message=message,
            sent_at=datetime.utcnow(),
            is_read=False
        )
        self.session.add(page)
        await self.session.commit()
        await self.session.refresh(page)
        return page

    async def get_recent_pages(self, player_id: int, limit: int = 10) -> List[Page]:
        """Get recent pages for a player (sent or received)"""
        from sqlalchemy import or_
        query = select(Page).where(
            or_(
                Page.from_player_id == player_id,
                Page.to_player_id == player_id
            )
        ).order_by(Page.sent_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def mark_as_read(self, page_id: int, player_id: int) -> bool:
        """Mark a page as read"""
        page = await self.session.get(Page, page_id)
        if not page or page.to_player_id != player_id:
            return False

        page.is_read = True
        await self.session.commit()
        return True

    async def format_page_history(self, player_id: int, limit: int = 10) -> str:
        """Format page history for display"""
        pages = await self.get_recent_pages(player_id, limit)
        if not pages:
            return "No recent pages."

        output = ["=== Recent Pages ==="]
        for page in pages:
            if page.from_player_id == player_id:
                direction = "To"
                other_id = page.to_player_id
            else:
                direction = "From"
                other_id = page.from_player_id

            time_str = page.sent_at.strftime("%H:%M")
            output.append(f"[{time_str}] {direction} #{other_id}: {page.message[:50]}...")

        return "\n".join(output)
