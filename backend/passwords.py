"""
Web-Pennmush password hashing
Author: Jordan Koch (GitHub: kochj23)

Thin bcrypt wrapper replacing the unmaintained passlib. Keeps the
`pwd_context.hash()/verify()` interface the rest of the code uses.
bcrypt only looks at the first 72 bytes, so longer passwords are rejected at
registration (see MAX_PASSWORD_BYTES) and simply fail verification.
"""
import asyncio
import os

import bcrypt

MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8
BCRYPT_ROUNDS = max(4, min(15, int(os.environ.get("BCRYPT_ROUNDS", "12"))))

# Pre-computed hash used to equalise timing when the account does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=BCRYPT_ROUNDS))


class PasswordContext:
    """bcrypt hash/verify with the passlib-compatible method names."""

    def hash(self, password: str) -> str:
        raw = password.encode("utf-8")
        if len(raw) > MAX_PASSWORD_BYTES:
            raise ValueError(f"password longer than {MAX_PASSWORD_BYTES} bytes")
        return bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)).decode("ascii")

    def verify(self, password: str, hashed: str) -> bool:
        if not password or not hashed:
            return False
        raw = password.encode("utf-8")
        if len(raw) > MAX_PASSWORD_BYTES:
            return False
        try:
            return bcrypt.checkpw(raw, hashed.encode("ascii"))
        except ValueError:
            return False

    def dummy_verify(self) -> None:
        """Spend the same time as a real verify (for unknown usernames)."""
        bcrypt.checkpw(b"not-the-password", _DUMMY_HASH)

    async def averify(self, password: str, hashed: str) -> bool:
        """verify() off the event loop (bcrypt is deliberately slow)."""
        return await asyncio.to_thread(self.verify, password, hashed)

    async def ahash(self, password: str) -> str:
        return await asyncio.to_thread(self.hash, password)


pwd_context = PasswordContext()
