from loguru import logger

import asyncio
from pathlib import Path
from typing import Dict, Iterable, Optional, Any

from pydispatch import Dispatcher

from tallypi.common import BaseIO, BaseInput, BaseOutput
from tallypi.config import Config

__all__ = ('Manager',)

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
    """Container for :class:`~.common.BaseOutput` instances
    """
    objects: Dict[str, BaseOutput]

    async def bind_to_input(self, inp: BaseInput, outp: BaseOutput):
        await outp.bind_to_input(inp)

    async def bind_all_to_input(self, inp: BaseInput):
        """Attach all :class:`outputs <.common.BaseOutput>` to the given
        :class:`input <.common.BaseInput>`

        Calls :meth:`.common.BaseOutput.bind_to_input` for each output instance
        """
        coros = set()
        for outp in self.values():
            coros.add(self.bind_to_input(inp=inp, outp=outp))
        if len(coros):
            await asyncio.gather(*coros)


class Manager:
    """Manager for tally inputs and outputs
    """
    inputs: Inputs #: All configured inputs
    outputs: Outputs #: All configured outputs
    config: Config #: Configuration storage
    running: bool
    config_read: bool
    readonly_override: 'ReadonlyOverride'
    """A context manager that can temporarily disable :attr:`readonly` mode

    For details, see the :class:`ReadonlyOverride` class
    """
    config_write_evt: asyncio.Event
    """An :class:`asyncio.events.Event` that is set when config changes are
    written
    """
    _events_ = ['config_written']
    def __init__(self,
                 config_filename: Optional[Path] = Config.DEFAULT_FILENAME,
                 readonly: Optional[bool] = False):

        self.__readonly = readonly
        self.loop = asyncio.get_event_loop()
        self.inputs = Inputs()
        self.outputs = Outputs()
        self.inputs.bind_async(self.loop,
            object_added=self.on_input_added,
            update=self.on_io_update,
        )
        self.outputs.bind_async(self.loop,
            object_added=self.on_output_added,
            update=self.on_io_update,
        )
        self.config = Config(filename=config_filename)
        self.running = False
        self.config_read = False
        self.config_write_evt = asyncio.Event()
        self.readonly_override = ReadonlyOverride(self.config_write_evt)

    @property
    def readonly(self) -> bool:
        """If ``True`` config changes are not written to disk (unless overridden)

        This is the immutable "readonly" state
        """
        return self.__readonly

    @property
    def _readonly(self) -> bool:
        """``True`` if :attr:`readonly` is ``True`` and :attr:`readonly_override`
        is ``False``

        (if "readonly" and not overridden)
        """
        if not self.__readonly:
            return False
        if self.readonly_override:
            return False
        return True

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

    @logger.catch
    async def on_input_added(self, key: str, obj: BaseInput, **kwargs):
        await self.outputs.bind_all_to_input(obj)

    @logger.catch
    async def on_output_added(self, key: str, obj: BaseOutput, **kwargs):
        coros = set()
        for inp in self.inputs.values():
            coros.add(obj.bind_to_input(inp))
        if len(coros):
            await asyncio.gather(*coros)

    async def on_io_update(self, *args, **kwargs):
        async with self.readonly_override.state_lock:
            if self._readonly:
                return
        await self.write_config()

    async def write_config(self):
        """Write the current configuration to :attr:`config` using
        :meth:`~IOContainer.serialize` on :attr:`inputs` and :attr:`outputs`
        """
        async with self.readonly_override.state_lock:
            if self._readonly:
                return
            data = {
                'inputs':self.inputs.serialize(),
                'outputs':self.outputs.serialize(),
            }
            self.config.write(data)
            self.config_write_evt.set()

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

class ReadonlyOverride:
    """An :term:`asynchronous context manager` used to override
    the :attr:`~Manager.readonly` mode of :class:`Manager`

    While the context is acquired, the :class:`Manager` is temporarily allowed
    to write config changes. The :attr:`config_write_evt` event is returned
    so it will be available as the *as* clause of the :keyword:`async with`
    statement::

        async with manager.readonly_override as config_write_evt:
            await manager.remove_input('foo')
            await config_write_evt.wait()

    This allows code to :keyword:`await` for config changes to be written before
    exiting the :keyword:`async with` context.
    """

    config_write_evt: asyncio.Event
    """Alias for :attr:`Manager.config_write_evt`
    """

    override: bool
    """``True`` if currently being overridden
    """

    state_lock: asyncio.Lock
    """A lock used while changing states

    (during :meth:`acquire` and :meth:`release` stages)
    """
    def __init__(self, config_write_evt: asyncio.Event):
        self.config_write_evt = config_write_evt
        self.override = False
        self._lock = asyncio.Lock()
        self.state_lock = asyncio.Lock()

    def locked(self):
        """``True`` if the context is acquired or if :attr:`state_lock` is locked
        """
        return self._lock.locked() or self.state_lock.locked()

    def __bool__(self):
        return self.override

    async def acquire(self):
        """Acquire the context and set :attr:`override` to ``True``

        Also clears :attr:`config_write_evt` so it can be *awaited*
        """
        async with self.state_lock:
            await self._lock.acquire()
            self.config_write_evt.clear()
            self.override = True

    async def release(self):
        """Set :attr:`override` to ``False`` and exit the context
        """
        async with self.state_lock:
            self.override = False
            self._lock.release()

    async def __aenter__(self):
        await self.acquire()
        return self.config_write_evt

    async def __aexit__(self, *args):
        await self.release()

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
