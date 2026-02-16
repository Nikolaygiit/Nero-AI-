import pytest
import asyncio
import os
from database.db import db
from database.models import User

@pytest.mark.asyncio
async def test_get_all_telegram_ids_chunks():
    """Test get_all_telegram_ids yields chunks correctly"""
    # Use temporary file for testing
    test_db_path = "test_db_ids.db"

    # Override global db path
    db.db_path = test_db_path
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    await db.init()

    try:
        # Create 10 users
        async with db.async_session() as session:
            for i in range(10):
                user = User(telegram_id=i+1, username=f"user_{i}")
                session.add(user)
            await session.commit()

        # Test with small chunk size
        ids = []
        chunk_count = 0
        async for chunk in db.get_all_telegram_ids(chunk_size=3):
            chunk_count += 1
            assert isinstance(chunk, list)
            assert len(chunk) <= 3
            ids.extend(chunk)

        assert len(ids) == 10
        assert sorted(ids) == list(range(1, 11))
        # 10 items with chunk size 3 -> 4 chunks (3, 3, 3, 1)
        assert chunk_count == 4

    finally:
        await db.close()
        if os.path.exists(test_db_path):
            os.remove(test_db_path)
