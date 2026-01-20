# Web-Pennmush AI Integration Guide

Web-Pennmush v2.0.0+ includes **local AI integration** for intelligent NPCs and an AI-powered game guide. No cloud APIs or API keys required!

## 🤖 Supported AI Backends

### 1. Ollama (Recommended for all platforms)
- **Works on**: macOS, Linux, Windows
- **Models**: Llama 2, Mistral, CodeLlama, and 50+ more
- **Performance**: Fast, runs locally
- **Memory**: 8GB RAM minimum, 16GB recommended

### 2. MLX (Apple Silicon only)
- **Works on**: M1, M2, M3, M4 Macs
- **Models**: Optimized for Apple Silicon
- **Performance**: Extremely fast on Apple hardware
- **Memory**: 8GB unified memory minimum

---

## 📦 Installation

### Option 1: Ollama (All Platforms)

**Step 1: Install Ollama**
```bash
# macOS
brew install ollama

# Or download from https://ollama.ai

# Linux
curl https://ollama.ai/install.sh | sh

# Windows
# Download installer from https://ollama.ai
```

**Step 2: Pull a model**
```bash
# Start Ollama service (it runs in the background)
ollama serve

# In a new terminal, pull a model
ollama pull llama2           # 3.8GB - Recommended for most users
ollama pull mistral          # 4.1GB - Great for conversation
ollama pull codellama        # 3.8GB - Good for technical topics
ollama pull llama2:13b       # 7.3GB - Better quality, needs more RAM
```

**Step 3: Verify installation**
```bash
ollama list
# Should show downloaded models

ollama run llama2 "Hello, how are you?"
# Should generate a response
```

**Step 4: Install Python package**
```bash
cd /Volumes/Data/xcode/Web-Pennmush
pip install ollama
```

**Step 5: Restart Web-Pennmush**
```bash
python -m backend.main
```

You should see:
```
Initializing AI backends...
✓ Ollama detected and available
AI Backend: ollama
✓ AI is ready! NPCs and game guide are functional.
```

### Option 2: MLX (Apple Silicon Only)

**Step 1: Install MLX**
```bash
cd /Volumes/Data/xcode/Web-Pennmush
pip install mlx-lm
```

**Step 2: Download a model** (automatic on first use)
```bash
# Models will download automatically when first used
# Or pre-download with:
python -c "from mlx_lm import load; load('mlx-community/Llama-2-7b-chat-mlx')"
```

**Step 3: Restart Web-Pennmush**
```bash
python -m backend.main
```

You should see:
```
Initializing AI backends...
✓ MLX detected and available (Apple Silicon)
AI Backend: mlx
✓ AI is ready! NPCs and game guide are functional.
```

---

## 🎮 Using AI Features

### 1. AI-Powered NPCs

**Create an NPC**
```bash
@npc/create Sage
# Created NPC: Sage(#15)
# Use '@npc/personality' and '@npc/knowledge' to configure.
```

**Set Personality**
```bash
@npc/personality Sage=A wise and ancient wizard who speaks in riddles and knows the secrets of magic
# Personality set for Sage: A wise and ancient wizard who speaks in riddles...
```

**Give Knowledge**
```bash
@npc/knowledge Sage=You know the locations of three ancient crystals: the Crystal of Light in the Sunlit Cave, the Crystal of Shadow in the Dark Abyss, and the Crystal of Time in the Frozen Tower. You also know spells for basic magic.
# Knowledge base set for Sage.
```

**Talk to the NPC**
```bash
talk to Sage=Where can I find a crystal?
# Sage says, "Seek ye the luminous stone within the cave kissed by sun's first light..."

talk to Sage=Can you teach me magic?
# Sage says, "Magic flows through those who seek wisdom. Begin with simple incantations..."

talk to Sage=What do you know about the towers?
# Sage says, "In the Frozen Tower dwells time itself, crystallized in eternal ice..."
```

The AI remembers your conversation! Each NPC maintains their own conversation history.

### 2. AI Game Guide

**Ask the guide anything**
```bash
guide How do I create a room?
# === AI Guide ===
#
# To create a new room, use the @dig command followed by the room name.
# For example: @dig Castle Entrance
# This creates a new room. You can then use @open to create exits...

guide What are channels?
# === AI Guide ===
#
# Channels are group chat rooms where players can communicate. Join with
# 'channel/join Public' and chat with 'pub <message>'. Use 'channel/list'...

guide How do I pick up objects?
# === AI Guide ===
#
# Use the 'get' command (or 'take') followed by the object name.
# For example: get crystal
# Use 'inventory' to see what you're carrying...
```

The guide is context-aware and knows:
- Your current location
- Your inventory
- All available commands
- Game mechanics

### 3. Check AI Status

```bash
@ai/status
# === AI Backend Status ===
# Active Backend: ollama
# Ollama Available: ✓ Yes
# MLX Available: ✗ No (Apple Silicon only)
# Configured: ✓ Yes
#
# Available Models:
#   - llama2:latest
#   - mistral:latest
#   - codellama:latest
```

---

## ⚙️ Configuration

Edit `backend/config.py` or create a `.env` file:

```python
# AI Backend Selection
AI_BACKEND="auto"          # auto, ollama, mlx, none
AI_DEFAULT_MODEL="llama2"  # Default model for NPCs
OLLAMA_BASE_URL="http://localhost:11434"
AI_ENABLE_GAME_GUIDE=True
```

### Environment Variables (.env file)

```bash
# AI Configuration
AI_BACKEND=ollama
AI_DEFAULT_MODEL=mistral
OLLAMA_BASE_URL=http://localhost:11434
AI_ENABLE_GAME_GUIDE=True
```

---

## 🎯 NPC Model Selection

Each NPC can use a different model. Set it when creating:

```bash
@npc/create Warrior
@npc/personality Warrior=Brave and strong, speaks with authority
@set Warrior=AI_MODEL:codellama
```

Or change the default in config.py.

---

## 📊 Performance & Resource Usage

### Ollama Performance

| Model | Size | RAM Usage | Speed | Quality |
|-------|------|-----------|-------|---------|
| llama2 | 3.8GB | ~4GB | Fast | Good |
| mistral | 4.1GB | ~5GB | Fast | Great |
| llama2:13b | 7.3GB | ~8GB | Medium | Excellent |
| codellama | 3.8GB | ~4GB | Fast | Good for tech |

### MLX Performance (Apple Silicon)

- **M1/M2/M3**: Extremely fast, uses unified memory efficiently
- **Memory**: 8GB minimum, 16GB recommended for larger models
- **Speed**: 2-3x faster than Ollama on same hardware

---

## 🔧 Troubleshooting

### Ollama Not Detected

**Check if Ollama is running:**
```bash
curl http://localhost:11434/api/tags
# Should return JSON with model list
```

**If not running:**
```bash
ollama serve
# Keep this terminal open, or run as background service
```

**Check Python package:**
```bash
pip list | grep ollama
# Should show: ollama x.x.x
```

**Reinstall if needed:**
```bash
pip uninstall ollama
pip install ollama
```

### MLX Not Working

**Check platform:**
```bash
python -c "import platform; print(platform.machine())"
# Should output: arm64 (for Apple Silicon)
# If it shows x86_64, MLX won't work (Intel Mac)
```

**Check installation:**
```bash
pip list | grep mlx
# Should show: mlx-lm x.x.x
```

**Test MLX:**
```bash
python -c "import mlx.core as mx; print('MLX works!')"
```

### NPCs Not Responding

1. **Check AI status in-game:**
   ```bash
   @ai/status
   ```

2. **Check logs:**
   Look for errors in the terminal where Web-Pennmush is running.

3. **Test model manually:**
   ```bash
   # For Ollama:
   ollama run llama2 "Hello!"

   # For MLX:
   python -c "from mlx_lm import load, generate; print(generate(load('mlx-community/Llama-2-7b-chat-mlx'), 'Hello!'))"
   ```

4. **Verify NPC configuration:**
   ```bash
   examine Sage
   # Check that personality and knowledge are set
   ```

### Slow Response Times

**For Ollama:**
- Use smaller models (llama2 instead of llama2:13b)
- Ensure Ollama service has enough RAM
- Check `ollama ps` to see what's running

**For MLX:**
- Use quantized models (they're faster)
- Close other memory-intensive apps
- Ensure you're on Apple Silicon

**Adjust max_tokens:**
```python
# In backend/models.py, NPC model:
max_tokens = Column(Integer, default=100, nullable=False)  # Reduce from 150 to 100
```

---

## 🎨 Advanced: Custom Prompts

### Modify NPC System Prompt

Edit `backend/engine/ai_manager.py`, function `_generate_ollama`:

```python
system_message = f"You are {personality}."
system_message += "\n\nYou are a character in a text-based multiplayer game (MUSH)."
system_message += "\n\nKeep responses brief (1-3 sentences) and in-character."
system_message += "\n\nBe engaging and helpful to players."
# Add your custom instructions here
```

### Modify Game Guide Prompt

Edit `backend/engine/ai_manager.py`, function `get_game_guidance`:

```python
context = f"""You are a helpful game guide for Web-Pennmush...
# Modify this prompt to change guide behavior
```

---

## 🚀 Best Practices

### NPC Design

1. **Clear Personalities**: Be specific about character traits
   ```bash
   Good: "Grumpy old blacksmith who doesn't suffer fools"
   Bad: "A blacksmith"
   ```

2. **Focused Knowledge**: Give NPCs specific expertise
   ```bash
   Good: "Expert on sword crafting, knows 50+ weapon types"
   Bad: "Knows everything about the game"
   ```

3. **Consistent Behavior**: Test conversations to ensure character stays in role

### Performance

1. **Use smaller models for background NPCs**: llama2 (3.8GB)
2. **Use larger models for important NPCs**: llama2:13b (7.3GB)
3. **Limit max_tokens** to 100-150 for faster responses
4. **Don't create too many NPCs** - 5-10 is reasonable

### Game Design

1. **Use NPCs for exposition** - they can explain game mechanics
2. **Create quest-giving NPCs** - they can guide players
3. **Build atmosphere** - NPCs make the world feel alive
4. **Test conversations** - ensure NPCs give useful info

---

## 📚 Example: Complete NPC Setup

```bash
# Create a quest-giving NPC
@npc/create Elder Mira

# Set detailed personality
@npc/personality Elder Mira=You are Elder Mira, the village elder. You are wise, patient, and speak with gravitas. You have lived for 300 years and have seen many heroes come and go. You offer guidance to worthy adventurers but test their resolve first.

# Give comprehensive knowledge
@npc/knowledge Elder Mira=You know of three main quests: 1) The Crystal Quest - retrieve three crystals from dangerous locations, 2) The Dragon's Lair - defeat the dragon threatening the village, 3) The Lost Tome - find the ancient book of spells in the library ruins. You can give hints about these quests but prefer players to discover things themselves. You know the village history, local legends, and can identify magical items.

# Use a better model for important NPCs
@set Elder Mira=AI_MODEL:mistral

# Test the NPC
talk to Elder Mira=Greetings, Elder. I seek adventure.
# Elder Mira says, "Greetings, young one. Many seek adventure, but few are truly ready for its trials. Tell me, what drives you to walk this path?"

talk to Elder Mira=I want to prove myself and help the village.
# Elder Mira says, "A noble cause. The village faces threats, ancient and new. Three crystals of power lie scattered across dangerous lands. Are you prepared to face such challenges?"

talk to Elder Mira=Tell me about the crystals.
# Elder Mira says, "The Crystal of Light rests in the Sunlit Cave, guarded by creatures of shadow. The Crystal of Shadow lurks in the Dark Abyss, where light fears to tread. The Crystal of Time lies frozen in the Tower of Eternity. Each trial will test you differently."
```

---

## 🎉 Ready to Go!

With AI configured, your Web-Pennmush is now powered by intelligent characters and helpful guidance. Players can:

- Have meaningful conversations with NPCs
- Get help from the AI guide
- Experience a living, responsive game world

**Enjoy your AI-powered MUSH!**

---

For more help:
- In-game: `help @npc/create` or `help guide`
- Ollama docs: https://ollama.ai
- MLX docs: https://github.com/ml-explore/mlx-examples
- Issues: https://github.com/kochj23/Web-Pennmush/issues
