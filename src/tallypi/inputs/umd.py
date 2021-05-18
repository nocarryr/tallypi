from loguru import logger
logger.disable('tslumd.tallyobj')
import asyncio
from typing import Optional, Tuple, Iterable, Set

from tslumd import UmdReceiver, TallyType, Screen, Tally, TallyKey

from tallypi.common import MultiTallyConfig, MultiTallyOption
from tallypi.baseio import BaseInput
from tallypi.config import Option

__all__ = ('UmdInput',)

class UmdInput(BaseInput, namespace='umd.UmdInput', final=True):
    """Networked tally input using the UMDv5 protocol

    Arguments:
        config(MultiTallyConfig): The initial value for
            :attr:`~tallypi.baseio.BaseIO.config`
        hostaddr(str, optional): The local :attr:`hostaddr` to listen on.
            Defaults to :attr:`tslumd.receiver.UmdReceiver.DEFAULT_HOST`
        hostport(int, optional): The UDP :attr:`hostport` to listen on.
            Defaults to :attr:`tslumd.receiver.UmdReceiver.DEFAULT_PORT`
    """
    receiver: UmdReceiver
    """The tslumd server
    """

    def __init__(self,
                 config: MultiTallyConfig,
                 hostaddr: str = UmdReceiver.DEFAULT_HOST,
                 hostport: int = UmdReceiver.DEFAULT_PORT):

        super().__init__(config)
        self.loop = asyncio.get_event_loop()
        self._screen_indices = set()
        self._tally_keys = set()
        self.receiver = UmdReceiver(hostaddr=hostaddr, hostport=hostport)
        self.receiver.bind(
            on_screen_added=self._on_receiver_screen_added,
            on_tally_added=self._on_receiver_tally_added,
            on_tally_updated=self._on_receiver_tally_updated
        )

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            MultiTallyOption,
            Option(
                name='hostaddr', type=str, required=False,
                default=UmdReceiver.DEFAULT_HOST, title='Listen Address',
            ),
            Option(
                name='hostport', type=int, required=False,
                default=UmdReceiver.DEFAULT_PORT, title='Listen Port',
            ),
        )

    @property
    def hostaddr(self) -> str:
        """The :attr:`~tslumd.receiver.UmdReceiver.hostaddr` of the :attr:`receiver`
        """
        return self.receiver.hostaddr

    @property
    def hostport(self) -> int:
        """The :attr:`~tslumd.receiver.UmdReceiver.hostport` of the :attr:`receiver`
        """
        return self.receiver.hostport

    async def open(self):
        if self.running:
            return
        await self.receiver.open()
        self.running = True

    async def close(self):
        if not self.running:
            return
        await self.receiver.close()

    async def set_hostaddr(self, hostaddr: str):
        """Set the :attr:`hostaddr` on the :attr:`receiver`
        """
        await self.receiver.set_hostaddr(hostaddr)

    async def set_hostport(self, hostport: int):
        """Set the :attr:`hostport` on the :attr:`receiver`
        """
        await self.receiver.set_hostport(hostport)

    def get_screen(self, screen_index: int) -> Optional[Screen]:
        if screen_index not in self._screen_indices:
            return None
        return self.receiver.screens.get(screen_index)

    def get_all_screens(self) -> Iterable[Screen]:
        for ix in self._screen_indices:
            yield self.receiver.screens[ix]

    def get_tally(self, tally_key: TallyKey) -> Optional[Tally]:
        if tally_key not in self._tally_keys:
            return None
        return self.receiver.tallies.get(tally_key)

    def get_all_tallies(self, screen_index: Optional[int] = None) -> Iterable[Tally]:
        if screen_index is not None:
            screen = self.get_screen(screen_index)
            tally_iter = []
            if screen is not None:
                tally_iter = screen
            for tally in tally_iter:
                if tally.id in self._tally_keys:
                    yield tally
        else:
            for tally_key in self._tally_keys:
                yield self.receiver.tallies[tally_key]

    def _on_receiver_screen_added(self, screen: Screen, **kwargs):
        if not screen.is_broadcast and self.screen_matches(screen):
            self._screen_indices.add(screen.index)
            self.emit('on_screen_added', self, screen)

    @logger.catch
    def _on_receiver_tally_added(self, tally, **kwargs):
        if self.tally_matches(tally):
            self._tally_keys.add(tally.id)
            self.emit('on_tally_added', self, tally)

    @logger.catch
    def _on_receiver_tally_updated(self, tally: Tally, props_changed: Set[str], **kwargs):
        if tally.id in self._tally_keys:
            self.emit('on_tally_updated', self, tally, props_changed)
