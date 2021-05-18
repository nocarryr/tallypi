from typing import Optional, Iterable, Tuple
import gpiozero
import colorzero

from tslumd import TallyType, TallyColor, Screen, Tally, TallyKey

from tallypi.common import (
    SingleTallyOption, SingleTallyConfig, Pixel, Rgb,
)
from tallypi.baseio import BaseInput
from tallypi.config import Option

__all__ = ('GpioInput',)

PinOption = Option(
    name='pin', type=int, required=True, title='Pin',
)

class GpioInput(BaseInput, namespace='gpio.GpioInput', final=True):
    """A single tally input using a GPIO pin on the RPi

    Arguments:
        config (SingleTallyConfig): The initial value for
            :attr:`~tallypi.baseio.BaseIO.config`
        pin: Initial value for :attr:`pin`
    """
    pin: int #: The GPIO input pin number
    screen: Screen #: A :class:`tslumd.tallyobj.Screen` instance for the input
    tally: Tally #: A :class:`tslumd.tallyobj.Tally` instance for the input

    def __init__(self, config: SingleTallyConfig, pin: int):
        super().__init__(config)
        self.pin = pin
        self.screen = None
        self.tally = None

    @classmethod
    def get_init_options(cls) -> Tuple[Option]:
        return (SingleTallyOption, PinOption)

    async def open(self):
        if self.running:
            return
        self.running = True
        self.screen, self.tally = self.config.create_tally()
        self.tally.bind(on_update=self._on_tallyobj_update)
        self.emit('on_screen_added', self, self.screen)
        self.emit('on_tally_added', self, self.tally)
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
        self.screen = None
        self.tally = None

    def get_screen(self, screen_index: int) -> Optional[Screen]:
        if self.screen is not None:
            return self.screen

    def get_all_screens(self) -> Iterable[Screen]:
        if self.screen is not None:
            return [self.screen]

    def get_tally(self, tally_key: TallyKey) -> Optional[Tally]:
        if self.running and tally_key == self.tally.id:
            return self.tally

    def get_all_tallies(self, screen_index: Optional[int] = None) -> Iterable[Tally]:
        if self.screen is None:
            yield None
        elif screen_index is not None and not self.matches_screen(screen_index):
            yield None
        else:
            yield self.tally

    def _set_tally_state(self, state: bool):
        attr = self.config.tally_type.name
        color = {True: self.config.color_mask, False: TallyColor.OFF}[state]
        setattr(self.tally, attr, color)

    def _on_tallyobj_update(self, tally: Tally, props_changed: Iterable[str], **kwargs):
        if self.config.tally_type.name not in props_changed:
            return
        self.emit('on_tally_updated', self, tally, [self.config.tally_type.name])

    def _on_button_pressed(self, button):
        if button is not self.button:
            return
        self._set_tally_state(True)

    def _on_button_released(self, button):
        if button is not self.button:
            return
        self._set_tally_state(True)
