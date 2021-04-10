import asyncio
from typing import Optional

from tslumd import UmdReceiver, TallyType, Tally

from tallypi.common import BaseInput, MultiTallyConfig

__all__ = ('UmdInput',)

class UmdInput(BaseInput):
    """Networked tally input using the UMDv5 protocol

    Arguments:
        config(MultiTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
    """
    receiver: UmdReceiver
    """The tslumd server
    """

    def __init__(self, config: MultiTallyConfig):
        super().__init__(config)
        self.loop = asyncio.get_event_loop()
        self.receiver = UmdReceiver()
        self.receiver.bind(
            on_tally_added=self._on_receiver_tally_added,
            on_tally_updated=self._on_receiver_tally_updated
        )

    async def open(self):
        if self.running:
            return
        await self.receiver.open()
        self.running = True

    async def close(self):
        if not self.running:
            return
        await self.receiver.close()

    def get_tally(self, index_: int) -> Optional[Tally]:
        return self.receiver.tallies.get(index_)

    def _on_receiver_tally_added(self, tally, **kwargs):
        self.emit('on_tally_added', tally)

    def _on_receiver_tally_updated(self, tally: Tally, **kwargs):
        self.emit('on_tally_updated', tally)
