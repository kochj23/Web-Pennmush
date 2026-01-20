"""
Web-Pennmush Economy System
Author: Jordan Koch (GitHub: kochj23)

Currency management, transactions, and economic system.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import PlayerCurrency, Transaction, DBObject
from typing import Optional, List
from datetime import datetime


class EconomyManager:
    """Manages economy and currency system"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_balance(self, player_id: int) -> int:
        """Get player's credit balance"""
        query = select(PlayerCurrency).where(PlayerCurrency.player_id == player_id)
        result = await self.session.execute(query)
        currency = result.scalar_one_or_none()

        if not currency:
            # Create currency record if doesn't exist
            currency = PlayerCurrency(player_id=player_id, credits=0)
            self.session.add(currency)
            await self.session.commit()
            return 0

        return currency.credits

    async def add_credits(
        self,
        player_id: int,
        amount: int,
        transaction_type: str = "admin_grant",
        description: Optional[str] = None
    ) -> int:
        """Add credits to player balance"""
        query = select(PlayerCurrency).where(PlayerCurrency.player_id == player_id)
        result = await self.session.execute(query)
        currency = result.scalar_one_or_none()

        if not currency:
            currency = PlayerCurrency(player_id=player_id, credits=amount)
            self.session.add(currency)
        else:
            currency.credits += amount

        # Log transaction
        transaction = Transaction(
            to_player_id=player_id,
            amount=amount,
            transaction_type=transaction_type,
            description=description
        )
        self.session.add(transaction)

        await self.session.commit()
        return currency.credits

    async def remove_credits(
        self,
        player_id: int,
        amount: int,
        transaction_type: str = "admin_remove",
        description: Optional[str] = None
    ) -> tuple[bool, int]:
        """
        Remove credits from player balance.

        Returns:
            (success, new_balance)
        """
        balance = await self.get_balance(player_id)

        if balance < amount:
            return False, balance  # Insufficient funds

        query = select(PlayerCurrency).where(PlayerCurrency.player_id == player_id)
        result = await self.session.execute(query)
        currency = result.scalar_one_or_none()

        if currency:
            currency.credits -= amount

            # Log transaction
            transaction = Transaction(
                from_player_id=player_id,
                amount=amount,
                transaction_type=transaction_type,
                description=description
            )
            self.session.add(transaction)

            await self.session.commit()
            return True, currency.credits

        return False, 0

    async def transfer_credits(
        self,
        from_player_id: int,
        to_player_id: int,
        amount: int,
        description: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Transfer credits from one player to another.

        Returns:
            (success, message)
        """
        if amount <= 0:
            return False, "Amount must be positive."

        # Check sender balance
        from_balance = await self.get_balance(from_player_id)
        if from_balance < amount:
            return False, f"Insufficient funds. You have {from_balance} credits."

        # Remove from sender
        success, new_from_balance = await self.remove_credits(
            from_player_id,
            amount,
            "transfer_send",
            f"Transfer to #{to_player_id}"
        )

        if not success:
            return False, "Transfer failed."

        # Add to recipient
        new_to_balance = await self.add_credits(
            to_player_id,
            amount,
            "transfer_receive",
            f"Transfer from #{from_player_id}"
        )

        # Log transaction
        transaction = Transaction(
            from_player_id=from_player_id,
            to_player_id=to_player_id,
            amount=amount,
            transaction_type="transfer",
            description=description
        )
        self.session.add(transaction)
        await self.session.commit()

        return True, f"Transferred {amount} credits. Your new balance: {new_from_balance} credits."

    async def get_transaction_history(
        self,
        player_id: int,
        limit: int = 20
    ) -> List[Transaction]:
        """Get transaction history for a player"""
        from sqlalchemy import or_
        query = select(Transaction).where(
            or_(
                Transaction.from_player_id == player_id,
                Transaction.to_player_id == player_id
            )
        ).order_by(Transaction.timestamp.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def format_transaction_history(self, player_id: int, limit: int = 10) -> str:
        """Format transaction history for display"""
        transactions = await self.get_transaction_history(player_id, limit)

        if not transactions:
            return "No transactions yet."

        output = ["=== Transaction History ==="]
        output.append(f"{'Date':<20} {'Type':<15} {'Amount':<10} {'Balance Change':<15}")
        output.append("-" * 60)

        for trans in transactions:
            date_str = trans.timestamp.strftime("%Y-%m-%d %H:%M")
            trans_type = trans.transaction_type[:13]

            if trans.from_player_id == player_id:
                amount_str = f"-{trans.amount}"
            elif trans.to_player_id == player_id:
                amount_str = f"+{trans.amount}"
            else:
                amount_str = str(trans.amount)

            desc = trans.description[:13] if trans.description else ""
            output.append(f"{date_str:<20} {trans_type:<15} {amount_str:<10} {desc:<15}")

        return "\n".join(output)

    async def get_richest_players(self, limit: int = 10) -> List[tuple[DBObject, int]]:
        """Get players with most credits"""
        query = select(PlayerCurrency).order_by(
            PlayerCurrency.credits.desc()
        ).limit(limit)
        result = await self.session.execute(query)
        currency_records = result.scalars().all()

        players_with_balance = []
        for currency in currency_records:
            player = await self.session.get(DBObject, currency.player_id)
            if player:
                players_with_balance.append((player, currency.credits))

        return players_with_balance
