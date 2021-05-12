import dataclasses
from dataclasses import dataclass, field
from typing import Dict, Tuple, List, Optional, Union

from tslumd import Screen, Tally, TallyType, TallyKey

from .config import Option, ListOption

__all__ = (
    'Pixel', 'Rgb', 'TallyConfig', 'SingleTallyConfig', 'MultiTallyConfig',
)

Pixel = Tuple[int, int] #: A tuple of ``(x, y)`` coordinates
Rgb = Tuple[int, int, int] #: A color tuple of ``(r, g, b)``

TallyOrTallyConfig = Union[Tally, 'SingleTallyConfig']
TallyOrMultiTallyConfig = Union[TallyOrTallyConfig, 'MultiTallyConfig']

def normalize_screen(obj: Union[TallyOrMultiTallyConfig, int]) -> Union[None, int]:
    if obj is None:
        return None
    elif isinstance(obj, int):
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
