"""
Web-Pennmush Moderation System
Author: Jordan Koch (GitHub: kochj23)

Moderation tools for banning, kicking, and muting players.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import BanRecord, DBObject
from typing import Optional, List
from datetime import datetime, timedelta


class ModerationManager:
    """Manages player moderation actions"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def ban_player(
        self,
        player_id: int,
        banned_by_id: int,
        reason: str,
        duration_days: Optional[int] = None
    ) -> BanRecord:
        """
        Ban a player.

        Args:
            player_id: Player to ban
            banned_by_id: Admin who issued ban
            reason: Reason for ban
            duration_days: Ban duration in days (None = permanent)

        Returns:
            BanRecord
        """
        expires_at = None
        if duration_days:
            expires_at = datetime.utcnow() + timedelta(days=duration_days)

        ban = BanRecord(
            player_id=player_id,
            banned_by_id=banned_by_id,
            reason=reason,
            banned_at=datetime.utcnow(),
            expires_at=expires_at,
            is_active=True
        )
        self.session.add(ban)

        # Mark player as banned (add flag)
        player = await self.session.get(DBObject, player_id)
        if player:
            if not player.flags:
                player.flags = "BANNED"
            elif "BANNED" not in player.flags:
                player.flags += ",BANNED"

        await self.session.commit()
        await self.session.refresh(ban)
        return ban

    async def unban_player(self, player_id: int) -> bool:
        """Remove ban from player"""
        # Deactivate all active bans
        query = select(BanRecord).where(
            BanRecord.player_id == player_id,
            BanRecord.is_active == True
        )
        result = await self.session.execute(query)
        bans = result.scalars().all()

        if not bans:
            return False

        for ban in bans:
            ban.is_active = False

        # Remove BANNED flag
        player = await self.session.get(DBObject, player_id)
        if player and player.flags:
            flags = [f.strip() for f in player.flags.split(",")]
            if "BANNED" in flags:
                flags.remove("BANNED")
                player.flags = ",".join(flags)

        await self.session.commit()
        return True

    async def is_banned(self, player_id: int) -> tuple[bool, Optional[BanRecord]]:
        """
        Check if player is currently banned.

        Returns:
            (is_banned, active_ban_record)
        """
        query = select(BanRecord).where(
            BanRecord.player_id == player_id,
            BanRecord.is_active == True
        )
        result = await self.session.execute(query)
        ban = result.scalar_one_or_none()

        if not ban:
            return False, None

        # Check if temporary ban has expired
        if ban.expires_at and ban.expires_at < datetime.utcnow():
            ban.is_active = False
            await self.session.commit()
            return False, None

        return True, ban

    async def get_ban_history(self, player_id: int) -> List[BanRecord]:
        """Get all bans for a player"""
        query = select(BanRecord).where(
            BanRecord.player_id == player_id
        ).order_by(BanRecord.banned_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_active_bans(self) -> List[BanRecord]:
        """List all currently active bans"""
        query = select(BanRecord).where(
            BanRecord.is_active == True
        ).order_by(BanRecord.banned_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def format_ban_list(self) -> str:
        """Format active bans for display"""
        bans = await self.list_active_bans()
        if not bans:
            return "No active bans."

        output = ["=== Active Bans ==="]
        output.append(f"{'Player ID':<10} {'Banned By':<12} {'Reason':<30} {'Expires':<20}")
        output.append("-" * 75)

        for ban in bans:
            expires = "Permanent" if not ban.expires_at else ban.expires_at.strftime("%Y-%m-%d %H:%M")
            reason = ban.reason[:28] + "..." if len(ban.reason) > 30 else ban.reason
            output.append(f"#{ban.player_id:<9} #{ban.banned_by_id:<11} {reason:<30} {expires:<20}")

        return "\n".join(output)
