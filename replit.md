# Telegram Dating Bot

## Overview
This is a Telegram dating bot written in Python using the aiogram 3.x framework. The bot allows users to create dating profiles, view other users' profiles, like/superlike profiles, and find matches.

## Project Status
- **Last Updated:** September 30, 2025
- **Current State:** Fully configured and running in Replit environment
- **Bot Name:** @rsuhinlove_bot (Знакомства РГГУ)

## Tech Stack
- **Language:** Python 3.12
- **Framework:** aiogram 3.22.0 (Telegram Bot API)
- **Database:** SQLite3
- **Environment:** Replit

## Project Structure
```
.
├── bot.py              # Main bot application
├── requirements.txt    # Python dependencies
├── runtime.txt         # Python version specification
├── .env.example        # Environment variables template
├── .gitignore          # Git ignore rules
├── database.db         # SQLite database (created at runtime)
└── database_backup.db  # Database backup (created at runtime)
```

## Features
- User profile creation (name, age, description, photo)
- Random profile browsing
- Like/Superlike system
- Match detection (mutual likes)
- Daily superlike cooldown
- Admin messaging system
- Automatic inactive user cleanup (30 days)
- Daily database backup

## Configuration

### Required Secrets
The bot requires the following Replit secret to be set:
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from [@BotFather](https://t.me/BotFather)

### Optional Secrets
- `ADMIN_USERNAME` - Admin username (defaults to @lxsonen if not set)

### Bot Settings
- **Min Age:** 16
- **Max Age:** 30
- **Superlike Cooldown:** 24 hours
- **Inactive User Cleanup:** 30 days

## Database Schema

### Users Table
- `user_id` (PRIMARY KEY) - Telegram user ID
- `username` - Telegram username
- `name` - Display name
- `age` - User age
- `description` - Profile description (max 1240 chars)
- `photo` - Telegram photo file_id
- `last_active` - Last activity timestamp
- `superlike_used` - Last superlike timestamp
- `ref_bonus` - Referral bonus count

### Likes Table
- `id` (PRIMARY KEY) - Auto-increment ID
- `from_id` - User who liked
- `to_id` - User who was liked
- `type` - Like type ('like' or 'superlike')

## Workflow
- **Name:** Telegram Bot
- **Command:** `python bot.py`
- **Type:** Console application (no web interface)
- **Status:** Running

## Recent Changes
- **Oct 1, 2025:** Fixed critical bugs - database race conditions, missing superlike status handler, error handling
- **Oct 1, 2025:** Added async database locking to prevent concurrent access issues
- **Oct 1, 2025:** Implemented activity tracking to prevent deletion of active users
- **Oct 1, 2025:** Added "⭐ Мой суперлайк" status handler showing cooldown and bonus info
- **Oct 1, 2025:** Improved error handling for failed message sends
- **Sep 30, 2025:** Migrated from aiogram 2.x to 3.x API
- **Sep 30, 2025:** Added environment variable support for sensitive data
- **Sep 30, 2025:** Configured for Replit environment with deployment support
- **Sep 30, 2025:** Added .gitignore for Python project
- **Sep 30, 2025:** Created database structure and backup system

## Bug Fixes (Oct 1, 2025)
1. **Database race conditions** - Replaced shared cursor with per-operation cursors and async lock
2. **Missing handler** - Added "⭐ Мой суперлайк" button handler to show status
3. **Bot freezing** - Added try/except around all message sends to prevent hangs
4. **User deletion bug** - Fixed activity tracking to prevent active users from being cleaned up
5. **Timestamp consistency** - Switched to ISO format for all datetime storage

## Architecture Notes
- Uses asyncio.Lock for thread-safe SQLite operations in async context
- Per-operation database cursors to prevent race conditions
- State machine pattern for multi-step profile creation
- Implements async/await for non-blocking Telegram API calls
- Comprehensive error handling with logging for all external API calls
- ISO format timestamps for consistent datetime handling
- Automated daily error reporting to admin
- Automatic cleanup of inactive users every 30 days (only affects users with last_active set)
