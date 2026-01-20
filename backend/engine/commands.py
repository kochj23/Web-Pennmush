"""
Web-Pennmush Command Parser
Author: Jordan Koch (GitHub: kochj23)

Processes user commands and routes them to appropriate handlers.
"""
from typing import Dict, Callable, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import DBObject, ObjectType
from backend.engine.objects import ObjectManager
from datetime import datetime
import re


class CommandParser:
    """
    Parses and executes MUSH commands.
    Commands follow the format: command [arguments]
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.obj_mgr = ObjectManager(session)
        self.commands: Dict[str, Callable] = {}
        self._register_commands()

    def _register_commands(self):
        """Register all available commands"""
        # Basic commands
        self.register_command("look", self.cmd_look, ["l"])
        self.register_command("examine", self.cmd_examine, ["ex", "exam"])
        self.register_command("say", self.cmd_say, ['"'])
        self.register_command("pose", self.cmd_pose, [":", "emote"])
        self.register_command("go", self.cmd_go)
        self.register_command("help", self.cmd_help, ["?"])

        # Object manipulation
        self.register_command("get", self.cmd_get, ["take"])
        self.register_command("drop", self.cmd_drop)
        self.register_command("inventory", self.cmd_inventory, ["i", "inv"])

        # Building commands
        self.register_command("@create", self.cmd_create)
        self.register_command("@dig", self.cmd_dig)
        self.register_command("@open", self.cmd_open)
        self.register_command("@link", self.cmd_link)
        self.register_command("@describe", self.cmd_describe, ["@desc"])
        self.register_command("@set", self.cmd_set)
        self.register_command("@destroy", self.cmd_destroy, ["@nuke"])

        # Information commands
        self.register_command("who", self.cmd_who)
        self.register_command("@stats", self.cmd_stats)

    def register_command(self, name: str, handler: Callable, aliases: list = None):
        """Register a command with optional aliases"""
        self.commands[name.lower()] = handler
        if aliases:
            for alias in aliases:
                self.commands[alias.lower()] = handler

    async def parse(self, player: DBObject, input_text: str) -> str:
        """
        Parse and execute a command.
        Returns the output text to send back to the player.
        """
        if not input_text or not input_text.strip():
            return ""

        input_text = input_text.strip()

        # Handle special say shortcut (")
        if input_text.startswith('"'):
            return await self.cmd_say(player, input_text[1:])

        # Handle special pose shortcut (:)
        if input_text.startswith(':'):
            return await self.cmd_pose(player, input_text[1:])

        # Split command and arguments
        parts = input_text.split(None, 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        # Find and execute command
        handler = self.commands.get(command)
        if handler:
            try:
                return await handler(player, args)
            except Exception as e:
                return f"Error executing command: {str(e)}"
        else:
            # Try to interpret as exit name
            exit_result = await self._try_exit(player, command)
            if exit_result:
                return exit_result
            return f"Huh? (Type 'help' for commands)"

    async def _try_exit(self, player: DBObject, exit_name: str) -> Optional[str]:
        """Try to use an exit with the given name"""
        if not player.location_id:
            return None

        exits = await self.obj_mgr.get_exits(player.location_id)
        for exit_obj in exits:
            # Check exit name and aliases
            exit_names = [exit_obj.name.lower()]
            if exit_obj.alias:
                exit_names.extend([a.strip().lower() for a in exit_obj.alias.split(";")])

            if exit_name.lower() in exit_names:
                # Use the exit
                return await self._use_exit(player, exit_obj)

        return None

    async def _use_exit(self, player: DBObject, exit_obj: DBObject) -> str:
        """Move player through an exit"""
        if not exit_obj.home_id:
            return "That exit doesn't lead anywhere."

        old_room = await self.obj_mgr.get_object(player.location_id)
        new_room = await self.obj_mgr.get_object(exit_obj.home_id)

        if not new_room:
            return "That exit doesn't lead anywhere."

        # Move player
        await self.obj_mgr.move_object(player.id, new_room.id)

        # Announce departure to old room
        if old_room:
            await self._announce_to_room(
                old_room.id,
                f"{player.name} has left through {exit_obj.name}.",
                exclude_player_id=player.id
            )

        # Announce arrival to new room
        await self._announce_to_room(
            new_room.id,
            f"{player.name} has arrived.",
            exclude_player_id=player.id
        )

        # Show new room to player
        return await self.cmd_look(player, "")

    async def _announce_to_room(self, room_id: int, message: str, exclude_player_id: Optional[int] = None):
        """Send a message to all players in a room"""
        players = await self.obj_mgr.get_players_in_room(room_id)
        # Note: In a full implementation, this would send messages via WebSocket
        # For now, this is a placeholder
        pass

    # ==================== COMMAND IMPLEMENTATIONS ====================

    async def cmd_look(self, player: DBObject, args: str) -> str:
        """Look at current room or specified object"""
        if not args:
            # Look at current room
            room = await self.obj_mgr.get_object(player.location_id)
            if not room:
                return "You are nowhere."

            output = [f"{room.name}(#{room.id})"]
            output.append(room.description or "You see nothing special.")

            # List exits
            exits = await self.obj_mgr.get_exits(room.id)
            if exits:
                exit_names = [e.name for e in exits]
                output.append(f"\nObvious exits: {', '.join(exit_names)}")

            # List contents (things and players)
            contents = await self.obj_mgr.get_contents(room.id)
            things = [obj for obj in contents if obj.type in (ObjectType.THING,)]
            players = [obj for obj in contents if obj.type == ObjectType.PLAYER and obj.id != player.id]

            if things:
                output.append("\nContents:")
                for thing in things:
                    output.append(f"  {thing.name}(#{thing.id})")

            if players:
                output.append("\nPlayers:")
                for p in players:
                    output.append(f"  {p.name}(#{p.id})")

            return "\n".join(output)
        else:
            # Look at specific object
            obj = await self.obj_mgr.get_object_by_name(args, player.location_id)
            if not obj:
                return f"I don't see '{args}' here."

            output = [f"{obj.name}(#{obj.id})"]
            output.append(obj.description or "You see nothing special.")
            return "\n".join(output)

    async def cmd_examine(self, player: DBObject, args: str) -> str:
        """Examine an object in detail"""
        if not args:
            return "Examine what?"

        obj = await self.obj_mgr.get_object_by_name(args, player.location_id)
        if not obj:
            # Try by ID
            try:
                obj_id = int(args.strip("#"))
                obj = await self.obj_mgr.get_object(obj_id)
            except ValueError:
                pass

        if not obj:
            return f"I don't see '{args}' here."

        info = await self.obj_mgr.get_object_info(obj.id)
        output = [
            f"Name: {info['name']}(#{info['id']})",
            f"Type: {info['type']}",
            f"Owner: #{info['owner_id']}",
            f"Location: #{info['location_id']}",
            f"Flags: {info['flags'] or 'none'}",
            f"Created: {info['created_at']}",
            f"Description:",
            info['description']
        ]

        if info['attributes']:
            output.append("\nAttributes:")
            for attr in info['attributes']:
                output.append(f"  {attr['name']}: {attr['value']}")

        return "\n".join(output)

    async def cmd_say(self, player: DBObject, args: str) -> str:
        """Say something to the room"""
        if not args:
            return "Say what?"

        message = f'{player.name} says, "{args}"'
        await self._announce_to_room(player.location_id, message)
        return f'You say, "{args}"'

    async def cmd_pose(self, player: DBObject, args: str) -> str:
        """Pose an action"""
        if not args:
            return "Pose what?"

        message = f"{player.name} {args}"
        await self._announce_to_room(player.location_id, message)
        return message

    async def cmd_go(self, player: DBObject, args: str) -> str:
        """Go through an exit"""
        if not args:
            return "Go where?"

        return await self._try_exit(player, args) or f"I don't see an exit named '{args}'."

    async def cmd_help(self, player: DBObject, args: str) -> str:
        """Display help information"""
        return """
=== Web-Pennmush Command Help ===

BASIC COMMANDS:
  look [object]       - Look at room or object (alias: l)
  examine <object>    - Examine object in detail (alias: ex)
  go <exit>           - Go through an exit
  say <message>       - Say something (alias: ")
  pose <action>       - Pose an action (alias: :)
  get <object>        - Pick up an object (alias: take)
  drop <object>       - Drop an object
  inventory           - See what you're carrying (alias: i)
  who                 - See who's online
  help                - This help (alias: ?)

BUILDING COMMANDS:
  @create <name>      - Create a new object
  @dig <name>         - Create a new room
  @open <name>        - Create an exit
  @describe <obj>=<desc> - Set object description (alias: @desc)
  @set <obj>=<flag>   - Set a flag on an object
  @destroy <object>   - Destroy an object (alias: @nuke)
  @stats              - Show database statistics

For more help, visit the Web-Pennmush documentation.
        """

    async def cmd_get(self, player: DBObject, args: str) -> str:
        """Pick up an object"""
        if not args:
            return "Get what?"

        obj = await self.obj_mgr.get_object_by_name(args, player.location_id)
        if not obj:
            return f"I don't see '{args}' here."

        if obj.type != ObjectType.THING:
            return "You can't pick that up."

        await self.obj_mgr.move_object(obj.id, player.id)
        await self._announce_to_room(player.location_id, f"{player.name} picks up {obj.name}.", player.id)
        return f"You pick up {obj.name}."

    async def cmd_drop(self, player: DBObject, args: str) -> str:
        """Drop an object"""
        if not args:
            return "Drop what?"

        # Find object in inventory
        obj = await self.obj_mgr.get_object_by_name(args, player.id)
        if not obj:
            return f"You aren't carrying '{args}'."

        await self.obj_mgr.move_object(obj.id, player.location_id)
        await self._announce_to_room(player.location_id, f"{player.name} drops {obj.name}.", player.id)
        return f"You drop {obj.name}."

    async def cmd_inventory(self, player: DBObject, args: str) -> str:
        """Show player inventory"""
        contents = await self.obj_mgr.get_contents(player.id)
        if not contents:
            return "You aren't carrying anything."

        output = ["You are carrying:"]
        for obj in contents:
            output.append(f"  {obj.name}(#{obj.id})")
        return "\n".join(output)

    async def cmd_create(self, player: DBObject, args: str) -> str:
        """Create a new object"""
        if not args:
            return "Create what?"

        obj = await self.obj_mgr.create_object(
            name=args,
            obj_type=ObjectType.THING,
            owner_id=player.id,
            location_id=player.id,
            description=f"A {args}."
        )
        return f"Created: {obj.name}(#{obj.id})"

    async def cmd_dig(self, player: DBObject, args: str) -> str:
        """Create a new room"""
        if not args:
            return "Dig what?"

        room = await self.obj_mgr.create_object(
            name=args,
            obj_type=ObjectType.ROOM,
            owner_id=player.id,
            description=f"A room named {args}."
        )
        return f"Dug: {room.name}(#{room.id})"

    async def cmd_open(self, player: DBObject, args: str) -> str:
        """Create an exit"""
        if not args:
            return "Open what?"

        # Parse: @open <name>=<destination>
        if "=" in args:
            name, dest = args.split("=", 1)
            name = name.strip()
            dest = dest.strip()

            # Get destination
            try:
                dest_id = int(dest.strip("#"))
                dest_obj = await self.obj_mgr.get_object(dest_id)
                if not dest_obj or dest_obj.type != ObjectType.ROOM:
                    return "Invalid destination room."
            except ValueError:
                return "Destination must be a room number (e.g., #123)."

            exit_obj = await self.obj_mgr.create_object(
                name=name,
                obj_type=ObjectType.EXIT,
                owner_id=player.id,
                location_id=player.location_id,
                home_id=dest_id,
                description=f"An exit to {dest_obj.name}."
            )
            return f"Opened: {exit_obj.name}(#{exit_obj.id}) to {dest_obj.name}(#{dest_id})"
        else:
            return "Usage: @open <name>=<destination room #>"

    async def cmd_link(self, player: DBObject, args: str) -> str:
        """Link an exit to a destination"""
        return "Not yet implemented."

    async def cmd_describe(self, player: DBObject, args: str) -> str:
        """Set object description"""
        if "=" not in args:
            return "Usage: @describe <object>=<description>"

        obj_name, description = args.split("=", 1)
        obj_name = obj_name.strip()
        description = description.strip()

        if obj_name.lower() == "here":
            obj = await self.obj_mgr.get_object(player.location_id)
        elif obj_name.lower() == "me":
            obj = player
        else:
            obj = await self.obj_mgr.get_object_by_name(obj_name, player.location_id)

        if not obj:
            return f"I don't see '{obj_name}' here."

        obj.description = description
        obj.modified_at = datetime.utcnow()
        await self.session.commit()
        return f"Description set on {obj.name}(#{obj.id})"

    async def cmd_set(self, player: DBObject, args: str) -> str:
        """Set a flag or attribute on an object"""
        if "=" not in args:
            return "Usage: @set <object>=<flag or attribute:value>"

        obj_name, setting = args.split("=", 1)
        obj_name = obj_name.strip()
        setting = setting.strip()

        obj = await self.obj_mgr.get_object_by_name(obj_name, player.location_id)
        if not obj:
            return f"I don't see '{obj_name}' here."

        # Check if it's an attribute (contains :)
        if ":" in setting:
            attr_name, attr_value = setting.split(":", 1)
            await self.obj_mgr.set_attribute(obj.id, attr_name.strip(), attr_value.strip())
            return f"Attribute {attr_name} set on {obj.name}(#{obj.id})"
        else:
            # It's a flag
            self.obj_mgr.add_flag(obj, setting)
            await self.session.commit()
            return f"Flag {setting} set on {obj.name}(#{obj.id})"

    async def cmd_destroy(self, player: DBObject, args: str) -> str:
        """Destroy an object"""
        if not args:
            return "Destroy what?"

        obj = await self.obj_mgr.get_object_by_name(args, player.location_id)
        if not obj:
            return f"I don't see '{args}' here."

        if obj.type == ObjectType.PLAYER:
            return "You can't destroy players."

        await self.obj_mgr.delete_object(obj.id)
        return f"Destroyed: {obj.name}(#{obj.id})"

    async def cmd_who(self, player: DBObject, args: str) -> str:
        """Show connected players"""
        from sqlalchemy import select
        query = select(DBObject).where(
            DBObject.type == ObjectType.PLAYER,
            DBObject.is_connected == True
        )
        result = await self.session.execute(query)
        players = result.scalars().all()

        if not players:
            return "No players online."

        output = ["=== Connected Players ==="]
        for p in players:
            idle_time = "Active"  # TODO: Calculate idle time
            output.append(f"  {p.name}(#{p.id}) - {idle_time}")
        output.append(f"\nTotal: {len(players)} player(s)")
        return "\n".join(output)

    async def cmd_stats(self, player: DBObject, args: str) -> str:
        """Show database statistics"""
        from sqlalchemy import select, func

        stats = {}
        for obj_type in ObjectType:
            if obj_type == ObjectType.GARBAGE:
                continue
            query = select(func.count()).where(DBObject.type == obj_type)
            result = await self.session.execute(query)
            stats[obj_type.value] = result.scalar()

        output = ["=== Database Statistics ==="]
        for obj_type, count in stats.items():
            output.append(f"  {obj_type}s: {count}")
        return "\n".join(output)
