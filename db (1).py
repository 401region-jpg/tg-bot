# db.py
import json
import asyncio
import logging
import aiosqlite
from typing import Optional, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path: str = "bot.db"):
        self.db_path = db_path

    async def cleanup_old_users(self, cutoff):
        """Удаляет пользователей, неактивных дольше cutoff"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM users WHERE last_active < ?",
                (cutoff.isoformat(),)
            )
            await db.commit()
            logger.info("Старые пользователи удалены")
            
    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                name TEXT,
                age INT,
                bio TEXT,
                photo_id TEXT,
                step TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_superlike TIMESTAMP,
                superlike_extra INT DEFAULT 0,
                superlike_extra_expires TIMESTAMP,
                referrer BIGINT,
                is_admin BOOLEAN DEFAULT FALSE
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS likes(
                liker BIGINT,
                liked BIGINT,
                type TEXT DEFAULT 'like',
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(liker, liked)
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS views(
                viewer BIGINT,
                viewed BIGINT,
                PRIMARY KEY(viewer, viewed)
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS matches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_a BIGINT,
                user_b BIGINT,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                shown_to_a BOOLEAN DEFAULT FALSE,
                shown_to_b BOOLEAN DEFAULT FALSE
            );
            """)

            await db.execute("""
            CREATE TABLE IF NOT EXISTS backups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                users_json TEXT,
                likes_json TEXT,
                views_json TEXT
            );
            """)
            await db.commit()

    # === helpers ===
    async def user_get(self, user_id: int) -> Optional[dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def user_create_if_missing(self, user_id: int, username: Optional[str], ref: Optional[int] = None):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
            INSERT INTO users(user_id, username, step, created_at, last_active, referrer)
            VALUES(?, ?, 'name', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, ?)
            ON CONFLICT(user_id) DO NOTHING
            """, (user_id, username, ref))
            await db.commit()

    async def user_update(self, user_id: int, **kwargs):
        if not kwargs:
            return
        set_clause = ", ".join(f"{k} = ?" for k in kwargs.keys())
        values = list(kwargs.values()) + [user_id]
        query = f"UPDATE users SET {set_clause} WHERE user_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, values)
            await db.commit()

    async def insert_like(self, liker: int, liked: int, typ: str = "like"):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO likes(liker, liked, type) VALUES(?, ?, ?) ON CONFLICT DO NOTHING",
                (liker, liked, typ)
            )
            await db.commit()

    async def exists_mutual(self, a: int, b: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT 1 FROM likes WHERE liker = ? AND liked = ?", (b, a))
            row = await cursor.fetchone()
            return bool(row)

    async def add_view(self, viewer: int, viewed: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO views(viewer, viewed) VALUES(?, ?) ON CONFLICT DO NOTHING",
                (viewer, viewed)
            )
            await db.commit()

    async def get_next_profile(self, viewer: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT u.user_id, u.name, u.age, u.bio, u.photo_id
                FROM users u
                WHERE u.step = 'done' AND u.user_id <> ?
                  AND u.user_id NOT IN (SELECT viewed FROM views WHERE viewer = ?)
                  AND u.user_id NOT IN (
                    SELECT CASE WHEN user_a = ? THEN user_b WHEN user_b = ? THEN user_a END
                    FROM matches WHERE user_a = ? OR user_b = ?
                  )
                ORDER BY RANDOM()
                LIMIT 1
            """, (viewer, viewer, viewer, viewer, viewer, viewer))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def clear_views(self, viewer: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM views WHERE viewer = ?", (viewer,))
            await db.commit()

    async def create_match(self, a: int, b: int):
        async with aiosqlite.connect(self.db_path) as db:
            # Проверяем существующий матч
            cursor = await db.execute("""
                SELECT id FROM matches WHERE (user_a = ? AND user_b = ?) OR (user_a = ? AND user_b = ?)
            """, (a, b, b, a))
            existing = await cursor.fetchone()
            if existing:
                return existing[0]

            cursor = await db.execute("INSERT INTO matches(user_a, user_b) VALUES(?, ?)", (a, b))
            await db.commit()
            return cursor.lastrowid

    async def get_unshown_matches(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT id, user_a, user_b FROM matches
                WHERE (user_a = ? AND shown_to_a = 0) OR (user_b = ? AND shown_to_b = 0)
                ORDER BY created
            """, (user_id, user_id))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def mark_match_shown(self, match_id: int, for_user: int):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT user_a, user_b FROM matches WHERE id = ?", (match_id,))
            row = await cursor.fetchone()
            if not row:
                return
            user_a, user_b = row[0], row[1]
            if user_a == for_user:
                await db.execute("UPDATE matches SET shown_to_a = 1 WHERE id = ?", (match_id,))
            elif user_b == for_user:
                await db.execute("UPDATE matches SET shown_to_b = 1 WHERE id = ?", (match_id,))
            await db.commit()

    async def all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT user_id, username, name, age, bio, photo_id, last_active
                FROM users WHERE step = 'done'
            """)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def delete_user(self, user_id: int):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM likes WHERE liker = ? OR liked = ?", (user_id, user_id))
            await db.execute("DELETE FROM views WHERE viewer = ? OR viewed = ?", (user_id, user_id))
            await db.execute("DELETE FROM matches WHERE user_a = ? OR user_b = ?", (user_id, user_id))
            await db.commit()

    async def backup_snapshot(self):
        users = await self.all_users()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT liker, liked, type, created FROM likes")
            likes = await cursor.fetchall()
            likes = [dict(row) for row in likes]

            cursor = await db.execute("SELECT viewer, viewed FROM views")
            views = await cursor.fetchall()
            views = [dict(row) for row in views]

            await db.execute("""
                INSERT INTO backups(users_json, likes_json, views_json)
                VALUES(?, ?, ?)
            """, (json.dumps(users), json.dumps(likes), json.dumps(views)))
            await db.commit()