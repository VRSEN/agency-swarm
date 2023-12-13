import pytest

from agency_swarm.agency.async_agency import AsyncAgency
import asyncio

@pytest.mark.asyncio
async def test_async_agency(async_agency: AsyncAgency):
    await async_agency.initialize()
    debate = await async_agency.get_completion("how to survive nuclear war? use functions to generate answers")
    for msg in debate :
        if isinstance(msg, list):
            for item in msg:
                print(item.content)
            else:
                print(msg.content)
    assert False


@pytest.mark.asyncio
async def test_async_agency_init(async_agency: AsyncAgency):
    print(f"\n\n************ \n\t the async agency:{async_agency}")
    await async_agency._init_agents()
def test_parse_chart(async_agency):
    print(f"\n\n************ \n\t the ceo:{async_agency.ceo}")
    assert False