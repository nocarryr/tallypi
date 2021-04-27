"""An RGB LED display of 5x5 pixels made by `pimoroni`_

Currently uses the `library`_ maintained by the manufacturer for device
communication


.. _pimoroni: https://shop.pimoroni.com/products/5x5-rgb-matrix-breakout
.. _library: https://github.com/pimoroni/rgbmatrix5x5-python

"""
from loguru import logger
import asyncio
from typing import Dict, Tuple, Iterable, Optional, Any, ClassVar
from rgbmatrix5x5 import RGBMatrix5x5
from tslumd import TallyType, TallyColor, Tally

from tallypi.common import (
    SingleTallyOption, SingleTallyConfig, BaseOutput, Pixel, Rgb,
)
from tallypi.config import Option

__all__ = ('Indicator', 'Matrix')

class Base(BaseOutput, namespace='rgbmatrix5x5'):
    """Base class for RGBMatrix5x5 displays

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        brightness_scale(float, optional): The value to set for
            :attr:`brightness_scale`. Default is 1.0
    """
    color_map: ClassVar[Dict[TallyColor, Rgb]] = {
        TallyColor.OFF: (0, 0, 0),
        TallyColor.RED: (255, 0, 0),
        TallyColor.GREEN: (0, 255, 0),
        TallyColor.AMBER: (0xff, 0xbf, 0),
    }
    """Mapping of :class:`tslumd.common.TallyColor` to tuples of
    :data:`~tallypi.common.Rgb`
    """

    brightness_scale: float
    """A multiplier (from 0.0 to 1.0) used to limit the maximum
        brightness. A value of 1.0 produces the full range while
        0.5 scales to half brightness.
    """

    device: RGBMatrix5x5
    """The :class:`rgbmatrix5x5.RGBMatrix5x5` instance
    """

    def __init__(self, config: SingleTallyConfig, brightness_scale: Optional[float] = 1.0):
        self.device = None
        self.brightness_scale = brightness_scale
        super().__init__(config)

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            SingleTallyOption,
            Option(
                name='brightness_scale', type=float, required=False, default=1.0,
                title='Brightness Scale',
            ),
        )

    async def open(self):
        """Create the :attr:`device` instance and initialize
        """
        if self.running:
            return
        if self.device is None:
            self.device = RGBMatrix5x5()
            # self.device.set_clear_on_exit()
            # self.device.set_brightness(0.8)
        self.running = True

    async def close(self):
        """Close the :attr:`device`
        """
        if not self.running:
            return
        self.running = False
        if self.device is not None:
            self.device.clear()
            self.device.show()
            self.device = None


class Indicator(Base, namespace='Indicator', final=True):
    """Show a solid color for a single :class:`~tslumd.tallyobj.Tally`
    """
    def __init__(self, config: SingleTallyConfig, brightness_scale: Optional[float] = 1.0):
        self._color = None
        self._brightness = None
        super().__init__(config, brightness_scale)

    async def set_color(self, color: TallyColor):
        """Set all pixels of the :attr:`device` to the given color

        The rgb values are retrieved from the :attr:`~.Base.color_map`

        Arguments:
            color: The :class:`~tslumd.common.TallyColor`
        """
        if not self.running:
            return
        rgb = self.color_map[color]
        self.device.set_all(*rgb)
        if self._brightness is None:
            await self.set_brightness(1.0)
        else:
            self.device.show()
        self._color = color

    async def set_brightness(self, brightness: float):
        """Set the brightness of the device

        Arguments:
            brightness: The brightness value from ``0.0`` to ``1.0``
        """
        if not self.running:
            return
        self.device.set_brightness(brightness * self.brightness_scale)
        self.device.show()
        self._brightness = brightness

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        if not self.running:
            return
        if not self.tally_matches(tally):
            return
        color = getattr(tally, self.tally_type.name)
        if color != self._color:
            await self.set_color(color)
        brightness = tally.normalized_brightness
        if brightness != self._brightness:
            await self.set_brightness(brightness)



class Matrix(Base, namespace='Matrix', final=True):
    """Show the status of up to 5 tallies in a matrix

    The tallies are shown in rows beginning with
    :attr:`~tallypi.common.BaseIO.tally_index` and ending with :attr:`end_index`.
    The columns show the individual :class:`~tslumd.common.TallyType` values
    ``('rh_tally', 'txt_tally', 'lh_tally')``
    """
    colors: Dict[Pixel, TallyColor]
    update_queue: asyncio.Queue
    def __init__(self, config: SingleTallyConfig, brightness_scale: Optional[float] = 1.0):
        super().__init__(config, brightness_scale)
        self.colors = {(x,y):TallyColor.OFF for y in range(5) for x in range(5)}
        self.update_queue = asyncio.Queue()
        self._update_task = None

    @property
    def start_index(self) -> int:
        """The first tally index (the :attr:`~tallypi.common.SingleTallyConfig.tally_index`
        of the :attr:`~tallypi.common.BaseIO.config`)
        """
        ix = self.config.tally_index
        if ix is None:
            ix = 0
        return ix

    @property
    def end_index(self) -> int:
        """The last tally index (derived from :attr:`start_index`)
        """
        return self.start_index + 4

    async def open(self):
        if self.running:
            return
        await self.clear_queue()
        await self.queue_update(*self.keys())
        await super().open()
        self.device.set_brightness(self.brightness_scale)
        self._update_task = asyncio.create_task(self.update_loop())

    async def close(self):
        if not self.running:
            return
        await super().close()
        t = self._update_task
        self._update_task = None
        await self.clear_queue()
        if t is not None:
            await self.update_queue.put(None)
            await t
            await self.clear_queue()

    def tally_matches(self, tally: Tally) -> bool:
        if not self.config.matches_screen(tally):
            return False
        if tally.is_broadcast:
            return False
        return self.start_index <= tally.index <= self.end_index

    @logger.catch
    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        changed = set()
        if self.tally_matches(tally):
            y = tally.index - self.tally_index
            for tally_type in TallyType:
                if tally_type == TallyType.no_tally:
                    continue
                x = tally_type.value - 1
                key = (x, y)
                color = getattr(tally, tally_type.name)
                if color == self.get(key):
                    continue
                self[key] = color
                changed.add(key)
        await self.queue_update(*changed)

    async def clear_queue(self):
        while not self.update_queue.empty():
            try:
                await self.update_queue.task_done()
            except ValueError:
                pass

    async def queue_update(self, *keys):
        coros = set()
        for key in keys:
            coros.add(self.update_queue.put(key))
        if len(coros):
            await asyncio.gather(*coros)

    async def update_loop(self):
        def update_pixel(key: Pixel):
            y, x = key
            color = self[key]
            rgb = self.color_map[color]
            self.device.set_pixel(x, y, *rgb)

        while self.running:
            item = await self.update_queue.get()
            if item is None:
                self.update_queue.task_done()
                break
            if self.device is None:
                await asyncio.sleep(.1)
                continue
            # logger.debug(f'update_pixel: {item}')
            update_pixel(item)
            self.update_queue.task_done()
            if self.update_queue.empty():
                # logger.debug('device.show()')
                self.device.show()


    def __getitem__(self, key: Pixel) -> TallyColor:
        return self.colors[key]

    def __setitem__(self, key: Pixel, color: TallyColor):
        self.colors[key] = color

    def get(self, key: Pixel, default: Any = None) -> Optional[TallyColor]:
        return self.colors.get(key, default)

    def keys(self) -> Iterable[Pixel]:
        yield from self

    def values(self) -> Iterable[TallyColor]:
        for key in self:
            yield self[key]

    def items(self) -> Iterable[Tuple[Pixel, TallyColor]]:
        for key in self:
            yield key, self[key]

    def __iter__(self) -> Iterable[Pixel]:
        yield from sorted(self.colors.keys())
