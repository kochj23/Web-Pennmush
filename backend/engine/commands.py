"""
Web-Pennmush Command Parser
Author: Jordan Koch (GitHub: kochj23)

Processes user commands and routes them to appropriate handlers.
"""
from typing import Dict, Callable, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models import DBObject, ObjectType
from backend.engine.objects import ObjectManager
from backend.engine.channels import ChannelManager, HelpManager
from backend.engine.locks import LockManager
from backend.engine.mail import MailManager
from backend.engine.pages import PageManager
from backend.engine.moderation import ModerationManager
from backend.engine.quests import QuestManager
from backend.engine.economy import EconomyManager
from backend.security import input_validator
from datetime import datetime
import re
import json


class CommandParser:
    """
    Parses and executes MUSH commands.
    Commands follow the format: command [arguments]
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.obj_mgr = ObjectManager(session)
        self.channel_mgr = ChannelManager(session)
        self.help_mgr = HelpManager(session)
        self.lock_mgr = LockManager(session)
        self.mail_mgr = MailManager(session)
        self.page_mgr = PageManager(session)
        self.mod_mgr = ModerationManager(session)
        self.quest_mgr = QuestManager(session)
        self.economy_mgr = EconomyManager(session)
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

        # Channel commands
        self.register_command("channel/list", self.cmd_channel_list, ["channels"])
        self.register_command("channel/join", self.cmd_channel_join)
        self.register_command("channel/leave", self.cmd_channel_leave)
        self.register_command("channel/who", self.cmd_channel_who)
        self.register_command("channel/create", self.cmd_channel_create)

        # NPC commands
        self.register_command("@npc/create", self.cmd_npc_create)
        self.register_command("@npc/personality", self.cmd_npc_personality)
        self.register_command("@npc/knowledge", self.cmd_npc_knowledge)
        self.register_command("talk", self.cmd_talk)
        self.register_command("ask", self.cmd_ask)

        # AI commands
        self.register_command("guide", self.cmd_guide, ["ai"])
        self.register_command("@ai/status", self.cmd_ai_status)

        # Lock commands
        self.register_command("@lock", self.cmd_lock)
        self.register_command("@unlock", self.cmd_unlock)
        self.register_command("@lock/list", self.cmd_lock_list)

        # Mail commands
        self.register_command("@mail", self.cmd_mail)
        self.register_command("@mail/list", self.cmd_mail_list, ["@mailist"])
        self.register_command("@mail/read", self.cmd_mail_read)
        self.register_command("@mail/delete", self.cmd_mail_delete)

        # Page commands
        self.register_command("page", self.cmd_page)
        self.register_command("page/list", self.cmd_page_list)

        # Moderation commands
        self.register_command("@ban", self.cmd_ban)
        self.register_command("@unban", self.cmd_unban)
        self.register_command("@kick", self.cmd_kick)
        self.register_command("@muzzle", self.cmd_muzzle)
        self.register_command("@unmuzzle", self.cmd_unmuzzle)
        self.register_command("@ban/list", self.cmd_ban_list)

        # Quest commands
        self.register_command("quest/list", self.cmd_quest_list, ["quests"])
        self.register_command("quest/start", self.cmd_quest_start)
        self.register_command("quest/progress", self.cmd_quest_progress, ["quest/status"])
        self.register_command("quest/log", self.cmd_quest_log)
        self.register_command("@quest/create", self.cmd_quest_create)
        self.register_command("@quest/addstep", self.cmd_quest_addstep)

        # Economy commands
        self.register_command("balance", self.cmd_balance, ["credits", "money"])
        self.register_command("give", self.cmd_give)
        self.register_command("transactions", self.cmd_transactions, ["trans"])
        self.register_command("@economy/grant", self.cmd_economy_grant)
        self.register_command("@economy/stats", self.cmd_economy_stats)

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
            # Try to interpret as channel alias (e.g., "pub Hello!")
            channel_result = await self._try_channel_message(player, command, args)
            if channel_result:
                return channel_result

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
        return await self.help_mgr.format_help(args if args else None)

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

        # Validate name
        is_valid, error = input_validator.validate_name(args)
        if not is_valid:
            return f"Cannot create object: {error}"

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

        # Validate name
        is_valid, error = input_validator.validate_name(args)
        if not is_valid:
            return f"Cannot create room: {error}"

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

        # Validate description
        is_valid, error = input_validator.validate_description(description)
        if not is_valid:
            return f"Cannot set description: {error}"

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

    # ==================== CHANNEL COMMANDS ====================

    async def _try_channel_message(self, player: DBObject, alias: str, message: str) -> Optional[str]:
        """Try to send a message to a channel by alias"""
        if not message:
            return None

        channel = await self.channel_mgr.get_channel_by_name(alias)
        if not channel:
            return None

        # Check if player is a member
        if not await self.channel_mgr.is_member(channel.id, player.id):
            return None

        # Broadcast message (will be handled by WebSocket manager)
        return f"[{channel.name}] {player.name}: {message}"

    async def cmd_channel_list(self, player: DBObject, args: str) -> str:
        """List all channels"""
        return await self.channel_mgr.format_channel_list(player.id)

    async def cmd_channel_join(self, player: DBObject, args: str) -> str:
        """Join a channel"""
        if not args:
            return "Usage: channel/join <channel name>"

        channel = await self.channel_mgr.get_channel_by_name(args)
        if not channel:
            return f"Channel '{args}' not found. Use 'channel/list' to see available channels."

        if await self.channel_mgr.join_channel(channel.id, player.id):
            return f"You have joined the {channel.name} channel. Use '{channel.alias}' to chat."
        else:
            return f"You are already a member of the {channel.name} channel."

    async def cmd_channel_leave(self, player: DBObject, args: str) -> str:
        """Leave a channel"""
        if not args:
            return "Usage: channel/leave <channel name>"

        channel = await self.channel_mgr.get_channel_by_name(args)
        if not channel:
            return f"Channel '{args}' not found."

        if await self.channel_mgr.leave_channel(channel.id, player.id):
            return f"You have left the {channel.name} channel."
        else:
            return f"You are not a member of the {channel.name} channel."

    async def cmd_channel_who(self, player: DBObject, args: str) -> str:
        """Show who's on a channel"""
        if not args:
            return "Usage: channel/who <channel name>"

        channel = await self.channel_mgr.get_channel_by_name(args)
        if not channel:
            return f"Channel '{args}' not found."

        members = await self.channel_mgr.get_members(channel.id)
        if not members:
            return f"No one is on the {channel.name} channel."

        output = [f"=== {channel.name} Channel Members ==="]
        for member in members:
            status = "Online" if member.is_connected else "Offline"
            output.append(f"  {member.name}(#{member.id}) - {status}")
        output.append(f"\nTotal: {len(members)} member(s)")
        return "\n".join(output)

    async def cmd_channel_create(self, player: DBObject, args: str) -> str:
        """Create a new channel"""
        if not args:
            return "Usage: channel/create <name>[=<alias>]"

        # Parse name=alias
        if "=" in args:
            name, alias = args.split("=", 1)
            name = name.strip()
            alias = alias.strip()
        else:
            name = args.strip()
            alias = name[:3].lower()  # Auto-generate alias

        # Check if channel already exists
        existing = await self.channel_mgr.get_channel_by_name(name)
        if existing:
            return f"A channel named '{name}' already exists."

        channel = await self.channel_mgr.create_channel(
            name=name,
            owner_id=player.id,
            alias=alias,
            description=f"Created by {player.name}"
        )

        return f"Channel '{channel.name}' created with alias '{channel.alias}'. Use '{channel.alias} <message>' to chat."

    # ==================== NPC COMMANDS ====================

    async def cmd_npc_create(self, player: DBObject, args: str) -> str:
        """Create an AI-powered NPC"""
        if not args:
            return "Usage: @npc/create <name>"

        from backend.models import NPC

        # Create the object
        npc_obj = await self.obj_mgr.create_object(
            name=args,
            obj_type=ObjectType.THING,
            owner_id=player.id,
            location_id=player.location_id,
            description=f"An AI-powered NPC named {args}.",
            flags="VISIBLE,NPC"
        )

        # Create NPC data
        npc = NPC(
            object_id=npc_obj.id,
            personality="A helpful and friendly character.",
            knowledge_base="General knowledge about the MUSH.",
            ai_model="gpt-4",
            temperature=7,
            is_active=True
        )
        self.session.add(npc)
        await self.session.commit()

        return f"Created NPC: {npc_obj.name}(#{npc_obj.id})\nUse '@npc/personality' and '@npc/knowledge' to configure."

    async def cmd_npc_personality(self, player: DBObject, args: str) -> str:
        """Set NPC personality"""
        if "=" not in args:
            return "Usage: @npc/personality <npc>=<personality description>"

        npc_name, personality = args.split("=", 1)
        npc_name = npc_name.strip()
        personality = personality.strip()

        # Find NPC
        npc_obj = await self.obj_mgr.get_object_by_name(npc_name, player.location_id)
        if not npc_obj:
            return f"NPC '{npc_name}' not found here."

        # Get NPC data
        from backend.models import NPC
        from sqlalchemy import select

        query = select(NPC).where(NPC.object_id == npc_obj.id)
        result = await self.session.execute(query)
        npc = result.scalar_one_or_none()

        if not npc:
            return f"{npc_obj.name} is not an NPC."

        npc.personality = personality
        await self.session.commit()

        return f"Personality set for {npc_obj.name}: {personality}"

    async def cmd_npc_knowledge(self, player: DBObject, args: str) -> str:
        """Set NPC knowledge base"""
        if "=" not in args:
            return "Usage: @npc/knowledge <npc>=<knowledge>"

        npc_name, knowledge = args.split("=", 1)
        npc_name = npc_name.strip()
        knowledge = knowledge.strip()

        # Find NPC
        npc_obj = await self.obj_mgr.get_object_by_name(npc_name, player.location_id)
        if not npc_obj:
            return f"NPC '{npc_name}' not found here."

        # Get NPC data
        from backend.models import NPC
        from sqlalchemy import select

        query = select(NPC).where(NPC.object_id == npc_obj.id)
        result = await self.session.execute(query)
        npc = result.scalar_one_or_none()

        if not npc:
            return f"{npc_obj.name} is not an NPC."

        npc.knowledge_base = knowledge
        await self.session.commit()

        return f"Knowledge base set for {npc_obj.name}."

    async def cmd_talk(self, player: DBObject, args: str) -> str:
        """Talk to an NPC"""
        if " to " not in args.lower() or "=" not in args:
            return "Usage: talk to <npc>=<message>"

        # Parse: talk to <npc>=<message>
        parts = args.lower().split(" to ", 1)
        if len(parts) < 2:
            return "Usage: talk to <npc>=<message>"

        rest = parts[1]
        if "=" not in rest:
            return "Usage: talk to <npc>=<message>"

        npc_name, message = rest.split("=", 1)
        npc_name = npc_name.strip()
        message = message.strip()

        # Find NPC
        npc_obj = await self.obj_mgr.get_object_by_name(npc_name, player.location_id)
        if not npc_obj:
            return f"NPC '{npc_name}' not found here."

        # Get NPC data
        from backend.models import NPC
        from sqlalchemy import select

        query = select(NPC).where(NPC.object_id == npc_obj.id)
        result = await self.session.execute(query)
        npc = result.scalar_one_or_none()

        if not npc or not npc.is_active:
            return f"{npc_obj.name} is not an NPC or is not active."

        # Generate AI response using local AI (Ollama or MLX)
        from backend.engine.ai_manager import ai_manager

        # Parse conversation history
        conversation_history = []
        if npc.conversation_history:
            try:
                conversation_history = json.loads(npc.conversation_history)
            except:
                conversation_history = []

        # Generate response
        ai_response = await ai_manager.generate_response(
            prompt=message,
            personality=npc.personality,
            knowledge_base=npc.knowledge_base or "",
            model=npc.ai_model,
            temperature=npc.temperature / 10.0,  # Convert from 0-10 to 0.0-1.0
            max_tokens=npc.max_tokens,
            conversation_history=conversation_history
        )

        # Update conversation history (keep last 10 exchanges)
        conversation_history.append({"role": "user", "content": message})
        conversation_history.append({"role": "assistant", "content": ai_response})
        if len(conversation_history) > 20:  # 10 exchanges = 20 messages
            conversation_history = conversation_history[-20:]

        npc.conversation_history = json.dumps(conversation_history)
        await self.session.commit()

        # Format response
        response = f'{npc_obj.name} says, "{ai_response}"'

        return response

    async def cmd_ask(self, player: DBObject, args: str) -> str:
        """Ask an NPC a question (alias for talk)"""
        if "=" not in args:
            # Convert "ask npc about topic" to "talk to npc=about topic"
            parts = args.split(None, 1)
            if len(parts) < 2:
                return "Usage: ask <npc>=<question>"
            npc_name = parts[0]
            question = parts[1] if len(parts) > 1 else ""
            return await self.cmd_talk(player, f"to {npc_name}={question}")
        else:
            # "ask npc=question" format
            npc_name, question = args.split("=", 1)
            return await self.cmd_talk(player, f"to {npc_name.strip()}={question.strip()}")

    # ==================== AI GUIDE COMMANDS ====================

    async def cmd_guide(self, player: DBObject, args: str) -> str:
        """
        AI-powered game guide.
        Ask questions and get helpful answers from the AI.
        """
        if not args:
            return """=== AI Game Guide ===

The AI guide can help you learn the game and answer questions.

Usage: guide <your question>

Examples:
  guide How do I create a room?
  guide What commands are available?
  guide How do I talk to other players?
  guide What is softcode?

Aliases: ai

The guide uses local AI (Ollama or MLX) if available.
            """

        from backend.engine.ai_manager import ai_manager

        if not ai_manager.is_available():
            return """AI Guide is not available. Please install a local AI backend:

Option 1 - Ollama (All platforms):
  1. Install from https://ollama.ai
  2. Run: ollama pull llama2
  3. Restart Web-Pennmush

Option 2 - MLX (Apple Silicon only):
  1. pip install mlx-lm
  2. Restart Web-Pennmush

Then try 'guide' again!"""

        # Build game context
        room = await self.obj_mgr.get_object(player.location_id)
        inventory = await self.obj_mgr.get_contents(player.id)

        game_context = {
            "location": room.name if room else "unknown",
            "inventory": [obj.name for obj in inventory] if inventory else []
        }

        # Get AI response
        response = await ai_manager.get_game_guidance(args, game_context)

        return f"=== AI Guide ===\n\n{response}\n\nNeed more help? Try 'help' for command documentation."

    async def cmd_ai_status(self, player: DBObject, args: str) -> str:
        """Show AI backend status"""
        from backend.engine.ai_manager import ai_manager

        status = ai_manager.get_status()

        output = ["=== AI Backend Status ==="]
        output.append(f"Active Backend: {status['backend']}")
        output.append(f"Ollama Available: {'✓ Yes' if status['ollama_available'] else '✗ No'}")
        output.append(f"MLX Available: {'✓ Yes' if status['mlx_available'] else '✗ No (Apple Silicon only)'}")
        output.append(f"Configured: {'✓ Yes' if status['is_configured'] else '✗ No'}")

        if status['is_configured']:
            # List available models
            models = await ai_manager.list_available_models()
            if models:
                output.append(f"\nAvailable Models:")
                for model in models[:5]:  # Show first 5
                    output.append(f"  - {model}")
                if len(models) > 5:
                    output.append(f"  ... and {len(models) - 5} more")
        else:
            output.append("\nTo enable AI:")
            output.append("  Option 1: Install Ollama from https://ollama.ai")
            output.append("  Option 2: pip install mlx-lm (Apple Silicon only)")

        return "\n".join(output)

    # ==================== LOCK COMMANDS ====================

    async def cmd_lock(self, player: DBObject, args: str) -> str:
        """Set a lock on an object"""
        if "=" not in args or "/" not in args:
            return "Usage: @lock/<type> <object>=<lock key>\nExample: @lock/use sword=#123|WIZARD"

        # Parse: @lock/<type> becomes just the args
        # But since we registered "@lock", we need to handle the type in args
        # Expected: @lock object/type=key
        if "/" not in args.split("=")[0]:
            return "Usage: @lock/<type> <object>=<lock key>\nExample: @lock/use sword=#123"

        obj_spec, lock_key = args.split("=", 1)
        obj_name, lock_type = obj_spec.rsplit("/", 1)
        obj_name = obj_name.strip()
        lock_type = lock_type.strip().lower()
        lock_key = lock_key.strip()

        # Find object
        if obj_name.lower() == "here":
            obj = await self.obj_mgr.get_object(player.location_id)
        elif obj_name.lower() == "me":
            obj = player
        else:
            obj = await self.obj_mgr.get_object_by_name(obj_name, player.location_id)

        if not obj:
            return f"I don't see '{obj_name}' here."

        # Set lock
        await self.lock_mgr.set_lock(obj.id, lock_type, lock_key)
        return f"Lock '{lock_type}' set on {obj.name}(#{obj.id}): {lock_key}"

    async def cmd_unlock(self, player: DBObject, args: str) -> str:
        """Remove a lock from an object"""
        if "/" not in args:
            return "Usage: @unlock/<type> <object>\nExample: @unlock/use sword"

        obj_name, lock_type = args.rsplit("/", 1)
        obj_name = obj_name.strip()
        lock_type = lock_type.strip().lower()

        # Find object
        obj = await self.obj_mgr.get_object_by_name(obj_name, player.location_id)
        if not obj:
            return f"I don't see '{obj_name}' here."

        # Remove lock
        if await self.lock_mgr.remove_lock(obj.id, lock_type):
            return f"Lock '{lock_type}' removed from {obj.name}(#{obj.id})"
        else:
            return f"No '{lock_type}' lock found on {obj.name}(#{obj.id})"

    async def cmd_lock_list(self, player: DBObject, args: str) -> str:
        """List all locks on an object"""
        if not args:
            args = "me"

        obj = await self.obj_mgr.get_object_by_name(args, player.location_id)
        if not obj:
            return f"I don't see '{args}' here."

        locks = await self.lock_mgr.list_locks(obj.id)
        if not locks:
            return f"{obj.name}(#{obj.id}) has no locks."

        output = [f"=== Locks on {obj.name}(#{obj.id}) ==="]
        for lock in locks:
            output.append(f"  {lock.lock_type}: {lock.lock_key}")

        return "\n".join(output)

    # ==================== MAIL COMMANDS ====================

    async def cmd_mail(self, player: DBObject, args: str) -> str:
        """Send mail to a player"""
        if "=" not in args or "/" not in args:
            return "Usage: @mail <player>=<subject>/<message>"

        recipient_name, content = args.split("=", 1)
        recipient_name = recipient_name.strip()

        if "/" not in content:
            return "Usage: @mail <player>=<subject>/<message>"

        subject, message = content.split("/", 1)
        subject = subject.strip()
        message = message.strip()

        # Validate message
        is_valid, error = input_validator.validate_message(message)
        if not is_valid:
            return f"Cannot send mail: {error}"

        # Find recipient
        recipient = await self.obj_mgr.get_object_by_name(recipient_name)
        if not recipient or recipient.type != ObjectType.PLAYER:
            return f"Player '{recipient_name}' not found."

        # Send mail
        mail = await self.mail_mgr.send_mail(player.id, recipient.id, subject, message)
        return f"Mail sent to {recipient.name}(#{recipient.id})"

    async def cmd_mail_list(self, player: DBObject, args: str) -> str:
        """List mail inbox"""
        inbox = await self.mail_mgr.get_inbox(player.id)
        return await self.mail_mgr.format_mail_list(inbox, show_full=True)

    async def cmd_mail_read(self, player: DBObject, args: str) -> str:
        """Read a mail message"""
        if not args:
            return "Usage: @mail/read <#>"

        try:
            mail_id = int(args.strip())
        except ValueError:
            return "Mail ID must be a number."

        mail = await self.mail_mgr.read_mail(mail_id, player.id)
        if not mail:
            return f"Mail #{mail_id} not found in your inbox."

        sender = await self.session.get(DBObject, mail.sender_id)
        sender_name = sender.name if sender else f"#{mail.sender_id}"

        output = [
            f"=== Mail #{mail.id} ===",
            f"From: {sender_name}(#{mail.sender_id})",
            f"Date: {mail.sent_at.strftime('%Y-%m-%d %H:%M')}",
            f"Subject: {mail.subject}",
            "",
            mail.message
        ]

        return "\n".join(output)

    async def cmd_mail_delete(self, player: DBObject, args: str) -> str:
        """Delete a mail message"""
        if not args:
            return "Usage: @mail/delete <#>"

        try:
            mail_id = int(args.strip())
        except ValueError:
            return "Mail ID must be a number."

        if await self.mail_mgr.delete_mail(mail_id, player.id):
            return f"Mail #{mail_id} deleted."
        else:
            return f"Mail #{mail_id} not found in your inbox."

    # ==================== PAGE COMMANDS ====================

    async def cmd_page(self, player: DBObject, args: str) -> str:
        """Send a page (direct message) to a player"""
        if "=" not in args:
            return "Usage: page <player>=<message>"

        recipient_name, message = args.split("=", 1)
        recipient_name = recipient_name.strip()
        message = message.strip()

        # Validate message
        is_valid, error = input_validator.validate_message(message)
        if not is_valid:
            return f"Cannot send page: {error}"

        # Find recipient
        recipient = await self.obj_mgr.get_object_by_name(recipient_name)
        if not recipient or recipient.type != ObjectType.PLAYER:
            return f"Player '{recipient_name}' not found."

        if not recipient.is_connected:
            return f"{recipient.name} is not connected. Consider using @mail instead."

        # Send page
        await self.page_mgr.send_page(player.id, recipient.id, message)

        # TODO: Broadcast page to recipient via WebSocket
        return f"You paged {recipient.name}: {message}"

    async def cmd_page_list(self, player: DBObject, args: str) -> str:
        """List recent pages"""
        return await self.page_mgr.format_page_history(player.id)

    # ==================== MODERATION COMMANDS ====================

    async def cmd_ban(self, player: DBObject, args: str) -> str:
        """Ban a player"""
        # Check if player is admin
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied. You must be a wizard or admin."

        if "=" not in args:
            return "Usage: @ban <player>=<reason>[/<days>]\nExample: @ban BadUser=Spamming/7"

        player_name, reason_duration = args.split("=", 1)
        player_name = player_name.strip()

        # Parse reason/duration
        if "/" in reason_duration:
            reason, duration_str = reason_duration.rsplit("/", 1)
            try:
                duration_days = int(duration_str.strip())
            except ValueError:
                return "Duration must be a number (days)."
        else:
            reason = reason_duration
            duration_days = None

        reason = reason.strip()

        # Find player to ban
        target = await self.obj_mgr.get_object_by_name(player_name)
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{player_name}' not found."

        # Cannot ban yourself
        if target.id == player.id:
            return "You cannot ban yourself."

        # Cannot ban gods (unless you're god)
        if self.obj_mgr.has_flag(target, "GOD") and not self.obj_mgr.has_flag(player, "GOD"):
            return f"You cannot ban {target.name}."

        # Issue ban
        ban = await self.mod_mgr.ban_player(target.id, player.id, reason, duration_days)

        duration_text = f" for {duration_days} days" if duration_days else " permanently"
        return f"{target.name}(#{target.id}) has been banned{duration_text}. Reason: {reason}"

    async def cmd_unban(self, player: DBObject, args: str) -> str:
        """Unban a player"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if not args:
            return "Usage: @unban <player>"

        target = await self.obj_mgr.get_object_by_name(args.strip())
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{args}' not found."

        if await self.mod_mgr.unban_player(target.id):
            return f"{target.name}(#{target.id}) has been unbanned."
        else:
            return f"{target.name} is not banned."

    async def cmd_kick(self, player: DBObject, args: str) -> str:
        """Kick a player (disconnect)"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if not args:
            return "Usage: @kick <player>[=<reason>]"

        if "=" in args:
            player_name, reason = args.split("=", 1)
        else:
            player_name = args
            reason = "No reason specified"

        target = await self.obj_mgr.get_object_by_name(player_name.strip())
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{player_name}' not found."

        if not target.is_connected:
            return f"{target.name} is not connected."

        # TODO: Actually disconnect the player via WebSocket manager
        return f"{target.name}(#{target.id}) kicked. Reason: {reason}"

    async def cmd_muzzle(self, player: DBObject, args: str) -> str:
        """Muzzle a player (prevent communication)"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if not args:
            return "Usage: @muzzle <player>"

        target = await self.obj_mgr.get_object_by_name(args.strip())
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{args}' not found."

        self.obj_mgr.add_flag(target, "MUZZLED")
        await self.session.commit()

        return f"{target.name}(#{target.id}) has been muzzled. They cannot use chat or channels."

    async def cmd_unmuzzle(self, player: DBObject, args: str) -> str:
        """Unmuzzle a player"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if not args:
            return "Usage: @unmuzzle <player>"

        target = await self.obj_mgr.get_object_by_name(args.strip())
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{args}' not found."

        self.obj_mgr.remove_flag(target, "MUZZLED")
        await self.session.commit()

        return f"{target.name}(#{target.id}) has been unmuzzled."

    async def cmd_ban_list(self, player: DBObject, args: str) -> str:
        """List active bans"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        return await self.mod_mgr.format_ban_list()

    # ==================== QUEST COMMANDS ====================

    async def cmd_quest_list(self, player: DBObject, args: str) -> str:
        """List available quests"""
        return await self.quest_mgr.format_quest_list()

    async def cmd_quest_start(self, player: DBObject, args: str) -> str:
        """Start a quest"""
        if not args:
            return "Usage: quest/start <quest name or ID>"

        # Try to find quest by name or ID
        quest = await self.quest_mgr.get_quest_by_name(args)
        if not quest:
            try:
                quest_id = int(args.strip())
                quest = await self.quest_mgr.get_quest(quest_id)
            except ValueError:
                pass

        if not quest:
            return f"Quest '{args}' not found. Use 'quest/list' to see available quests."

        # Start quest
        progress = await self.quest_mgr.start_quest(quest.id, player.id)
        return f"Quest started: {quest.name}\nUse 'quest/progress' to track your progress."

    async def cmd_quest_progress(self, player: DBObject, args: str) -> str:
        """Show quest progress"""
        return await self.quest_mgr.format_player_quests(player.id)

    async def cmd_quest_log(self, player: DBObject, args: str) -> str:
        """Show quest log (alias for quest/progress)"""
        return await self.quest_mgr.format_player_quests(player.id)

    async def cmd_quest_create(self, player: DBObject, args: str) -> str:
        """Create a new quest"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied. Only wizards can create quests."

        if "=" not in args:
            return "Usage: @quest/create <name>=<description>[/<reward>]"

        name, rest = args.split("=", 1)
        name = name.strip()

        # Parse description/reward
        if "/" in rest:
            description, reward_str = rest.rsplit("/", 1)
            try:
                reward_credits = int(reward_str.strip())
            except ValueError:
                reward_credits = 0
        else:
            description = rest
            reward_credits = 0

        description = description.strip()

        # Create quest
        quest = await self.quest_mgr.create_quest(name, description, player.id, reward_credits)
        return f"Quest created: {quest.name} (ID: {quest.id})\nUse '@quest/addstep' to add steps."

    async def cmd_quest_addstep(self, player: DBObject, args: str) -> str:
        """Add a step to a quest"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if "=" not in args:
            return "Usage: @quest/addstep <quest>=<step number>/<description>"

        quest_name, step_spec = args.split("=", 1)
        quest_name = quest_name.strip()

        if "/" not in step_spec:
            return "Usage: @quest/addstep <quest>=<step number>/<description>"

        step_num_str, description = step_spec.split("/", 1)
        try:
            step_number = int(step_num_str.strip())
        except ValueError:
            return "Step number must be a number."

        description = description.strip()

        # Find quest
        quest = await self.quest_mgr.get_quest_by_name(quest_name)
        if not quest:
            return f"Quest '{quest_name}' not found."

        # Add step
        step = await self.quest_mgr.add_quest_step(quest.id, step_number, description)
        return f"Step {step_number} added to quest '{quest.name}'"

    # ==================== ECONOMY COMMANDS ====================

    async def cmd_balance(self, player: DBObject, args: str) -> str:
        """Show credit balance"""
        balance = await self.economy_mgr.get_balance(player.id)
        return f"Your balance: {balance} credits"

    async def cmd_give(self, player: DBObject, args: str) -> str:
        """Give credits to another player"""
        if "=" not in args:
            return "Usage: give <player>=<amount>\nExample: give Alice=100"

        recipient_name, amount_str = args.split("=", 1)
        recipient_name = recipient_name.strip()

        try:
            amount = int(amount_str.strip())
        except ValueError:
            return "Amount must be a number."

        if amount <= 0:
            return "Amount must be positive."

        # Find recipient
        recipient = await self.obj_mgr.get_object_by_name(recipient_name)
        if not recipient or recipient.type != ObjectType.PLAYER:
            return f"Player '{recipient_name}' not found."

        if recipient.id == player.id:
            return "You cannot give credits to yourself."

        # Transfer
        success, message = await self.economy_mgr.transfer_credits(
            player.id,
            recipient.id,
            amount,
            f"Gift to {recipient.name}"
        )

        if success:
            return f"You gave {amount} credits to {recipient.name}. {message}"
        else:
            return message

    async def cmd_transactions(self, player: DBObject, args: str) -> str:
        """Show transaction history"""
        return await self.economy_mgr.format_transaction_history(player.id)

    async def cmd_economy_grant(self, player: DBObject, args: str) -> str:
        """Grant credits to a player (admin only)"""
        if not self.obj_mgr.has_flag(player, "WIZARD") and not self.obj_mgr.has_flag(player, "GOD"):
            return "Permission denied."

        if "=" not in args:
            return "Usage: @economy/grant <player>=<amount>"

        player_name, amount_str = args.split("=", 1)
        player_name = player_name.strip()

        try:
            amount = int(amount_str.strip())
        except ValueError:
            return "Amount must be a number."

        # Find player
        target = await self.obj_mgr.get_object_by_name(player_name)
        if not target or target.type != ObjectType.PLAYER:
            return f"Player '{player_name}' not found."

        # Grant credits
        new_balance = await self.economy_mgr.add_credits(
            target.id,
            amount,
            "admin_grant",
            f"Granted by {player.name}"
        )

        return f"Granted {amount} credits to {target.name}. New balance: {new_balance} credits."

    async def cmd_economy_stats(self, player: DBObject, args: str) -> str:
        """Show economy statistics"""
        richest = await self.economy_mgr.get_richest_players(10)

        output = ["=== Economy Statistics ==="]
        output.append("\nRichest Players:")
        output.append(f"{'Rank':<6} {'Player':<20} {'Credits':<15}")
        output.append("-" * 45)

        for idx, (player_obj, balance) in enumerate(richest, 1):
            output.append(f"{idx:<6} {player_obj.name:<20} {balance:<15}")

        return "\n".join(output)
