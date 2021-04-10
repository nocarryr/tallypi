import dataclasses
from dataclasses import dataclass
from typing import Dict, Tuple

from tslumd import Tally, TallyColor, TallyType

__all__ = ('Pixel', 'Rgb', 'TallyConfig', 'BaseOutput')

Pixel = Tuple[int, int] #: A tuple of ``(x, y)`` coordinates
Rgb = Tuple[int, int, int] #: A color tuple of ``(r, g, b)``

@dataclass
class TallyConfig:
    """Configuration data for tally assignment
    """

    tally_index: int
    """The tally index
    """

    tally_type: TallyType = TallyType.no_tally
    """The :class:`~tslumd.common.TallyType`
    """

    def to_dict(self) -> Dict:
        """Serialize the config data
        """
        return {
            'tally_index':self.tally_index,
            'tally_type':self.tally_type.name,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> 'TallyConfig':
        """Create a :class:`TallyConfig` from serialized data
        """
        kw = d.copy()
        if not isinstance(kw['tally_type'], TallyType):
            kw['tally_type'] = TallyType(kw['tally_type'])
        return cls(**kw)


class BaseIO:
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

    @property
    def tally_index(self) -> int:
        """Alias for :attr:`~TallyConfig.tally_index` of the :attr:`config`
        """
        return self.config.tally_index
    @tally_index.setter
    def tally_index(self, value: int):
        if value == self.tally_index:
            return
        self.config.tally_index = value
        self._tally_config_changed()

    @property
    def tally_type(self) -> TallyType:
        """Alias for :attr:`~TallyConfig.tally_type` of the :attr:`config`
        """
        return self.config.tally_type
    @tally_type.setter
    def tally_type(self, value: TallyType):
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

class BaseOutput(BaseIO):
    """Base class for tally outputs

    Arguments:
        config: The initial value for :attr:`config`
    """
    pass
