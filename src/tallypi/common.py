import dataclasses
from dataclasses import dataclass, field, InitVar
from typing import Dict, Tuple, List, Optional, Union
from pydispatch.properties import ObservableList

from tslumd import Screen, Tally, TallyType, TallyKey, TallyColor

from .config import Option, ListOption

__all__ = (
    'Pixel', 'Rgb', 'TallyConfig', 'SingleTallyConfig', 'MultiTallyConfig',
)

Pixel = Tuple[int, int] #: A tuple of ``(x, y)`` coordinates
Rgb = Tuple[int, int, int] #: A color tuple of ``(r, g, b)``

TallyOrTallyConfig = Union[Tally, 'SingleTallyConfig']
TallyOrMultiTallyConfig = Union[TallyOrTallyConfig, 'MultiTallyConfig']

TallyColorOption = Option(
    name='color_mask', type=str, required=False, title='Color',
    serialize_cb=lambda x: x.to_str(),
    validate_cb=lambda x: TallyColor.from_str(x),
)

def normalize_screen(obj: Union[TallyKey, TallyOrMultiTallyConfig, int]) -> Union[None, int]:
    if obj is None:
        return None
    elif isinstance(obj, tuple):
        obj = obj[0]
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

def normalize_tally_index(obj: Union[TallyKey, TallyOrTallyConfig, int]) -> Union[None, int]:
    if isinstance(obj, tuple):
        obj = obj[1]
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

def get_tally_key(obj: Union[TallyKey, TallyOrTallyConfig]) -> TallyKey:
    if isinstance(obj, tuple):
        return obj
    return obj.id

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

    color_mask: TallyColor = TallyColor.AMBER
    """An optional mask which can limit the color changes

    The default (:attr:`~.tslumd.common.TallyColor.AMBER`) allows all changes
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

    @classmethod
    def from_tally(cls, tally: Tally, **kwargs) -> 'SingleTallyConfig':
        """Create a :class:`SingleTallyConfig` from a :class:`~tslumd.tallyobj.Tally`
        """
        kwargs.setdefault('tally_type', TallyType.all_tally)
        scr, tly = tally.id
        scr = normalize_screen(tally)
        tly = normalize_tally_index(tally)
        return cls(screen_index=scr, tally_index=tly, **kwargs)

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
    def id(self) -> TallyKey:
        """Alias for :attr:`tally_key` to match
        :attr:`Tally.id <tslumd.tallyobj.Tally.id>`
        """
        return self.tally_key

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
                serialize_cb=lambda x: x.to_str(),
                validate_cb=lambda x: TallyType.from_str(x),
                title='TallyType',
            ),
            TallyColorOption,
            Option(name='screen_index', type=int, required=False, title='Screen'),
            Option(name='name', type=str, required=False, default='', title='Name'),
        )

    def matches(
        self,
        other: Union[TallyOrTallyConfig, TallyKey],
        tally_type: Optional[TallyType] = TallyType.all_tally,
        return_matched: Optional[bool] = False
    ) -> Union[bool, 'SingleTallyConfig']:
        """Determine whether the given tally argument matches this one

        For :attr:`screen_index` the :meth:`matches_screen` method is used

        Arguments:
            other: Either another :class:`SingleTallyConfig`, a
                :class:`tslumd.tallyobj.Tally` instance or a :term:`TallyKey`
            tally_type: If provided, a :class:`~tslumd.common.TallyType` member
                (or members) to match against
            return_matched: If False (the default), only return a boolean result,
                otherwise return the matched :class:`SingleTallyConfig` if one
                was found.

        """
        if not self.matches_screen(other):
            return False
        if isinstance(other, SingleTallyConfig):
            if self.tally_type & other.tally_type == TallyType.no_tally:
                return False
        if self.tally_type & tally_type == TallyType.no_tally:
            return False
        self_ix = normalize_tally_index(self)
        oth_ix = normalize_tally_index(other)
        if None in (self_ix, oth_ix):
            r = True
        else:
            r = self_ix == oth_ix
        if r and return_matched:
            return self
        return r

    def matches_screen(self, other: Union[TallyOrMultiTallyConfig, TallyKey, int]) -> bool:
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
        d['tally_type'] = d['tally_type'].to_str()
        return d

    @classmethod
    def from_dict(cls, d: Dict) -> 'SingleTallyConfig':
        kw = d.copy()
        if not isinstance(kw['tally_type'], TallyType):
            kw['tally_type'] = TallyType.from_str(kw['tally_type'])
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
            tally = screen.add_tally(self.tally_index)
        return screen, tally


@dataclass
class MultiTallyConfig(TallyConfig):
    """Configuration for multiple tallies
    """
    tallies: InitVar[List[SingleTallyConfig]] = None
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

    def __post_init__(self, tallies):
        if tallies is None:
            tallies = []
        self._tallies_by_key = None
        self.copy_on_change = False
        self.tallies = ObservableList(tallies, obj=self, property=self)

    def _on_change(self, obj, old, value, **kwargs):
        """This is a callback from :class:`pydispatch.properties.ObservableList`
        """
        self._memoized_tally_confs = None

    @property
    def memoized_tally_confs(self) -> Dict[TallyKey, Dict[TallyType, SingleTallyConfig]]:
        r = getattr(self, '_memoized_tally_confs', None)
        if r is None:
            r = self._memoized_tally_confs = {}
        return r

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

    def matches(
        self,
        tally: Union[TallyOrTallyConfig, TallyKey],
        tally_type: Optional[TallyType] = TallyType.all_tally,
        return_matched: Optional[bool] = False
    ) -> Union[bool, SingleTallyConfig]:
        """Alias for :meth:`contains`
        """
        return self.contains(tally, tally_type, return_matched)

    def matches_screen(self, other: Union[TallyOrMultiTallyConfig, TallyKey, int]) -> bool:
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
        if self.screen_index is None:
            return True
        if isinstance(other, SingleTallyConfig):
            return other.matches_screen(self)
        self_screen = normalize_screen(self)
        oth_screen = normalize_screen(other)
        if None not in (self_screen, oth_screen):
            return self_screen == oth_screen
        return True

    def contains(
        self,
        tally: Union[TallyOrTallyConfig, TallyKey],
        tally_type: Optional[TallyType] = TallyType.all_tally,
        return_matched: Optional[bool] = False
    ) -> Union[bool, SingleTallyConfig]:
        """Determine whether the given tally argument is included in this
        configuration

        The :meth:`matches_screen` method is used to match the :attr:`screen_index`.
        If :attr:`allow_all` is ``False``, each object in :attr:`tallies` is
        :meth:`checked <SingleTallyConfig.matches>`

        Arguments:
            tally: Either a :class:`SingleTallyConfig` or a
                :class:`tslumd.tallyobj.Tally` instance
        """

        memoized = self.search_memoized(tally, tally_type)
        if memoized is not None:
            if return_matched:
                return memoized
            return True

        if self.allow_all:
            if not self.matches_screen(tally):
                return False
            if return_matched:
                ret = self._create_single_conf(tally, tally_type)
                self.add_memoized(ret)
                return ret
            return True
        t = self._search_tallies(tally, tally_type)
        if t is not None:
            self.add_memoized(t)
            if return_matched:
                return t
            return True
        return False

    def _search_tallies(
        self,
        tally: Union[TallyOrTallyConfig, TallyKey],
        tally_type: Optional[TallyType] = TallyType.all_tally
    ) -> Optional[SingleTallyConfig]:
        for t in self.tallies:
            if t.matches(tally, tally_type):
                return t

    def search_memoized(
        self,
        obj: Union[TallyOrTallyConfig],
        tally_type: Optional[TallyType] = TallyType.all_tally
    ) -> Optional[SingleTallyConfig]:
        memo = self.memoized_tally_confs
        t_id = get_tally_key(obj)
        if t_id not in memo:
            return None
        if isinstance(obj, SingleTallyConfig):
            ttype = obj.tally_type
        else:
            ttype = tally_type
        return memo[t_id].get(ttype)

    def add_memoized(self, obj: SingleTallyConfig):
        memo = self.memoized_tally_confs
        if obj.id not in memo:
            memo[obj.id] = {}
        # assert obj.tally_type not in memo[obj.id], 'obj exists'
        if obj.tally_type in memo[obj.id]:
            oth = memo[obj.id][obj.tally_type]
            assert obj == oth
        memo[obj.id][obj.tally_type] = obj

    def to_dict(self) -> Dict:
        tallies = [c.to_dict() for c in self.tallies]
        return {'tallies':tallies, 'allow_all':self.allow_all}

    @classmethod
    def from_dict(cls, d: Dict) -> 'MultiTallyConfig':
        kw = d.copy()
        tallies = kw['tallies']
        kw['tallies'] = [SingleTallyConfig.from_dict(td) for td in tallies]
        return super().from_dict(kw)

    def _create_single_conf(
        self,
        tally: Union[TallyOrTallyConfig, TallyKey],
        tally_type: Optional[TallyType] = TallyType.all_tally
    ) -> SingleTallyConfig:

        if isinstance(tally, SingleTallyConfig):
            ret = tally
        elif not isinstance(tally, Tally):
            scr, tly = tally
            ret = SingleTallyConfig(
                screen_index=scr,
                tally_index=tly,
                tally_type=tally_type,
            )
        else:
            ret = SingleTallyConfig.from_tally(tally, tally_type=tally_type)
        return ret

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
