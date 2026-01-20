"""
Web-Pennmush Mail System
Author: Jordan Koch (GitHub: kochj23)

Complete mail system for async player communication.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Mail, DBObject
from typing import List, Optional
from datetime import datetime


class MailManager:
    """Manages player-to-player mail system"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def send_mail(
        self,
        sender_id: int,
        recipient_id: int,
        subject: str,
        message: str
    ) -> Mail:
        """Send mail to a player"""
        mail = Mail(
            sender_id=sender_id,
            recipient_id=recipient_id,
            subject=subject,
            message=message,
            is_read=False,
            sent_at=datetime.utcnow()
        )
        self.session.add(mail)
        await self.session.commit()
        await self.session.refresh(mail)
        return mail

    async def get_inbox(self, player_id: int, unread_only: bool = False) -> List[Mail]:
        """Get player's inbox"""
        query = select(Mail).where(Mail.recipient_id == player_id)
        if unread_only:
            query = query.where(Mail.is_read == False)
        query = query.order_by(Mail.sent_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_sent_mail(self, player_id: int) -> List[Mail]:
        """Get mail sent by player"""
        query = select(Mail).where(
            Mail.sender_id == player_id
        ).order_by(Mail.sent_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def read_mail(self, mail_id: int, player_id: int) -> Optional[Mail]:
        """Read a mail message"""
        mail = await self.session.get(Mail, mail_id)
        if not mail or mail.recipient_id != player_id:
            return None

        if not mail.is_read:
            mail.is_read = True
            mail.read_at = datetime.utcnow()
            await self.session.commit()

        return mail

    async def delete_mail(self, mail_id: int, player_id: int) -> bool:
        """Delete a mail message"""
        mail = await self.session.get(Mail, mail_id)
        if not mail or mail.recipient_id != player_id:
            return False

        await self.session.delete(mail)
        await self.session.commit()
        return True

    async def get_unread_count(self, player_id: int) -> int:
        """Get count of unread mail"""
        from sqlalchemy import func
        query = select(func.count()).where(
            Mail.recipient_id == player_id,
            Mail.is_read == False
        )
        result = await self.session.execute(query)
        return result.scalar()

    async def format_mail_list(self, mail_list: List[Mail], show_full: bool = False) -> str:
        """Format mail list for display"""
        if not mail_list:
            return "No mail messages."

        output = ["=== Mail ==="]
        output.append(f"{'#':<5} {'From':<15} {'Subject':<30} {'Date':<20} {'Status':<8}")
        output.append("-" * 80)

        for mail in mail_list[:20]:  # Show first 20
            sender_name = f"#{mail.sender_id}"
            if show_full:
                sender = await self.session.get(DBObject, mail.sender_id)
                if sender:
                    sender_name = sender.name

            status = "Unread" if not mail.is_read else "Read"
            date_str = mail.sent_at.strftime("%Y-%m-%d %H:%M")
            subject = mail.subject[:28] + "..." if len(mail.subject) > 30 else mail.subject

            output.append(f"{mail.id:<5} {sender_name:<15} {subject:<30} {date_str:<20} {status:<8}")

        if len(mail_list) > 20:
            output.append(f"\n... and {len(mail_list) - 20} more")

        return "\n".join(output)
