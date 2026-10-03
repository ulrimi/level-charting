import pytest

from level_charting.demo import synthetic_packet, synthetic_proposal


@pytest.fixture(scope="session")
def packet():
    return synthetic_packet()


@pytest.fixture(scope="session")
def proposal(packet):
    return synthetic_proposal(packet)
