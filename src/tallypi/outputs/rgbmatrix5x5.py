from loguru import logger
import asyncio
from typing import Dict, Tuple, Iterable, Optional, Any
from rgbmatrix5x5 import RGBMatrix5x5
from tslumd import TallyType, TallyColor, Tally

Pixel = Tuple[int, int]

class Base:
    color_map: Dict[TallyColor, Tuple] = {
        TallyColor.OFF: (0, 0, 0),
        TallyColor.RED: (255, 0, 0),
        TallyColor.GREEN: (0, 255, 0),
        TallyColor.AMBER: (255, 255, 0),
    }
    device: RGBMatrix5x5
    running: bool
    def __init__(self, *args):
        self.device = None
        self.running = False

    async def open(self):
        if self.running:
            return
        if self.device is None:
            self.device = RGBMatrix5x5()
            # self.device.set_clear_on_exit()
            # self.device.set_brightness(0.8)
        self.running = True

    async def close(self):
        if not self.running:
            return
        self.running = False
        if self.device is not None:
            self.device.clear()
            self.device.show()
            self.device = None

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        pass

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

class Indicator(Base):
    tally_index: int
    tally_type: TallyType
    def __init__(self, tally_index: int, tally_type: TallyType):
        self.tally_index = tally_index
        self.tally_type = tally_type
        self._color = None
        self._brightness = None
        super().__init__()

    async def set_color(self, color: TallyColor):
        if not self.running:
            return
        rgb = self.color_map[color]
        self.device.set_all(*rgb)
        self.device.show()
        self._color = color

    async def set_brightness(self, brightness: float):
        if not self.running:
            return
        self.device.set_brightness(brightness)
        self.device.show()
        self._brightness = brightness

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        if not self.running:
            return
        if tally.index != self.tally_index:
            return
        color = getattr(tally, self.tally_type.name)
        if color != self._color:
            await self.set_color(color)
        brightness = tally.brightness / 4
        if brightness != self._brightness:
            await self.set_brightness(brightness)



class Matrix(Base):
    start_index: int
    end_index: int
    colors: Dict[Pixel, TallyColor]
    update_queue: asyncio.Queue
    def __init__(self, start_index: int):
        self.start_index = start_index
        self.end_index = start_index + 5
        self.colors = {(x,y):TallyColor.OFF for y in range(5) for x in range(5)}
        self.update_queue = asyncio.Queue()
        self._update_task = None
        super().__init__()

    async def open(self):
        if self.running:
            return
        await self.clear_queue()
        await self.queue_update(*self.keys())
        await super().open()
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

    @logger.catch
    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        changed = set()
        if self.start_index <= tally.index <= self.end_index:
            y = tally.index - self.start_index
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