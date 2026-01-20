"""
Web-Pennmush Quest System
Author: Jordan Koch (GitHub: kochj23)

Quest creation, tracking, and reward system.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Quest, QuestStep, QuestProgress, DBObject
from typing import List, Optional, Dict
from datetime import datetime
import json


class QuestManager:
    """Manages quest system"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_quest(
        self,
        name: str,
        description: str,
        creator_id: int,
        reward_credits: int = 0
    ) -> Quest:
        """Create a new quest"""
        quest = Quest(
            name=name,
            description=description,
            creator_id=creator_id,
            reward_credits=reward_credits,
            is_active=True
        )
        self.session.add(quest)
        await self.session.commit()
        await self.session.refresh(quest)
        return quest

    async def add_quest_step(
        self,
        quest_id: int,
        step_number: int,
        description: str,
        **kwargs
    ) -> QuestStep:
        """Add a step to a quest"""
        step = QuestStep(
            quest_id=quest_id,
            step_number=step_number,
            description=description,
            **kwargs
        )
        self.session.add(step)
        await self.session.commit()
        await self.session.refresh(step)
        return step

    async def get_quest(self, quest_id: int) -> Optional[Quest]:
        """Get quest by ID"""
        return await self.session.get(Quest, quest_id)

    async def get_quest_by_name(self, name: str) -> Optional[Quest]:
        """Get quest by name"""
        query = select(Quest).where(Quest.name.ilike(name))
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def list_active_quests(self) -> List[Quest]:
        """List all active quests"""
        query = select(Quest).where(Quest.is_active == True).order_by(Quest.name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def start_quest(self, quest_id: int, player_id: int) -> QuestProgress:
        """Start a quest for a player"""
        # Check if already in progress
        query = select(QuestProgress).where(
            QuestProgress.quest_id == quest_id,
            QuestProgress.player_id == player_id,
            QuestProgress.is_completed == False
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        progress = QuestProgress(
            quest_id=quest_id,
            player_id=player_id,
            current_step=0,
            is_completed=False,
            started_at=datetime.utcnow()
        )
        self.session.add(progress)
        await self.session.commit()
        await self.session.refresh(progress)
        return progress

    async def advance_quest(self, quest_id: int, player_id: int) -> Optional[QuestProgress]:
        """Advance player to next quest step"""
        query = select(QuestProgress).where(
            QuestProgress.quest_id == quest_id,
            QuestProgress.player_id == player_id,
            QuestProgress.is_completed == False
        )
        result = await self.session.execute(query)
        progress = result.scalar_one_or_none()

        if not progress:
            return None

        # Get quest steps
        quest = await self.get_quest(quest_id)
        if not quest:
            return None

        # Check if there are more steps
        query_steps = select(QuestStep).where(
            QuestStep.quest_id == quest_id,
            QuestStep.step_number > progress.current_step
        ).order_by(QuestStep.step_number)
        result_steps = await self.session.execute(query_steps)
        next_step = result_steps.scalar_one_or_none()

        if next_step:
            progress.current_step = next_step.step_number
        else:
            # Quest completed!
            progress.is_completed = True
            progress.completed_at = datetime.utcnow()
            progress.times_completed += 1

        await self.session.commit()
        return progress

    async def get_player_progress(self, player_id: int) -> List[QuestProgress]:
        """Get all quests a player is working on"""
        query = select(QuestProgress).where(
            QuestProgress.player_id == player_id
        ).order_by(QuestProgress.started_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def format_quest_list(self) -> str:
        """Format available quests for display"""
        quests = await self.list_active_quests()
        if not quests:
            return "No quests available."

        output = ["=== Available Quests ==="]
        for quest in quests:
            output.append(f"\n{quest.name} (ID: {quest.id})")
            output.append(f"  {quest.description}")
            if quest.reward_credits > 0:
                output.append(f"  Reward: {quest.reward_credits} credits")
            if quest.is_repeatable:
                output.append(f"  (Repeatable)")

        return "\n".join(output)

    async def format_player_quests(self, player_id: int) -> str:
        """Format player's active quests"""
        progress_list = await self.get_player_progress(player_id)
        active = [p for p in progress_list if not p.is_completed]
        completed = [p for p in progress_list if p.is_completed]

        output = ["=== Your Quests ==="]

        if active:
            output.append("\nActive:")
            for progress in active:
                quest = await self.get_quest(progress.quest_id)
                if quest:
                    output.append(f"  {quest.name} - Step {progress.current_step}")

        if completed:
            output.append("\nCompleted:")
            for progress in completed[:5]:  # Show last 5 completed
                quest = await self.get_quest(progress.quest_id)
                if quest:
                    times = f" (x{progress.times_completed})" if progress.times_completed > 1 else ""
                    output.append(f"  {quest.name}{times}")

        if not active and not completed:
            output.append("\nNo quests started. Use 'quest/list' to see available quests.")

        return "\n".join(output)
