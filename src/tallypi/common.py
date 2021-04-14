import dataclasses
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional

from pydispatch import Dispatcher
from tslumd import Tally, TallyColor, TallyType

from .config import Option, ListOption

__all__ = (
    'Pixel', 'Rgb', 'BaseInput', 'BaseOutput',
    'TallyConfig', 'SingleTallyConfig', 'MultiTallyConfig',
)

Pixel = Tuple[int, int] #: A tuple of ``(x, y)`` coordinates
Rgb = Tuple[int, int, int] #: A color tuple of ``(r, g, b)``

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
    """The tally index
    """

    tally_type: TallyType = TallyType.no_tally
    """The :class:`~tslumd.common.TallyType`
    """

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        tt_choices = tuple((tt.name for tt in TallyType))
        return (
            Option(name='tally_index', type=int, required=True),
            Option(
                name='tally_type', type=str, required=True, choices=tt_choices,
                serialize_cb=lambda x: x.name,
                validate_cb=lambda x: getattr(TallyType, x)
            ),
        )

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


@dataclass
class MultiTallyConfig(TallyConfig):
    """Configuration for multiple tallies
    """
    tallies: List[SingleTallyConfig] = field(default_factory=list)
    """A list of :class:`SingleTallyConfig` instances
    """

    allow_all: bool = False
    """If ``True``, all possible tally configurations exist within this instance
    """

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            ListOption(
                name='tallies', type=SingleTallyConfig, required=False,
                sub_options=SingleTallyConfig.get_init_options(),
            ),
            Option(name='allow_all', type=bool, required=False, default=False),
        )

    def contains(self, tally_conf: SingleTallyConfig) -> bool:
        """Determine if the given :class:`config <SingleTallyConfig>` exists within
        :attr:`tallies`
        """
        if self.allow_all:
            return True
        for t in self.tallies:
            if t == tally_conf:
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
)
MultiTallyOption = Option(
    name='config', type=MultiTallyConfig, required=True,
    sub_options=MultiTallyConfig.get_init_options(),
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
    def __init__(self, config: TallyConfig):
        self.config = config
        self.running = False

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

    def serialize_options(self):
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

    async def on_receiver_tally_change(self, tally: Tally, *args, **kwargs):
        """Callback for tally updates from :class:`tslumd.receiver.UmdReceiver`
        """
        pass

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, *args):
        await self.close()

class BaseInput(BaseIO):
    """Base class for tally inputs

    Arguments:
        config: The initial value for :attr:`~BaseIO.config`

    :Events:
        .. event:: on_tally_added(tally: Tally)

            Fired when a :class:`~tslumd.tallyobj.Tally` instance has been added

        .. event:: on_tally_updated(tally: Tally)

            Fired when any :class:`~tslumd.tallyobj.Tally` instance
            has been updated
    """

    _events_ = ['on_tally_added', 'on_tally_updated']

    def get_tally(self, index_: int) -> Optional[Tally]:
        """Get a :class:`~tslumd.tallyobj.Tally` object by the given index

        If no tally information exists for this input, ``None`` is returned
        """
        raise NotImplementedError

    def get_tally_color(self, tally_conf: SingleTallyConfig) -> Optional[TallyColor]:
        """Get the current :class:`~tslumd.common.TallyColor` for the given
        :class:`config specifier <SingleTallyConfig>`

        If the tally state is unknown for does not match the :attr:`~BaseIO.config`,
        ``None`` is returned
        """
        if not self.is_tally_configured(tally_conf):
            return None
        tally = self.get_tally(tally_conf.tally_index)
        if tally is not None:
            return getattr(tally, tally_conf.tally_type.name)

    def is_tally_configured(self, tally_conf: SingleTallyConfig) -> bool:
        """Determine if the given :class:`tally config <SingleTallyConfig>`
        matches the input's :attr:`~BaseIO.config`
        """
        if isinstance(self.config, SingleTallyConfig):
            return tally_conf == self.config
        elif isinstance(self.config, MultiTallyConfig):
            return self.config.contains(tally_conf)
        return False


class BaseOutput(BaseIO):
    """Base class for tally outputs

    Arguments:
        config: The initial value for :attr:`~BaseIO.config`
    """
    pass
