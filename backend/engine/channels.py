"""
Web-Pennmush Channel System
Author: Jordan Koch (GitHub: kochj23)

Manages communication channels for group chat.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Channel, ChannelMembership, DBObject, ObjectType
from typing import List, Optional, Dict
from datetime import datetime


class ChannelManager:
    """Manages channel creation, membership, and messaging"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_channel(self, channel_id: int) -> Optional[Channel]:
        """Get a channel by ID"""
        return await self.session.get(Channel, channel_id)

    async def get_channel_by_name(self, name: str) -> Optional[Channel]:
        """Get a channel by name or alias"""
        query = select(Channel).where(
            (Channel.name.ilike(name)) | (Channel.alias.ilike(name))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_all_channels(self) -> List[Channel]:
        """List all public channels"""
        query = select(Channel).where(Channel.is_public == True).order_by(Channel.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_channel(
        self,
        name: str,
        owner_id: int,
        alias: Optional[str] = None,
        description: Optional[str] = None,
        is_public: bool = True
    ) -> Channel:
        """Create a new channel"""
        channel = Channel(
            name=name,
            alias=alias,
            description=description,
            owner_id=owner_id,
            is_public=is_public,
            created_at=datetime.utcnow()
        )
        self.session.add(channel)
        await self.session.commit()
        await self.session.refresh(channel)

        # Auto-join owner as moderator
        membership = ChannelMembership(
            channel_id=channel.id,
            player_id=owner_id,
            is_moderator=True
        )
        self.session.add(membership)
        await self.session.commit()

        return channel

    async def join_channel(self, channel_id: int, player_id: int) -> bool:
        """Join a channel"""
        # Check if already a member
        query = select(ChannelMembership).where(
            ChannelMembership.channel_id == channel_id,
            ChannelMembership.player_id == player_id
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            return False  # Already a member

        membership = ChannelMembership(
            channel_id=channel_id,
            player_id=player_id
        )
        self.session.add(membership)
        await self.session.commit()
        return True

    async def leave_channel(self, channel_id: int, player_id: int) -> bool:
        """Leave a channel"""
        query = select(ChannelMembership).where(
            ChannelMembership.channel_id == channel_id,
            ChannelMembership.player_id == player_id
        )
        result = await self.session.execute(query)
        membership = result.scalar_one_or_none()

        if not membership:
            return False

        await self.session.delete(membership)
        await self.session.commit()
        return True

    async def is_member(self, channel_id: int, player_id: int) -> bool:
        """Check if a player is a member of a channel"""
        query = select(ChannelMembership).where(
            ChannelMembership.channel_id == channel_id,
            ChannelMembership.player_id == player_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_members(self, channel_id: int) -> List[DBObject]:
        """Get all members of a channel"""
        query = select(DBObject).join(
            ChannelMembership,
            ChannelMembership.player_id == DBObject.id
        ).where(
            ChannelMembership.channel_id == channel_id
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_player_channels(self, player_id: int) -> List[Channel]:
        """Get all channels a player is a member of"""
        query = select(Channel).join(
            ChannelMembership,
            ChannelMembership.channel_id == Channel.id
        ).where(
            ChannelMembership.player_id == player_id
        ).order_by(Channel.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def format_channel_list(self, player_id: int) -> str:
        """Format a list of channels for display"""
        all_channels = await self.list_all_channels()
        player_channels = await self.get_player_channels(player_id)
        player_channel_ids = {c.id for c in player_channels}

        output = ["=== Available Channels ==="]
        output.append(f"{'Name':<15} {'Alias':<8} {'Status':<10} {'Description':<40}")
        output.append("-" * 75)

        for channel in all_channels:
            status = "Joined" if channel.id in player_channel_ids else "Available"
            alias = channel.alias or "-"
            desc = channel.description or "No description"
            output.append(f"{channel.name:<15} {alias:<8} {status:<10} {desc:<40}")

        output.append("")
        output.append(f"Total channels: {len(all_channels)} | Joined: {len(player_channels)}")
        return "\n".join(output)

    async def format_channel_message(
        self,
        channel: Channel,
        player: DBObject,
        message: str
    ) -> Dict[str, any]:
        """Format a channel message for broadcast"""
        return {
            "type": "channel_message",
            "channel_name": channel.name,
            "channel_alias": channel.alias,
            "player_id": player.id,
            "player_name": player.name,
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }


class HelpManager:
    """Manages help topics and documentation"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_topic(self, topic: str) -> Optional[any]:
        """Get a help topic by name or alias"""
        from backend.models import HelpTopic

        # Try exact match first
        query = select(HelpTopic).where(HelpTopic.topic.ilike(topic))
        result = await self.session.execute(query)
        help_topic = result.scalar_one_or_none()

        if help_topic:
            return help_topic

        # Try alias match
        query = select(HelpTopic).where(
            HelpTopic.aliases.like(f"%{topic}%")
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_categories(self) -> Dict[str, int]:
        """List all help categories with topic counts"""
        from backend.models import HelpTopic
        from sqlalchemy import func

        query = select(
            HelpTopic.category,
            func.count(HelpTopic.id)
        ).group_by(HelpTopic.category)
        result = await self.session.execute(query)
        return dict(result.all())

    async def list_topics_in_category(self, category: str) -> List[any]:
        """List all topics in a category"""
        from backend.models import HelpTopic

        query = select(HelpTopic).where(
            HelpTopic.category.ilike(category)
        ).order_by(HelpTopic.topic)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def search_topics(self, search_term: str) -> List[any]:
        """Search for help topics"""
        from backend.models import HelpTopic

        query = select(HelpTopic).where(
            (HelpTopic.topic.ilike(f"%{search_term}%")) |
            (HelpTopic.content.ilike(f"%{search_term}%")) |
            (HelpTopic.aliases.ilike(f"%{search_term}%"))
        ).order_by(HelpTopic.topic)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def format_help(self, topic: Optional[str] = None) -> str:
        """Format help output"""
        if not topic:
            # Show categories
            categories = await self.list_categories()
            output = ["=== Help Categories ==="]
            output.append("")
            for category, count in sorted(categories.items()):
                output.append(f"  {category.title():<15} ({count} topics)")
            output.append("")
            output.append("Usage: help <topic> or help <category>")
            output.append("Example: help look, help commands, help building")
            return "\n".join(output)

        # Try to get specific topic
        help_topic = await self.get_topic(topic)
        if help_topic:
            output = [help_topic.content]
            if help_topic.related_topics:
                output.append("")
                output.append(f"Related topics: {help_topic.related_topics}")
            return "\n".join(output)

        # Try as category
        topics = await self.list_topics_in_category(topic)
        if topics:
            output = [f"=== {topic.title()} Topics ==="]
            output.append("")
            for t in topics:
                aliases = f" ({t.aliases})" if t.aliases else ""
                output.append(f"  {t.topic}{aliases}")
            output.append("")
            output.append(f"Use 'help <topic>' for detailed information.")
            return "\n".join(output)

        # Search fallback
        results = await self.search_topics(topic)
        if results:
            output = [f"=== Search results for '{topic}' ==="]
            output.append("")
            for t in results[:10]:  # Limit to 10 results
                output.append(f"  {t.topic} ({t.category})")
            output.append("")
            output.append(f"Use 'help <topic>' to view a specific topic.")
            return "\n".join(output)

        return f"No help available for '{topic}'. Try 'help' for a list of categories."
