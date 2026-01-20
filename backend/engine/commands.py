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
