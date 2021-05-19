import asyncio
import pytest

from pydispatch import Dispatcher
from tallypi.utils import SetProperty

@pytest.mark.asyncio
async def test_set_property(faker):
    loop = asyncio.get_event_loop()

    class Emitter(Dispatcher):
        foo = SetProperty()

    class Listener:
        def __init__(self):
            self.queue = asyncio.Queue()
        async def callback(self, instance, value, **kwargs):
            await self.queue.put(value)
        async def get(self, timeout=1):
            r = await asyncio.wait_for(self.queue.get(), timeout)
            self.queue.task_done()
            return r
        def empty(self):
            return self.queue.empty()

    emitter = Emitter()
    listener = Listener()
    emitter.bind_async(loop, foo=listener.callback)

    expected = set()

    for _ in range(20):
        item = faker.pystr()
        emitter.foo.add(item)
        expected.add(item)
        value = await listener.get()
        assert value == expected

    while len(expected):
        item = expected.pop()
        emitter.foo.discard(item)
        value = await listener.get()
        assert value == expected

    for _ in range(20):
        s = faker.pyset()
        expected |= s
        emitter.foo |= s
        value = await listener.get()
        assert value == expected

    expected.clear()
    emitter.foo.clear()
    value = await listener.get()
    assert value == expected

    emitter.foo.clear()
    await asyncio.sleep(.1)
    assert listener.empty()

    expected |= set(range(10))
    emitter.foo = expected
    value = await listener.get()
    assert value == expected

    emitter.foo.add(0)
    await asyncio.sleep(.1)
    assert listener.empty()

    even_nums = set([v for v in expected if v % 2 == 0])
    odd_nums = expected - even_nums

    expected &= odd_nums
    emitter.foo &= odd_nums
    value = await listener.get()
    assert value == expected

    with pytest.raises(KeyError):
        emitter.foo.remove(2)

    emitter.foo.discard(2)
    await asyncio.sleep(.1)
    assert listener.empty()

    expected.remove(1)
    emitter.foo.remove(1)
    value = await listener.get()
    assert value == expected

    item = emitter.foo.pop()
    expected.remove(item)
    value = await listener.get()
    assert value == expected
