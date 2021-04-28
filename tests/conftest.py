import pytest

from tslumd import TallyType
from tallypi.common import SingleTallyConfig, Pixel, Rgb

@pytest.fixture
def tally_conf_factory(faker):
    tally_types = [tt for tt in TallyType if tt != TallyType.no_tally]
    def build(num):
        for _ in range(num):
            ix = faker.pyint(min_value=0, max_value=0xffff)
            tally_type = faker.random_element(tally_types)
            yield SingleTallyConfig(tally_index=ix, tally_type=tally_type)
    return build

@pytest.fixture
def fake_rgb5x5(monkeypatch):
    monkeypatch.setenv('TALLYPI_MOCK', 'rgbmatrix5x5', prepend=':')
    from tallypi import mock
    mock.mock()
    import rgbmatrix5x5
    assert rgbmatrix5x5.RGBMatrix5x5.__module__ == 'tallypi.mock'
