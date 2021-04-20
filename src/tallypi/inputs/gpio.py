from typing import Optional, Iterable, Tuple
import gpiozero
import colorzero

from tslumd import TallyType, TallyColor, Tally

from tallypi.common import (
    SingleTallyOption, SingleTallyConfig, BaseInput, Pixel, Rgb,
)
from tallypi.config import Option

__all__ = ('GpioInput',)

PinOption = Option(
    name='pin', type=int, required=True, title='Pin',
)

class GpioInput(BaseInput, namespace='gpio.GpioInput', final=True):
    """A single tally input using a GPIO pin on the RPi

    Arguments:
        config (SingleTallyConfig): The initial value for
            :attr:`~tallypi.common.BaseIO.config`
        pin: Initial value for :attr:`pin`
    """
    pin: int #: The GPIO input pin number
    tally: Tally #: A :class:`tslumd.tallyobj.Tally` instance for the input

    def __init__(self, config: SingleTallyConfig, pin: int):
        super().__init__(config)
        self.pin = pin
        self.tally = None

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (SingleTallyOption, PinOption)

    async def open(self):
        if self.running:
            return
        self.running = True
        self.tally = Tally(self.tally_index)
        self.tally.bind(on_update=self._on_tallyobj_update)
        self.emit('on_tally_added', self.tally)
        self.button = gpiozero.Button(self.pin)
        self.button.when_pressed = self._on_button_pressed
        self.button.when_released = self._on_button_released
        if self.button.is_pressed:
            self._set_tally_state(True)

    async def close(self):
        if not self.running:
            return
        self.running = False
        self.tally.unbind(self)
        self.tally = None

    def get_tally(self, index_: int) -> Optional[Tally]:
        if self.running and index_ == self.tally_index:
            return self.tally

    def _set_tally_state(self, state: bool):
        attr = self.tally_type.name
        color = {True: TallyColor.RED, False: TallyColor.OFF}[state]
        setattr(self.tally, attr, color)

    def _on_tallyobj_update(self, tally: Tally, props_changed: Iterable[str], **kwargs):
        if self.tally_type.name not in props_changed:
            return
        self.emit('on_tally_updated', [self.tally_type.name])

    def _on_button_pressed(self, button):
        if button is not self.button:
            return
        self._set_tally_state(True)

    def _on_button_released(self, button):
        if button is not self.button:
            return
        self._set_tally_state(True)
