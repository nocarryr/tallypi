from loguru import logger
from typing import Dict, Tuple
from rgbmatrix5x5 import RGBMatrix5x5
from tslumd import TallyType, TallyColor, Tally

class Indicator:
    color_map: Dict[TallyColor, Tuple] = {
        TallyColor.OFF: (0, 0, 0),
        TallyColor.RED: (255, 0, 0),
        TallyColor.GREEN: (0, 255, 0),
        TallyColor.AMBER: (255, 255, 0),
    }
    def __init__(self, tally_index: int, tally_type: TallyType):
        self.tally_index = tally_index
        self.tally_type = tally_type
        self._color = None
        self._brightness = None
        self.device = None

    async def open(self):
        if self.device is None:
            self.device = RGBMatrix5x5()
            # self.device.set_clear_on_exit()
            # self.device.set_brightness(0.8)

    async def close(self):
        if self.device is not None:
            self.device.clear()
            self.device.show()
            self.device = None

    async def set_color(self, color: TallyColor):
        rgb = self.color_map[color]
        self.device.set_all(*rgb)
        self.device.show()
        self._color = color

    async def set_brightness(self, brightness: float):
        self.device.set_brightness(brightness)
        self.device.show()
        self._brightness = brightness

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        if tally.index != self.tally_index:
            return
        color = getattr(tally, self.tally_type.name)
        if color != self._color:
            await self.set_color(color)
        brightness = tally.brightness / 4
        if brightness != self._brightness:
            await self.set_brightness(brightness)

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()
