from loguru import logger

import asyncio
from pathlib import Path
from typing import Dict, Iterable, Optional, Any

from pydispatch import Dispatcher

from tallypi.common import BaseIO, BaseInput, BaseOutput
from tallypi.config import Config

class IOContainer(Dispatcher):
    """Container for :class:`~.common.BaseIO` instances

    :Events:
        .. event:: object_added(key: str, obj: tallypi.common.BaseIO)

            Fired when an instance is added by either :meth:`deserialize` or
            :meth:`add`

        .. event:: object_removed(key: str, obj: tallypi.common.BaseIO)

            Fired when an instance has been removed

        .. event:: update()

            Fired when any change happens that requires a config update
    """
    objects: Dict[str, BaseIO]
    running: bool
    _events_ = [
        'object_added', 'object_removed', 'update',
    ]
    def __init__(self):
        self.objects = {}
        self.running = False

    async def open(self):
        """Call the :meth:`~.common.BaseIO.open` method on all instances
        """
        if self.running:
            return
        logger.info(f'{self.__class__} starting...')
        self.running = True
        coros = set()
        for obj in self.values():
            coros.add(obj.open())
        if len(coros):
            await asyncio.gather(*coros)
        logger.info(f'{self.__class__} running')

    async def close(self):
        """Call the :meth:`~.common.BaseIO.close` method on all instances
        """
        if not self.running:
            return
        logger.info(f'{self.__class__} stopping...')
        self.running = False
        coros = set()
        for obj in self.values():
            coros.add(obj.close())
        if len(coros):
            await asyncio.gather(*coros)
        logger.info(f'{self.__class__} stopped...')

    async def add(self, obj: BaseIO, key: Optional[str] = None):
        """Add an instance to the container

        Arguments:
            obj(BaseIO): The instance to add
            key(str, optional): The key for the instance. If not given, one will
                be created by :meth:`key_for_object`
        """
        if key is None:
            key = self.key_for_object(obj)
        self.objects[key] = obj
        if self.running:
            await obj.open()
        self.emit('object_added', key, obj)
        self.emit('update')

    async def replace(self, key: str, obj: BaseIO):
        """Replace an instance by the given key
        """
        old = self.objects[key]
        await old.close()
        del self.objects[key]
        self.emit('object_removed', key, old)
        await self.add(obj, key)

    async def remove(self, key: str):
        """Remove an instance by the given key
        """
        obj = self[key]
        del self.objects[key]
        await obj.close()
        self.emit('object_removed', key, obj)
        self.emit('update')

    def key_for_object(self, obj: BaseIO):
        """Create a unique key based on the class namespace
        """
        ns = '.'.join(obj.namespace.split('.')[1:])
        ix = 0
        key = f'{ns}:{ix:03d}'
        while key in self:
            ix += 1
            key = f'{ns}:{ix:03d}'
        return key

    async def deserialize(self, data: Dict):
        """Deserialize instances from config data using
        :meth:`.common.BaseIO.deserialize`
        """
        coros = set()
        for key, val in data.items():
            obj = BaseIO.deserialize(val)
            self.objects[key] = obj
            if self.running:
                coros.add(obj.open())
            self.emit('object_added', key, obj)
        if len(coros):
            await asyncio.gather(*coros)

    def serialize(self) -> Dict:
        """Serialize instances to store in the config using
        :meth:`.common.BaseIO.serialize`
        """
        data = {}
        for key, obj in self.items():
            data[key] = obj.serialize()
        return data

    def __getitem__(self, key: str) -> BaseIO:
        return self.objects[key]

    def get(self, key: str, default: Optional[Any] = None) -> Optional[BaseIO]:
        return self.objects.get(key, default)

    def __iter__(self) -> Iterable[str]:
        yield from sorted(self.objects.keys())

    def keys(self):
        yield from self

    def values(self):
        for key in self:
            yield self[key]

    def items(self):
        for key in self:
            yield key, self[key]

    def __contains__(self, key):
        return key in self.objects

    def __len__(self):
        return len(self.objects)

    def __repr__(self):
        return f'<{self.__class__.__name__}: {self}>'

    def __str__(self):
        return str(self.objects)

class Inputs(IOContainer):
    """Container for :class:`~.common.BaseInput` instances

    :Events:
        .. event:: on_tally_added(tally: tslumd.tallyobj.Tally)

            Fired when the :event:`.common.BaseInput.on_tally_added`
            event received from any of the inputs in the container

        .. event:: on_tally_updated(tally: tslumd.tallyobj.Tally)

            Fired when the :event:`.common.BaseInput.on_tally_updated`
            event received from any of the inputs in the container
    """
    objects: Dict[str, BaseInput]
    _events_ = ['on_tally_added', 'on_tally_updated']
    async def add(self, obj: BaseInput, key: Optional[str] = None):
        await super().add(obj, key)
        obj.bind(
            on_tally_added=self._on_input_tally_added,
            on_tally_updated=self._on_input_tally_updated,
        )
    async def deserialize(self, data: Dict):
        await super().deserialize(data)
        for obj in self.values():
            obj.bind(
                on_tally_added=self._on_input_tally_added,
                on_tally_updated=self._on_input_tally_updated,
            )
    def _on_input_tally_added(self, *args, **kwargs):
        self.emit('on_tally_added', *args, **kwargs)
    def _on_input_tally_updated(self, *args, **kwargs):
        self.emit('on_tally_updated', *args, **kwargs)

class Outputs(IOContainer):
    objects: Dict[str, BaseOutput]


class Manager:
    """Manager for tally inputs and outputs
    """
    inputs: Inputs #: All configured inputs
    outputs: Outputs #: All configured outputs
    config: Config #: Configuration storage
    running: bool
    config_read: bool
    def __init__(self, config_filename: Optional[Path] = Config.DEFAULT_FILENAME):
        self.loop = asyncio.get_event_loop()
        self.inputs = Inputs()
        self.outputs = Outputs()
        self.outputs.bind(object_added=self.on_output_added)
        self.inputs.bind_async(self.loop, update=self.on_io_update)
        self.outputs.bind_async(self.loop, update=self.on_io_update)
        self.config = Config(filename=config_filename)
        self.running = False
        self.config_read = False

    async def open(self):
        """Opens all inputs and outputs

        Reads configuration data if necessary with a call to :meth:`read_config`,
        then calls :meth:`~IOContainer.open` on the :attr:`inputs` and :attr:`outputs`
        """
        if self.running:
            return
        logger.info('Manager starting...')
        self.running = True
        if not self.config_read:
            await self.read_config()
        await self.inputs.open()
        await self.outputs.open()
        logger.success('Manager running')

    async def close(self):
        """Closes all inputs and outputs
        """
        if not self.running:
            return
        logger.info('Manager stopping...')
        self.running = False
        await self.outputs.close()
        await self.inputs.close()
        logger.success('Manager stopped')

    async def add_input(self, obj: BaseInput):
        """Add an input

        Shortcut for calling :meth:`IOContainer.add` on :attr:`inputs`
        """
        await self.inputs.add(obj)

    async def add_output(self, obj: BaseOutput):
        """Add an input

        Shortcut for calling :meth:`IOContainer.add` on :attr:`outputs`
        """
        await self.outputs.add(obj)

    async def read_config(self):
        """Read configuration stored in :attr:`config` and
        :meth:`~IOContainer.deserialize` the :attr:`inputs` and :attr:`outputs`
        """
        data = self.config.read()
        await self.inputs.deserialize(data.get('inputs', {}))
        await self.outputs.deserialize(data.get('outputs', {}))
        self.config_read = True

    def on_output_added(self, key, obj, **kwargs):
        # Binding all input events to all outputs.
        # Not efficient and needs to be minimized
        self.inputs.bind_async(self.loop,
            on_tally_added=obj.on_receiver_tally_change,
            on_tally_updated=obj.on_receiver_tally_change,
        )

    async def on_io_update(self, *args, **kwargs):
        await self.write_config()

    async def write_config(self):
        """Write the current configuration to :attr:`config` using
        :meth:`~IOContainer.serialize` on :attr:`inputs` and :attr:`outputs`
        """
        data = {
            'inputs':self.inputs.serialize(),
            'outputs':self.outputs.serialize(),
        }
        self.config.write(data)

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    mgr = Manager()
    loop.run_until_complete(mgr.open())
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        loop.run_until_complete(mgr.close())
    finally:
        loop.run_until_complete(mgr.close())
        loop.close()
