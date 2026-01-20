"""
Web-Pennmush AI Manager
Author: Jordan Koch (GitHub: kochj23)

Manages local AI integration with Ollama and MLX for intelligent NPCs and game guidance.
"""
from typing import Optional, List, Dict, Any
from enum import Enum
import json
import asyncio
import platform


class AIBackend(str, Enum):
    """Available AI backends"""
    OLLAMA = "ollama"
    MLX = "mlx"
    NONE = "none"


class AIManager:
    """
    Manages AI interactions using local models (Ollama, MLX).
    Automatically detects available backends and uses the best one.
    """

    def __init__(self):
        self.backend = AIBackend.NONE
        self.ollama_available = False
        self.mlx_available = False
        self.ollama_base_url = "http://localhost:11434"
        self._detect_backends()

    def _detect_backends(self):
        """Detect which AI backends are available"""
        # Check for Ollama
        try:
            import ollama
            self.ollama_available = True
            self.backend = AIBackend.OLLAMA
            print("✓ Ollama detected and available")
        except ImportError:
            print("✗ Ollama not installed (pip install ollama)")

        # Check for MLX (only on Apple Silicon)
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            try:
                import mlx.core as mx
                from mlx_lm import load, generate
                self.mlx_available = True
                if self.backend == AIBackend.NONE:
                    self.backend = AIBackend.MLX
                print("✓ MLX detected and available (Apple Silicon)")
            except ImportError:
                print("✗ MLX not installed (pip install mlx-lm)")
        else:
            print("ℹ MLX only available on Apple Silicon")

        if self.backend == AIBackend.NONE:
            print("⚠ No AI backend available. NPCs will use placeholder responses.")
            print("  Install Ollama: https://ollama.ai")
            print("  Or install MLX (Apple Silicon): pip install mlx-lm")

    async def generate_response(
        self,
        prompt: str,
        personality: str = "helpful assistant",
        knowledge_base: str = "",
        model: str = "llama2",
        temperature: float = 0.7,
        max_tokens: int = 150,
        conversation_history: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Generate an AI response using available backend.

        Args:
            prompt: The user's input/question
            personality: NPC personality description
            knowledge_base: Context/knowledge the NPC has
            model: Model name (for Ollama: llama2, mistral, etc.)
            temperature: Response randomness (0-1)
            max_tokens: Maximum response length
            conversation_history: Previous messages in conversation

        Returns:
            Generated response text
        """
        if self.backend == AIBackend.OLLAMA:
            return await self._generate_ollama(
                prompt, personality, knowledge_base, model,
                temperature, max_tokens, conversation_history
            )
        elif self.backend == AIBackend.MLX:
            return await self._generate_mlx(
                prompt, personality, knowledge_base, model,
                temperature, max_tokens, conversation_history
            )
        else:
            return self._generate_placeholder(prompt, personality)

    async def _generate_ollama(
        self,
        prompt: str,
        personality: str,
        knowledge_base: str,
        model: str,
        temperature: float,
        max_tokens: int,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Generate response using Ollama"""
        try:
            import ollama

            # Build system message
            system_message = f"You are {personality}."
            if knowledge_base:
                system_message += f"\n\nYour knowledge: {knowledge_base}"
            system_message += "\n\nYou are a character in a text-based multiplayer game (MUSH). Keep responses brief (1-3 sentences) and in-character. Be engaging and helpful to players."

            # Build messages
            messages = [{"role": "system", "content": system_message}]

            # Add conversation history
            if conversation_history:
                for msg in conversation_history[-5:]:  # Last 5 messages
                    messages.append(msg)

            # Add current prompt
            messages.append({"role": "user", "content": prompt})

            # Generate response (async)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: ollama.chat(
                    model=model,
                    messages=messages,
                    options={
                        "temperature": temperature,
                        "num_predict": max_tokens,
                    }
                )
            )

            return response['message']['content'].strip()

        except Exception as e:
            print(f"Ollama error: {e}")
            return self._generate_placeholder(prompt, personality)

    async def _generate_mlx(
        self,
        prompt: str,
        personality: str,
        knowledge_base: str,
        model: str,
        temperature: float,
        max_tokens: int,
        conversation_history: Optional[List[Dict[str, str]]]
    ) -> str:
        """Generate response using MLX (Apple Silicon)"""
        try:
            from mlx_lm import load, generate

            # Build prompt with personality and context
            full_prompt = f"You are {personality}."
            if knowledge_base:
                full_prompt += f" {knowledge_base}"
            full_prompt += f"\n\nPlayer: {prompt}\nYou (stay in character, 1-3 sentences):"

            # Load model (use a small model for speed)
            # Common MLX-compatible models: mlx-community/Llama-2-7b-chat-mlx
            model_path = f"mlx-community/{model}-mlx" if "mlx" not in model else model

            # Generate (async)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: generate(
                    load(model_path),
                    full_prompt,
                    max_tokens=max_tokens,
                    temp=temperature
                )
            )

            # Extract response after the prompt
            if response:
                # MLX returns full text including prompt, extract just the response
                lines = response.split('\n')
                for line in lines:
                    if line.strip() and not line.startswith("You are") and not line.startswith("Player:"):
                        return line.strip()

            return response.strip() if response else self._generate_placeholder(prompt, personality)

        except Exception as e:
            print(f"MLX error: {e}")
            return self._generate_placeholder(prompt, personality)

    def _generate_placeholder(self, prompt: str, personality: str) -> str:
        """Generate a placeholder response when no AI backend is available"""
        responses = [
            f"As {personality}, I acknowledge your message: '{prompt[:50]}...'",
            f"I heard you say something about '{prompt[:30]}...'. [AI not configured]",
            f"Interesting. Tell me more about that. [Local AI not available]",
            f"I appreciate you talking to me, though I must confess my AI isn't fully configured yet.",
            f"That's a fascinating question about '{prompt[:40]}...'. [Install Ollama for full AI responses]",
        ]
        import random
        return random.choice(responses)

    async def get_game_guidance(
        self,
        player_query: str,
        game_context: Dict[str, Any],
        model: str = "llama2"
    ) -> str:
        """
        Provide AI-powered game guidance to players.

        Args:
            player_query: The player's question
            game_context: Current game state (location, inventory, etc.)
            model: AI model to use

        Returns:
            Helpful guidance response
        """
        # Build context
        context = f"""You are a helpful game guide for Web-Pennmush, a text-based multiplayer game.

Current player context:
- Location: {game_context.get('location', 'unknown')}
- Inventory: {game_context.get('inventory', 'empty')}
- Available commands: look, examine, say, pose, go, get, drop, inventory, who, help, channel/list, @create, @dig, @open

Player question: {player_query}

Provide a brief, helpful response (2-3 sentences). If it's about commands, explain what they do. If it's about the game world, be creative but helpful."""

        messages = [{"role": "user", "content": context}]

        try:
            if self.backend == AIBackend.OLLAMA:
                import ollama
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: ollama.chat(
                        model=model,
                        messages=messages,
                        options={"temperature": 0.7, "num_predict": 150}
                    )
                )
                return response['message']['content'].strip()
            else:
                return "Game guidance AI is not configured. Try 'help' for command documentation."
        except Exception as e:
            print(f"Game guidance error: {e}")
            return "I'm having trouble accessing my guidance systems. Try 'help [command]' for specific information."

    def is_available(self) -> bool:
        """Check if any AI backend is available"""
        return self.backend != AIBackend.NONE

    def get_status(self) -> Dict[str, Any]:
        """Get AI backend status"""
        return {
            "backend": self.backend.value,
            "ollama_available": self.ollama_available,
            "mlx_available": self.mlx_available,
            "is_configured": self.is_available()
        }

    async def list_available_models(self) -> List[str]:
        """List available AI models"""
        if self.backend == AIBackend.OLLAMA:
            try:
                import ollama
                loop = asyncio.get_event_loop()
                models = await loop.run_in_executor(None, ollama.list)
                return [model['name'] for model in models.get('models', [])]
            except Exception as e:
                print(f"Error listing Ollama models: {e}")
                return ["llama2", "mistral", "codellama"]
        elif self.backend == AIBackend.MLX:
            return ["Llama-2-7b-chat", "mistral-7b", "phi-2"]
        else:
            return []


# Global AI manager instance
ai_manager = AIManager()
