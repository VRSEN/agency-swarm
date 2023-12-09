from agency_swarm import Agent, Agency
import pytest



def test_agency(agency):
    debate = agency.get_completion("Hello, how can I help you?")
    for msg in debate:
        print(msg.content)


def test_parse_chart(agency):
    print(f"\n\n************ \n\t the ceo:{agency.ceo}")
    assert False
    #print(Agency.parse_chart(agency_chart))