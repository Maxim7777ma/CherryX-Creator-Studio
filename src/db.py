from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time

import aiosqlite


@dataclass(frozen=True)
class Subscription:
    user_id: int
    active_until: int
    charge_id: str | None

    @property
    def is_active(self) -> bool:
        return self.active_until > int(time.time())

    @property
    def active_until_text(self) -> str:
        dt = datetime.fromtimestamp(self.active_until, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")


@dataclass(frozen=True)
class ConversionRecord:
    media_type: str
    source_name: str
    output_name: str
    output_format: str
    output_size: int
    created_at: int


@dataclass(frozen=True)
class PaymentRecord:
    user_id: int
    currency: str
    total_amount: int
    invoice_payload: str
    telegram_payment_charge_id: str | None
    provider_payment_charge_id: str | None
    subscription_until: int
    created_at: int


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language TEXT,
                    active_until INTEGER NOT NULL DEFAULT 0,
                    charge_id TEXT,
                    updated_at INTEGER NOT NULL
                )
                """
            )
            await self._ensure_column(db, "users", "language", "TEXT")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS conversions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL DEFAULT 'image',
                    source_name TEXT NOT NULL,
                    output_name TEXT NOT NULL,
                    output_format TEXT NOT NULL,
                    source_size INTEGER NOT NULL,
                    output_size INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await self._ensure_column(db, "conversions", "media_type", "TEXT NOT NULL DEFAULT 'image'")
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    currency TEXT NOT NULL,
                    total_amount INTEGER NOT NULL,
                    invoice_payload TEXT NOT NULL,
                    telegram_payment_charge_id TEXT,
                    provider_payment_charge_id TEXT,
                    subscription_until INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
                """
            )
            await db.commit()

    async def upsert_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, username, first_name, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    updated_at=excluded.updated_at
                """,
                (user_id, username, first_name, int(time.time())),
            )
            await db.commit()

    async def set_subscription(self, user_id: int, active_until: int, charge_id: str | None) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, active_until, charge_id, updated_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    active_until=excluded.active_until,
                    charge_id=excluded.charge_id,
                    updated_at=excluded.updated_at
                """,
                (user_id, active_until, charge_id, int(time.time())),
            )
            await db.commit()

    async def add_payment(
        self,
        user_id: int,
        currency: str,
        total_amount: int,
        invoice_payload: str,
        telegram_payment_charge_id: str | None,
        provider_payment_charge_id: str | None,
        subscription_until: int,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO payments(
                    user_id, currency, total_amount, invoice_payload,
                    telegram_payment_charge_id, provider_payment_charge_id,
                    subscription_until, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    currency,
                    total_amount,
                    invoice_payload,
                    telegram_payment_charge_id,
                    provider_payment_charge_id,
                    subscription_until,
                    int(time.time()),
                ),
            )
            await db.commit()

    async def recent_payments(self, user_id: int, limit: int = 5) -> list[PaymentRecord]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT user_id, currency, total_amount, invoice_payload,
                       telegram_payment_charge_id, provider_payment_charge_id,
                       subscription_until, created_at
                FROM payments
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            PaymentRecord(
                user_id=row[0],
                currency=row[1],
                total_amount=row[2],
                invoice_payload=row[3],
                telegram_payment_charge_id=row[4],
                provider_payment_charge_id=row[5],
                subscription_until=row[6],
                created_at=row[7],
            )
            for row in rows
        ]

    async def get_subscription(self, user_id: int) -> Subscription:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT user_id, active_until, charge_id FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
        if not row:
            return Subscription(user_id=user_id, active_until=0, charge_id=None)
        return Subscription(user_id=row[0], active_until=row[1], charge_id=row[2])

    async def set_language(self, user_id: int, language: str) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO users(user_id, language, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    language=excluded.language,
                    updated_at=excluded.updated_at
                """,
                (user_id, language, int(time.time())),
            )
            await db.commit()

    async def get_language(self, user_id: int) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT language FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
        return row[0] if row and row[0] else None

    async def all_languages(self) -> dict[int, str]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT user_id, language FROM users WHERE language IS NOT NULL AND language != ''") as cursor:
                rows = await cursor.fetchall()
        return {int(row[0]): str(row[1]) for row in rows if row[1]}

    async def all_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT user_id FROM users ORDER BY updated_at DESC") as cursor:
                rows = await cursor.fetchall()
        return [int(row[0]) for row in rows]

    async def bot_stats(self) -> dict[str, int]:
        now = int(time.time())
        async with aiosqlite.connect(self.path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                users = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE active_until > ?", (now,)) as cursor:
                active = (await cursor.fetchone())[0]
            async with db.execute("SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM payments") as cursor:
                payments_row = await cursor.fetchone()
        return {
            "users": int(users or 0),
            "active": int(active or 0),
            "payments": int(payments_row[0] if payments_row else 0),
            "stars": int(payments_row[1] if payments_row else 0),
        }

    async def add_conversion(
        self,
        user_id: int,
        media_type: str,
        source_name: str,
        output_name: str,
        output_format: str,
        source_size: int,
        output_size: int,
    ) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO conversions(
                    user_id, media_type, source_name, output_name, output_format,
                    source_size, output_size, created_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    media_type,
                    source_name,
                    output_name,
                    output_format,
                    source_size,
                    output_size,
                    int(time.time()),
                ),
            )
            await db.commit()

    async def recent_conversions(self, user_id: int, limit: int = 10) -> list[ConversionRecord]:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """
                SELECT media_type, source_name, output_name, output_format, output_size, created_at
                FROM conversions
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            ConversionRecord(
                media_type=row[0],
                source_name=row[1],
                output_name=row[2],
                output_format=row[3],
                output_size=row[4],
                created_at=row[5],
            )
            for row in rows
        ]

    async def count_conversions_since(self, user_id: int, media_types: list[str], since: int) -> int:
        if not media_types:
            return 0
        placeholders = ",".join("?" for _ in media_types)
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                f"""
                SELECT COUNT(*)
                FROM conversions
                WHERE user_id = ?
                  AND created_at >= ?
                  AND media_type IN ({placeholders})
                """,
                (user_id, since, *media_types),
            ) as cursor:
                row = await cursor.fetchone()
        return int(row[0] if row else 0)

    async def _ensure_column(self, db: aiosqlite.Connection, table: str, column: str, definition: str) -> None:
        async with db.execute(f"PRAGMA table_info({table})") as cursor:
            columns = {row[1] async for row in cursor}
        if column not in columns:
            await db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
