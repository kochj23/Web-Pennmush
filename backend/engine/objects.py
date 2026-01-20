"""
Web-Pennmush Object System
Author: Jordan Koch (GitHub: kochj23)

Core object manipulation following PennMUSH conventions.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import DBObject, ObjectType, Attribute, Lock
from typing import Optional, List, Dict
from datetime import datetime


class ObjectManager:
    """Handles object creation, retrieval, and manipulation"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_object(self, obj_id: int) -> Optional[DBObject]:
        """Retrieve an object by ID"""
        return await self.session.get(DBObject, obj_id)

    async def get_object_by_name(self, name: str, location_id: Optional[int] = None) -> Optional[DBObject]:
        """
        Find an object by name, optionally scoped to a location.
        Matches on name or alias.
        """
        query = select(DBObject).where(
            (DBObject.name.ilike(f"%{name}%")) |
            (DBObject.alias.ilike(f"%{name}%"))
        )

        if location_id is not None:
            query = query.where(DBObject.location_id == location_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def create_object(
        self,
        name: str,
        obj_type: ObjectType,
        owner_id: int,
        location_id: Optional[int] = None,
        description: str = "",
        **kwargs
    ) -> DBObject:
        """Create a new object"""
        obj = DBObject(
            name=name,
            type=obj_type,
            owner_id=owner_id,
            location_id=location_id,
            description=description,
            created_at=datetime.utcnow(),
            **kwargs
        )
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def set_attribute(self, obj_id: int, attr_name: str, attr_value: str, flags: str = "") -> Attribute:
        """Set an attribute on an object"""
        # Check if attribute already exists
        query = select(Attribute).where(
            Attribute.object_id == obj_id,
            Attribute.name == attr_name.upper()
        )
        result = await self.session.execute(query)
        attr = result.scalar_one_or_none()

        if attr:
            # Update existing attribute
            attr.value = attr_value
            attr.modified_at = datetime.utcnow()
        else:
            # Create new attribute
            attr = Attribute(
                object_id=obj_id,
                name=attr_name.upper(),
                value=attr_value,
                flags=flags,
                created_at=datetime.utcnow()
            )
            self.session.add(attr)

        await self.session.commit()
        await self.session.refresh(attr)
        return attr

    async def get_attribute(self, obj_id: int, attr_name: str) -> Optional[Attribute]:
        """Get an attribute from an object"""
        query = select(Attribute).where(
            Attribute.object_id == obj_id,
            Attribute.name == attr_name.upper()
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all_attributes(self, obj_id: int) -> List[Attribute]:
        """Get all attributes for an object"""
        query = select(Attribute).where(Attribute.object_id == obj_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def move_object(self, obj_id: int, new_location_id: int) -> bool:
        """
        Move an object to a new location.
        Returns True if successful, False otherwise.
        """
        obj = await self.get_object(obj_id)
        if not obj:
            return False

        # Verify destination exists
        destination = await self.get_object(new_location_id)
        if not destination:
            return False

        # Update location
        obj.location_id = new_location_id
        obj.modified_at = datetime.utcnow()
        await self.session.commit()
        return True

    async def get_contents(self, location_id: int) -> List[DBObject]:
        """Get all objects at a location"""
        query = select(DBObject).where(
            DBObject.location_id == location_id,
            DBObject.type != ObjectType.GARBAGE
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_exits(self, room_id: int) -> List[DBObject]:
        """Get all exits in a room"""
        query = select(DBObject).where(
            DBObject.location_id == room_id,
            DBObject.type == ObjectType.EXIT
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_players_in_room(self, room_id: int) -> List[DBObject]:
        """Get all players in a room"""
        query = select(DBObject).where(
            DBObject.location_id == room_id,
            DBObject.type == ObjectType.PLAYER
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def delete_object(self, obj_id: int) -> bool:
        """
        Mark an object as GARBAGE (soft delete).
        Objects are never truly deleted in MUSH tradition.
        """
        obj = await self.get_object(obj_id)
        if not obj:
            return False

        obj.type = ObjectType.GARBAGE
        obj.modified_at = datetime.utcnow()
        await self.session.commit()
        return True

    def has_flag(self, obj: DBObject, flag: str) -> bool:
        """Check if an object has a specific flag"""
        if not obj.flags:
            return False
        flags_list = [f.strip().upper() for f in obj.flags.split(",")]
        return flag.upper() in flags_list

    def add_flag(self, obj: DBObject, flag: str):
        """Add a flag to an object"""
        if not obj.flags:
            obj.flags = flag.upper()
        else:
            flags_list = [f.strip().upper() for f in obj.flags.split(",")]
            if flag.upper() not in flags_list:
                flags_list.append(flag.upper())
                obj.flags = ",".join(flags_list)

    def remove_flag(self, obj: DBObject, flag: str):
        """Remove a flag from an object"""
        if not obj.flags:
            return
        flags_list = [f.strip().upper() for f in obj.flags.split(",")]
        if flag.upper() in flags_list:
            flags_list.remove(flag.upper())
            obj.flags = ",".join(flags_list)

    async def format_object_name(self, obj: DBObject) -> str:
        """Format an object name for display with ID"""
        return f"{obj.name}(#{obj.id})"

    async def get_object_info(self, obj_id: int) -> Dict:
        """Get detailed information about an object"""
        obj = await self.get_object(obj_id)
        if not obj:
            return {}

        attributes = await self.get_all_attributes(obj_id)

        return {
            "id": obj.id,
            "name": obj.name,
            "type": obj.type.value,
            "description": obj.description or "You see nothing special.",
            "owner_id": obj.owner_id,
            "location_id": obj.location_id,
            "flags": obj.flags,
            "created_at": obj.created_at.isoformat(),
            "modified_at": obj.modified_at.isoformat(),
            "attributes": [
                {"name": attr.name, "value": attr.value, "flags": attr.flags}
                for attr in attributes
            ]
        }
