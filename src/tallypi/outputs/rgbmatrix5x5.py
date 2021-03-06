"""An RGB LED display of 5x5 pixels made by `pimoroni`_

Currently uses the `library`_ maintained by the manufacturer for device
communication


.. _pimoroni: https://shop.pimoroni.com/products/5x5-rgb-matrix-breakout
.. _library: https://github.com/pimoroni/rgbmatrix5x5-python

"""
from loguru import logger
import asyncio
from typing import Dict, List, Tuple, Set, Iterable, Optional, Any, ClassVar, Union
import rgbmatrix5x5
from tslumd import TallyType, TallyColor, Tally, TallyKey

from tallypi.common import (
    SingleTallyOption, SingleTallyConfig, MultiTallyConfig, Pixel, Rgb,
)
from tallypi.baseio import BaseOutput
from tallypi.config import Option

__all__ = ('Indicator', 'Matrix')

TallyTypeKey = Tuple[int, int, TallyType]

class Base(BaseOutput, namespace='rgbmatrix5x5'):
    """Base class for RGBMatrix5x5 displays

    Arguments:
        config(SingleTallyConfig): The initial value for
            :attr:`~tallypi.baseio.BaseIO.config`
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

    device: 'rgbmatrix5x5.RGBMatrix5x5'
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
            self.device = rgbmatrix5x5.RGBMatrix5x5()
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

    async def on_receiver_tally_change(self, tally: Tally, props_changed: Set[str], **kwargs):
        if not self.running:
            return
        if not self.tally_matches(tally):
            return
        color = self.get_merged_tally(tally, self.config.tally_type)
        if color != self._color:
            await self.set_color(color)
        brightness = tally.normalized_brightness
        if brightness != self._brightness:
            await self.set_brightness(brightness)



class Matrix(Base, namespace='Matrix', final=True):
    """Show the status of up to 5 tallies in a matrix

    The tallies are shown in 5 rows beginning with the
    :attr:`~.common.SingleTallyConfig.tally_index`
    of the :attr:`~.baseio.BaseIO.config`

    The columns show the individual :class:`~tslumd.common.TallyType` values
    ``('rh_tally', 'txt_tally', 'lh_tally')``
    """
    colors: Dict[Pixel, TallyColor]
    update_queue: asyncio.Queue
    multi_config: MultiTallyConfig
    tally_type_map: Dict[TallyTypeKey, Pixel]
    def __init__(self, config: SingleTallyConfig, brightness_scale: Optional[float] = 1.0):
        super().__init__(config, brightness_scale)
        self.colors = {(x,y):TallyColor.OFF for y in range(5) for x in range(5)}
        self.tally_type_map = {}
        self.build_multi_config()
        self.update_queue = asyncio.Queue()
        self._update_task = None

    def build_multi_config(self) -> MultiTallyConfig:
        self.tally_type_map.clear()
        tconfs = []
        scr = self.config.screen_index
        start_index = self.config.tally_index
        for i in range(5):
            tally_index = start_index + i
            for j, ttype in enumerate(TallyType.all()):
                pixel = (j, i)
                tconf = SingleTallyConfig(
                    screen_index=scr,
                    tally_index=tally_index,
                    tally_type=ttype
                )
                tconfs.append(tconf)
                key = tconf.tally_key + (ttype,)
                self.tally_type_map[key] = pixel
        self.multi_config = MultiTallyConfig(tallies=tconfs)

    async def open(self):
        if self.running:
            return
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
        self.clear_queue()
        if t is not None:
            await self.update_queue.put(None)
            await t
            self.clear_queue()

    def tally_matches(
        self,
        tally: Tally,
        tally_type: Optional[TallyType] = TallyType.all_tally,
        return_matched: Optional[bool] = False
    ) -> Union[bool, SingleTallyConfig]:
        return self.multi_config.matches(tally, tally_type, return_matched)

    @logger.catch
    async def on_receiver_tally_change(self, tally: Tally, props_changed: Set[str], **kwargs):
        changed = set()
        for prop in props_changed:
            if prop not in TallyType.__members__:
                continue
            ttype = TallyType.from_str(prop)
            pixel = self.tally_type_map.get(tally.id + (ttype,))
            color = self.get_merged_tally(tally, ttype)
            if color == self.get(pixel):
                continue
            self[pixel] = color
            changed.add(pixel)
        await self.queue_update(*changed)

    def clear_queue(self):
        while not self.update_queue.empty():
            try:
                self.update_queue.task_done()
            except ValueError:
                break

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
