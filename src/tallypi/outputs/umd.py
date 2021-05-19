from loguru import logger
logger.disable('tslumd.sender')
import asyncio
from dataclasses import dataclass
from typing import Optional, Tuple, Iterable, Set, Dict, Union

from tslumd import UmdSender, TallyType, Screen, Tally, TallyKey
from tslumd.sender import Client

from tallypi.common import MultiTallyConfig, MultiTallyOption
from tallypi.baseio import BaseOutput
from tallypi.config import Option, ListOption
from tallypi.utils import SetProperty


@dataclass(frozen=True)
class ClientData:
    """Container for network client data
    """
    hostaddr: str #: The network host address
    hostport: int #: The port number

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            Option(name='hostaddr', type=str, required=True, title='Host Address'),
            Option(name='hostport', type=int, required=True, title='Host Port'),
        )

    @classmethod
    def from_tuple(cls, client: Client) -> 'ClientData':
        addr, port = client
        return ClientData(hostaddr=addr, hostport=port)

    @property
    def as_tuple(self) -> Client:
        """The client data as a tuple of (:attr:`hostaddr`, :attr:`hostport`)
        """
        return (self.hostaddr, self.hostport)


ClientsOption = ListOption(
    name='clients', type=ClientData, required=False,
    sub_options=ClientData.get_init_options(),
    title='Clients',
)

ClientOrData = Union[Client, ClientData]
""":data:`~tslumd.sender.Client` or :class:`ClientData`
"""

INDICATOR_PROPS = {tt.name: tt for tt in TallyType.all()}


class UmdOutput(BaseOutput, namespace='umd.UmdOutput', final=True):
    """Networked tally output using the UMDv5 protocol

    Arguments:
        config (MultiTallyConfig): The initial value for
            :attr:`~tallypi.baseio.BaseIO.config`
        clients (Iterable[ClientOrData], optional): The initial :attr:`clients` to set
        all_off_on_close: (bool, optional): Value to set for :attr:`all_off_on_close`

    Properties:
        clients (set): A :class:`~.utils.SetProperty` containing the remote host
            addresses as address/port tuples.

    """
    sender: UmdSender
    """The :class:`tslumd.sender.UmdSender` instance
    """

    clients = SetProperty(copy_on_change=True)

    def __init__(
        self,
        config: MultiTallyConfig,
        clients: Optional[Iterable[ClientOrData]] = None,
        all_off_on_close: Optional[bool] = False,
    ) -> None:
        super().__init__(config)
        self.sender = UmdSender(all_off_on_close=all_off_on_close)
        self.bind(clients=self._on_clients_changed)
        if clients is not None:
            for c in clients:
                self.add_client(c)

    @property
    def all_off_on_close(self) -> bool:
        """Alias for :attr:`tslumd.sender.UmdSender.all_off_on_close`.

        If ``True``, the sender will turn all tally indicators off before
        closing. Default is ``False``
        """
        return self.sender.all_off_on_close
    @all_off_on_close.setter
    def all_off_on_close(self, value: bool):
        self.sender.all_off_on_close = value

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (
            MultiTallyOption,
            ClientsOption,
            Option(
                name='all_off_on_close', type=bool,
                required=False, default=False,
            )
        )

    async def open(self):
        if self.running:
            return
        await self.sender.open()
        self.running = True

    async def close(self):
        if not self.running:
            return
        await self.sender.close()

    def add_client(self, client: ClientOrData):
        """Add an item to :attr:`clients`
        """
        if not isinstance(client, ClientData):
            client = ClientData.from_tuple(client)
        self.clients.add(client)

    def remove_client(self, client: ClientOrData):
        """Remove an item from :attr:`clients`
        """
        if not isinstance(client, ClientData):
            client = ClientData.from_tuple(client)
        self.clients.discard(client)

    @logger.catch
    async def on_receiver_tally_change(self, tally: Tally, props_changed: Set[str], **kwargs):
        if not self.running:
            return
        if not self.tally_matches(tally):
            return
        for prop, tally_type in INDICATOR_PROPS.items():
            if prop not in props_changed:
                continue
            match = self.tally_matches(tally, tally_type, return_matched=True)
            if not match:
                continue
            color = self.get_merged_tally(tally, tally_type)
            self.sender.set_tally_color(tally.id, tally_type, color)

    def _on_clients_changed(self, instance, value, **kwargs):
        cl_tuples = set([c.as_tuple for c in value])
        self.sender.clients &= cl_tuples
        self.sender.clients |= cl_tuples
