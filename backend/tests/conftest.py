import tempfile
from pathlib import Path

import pytest_asyncio

from sahay.factory import build_agent


@pytest_asyncio.fixture
async def agent():
    async with build_agent(data_dir=Path(tempfile.mkdtemp(prefix="sahay-test-"))) as a:
        yield a
