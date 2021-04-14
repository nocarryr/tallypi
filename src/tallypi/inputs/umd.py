import asyncio
from typing import Optional, Tuple

from tslumd import UmdReceiver, TallyType, Tally

from tallypi.common import BaseInput, MultiTallyConfig, MultiTallyOption
from tallypi.config import Option

__all__ = ('UmdInput',)

class UmdInput(BaseInput):
    """Networked tally input using the UMDv5 protocol

    Arguments:
        config(MultiTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
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
        self.receiver = UmdReceiver(hostaddr=hostaddr, hostport=hostport)
        self.receiver.bind(
            on_tally_added=self._on_receiver_tally_added,
            on_tally_updated=self._on_receiver_tally_updated
        )

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            MultiTallyOption,
            Option(
                name='hostaddr', type=str, required=False,
                default=UmdReceiver.DEFAULT_HOST,
            ),
            Option(
                name='hostport', type=int, required=False,
                default=UmdReceiver.DEFAULT_PORT,
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

    def get_tally(self, index_: int) -> Optional[Tally]:
        return self.receiver.tallies.get(index_)

    def _on_receiver_tally_added(self, tally, **kwargs):
        self.emit('on_tally_added', tally)

    def _on_receiver_tally_updated(self, tally: Tally, **kwargs):
        self.emit('on_tally_updated', tally)
