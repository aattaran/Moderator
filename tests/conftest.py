"""Shared test fixtures."""

import os
import sys

import pytest
import pytest_asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest_asyncio.fixture
async def db():
    """Create an in-memory database for testing."""
    from storage.database import Database

    database = Database(":memory:")
    await database.initialize()
    yield database
    await database.close()
