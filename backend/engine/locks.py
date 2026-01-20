"""
Web-Pennmush Lock System
Author: Jordan Koch (GitHub: kochj23)

Advanced lock evaluation for access control, puzzles, and game mechanics.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import Lock, DBObject
from backend.engine.objects import ObjectManager
from typing import Optional
import re


class LockEvaluator:
    """
    Evaluates lock expressions to determine access.

    Lock Syntax:
    - #123          - Object ID #123
    - !#123         - NOT object ID #123
    - @player       - Player type
    - WIZARD        - Has WIZARD flag
    - HP:>50        - Attribute HP greater than 50
    - HP:=100       - Attribute HP equals 100
    - HP:<50        - Attribute HP less than 50
    - &             - AND operator
    - |             - OR operator
    - ()            - Grouping

    Examples:
    - @lock/use sword=#123|WIZARD
      (Only player #123 OR wizards can use)
    - @lock/enter door=HP:>50&QUEST_COMPLETE:1
      (Need HP>50 AND quest complete to enter)
    - @lock/get treasure=!THIEF&(WIZARD|ROYAL)
      (Can get if not a thief AND (wizard OR royal))
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.obj_mgr = ObjectManager(session)

    async def evaluate(
        self,
        lock_key: str,
        player: DBObject,
        target: Optional[DBObject] = None
    ) -> bool:
        """
        Evaluate a lock expression.

        Args:
            lock_key: Lock expression to evaluate
            player: Player attempting access
            target: Optional target object (for context)

        Returns:
            True if player passes lock, False otherwise
        """
        if not lock_key or lock_key.strip() == "":
            return True  # Empty lock = always pass

        try:
            return await self._eval_expression(lock_key, player, target)
        except Exception as e:
            print(f"Lock evaluation error: {e}")
            return False  # Fail secure

    async def _eval_expression(
        self,
        expr: str,
        player: DBObject,
        target: Optional[DBObject]
    ) -> bool:
        """Recursively evaluate lock expression"""
        expr = expr.strip()

        # Handle OR operator (lowest precedence)
        if "|" in expr:
            parts = self._split_by_operator(expr, "|")
            for part in parts:
                if await self._eval_expression(part, player, target):
                    return True
            return False

        # Handle AND operator
        if "&" in expr:
            parts = self._split_by_operator(expr, "&")
            for part in parts:
                if not await self._eval_expression(part, player, target):
                    return False
            return True

        # Handle NOT operator
        if expr.startswith("!"):
            return not await self._eval_expression(expr[1:], player, target)

        # Handle parentheses
        if expr.startswith("(") and expr.endswith(")"):
            return await self._eval_expression(expr[1:-1], player, target)

        # Evaluate atomic condition
        return await self._eval_atomic(expr, player, target)

    def _split_by_operator(self, expr: str, operator: str) -> list:
        """Split expression by operator, respecting parentheses"""
        parts = []
        current = ""
        depth = 0

        for char in expr:
            if char == "(":
                depth += 1
                current += char
            elif char == ")":
                depth -= 1
                current += char
            elif char == operator and depth == 0:
                parts.append(current.strip())
                current = ""
            else:
                current += char

        if current:
            parts.append(current.strip())

        return parts

    async def _eval_atomic(
        self,
        condition: str,
        player: DBObject,
        target: Optional[DBObject]
    ) -> bool:
        """Evaluate atomic condition"""
        condition = condition.strip()

        # Object ID: #123
        if condition.startswith("#"):
            try:
                obj_id = int(condition[1:])
                return player.id == obj_id
            except ValueError:
                return False

        # Type check: @player, @room, @thing, @exit
        if condition.startswith("@"):
            obj_type = condition[1:].upper()
            return player.type.value == obj_type

        # Attribute comparison: HP:>50, QUEST:=done, LEVEL:<10
        if ":" in condition:
            return await self._eval_attribute(condition, player)

        # Flag check: WIZARD, GOD, ROYAL
        return self.obj_mgr.has_flag(player, condition)

    async def _eval_attribute(self, condition: str, player: DBObject) -> bool:
        """Evaluate attribute condition"""
        # Parse: ATTR:OP:VALUE or ATTR:OPVALUE
        parts = condition.split(":")
        if len(parts) < 2:
            return False

        attr_name = parts[0].strip()
        comparison = ":".join(parts[1:]).strip()

        # Get attribute value
        attr = await self.obj_mgr.get_attribute(player.id, attr_name)
        if not attr:
            return False

        attr_value = attr.value

        # Determine operator and value
        if comparison.startswith(">="):
            op = ">="
            value = comparison[2:].strip()
        elif comparison.startswith("<="):
            op = "<="
            value = comparison[2:].strip()
        elif comparison.startswith(">"):
            op = ">"
            value = comparison[1:].strip()
        elif comparison.startswith("<"):
            op = "<"
            value = comparison[1:].strip()
        elif comparison.startswith("="):
            op = "="
            value = comparison[1:].strip()
        else:
            # No operator, just check existence
            return True

        # Perform comparison
        try:
            # Try numeric comparison first
            attr_num = float(attr_value)
            value_num = float(value)

            if op == "=":
                return attr_num == value_num
            elif op == ">":
                return attr_num > value_num
            elif op == "<":
                return attr_num < value_num
            elif op == ">=":
                return attr_num >= value_num
            elif op == "<=":
                return attr_num <= value_num
        except ValueError:
            # String comparison
            if op == "=":
                return attr_value == value
            else:
                return False  # Can't do inequality on strings

        return False


class LockManager:
    """Manages locks on objects"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.evaluator = LockEvaluator(session)

    async def set_lock(
        self,
        object_id: int,
        lock_type: str,
        lock_key: str
    ) -> Lock:
        """Set a lock on an object"""
        # Remove existing lock of this type
        query = select(Lock).where(
            Lock.object_id == object_id,
            Lock.lock_type == lock_type
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()

        if existing:
            existing.lock_key = lock_key
            lock = existing
        else:
            lock = Lock(
                object_id=object_id,
                lock_type=lock_type,
                lock_key=lock_key
            )
            self.session.add(lock)

        await self.session.commit()
        return lock

    async def get_lock(self, object_id: int, lock_type: str) -> Optional[Lock]:
        """Get a lock from an object"""
        query = select(Lock).where(
            Lock.object_id == object_id,
            Lock.lock_type == lock_type
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def check_lock(
        self,
        object_id: int,
        lock_type: str,
        player: DBObject,
        target: Optional[DBObject] = None
    ) -> bool:
        """
        Check if player passes a lock.

        Args:
            object_id: Object with the lock
            lock_type: Type of lock (use, enter, get, etc.)
            player: Player attempting action
            target: Optional target object

        Returns:
            True if player passes, False otherwise
        """
        lock = await self.get_lock(object_id, lock_type)
        if not lock:
            return True  # No lock = always pass

        return await self.evaluator.evaluate(lock.lock_key, player, target)

    async def remove_lock(self, object_id: int, lock_type: str) -> bool:
        """Remove a lock from an object"""
        lock = await self.get_lock(object_id, lock_type)
        if lock:
            await self.session.delete(lock)
            await self.session.commit()
            return True
        return False

    async def list_locks(self, object_id: int) -> list:
        """List all locks on an object"""
        query = select(Lock).where(Lock.object_id == object_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())
