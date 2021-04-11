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

    class FakeDevice:
        def __init__(self):
            self.pixels = {(x,y):(0,0,0) for y in range(5) for x in range(5)}
            self._brightness = 1.0
        @property
        def brightness(self) -> float:
            return self._brightness
        @brightness.setter
        def brightness(self, value: float):
            if value == self.brightness:
                return
            self._brightness = value
            # logger.debug(f'brightness = {value}')
        def set_brightness(self, brightness):
            self.brightness = brightness
        def set_pixel(self, x, y, r, g, b, brightness=1.0):
            key = (x, y)
            rgb = (r, g, b)
            self[key] = rgb
            # logger.debug(f'{key} = {rgb}')
            self.brightness = 1.0
        def set_all(self, r, g, b, brightness=1.0):
            rgb = (r, g, b)
            # logger.debug(f'solid: {rgb}')
            for key in self:
                self[key] = rgb
            self.brightness = brightness
        def show(self):
            # logger.debug('show()')
            pass
        def clear(self):
            # logger.debug('clear()')
            for key in self:
                self[key] = (0,0,0)
        def __setitem__(self, key: Pixel, item: Rgb):
            self.pixels[key] = item
        def __getitem__(self, key: Pixel) -> Rgb:
            return self.pixels[key]
        def __iter__(self):
            yield from sorted(self.pixels.keys())
    monkeypatch.setattr('rgbmatrix5x5.RGBMatrix5x5', FakeDevice)
    return FakeDevice
