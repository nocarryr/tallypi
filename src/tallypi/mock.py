import os
import asyncio
from typing import Tuple
from loguru import logger

MOCK_MODNAMES = set()

def get_mock_modnames():
    global MOCK_MODNAMES
    modnames = os.environ.get('TALLYPI_MOCK')
    if modnames is not None:
        modnames = modnames.split(':')
    else:
        modnames = []
    MOCK_MODNAMES |= set(modnames)

MOCKED_MODULES = {}

def mock_gpio():
    import gpiozero
    from gpiozero import Device
    from gpiozero.pins.mock import MockFactory, MockPWMPin

    class LoggingMockPWMPin(MockPWMPin):
        def _set_state(self, value):
            super()._set_state(value)
            logger.debug(f'{self}._set_state({value})')
        def _set_frequency(self, value):
            super()._set_frequency(value)
            if value is not None:
                logger.debug(f'{self}._set_frequency({value})')


    Device.pin_factory = MockFactory()
    Device.pin_factory.pin_class = LoggingMockPWMPin
    return gpiozero

def mock_rgbmatrix5x5():
    import rgbmatrix5x5
    from rgbmatrix5x5 import RGBMatrix5x5 as OrigDevice

    Pixel = Tuple[int, int]
    Rgb = Tuple[int, int, int]

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
            # logger.debug(f'rgbmatrix5x5.brightness = {value}')
        def set_brightness(self, brightness):
            logger.debug(f'rgbmatrix5x5.set_brightness({brightness})')
            self.brightness = brightness
        def set_pixel(self, x, y, r, g, b, brightness=1.0):
            key = (x, y)
            rgb = (r, g, b)
            self[key] = rgb
            logger.debug(f'rgbmatrix5x5[{key}] = {rgb}')
            self.brightness = 1.0
        def set_all(self, r, g, b, brightness=1.0):
            rgb = (r, g, b)
            logger.debug(f'rgbmatrix5x5.all = {rgb}')
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

    if not hasattr(rgbmatrix5x5.is31fl3731, '_OrigRGBMatrix5x5'):
        rgbmatrix5x5.is31fl3731._OrigRGBMatrix5x5 = OrigDevice
        rgbmatrix5x5.is31fl3731.RGBMatrix5x5 = FakeDevice

    if not hasattr(rgbmatrix5x5, '_OrigRGBMatrix5x5'):
        rgbmatrix5x5._OrigRGBMatrix5x5 = OrigDevice
        rgbmatrix5x5.RGBMatrix5x5 = FakeDevice

    return rgbmatrix5x5

def mock():
    get_mock_modnames()
    for modname in MOCK_MODNAMES:
        if 'gpio' in modname.lower() and 'gpio' not in MOCKED_MODULES:
            logger.info('Mocking gpio...')
            MOCKED_MODULES['gpio'] = mock_gpio()
        elif 'rgbmatrix' in modname.lower() and 'rgbmatrix5x5' not in MOCKED_MODULES:
            logger.info('Mocking rgbmatrix5x5...')
            MOCKED_MODULES['rgbmatrix5x5'] = mock_rgbmatrix5x5()
