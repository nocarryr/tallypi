from loguru import logger
import asyncio
from typing import Dict, Tuple, Optional, ClassVar, Iterable

from pydispatch import Dispatcher
from tslumd import Screen, Tally, TallyColor, TallyKey

from .common import TallyConfig, SingleTallyConfig, MultiTallyConfig
from .config import Option

__all__ = ('BaseIO', 'BaseInput', 'BaseOutput')

class BaseIO(Dispatcher):
    """Base class for tally inputs and outputs

    Arguments:
        config: The initial value for :attr:`config`
    """

    config: TallyConfig
    """The output tally configuration
    """

    running: bool
    """``True`` if the display is running
    """

    namespace: ClassVar[str]
    """Dotted name given to subclasses to uniquely identify them

    :class:`BaseInput` and :class:`BaseOutput` have the root namespaces "input"
    and "output" (respectively).

    Subclasses that are meant to be used as inputs or outputs should indicate
    this by adding a ``final=True`` keyword argument to the class definition.

    This tells :class:`BaseIO` to track the subclass and makes it available in
    :meth:`get_class_for_namespace` and :meth:`get_all_namespaces`.


    This is a class attribute and is generated using keyword arguments in the
    subclass definition::

        >>> from tallypi.common import BaseInput

        >>> class AwesomeInputBase(BaseInput, namespace='awesome'):
        >>>     pass

        >>> class AwesomeTCPInput(AwesomeInputBase, namespace='tcp', final=True):
        >>>     pass

        >>> print(AwesomeInputBase.namespace)
        'input.awesome'
        >>> print(AwesomeTCPInput.namespace)
        'input.awesome.tcp'
        >>> print(repr(BaseInput.get_class_for_namespace('input.awesome.tcp')))
        <class '__main__.AwesomeTCPInput'>

    """

    __subclass_map: ClassVar[Dict[str, 'BaseIO']] = {}

    def __init_subclass__(cls, namespace=None, final=False, **kwargs):
        if namespace is None:
            return
        cls_namespace = None
        for basecls in cls.mro():
            if basecls is cls:
                continue
            elif basecls is BaseIO:
                break
            if hasattr(basecls, 'namespace'):
                cls_namespace = f'{basecls.namespace}.{namespace}'
                break
        if cls_namespace is None:
            cls_namespace = namespace
        cls.namespace = cls_namespace
        if final:
            assert cls_namespace not in BaseIO._BaseIO__subclass_map
            BaseIO._BaseIO__subclass_map[cls_namespace] = cls

    def __init__(self, config: TallyConfig):
        self.config = config
        self.running = False

    # @final
    @classmethod
    def get_class_for_namespace(cls, namespace: str) -> 'BaseIO':
        """Get the :class:`BaseIO` subclass matching the given :attr:`namespace`
        """
        if cls is not BaseIO:
            return BaseIO.get_class_for_namespace(namespace)
        return cls.__subclass_map[namespace]

    @classmethod
    def get_all_namespaces(cls, prefix: Optional[str] = '') -> Iterable[str]:
        """Get all currently available :attr:`namespaces <namespace>`
        """
        if cls is not BaseIO:
            return BaseIO.get_all_namespaces(namespace)
        for ns in sorted(cls.__subclass_map.keys()):
            if ns.startswith(prefix):
                yield ns

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        """Get the :class:`.config.Option` definitions required for this object
        """
        return (Option(name='config', type=TallyConfig, required=True),)

    @classmethod
    def create_from_options(cls, values: Dict) -> 'BaseIO':
        """Create an instance using definitions from :meth:`get_init_options`
        and the given values

        Arguments:
            values(dict): A dict of values formatted as the result from the
                :meth:`serialize_options` method
        """
        kw = {}
        for opt in cls.get_init_options():
            if opt.name not in values:
                continue
            kw[opt.name] = opt.validate(values[opt.name])
        return cls(**kw)

    # @final
    @classmethod
    def deserialize(cls, data: Dict) -> 'BaseIO':
        """Deserialize an object using data from the :meth:`serialize` method
        """
        ns = data['namespace']
        opt_vals = data['options']
        subcls = cls.get_class_for_namespace(ns)
        return subcls.create_from_options(opt_vals)

    def serialize(self) -> Dict:
        """Serialize the instance :meth:`values <serialize_options>` and the
        class namespace
        """
        opt_vals = self.serialize_options()
        return {'namespace':self.namespace, 'options':opt_vals}

    def serialize_options(self) -> Dict:
        """Serialize the values defined in :meth:`get_init_options` using
        the :attr:`.config.Option.name` as keys and :meth:`.config.Option.serialize`
        as values.

        This can then be used to create an instance using the
        :meth:`create_from_options` method
        """
        d = {}
        for opt in self.get_init_options():
            value = getattr(self, opt.name)
            if value is None:
                continue
            d[opt.name] = opt.serialize(value)
        return d

    async def open(self):
        """Initalize any necessary device communication
        """
        self.running = True

    async def close(self):
        """Close device communication
        """
        self.running = False

    def screen_matches(self, screen: Screen) -> bool:
        """Determine whether the given screen matches the :attr:`config`

        Uses either :meth:`SingleTallyConfig.matches_screen` or
        :meth:`MultiTallyConfig.matches_screen`, depending on which of the two
        are used for the :class:`BaseIO` subclass
        """
        return self.config.matches_screen(screen)

    def tally_matches(self, tally: Tally) -> bool:
        """Determine whether the given tally matches the :attr:`config`

        Uses either :meth:`SingleTallyConfig.matches` or
        :meth:`MultiTallyConfig.matches`, depending on which of the two are
        used for the :class:`BaseIO` subclass
        """
        return self.config.matches(tally)

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        """Callback for tally updates from :class:`tslumd.tallyobj.Tally`
        """
        pass

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

class BaseInput(BaseIO, namespace='input'):
    """Base class for tally inputs

    Arguments:
        config: The initial value for :attr:`~BaseIO.config`

    :Events:
        .. event:: on_screen_added(instance: BaseInput, screen: Screen)

            Fired when a :class:`~tslumd.tallyobj.Screen` has been added

        .. event:: on_tally_added(tally: Tally)

            Fired when a :class:`~tslumd.tallyobj.Tally` instance has been added

        .. event:: on_tally_updated(tally: Tally)

            Fired when any :class:`~tslumd.tallyobj.Tally` instance
            has been updated
    """

    _events_ = ['on_screen_added', 'on_tally_added', 'on_tally_updated']

    def get_screen(self, screen_index: int) -> Optional[Screen]:
        """Get a :class:`~tslumd.tallyobj.Screen` object by the given index

        If no screen exists, ``None`` is returned
        """
        raise NotImplementedError

    def get_all_screens(self) -> Iterable[Screen]:
        """Get all available :class:`~tslumd.tallyobj.Screen` instances for the
        input
        """
        raise NotImplementedError

    def get_tally(self, tally_key: TallyKey) -> Optional[Tally]:
        """Get a :class:`~tslumd.tallyobj.Tally` object by the given key

        If no tally information exists for this input, ``None`` is returned

        Arguments:
            tally_key (tslumd.common.TallyKey): A tuple of (``screen_index``,
                ``tally_index``) formatted as :attr:`SingleTallyConfig.tally_key`
        """
        raise NotImplementedError

    def get_all_tallies(self, screen_index: Optional[int] == None) -> Iterable[Tally]:
        """Get all available :class:`~tslumd.tallyobj.Tally` instances for the
        input

        Arguments:
            screen_index (int, optional): If present, only include tallies
                within the specified screen
        """
        raise NotImplementedError

    def get_tally_color(self, tally_conf: SingleTallyConfig) -> Optional[TallyColor]:
        """Get the current :class:`~tslumd.common.TallyColor` for the given
        :class:`config specifier <SingleTallyConfig>`

        If the tally state is unknown for does not match the :attr:`~BaseIO.config`,
        ``None`` is returned
        """
        if not self.tally_matches(tally_conf):
            return None
        tally = self.get_tally(tally_conf.tally_key)
        if tally is not None:
            return getattr(tally, tally_conf.tally_type.name)


class BaseOutput(BaseIO, namespace='output'):
    """Base class for tally outputs

    Arguments:
        config: The initial value for :attr:`~BaseIO.config`
    """
    async def bind_to_input(self, inp: BaseInput):
        """Find and set up listeners for matching tallies in the
        :class:`input <BaseInput>`

        Searches for any matching screens in the input and calls
        :meth:`bind_to_screen` for them.
        Also binds to the :event:`BaseInput.on_screen_added` event to listen
        for new screens
        """
        loop = asyncio.get_event_loop()
        coros = set()
        for screen in inp.get_all_screens():
            if not self.screen_matches(screen):
                continue
            coros.add(self.bind_to_screen(inp, screen))
        inp.bind_async(loop, on_screen_added=self.on_screen_added)
        if len(coros):
            await asyncio.gather(*coros)

    async def bind_to_screen(self, inp: BaseInput, screen: Screen):
        """Find and set up listeners for matching tallies in the given
        :class:`input <BaseInput>` and :class:`~tslumd.tallyobj.Screen`

        Searches for any matching tallies in the input and calls
        :meth:`bind_to_tally` for them.
        Also binds to the :event:`BaseInput.on_tally_added` event to listen
        for new tallies from the input

        Arguments:
            inp: The :class:`BaseInput` instance
            screen: The :class:`~tslumd.tallyobj.Screen` within the input
        """
        loop = asyncio.get_event_loop()
        coros = set()
        for tally in inp.get_all_tallies(screen.index):
            if not self.tally_matches(tally):
                continue
            coros.add(self.bind_to_tally(tally))
        screen.bind_async(loop, on_tally_added=self.on_tally_added)
        if len(coros):
            await asyncio.gather(*coros)

    @logger.catch
    async def on_screen_added(self, inp: BaseInput, screen: Screen, **kwargs):
        if self.screen_matches(screen):
            await self.bind_to_screen(inp, screen)

    @logger.catch
    async def on_tally_added(self, tally: Tally, **kwargs):
        if self.tally_matches(tally):
            await self.bind_to_tally(tally)

    async def bind_to_tally(self, tally: Tally):
        """Update current state and subscribe to changes from the given
        :class:`~tslumd.tallyobj.Tally`

        Calls :meth:`~BaseIO.on_receiver_tally_change` and binds tally update
        events to it
        """
        loop = asyncio.get_event_loop()
        tally.bind_async(loop, on_update=self.on_receiver_tally_change)
        props_changed = ('rh_tally', 'txt_tally', 'lh_tally')
        await self.on_receiver_tally_change(tally, props_changed=props_changed)
