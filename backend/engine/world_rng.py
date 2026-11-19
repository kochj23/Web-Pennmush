"""
Web-Pennmush world randomness
Author: Jordan Koch (GitHub: kochj23)

One seeded source of randomness per world, instead of the global `random`.

- The seed lives in the database (`world_settings.rng_seed`, created once with
  `secrets`). Every server start bumps `world_settings.rng_epoch`.
- Each top-level softcode evaluation gets its own stream, derived from
  (seed, epoch, evaluation counter). Players still see unpredictable values
  (they never learn the seed), but a bug report carrying the logged
  `epoch`/`n` can be replayed exactly with `SoftcodeInterpreter.eval(...,
  rng_ref=(epoch, n))`.
- Scripted NPC lines and the +watch scene share one world stream (`npc`).

Tests inject `WorldRandom(seed=..., epoch=...)`. This is game randomness, not
cryptography: never use it for tokens or passwords.
"""
import random
import secrets
from typing import Optional, Tuple


class WorldRandom:
    def __init__(self, seed: Optional[int] = None, epoch: int = 0):
        # Until configure() runs (unit tests without a DB) the seed is random.
        self.npc = random.Random()
        self.configure(secrets.randbits(63) if seed is None else seed, epoch)

    def configure(self, seed: int, epoch: int) -> None:
        """Adopt the world's seed/epoch. Reseeds `npc` in place so holders keep their reference."""
        self.seed = int(seed)
        self.epoch = int(epoch)
        self.counter = 0
        self.npc.seed(f"{self.seed}:{self.epoch}:npc")

    def stream(self, epoch: int, n: int) -> random.Random:
        """The stream for evaluation n of a given epoch (string seeds hash with SHA-512, stable across runs)."""
        return random.Random(f"{self.seed}:{epoch}:softcode:{n}")

    def next_eval(self) -> Tuple[Tuple[int, int], random.Random]:
        """Reserve the next evaluation number and return ((epoch, n), its stream)."""
        self.counter += 1
        ref = (self.epoch, self.counter)
        return ref, self.stream(*ref)


world_rng = WorldRandom()
