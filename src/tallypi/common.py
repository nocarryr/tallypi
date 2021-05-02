from loguru import logger
import asyncio
import dataclasses
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, ClassVar, Iterable, Union

from pydispatch import Dispatcher
from tslumd import Screen, Tally, TallyColor, TallyType, TallyKey

from .config import Option, ListOption

__all__ = (
    'Pixel', 'Rgb', 'BaseInput', 'BaseOutput',
    'TallyConfig', 'SingleTallyConfig', 'MultiTallyConfig',
)

Pixel = Tuple[int, int] #: A tuple of ``(x, y)`` coordinates
Rgb = Tuple[int, int, int] #: A color tuple of ``(r, g, b)``

TallyOrTallyConfig = Union[Tally, 'SingleTallyConfig']
TallyOrMultiTallyConfig = Union[TallyOrTallyConfig, 'MultiTallyConfig']

def normalize_screen(obj: Union[TallyOrMultiTallyConfig, int]) -> Union[None, int]:
    if isinstance(obj, int):
        screen = obj
        if obj == 0xffff:
            screen = None
    elif isinstance(obj, Tally):
        screen = obj.screen.index
        if obj.screen.is_broadcast:
            screen = None
    elif isinstance(obj, Screen):
        screen = obj.index
        if obj.is_broadcast:
            screen = None
    else:
        screen = obj.screen_index
        if obj.is_broadcast_screen:
            screen = None
    return screen

def normalize_tally_index(obj: Union[TallyOrTallyConfig, int]) -> Union[None, int]:
    if isinstance(obj, int):
        ix = obj
        if obj == 0xffff:
            ix = None
    elif isinstance(obj, Tally):
        ix = obj.index
        if obj.is_broadcast:
            ix = None
    else:
        ix = obj.tally_index
        if obj.is_broadcast_tally:
            ix = None
    return ix

@dataclass
class TallyConfig:
    """Configuration data for tally assignment
    """

    def to_dict(self) -> Dict:
        """Serialize the config data
        """
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> 'TallyConfig':
        """Create a :class:`TallyConfig` from serialized data
        """
        return cls(**d)


@dataclass
class SingleTallyConfig(TallyConfig):
    """Configuration for a single tally
    """

    tally_index: int
    """The tally index ranging from 0 to 65534 (``0xfffe``)

    The special value of 65535 (``0xffff``) is used as a "broadcast" address
    """

    tally_type: TallyType = TallyType.no_tally
    """The :class:`~tslumd.common.TallyType`
    """

    screen_index: Optional[int] = None
    """The :attr:`~tslumd.tallyobj.Screen.index` of the
    :class:`tslumd.tallyobj.Screen` the tally belongs to,
    ranging from 0 to 65534 (``0xfffe``)

    If not provided (or ``None``), the tally is assumed to belong to *any* screen.
    This is also the case if the value is 65535 (``0xffff``), defined as the
    "broadcast" screen address.
    """

    name: Optional[str] = ''
    """User-defined name for the tally
    """

    @property
    def tally_key(self) -> TallyKey:
        """A tuple of (:attr:`screen_index`, :attr:`tally_index`) matching the
        format used for :attr:`tslumd.tallyobj.Tally.id`

        If :attr:`screen_index` or :attr:`tally_index` is ``None``, they are set
        to 65535 (``0xffff``)
        """
        scr, tly = self.screen_index, self.tally_index
        if scr is None:
            scr = 0xffff
        if tly is None:
            tly = 0xffff
        return (scr, tly)

    @property
    def is_broadcast_screen(self) -> bool:
        """``True`` if :attr:`screen_index` is set to ``None`` or the "broadcast"
        address of 65535 (``0xffff``)
        """
        return self.screen_index in (None, 0xffff)

    @property
    def is_broadcast_tally(self) -> bool:
        """``True`` if :attr:`tally_index` is set to ``None`` or the "broadcast"
        address of 65535 (``0xffff``)
        """
        return self.tally_index in (None, 0xffff)

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        tt_choices = tuple((tt.name for tt in TallyType))
        return (
            Option(name='tally_index', type=int, required=True, title='Index'),
            Option(
                name='tally_type', type=str, required=True, choices=tt_choices,
                serialize_cb=lambda x: x.name,
                validate_cb=lambda x: getattr(TallyType, x),
                title='TallyType',
            ),
            Option(name='screen_index', type=int, required=False, title='Screen'),
            Option(name='name', type=str, required=False, default='', title='Name'),
        )

    def matches(self, other: TallyOrTallyConfig) -> bool:
        """Determine whether the given tally argument matches this one

        For :attr:`screen_index` the :meth:`matches_screen` method is used

        Arguments:
            other: Either another :class:`SingleTallyConfig` or a
                :class:`tslumd.tallyobj.Tally` instance
        """
        if not self.matches_screen(other):
            return False
        if isinstance(other, SingleTallyConfig):
            if self.tally_type != other.tally_type:
                return False
        self_ix = normalize_tally_index(self)
        oth_ix = normalize_tally_index(other)
        if None in (self_ix, oth_ix):
            return True
        return self_ix == oth_ix

    def matches_screen(self, other: Union[TallyOrMultiTallyConfig, int]) -> bool:
        """Determine whether the :attr:`screen_index` matches the given argument

        For :class:`tslumd.tallyobj.Tally`, the
        :attr:`screen's <tslumd.tallyobj.Tally.screen>`
        :attr:`~tslumd.tallyobj.Screen.is_broadcast` value is taken into account
        as well as cases where :attr:`screen_index` is set to ``None``

        Arguments:
            other: A :class:`SingleTallyConfig`, :class:`MultiTallyConfig`,
                :class:`tslumd.tallyobj.Tally` or :class:`int`
        """
        if self.is_broadcast_screen:
            return True
        self_screen = normalize_screen(self)
        oth_screen = normalize_screen(other)
        if None not in (self_screen, oth_screen):
            return self_screen == oth_screen
        return True

    def to_dict(self) -> Dict:
        d = super().to_dict()
        d['tally_type'] = d['tally_type'].name
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'SingleTallyConfig':
        kw = d.copy()
        if not isinstance(kw['tally_type'], TallyType):
            kw['tally_type'] = getattr(TallyType, kw['tally_type'])
        return super().from_dict(kw)

    def create_screen(self) -> Screen:
        """Create a :class:`tslumd.tallyobj.Screen` with the :attr:`screen_index`
        of this object
        """
        if self.screen_index is None:
            return Screen.broadcast()
        return Screen(self.screen_index)

    def create_tally(self, screen: Optional[Screen] = None) -> Tuple[Screen, Tally]:
        """Create a :class:`tslumd.tallyobj.Tally` from this instance

        Arguments:
            screen (tslumd.tallyobj.Screen, optional): The parent
                :attr:`tslumd.tallyobj.Tally.screen` to add the tally to.
                If not provided, one will be created

        Returns
        -------
        screen : tslumd.tallyobj.Screen
            The parent screen that was either created or given as an argument
        tally : tslumd.tallyobj.Tally
            The tally object
        """
        if screen is None:
            screen = self.create_screen()
        if self.tally_index is None:
            tally = screen.broadcast_tally()
        else:
            tally = screen.add_tally(self.screen_index)
        return screen, tally


@dataclass
class MultiTallyConfig(TallyConfig):
    """Configuration for multiple tallies
    """
    tallies: List[SingleTallyConfig] = field(default_factory=list)
    """A list of :class:`SingleTallyConfig` instances
    """

    screen_index: Optional[int] = None
    """The :attr:`~tslumd.tallyobj.Screen.index` of the
    :class:`tslumd.tallyobj.Screen` for the configuration
    ranging from 0 to 65534 (``0xfffe``)

    This only takes effect if :attr:`allow_all` is ``True`` and provides a method
    of filtering the tally assignments to a single :class:`tslumd.tallyobj.Screen`
    if desired.

    If not provided (or ``None``), all tallies within all screens are considered
    to be members of the configuration. This is also the case if the value
    is 65535 (``0xffff``), defined as the "broadcast" screen address.
    """

    allow_all: bool = False
    """If ``True``, all possible tally configurations exist within this instance

    Tallies can still be limited to a specific :attr:`screen_index` if desired
    """

    name: Optional[str] = ''
    """User-defined name for the tally config
    """

    @property
    def is_broadcast_screen(self) -> bool:
        """``True`` if :attr:`screen_index` is set to ``None`` or the "broadcast"
        address of 65535 (``0xffff``)

        Note:
            Behavior is undefined if :attr:`allow_all` is ``False``
        """
        if not self.allow_all:
            return True
        return self.screen_index in (None, 0xffff)

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            ListOption(
                name='tallies', type=SingleTallyConfig, required=False,
                sub_options=SingleTallyConfig.get_init_options(),
                title='Tallies',
            ),
            Option(name='screen_index', type=int, required=False, title='Screen'),
            Option(
                name='allow_all', type=bool, required=False, default=False,
                title='Allow All',
            ),
            Option(name='name', type=str, required=False, default='', title='Name'),
        )

    def matches(self, tally: Union[SingleTallyConfig, Tally]) -> bool:
        """Alias for :meth:`contains`
        """
        return self.contains(tally)

    def matches_screen(self, other: Union[TallyOrMultiTallyConfig, int]) -> bool:
        """Determine whether the :attr:`screen_index` matches the given argument

        For :class:`tslumd.tallyobj.Tally`, the
        :attr:`screen's <tslumd.tallyobj.Tally.screen>`
        :attr:`~tslumd.tallyobj.Screen.is_broadcast` value is taken into account
        as well as cases where :attr:`screen_index` is set to ``None``

        Arguments:
            other: A :class:`SingleTallyConfig`, :class:`MultiTallyConfig`,
                :class:`tslumd.tallyobj.Tally` or :class:`int`

        Note:
            Behavior is undefined if :attr:`allow_all` is ``False``
        """
        if isinstance(other, SingleTallyConfig):
            return other.matches_screen(self)
        self_screen = normalize_screen(self)
        oth_screen = normalize_screen(other)
        if None not in (self_screen, oth_screen):
            return self_screen == oth_screen
        return True

    def contains(self, tally: TallyOrTallyConfig) -> bool:
        """Determine whether the given tally argument is included in this
        configuration

        The :meth:`matches_screen` method is used to match the :attr:`screen_index`.
        If :attr:`allow_all` is ``False``, each object in :attr:`tallies` is
        :meth:`checked <SingleTallyConfig.matches>`

        Arguments:
            tally: Either a :class:`SingleTallyConfig` or a
                :class:`tslumd.tallyobj.Tally` instance
        """
        if self.allow_all:
            return self.matches_screen(tally)
        for t in self.tallies:
            if t.matches(tally):
                return True
        return False

    def to_dict(self) -> Dict:
        tallies = [c.to_dict() for c in self.tallies]
        return {'tallies':tallies, 'allow_all':self.allow_all}

    @classmethod
    def from_dict(cls, d: Dict) -> 'MultiTallyConfig':
        kw = d.copy()
        tallies = kw['tallies']
        kw['tallies'] = [SingleTallyConfig.from_dict(td) for td in tallies]
        return super().from_dict(kw)

SingleTallyOption = Option(
    name='config', type=SingleTallyConfig, required=True,
    sub_options=SingleTallyConfig.get_init_options(),
    title='Tally Config',
)
MultiTallyOption = Option(
    name='config', type=MultiTallyConfig, required=True,
    sub_options=MultiTallyConfig.get_init_options(),
    title='Multi Tally Config',
)

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

    @property
    def tally_index(self) -> int:
        """Alias for :attr:`~SingleTallyConfig.tally_index` of the :attr:`config`

        Note:
            Only valid if :attr:`config` is a :class:`SingleTallyConfig`
        """
        if not isinstance(self.config, SingleTallyConfig):
            raise ValueError('tally_index not available')
        return self.config.tally_index
    @tally_index.setter
    def tally_index(self, value: int):
        if not isinstance(self.config, SingleTallyConfig):
            raise ValueError('tally_index not available')
        if value == self.tally_index:
            return
        self.config.tally_index = value
        self._tally_config_changed()

    @property
    def tally_type(self) -> TallyType:
        """Alias for :attr:`~SingleTallyConfig.tally_type` of the :attr:`config`

        Note:
            Only valid if :attr:`config` is a :class:`SingleTallyConfig`
        """
        if not isinstance(self.config, SingleTallyConfig):
            raise ValueError('tally_index not available')
        return self.config.tally_type
    @tally_type.setter
    def tally_type(self, value: TallyType):
        if not isinstance(self.config, SingleTallyConfig):
            raise ValueError('tally_index not available')
        if value == self.tally_type:
            return
        self._tally_config_changed()
        self.config.tally_type = value

    def _tally_config_changed(self):
        """Called when changes to the :attr:`config` are made.

        Subclasses can use this perform any necessary changes
        :meta public:
        """
        pass

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
        await self.on_receiver_tally_change(tally)
