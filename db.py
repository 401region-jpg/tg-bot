# db.py
import json
import asyncio
import logging
from typing import Optional, List, Any
import asyncpg
from config import DATABASE_URL

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def init(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(DATABASE_URL, ssl="require")
            logger.info("✅ Подключение к Supabase установлено")

        # Создание таблиц (если не существуют)
        async with self.pool.acquire() as conn:
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS users(
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                name TEXT,
                age INT,
                bio TEXT,
                photo_id TEXT,
                step TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                last_active TIMESTAMP DEFAULT NOW(),
                last_superlike TIMESTAMP,
                superlike_extra INT DEFAULT 0,
                superlike_extra_expires TIMESTAMP,
                referrer BIGINT,
                is_admin BOOLEAN DEFAULT FALSE
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS likes(
                liker BIGINT,
                liked BIGINT,
                type TEXT DEFAULT 'like',
                created TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY(liker, liked)
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS views(
                viewer BIGINT,
                viewed BIGINT,
                PRIMARY KEY(viewer, viewed)
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS matches(
                id BIGSERIAL PRIMARY KEY,
                user_a BIGINT,
                user_b BIGINT,
                created TIMESTAMP DEFAULT NOW(),
                shown_to_a BOOLEAN DEFAULT FALSE,
                shown_to_b BOOLEAN DEFAULT FALSE
            );
            """)

            await conn.execute("""
            CREATE TABLE IF NOT EXISTS backups (
                id BIGSERIAL PRIMARY KEY,
                created TIMESTAMP DEFAULT NOW(),
                users_json JSONB,
                likes_json JSONB,
                views_json JSONB
            );
            """)

    async def cleanup_old_users(self, cutoff):
        """Удаляет пользователей, неактивных дольше cutoff"""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM users WHERE last_active < $1",
                (cutoff,)
            )
            logger.info("🧹 Старые пользователи удалены")

    # === helpers ===
    async def user_get(self, user_id: int) -> Optional[asyncpg.Record]:
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", user_id)

    async def user_create_if_missing(self, user_id: int, username: Optional[str], ref: Optional[int] = None):
        async with self.pool.acquire() as conn:
            await conn.execute("""
            INSERT INTO users(user_id, username, step, created_at, last_active, referrer)
            VALUES($1, $2, 'name', NOW(), NOW(), $3) ON CONFLICT (user_id) DO NOTHING
            """, user_id, username, ref)

    async def user_update(self, user_id: int, **kwargs):
        if not kwargs:
            return
        cols = []
        vals = []
        i = 1
        for k, v in kwargs.items():
            cols.append(f"{k} = ${i}")
            vals.append(v)
            i += 1
        sql = f"UPDATE users SET {', '.join(cols)} WHERE user_id = ${i}"
        vals.append(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute(sql, *vals)

    async def insert_like(self, liker: int, liked: int, typ: str = "like"):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO likes(liker, liked, type) VALUES($1, $2, $3) ON CONFLICT DO NOTHING",
                liker, liked, typ
            )

    async def exists_mutual(self, a: int, b: int) -> bool:
        async with self.pool.acquire() as conn:
            r = await conn.fetchrow("SELECT 1 FROM likes WHERE liker = $1 AND liked = $2", b, a)
            return bool(r)

    async def add_view(self, viewer: int, viewed: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO views(viewer, viewed) VALUES($1, $2) ON CONFLICT DO NOTHING",
                viewer, viewed
            )

    async def get_next_profile(self, viewer: int):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT u.user_id, u.name, u.age, u.bio, u.photo_id
                FROM users u
                WHERE u.step = 'done' AND u.user_id <> $1
                  AND u.user_id NOT IN (SELECT viewed FROM views WHERE viewer = $1)
                  AND u.user_id NOT IN (
                    SELECT CASE WHEN user_a = $1 THEN user_b WHEN user_b = $1 THEN user_a END
                    FROM matches WHERE user_a = $1 OR user_b = $1
                  )
                ORDER BY random()
                LIMIT 1
            """, viewer)

    async def clear_views(self, viewer: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM views WHERE viewer = $1", viewer)

    async def create_match(self, a: int, b: int):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow("""
                    SELECT id FROM matches 
                    WHERE (user_a = $1 AND user_b = $2) OR (user_a = $2 AND user_b = $1)
                """, a, b)
                if existing:
                    return existing["id"]
                r = await conn.fetchrow("INSERT INTO matches(user_a, user_b) VALUES($1, $2) RETURNING id", a, b)
                return r["id"]

    async def get_unshown_matches(self, user_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, user_a, user_b FROM matches
                WHERE (user_a = $1 AND shown_to_a = false) OR (user_b = $1 AND shown_to_b = false)
                ORDER BY created
            """, user_id)

    async def mark_match_shown(self, match_id: int, for_user: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT user_a, user_b FROM matches WHERE id = $1", match_id)
            if not row:
                return
            if row["user_a"] == for_user:
                await conn.execute("UPDATE matches SET shown_to_a = true WHERE id = $1", match_id)
            elif row["user_b"] == for_user:
                await conn.execute("UPDATE matches SET shown_to_b = true WHERE id = $1", match_id)

    async def all_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT user_id, username, name, age, bio, photo_id, last_active 
                FROM users WHERE step = 'done'
            """)

    async def delete_user(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM users WHERE user_id = $1", user_id)
            await conn.execute("DELETE FROM likes WHERE liker = $1 OR liked = $1", user_id)
            await conn.execute("DELETE FROM views WHERE viewer = $1 OR viewed = $1", user_id)
            await conn.execute("DELETE FROM matches WHERE user_a = $1 OR user_b = $1", user_id)

    async def backup_snapshot(self):
        async with self.pool.acquire() as conn:
            users = await conn.fetch("SELECT user_id, username, name, age, bio, photo_id, last_active FROM users")
            likes = await conn.fetch("SELECT liker, liked, type, created FROM likes")
            views = await conn.fetch("SELECT viewer, viewed FROM views")
            await conn.execute("""
                INSERT INTO backups(users_json, likes_json, views_json)
                VALUES($1::jsonb, $2::jsonb, $3::jsonb)
            """, 
                json.dumps([dict(r) for r in users]),
                json.dumps([dict(r) for r in likes]),
                json.dumps([dict(r) for r in views])
            )
