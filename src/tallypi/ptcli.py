from loguru import logger
logger.disable('tslumd')
import asyncio
import dataclasses
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict, Tuple, Any
import enum
from functools import partial

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.key_binding.key_bindings import KeyBindings
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout import ScrollablePane
from prompt_toolkit.layout.containers import VSplit, HSplit, Window, Float, FloatContainer
from prompt_toolkit.layout.layout import Layout, BufferControl
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit import widgets

from pydispatch import Dispatcher

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

yaml = YAML(typ='safe')

from tallypi.config import Option, ListOption
from tallypi.manager import Manager
from tallypi.common import BaseIO

kb = KeyBindings()

class Extent(enum.IntFlag):
    """Enum for bounding boxes
    """
    none = 0    #: No extent
    top = 1     #: Top extent
    bottom = 2  #: Bottom extent
    left = 4    #: Left extent
    right = 8   #: Right extent

class FormMode(enum.Enum):
    """Enum for :attr:`FormDialog.mode`
    """
    add = enum.auto()   #: Add mode
    edit = enum.auto()  #: Edit mode

class ChooserMode(enum.Enum):
    """Enum for :attr:`ChooserDialog.mode`
    """
    edit = enum.auto()      #: Edit mode
    remove = enum.auto()    #: Remove mode

class IOType(enum.Enum):
    """Enum for input / output types
    """
    input = enum.auto()     #: Input type
    output = enum.auto()    #: Output type


@dataclass
class MenuDef:
    """A definition for a MenuItem
    """
    title: str
    """The menu item title"""
    id: Optional[str] = ''
    """Unique item id within its parent menu"""
    is_root: bool = False
    """``True`` if the item is at the root of the tree"""
    handler: Optional[Callable] = None
    """Optional callback for the item"""
    class_namespace: Optional[str] = None
    """A :attr:`tallypi.common.BaseIO.namespace` reference"""
    children: List['MenuDef'] = field(default_factory=list)
    """List of :class:`MenuDef` child instances"""
    def __post_init__(self):
        if not len(self.id):
            if self.is_root:
                self.id = 'root'
            else:
                self.id = self.title.lower()
        for child in self.children:
            child.parent = self

    @property
    def parent(self) -> Optional['MenuDef']:
        """The parent :class:`MenuDef`, or ``None`` if the item :attr:`is_root`
        """
        return getattr(self, '_parent', None)
    @parent.setter
    def parent(self, value: 'MenuDef'):
        if value is self.parent:
            return
        self._parent = value

    @property
    def fqdn(self) -> str:
        """Fully qualified MenuDef name

        Built by traversing the tree up to the :attr:`root <is_root>` item and
        combining the :attr:`id` of each ancestor, delimited by a ``"."``

        The result is ``'.'.join([self.parent.fqdn, self.id])``
        """
        if self.is_root:
            return self.id
        return f'{self.parent.fqdn}.{self.id}'


class AppState:
    """One big honkin' rats nest of state and widget storage for prompt_toolkit
    """

    menu_defs: MenuDef
    """Definitions for the main menu"""
    menu: widgets.MenuContainer
    """The main menu container widget"""
    form_dialog: Optional['FormDialog']
    """The current :class:`FormDialog`"""
    chooser_dialog: Optional['ChooserDialog']
    """The current :class:`ChooserDialog`"""
    label_left: widgets.TextArea
    """Display for the input config state"""
    label_right: widgets.TextArea
    """Display for the output config state"""
    manager: Manager
    """:class:`.manager.Manager` instance to track i/o objects and config"""
    def __init__(self):
        self._app = None
        self.loop = asyncio.get_event_loop()

        self.menu_defs = MenuDef(title='Root', is_root=True, children=[
            MenuDef('Show', handler=self.focus_conf),
            MenuDef(title='Edit', children=[
                MenuDef(title='Input'),
                MenuDef(title='Output'),
            ]),
            MenuDef('Add', children=[
                MenuDef('Input', children=[
                    MenuDef(title='Umd', class_namespace='input.umd.UmdInput'),
                    MenuDef(title='GPIO', class_namespace='input.gpio.GpioInput'),
                ]),
                MenuDef('Output', children=[
                    MenuDef(title='GPIO', children=[
                        MenuDef(title='LED', class_namespace='output.gpio.LED'),
                        MenuDef(title='PWMLED', class_namespace='output.gpio.PWMLED'),
                        MenuDef(title='RGBLED', class_namespace='output.gpio.RGBLED'),
                    ]),
                    MenuDef(title='rgbmatrix5x5', children=[
                        MenuDef(
                            title='Indicator',
                            class_namespace='output.rgbmatrix5x5.Indicator',
                        ),
                        MenuDef(
                            title='Matrix',
                            class_namespace='output.rgbmatrix5x5.Matrix',
                        ),
                    ]),
                ]),
            ]),
            MenuDef(title='Remove', children=[
                MenuDef(title='Input'),
                MenuDef(title='Output'),
            ]),
            MenuDef(title='Exit', handler=self.exit),
        ])

        self.form_dialog = None
        self.chooser_dialog = None

        self.build_root()
        self.manager = Manager(readonly=True)

    @property
    def app(self) -> Application:
        """The :class:`prompt_toolkit.application.Application`
        """
        app = self._app
        if app is None:
            app = self._app = get_app()
        return app

    def build_root(self):
        """Build the root containers and widgets
        """
        self.label_left = widgets.TextArea(text='', focus_on_click=True, read_only=True)#, style='class:output-field')
        self.label_right = widgets.TextArea(text='', style='class:output-field')
        self.tally_view_window = HSplit([])
        self.body = FloatContainer(
            modal=True,
            content=VSplit([
                self.label_left,
                self.label_right,
                self.tally_view_window,
            ]),
            floats=[],
        )

        self.menu = self.root_container = widgets.MenuContainer(
            body=self.body,
            menu_items=self.build_menu_items(self.menu_defs),
        )
        self.add_label_filters()

    def add_label_filters(self):
        """Add KeyBindings to allow scrolling thru :attr:`label_left` and
        :attr:`label_right`, and refocus the :attr:`menu` if ``up`` is pressed
        at the top of the document
        """
        def check_text_extent(doc):
            extent = Extent.none
            if doc.on_first_line:
                extent |= Extent.top
            if doc.on_last_line:
                extent |= Extent.bottom
            if doc.cursor_position_col == 0:
                extent |= Extent.left
            if doc.is_cursor_at_the_end_of_line:
                extent |= Extent.right
            return extent

        def text_at_bounds(label: widgets.TextArea, extent: Extent):
            @Condition
            def inner():
                doc = label.document
                doc_extents = check_text_extent(doc)
                return extent in doc_extents
            return inner

        filt = has_focus(self.label_left) & text_at_bounds(self.label_left, Extent.top)
        @kb.add('up', filter=filt)
        def _input_up(event):
            event.app.layout.focus(self.menu.window)

        filt = has_focus(self.label_right) & text_at_bounds(self.label_right, Extent.top)
        @kb.add('up', filter=filt)
        def _output_up(event):
            event.app.layout.focus(self.menu.window)

        filt = has_focus(self.label_left) & text_at_bounds(self.label_left, Extent.right)
        @kb.add('right', filter=filt)
        def _right(event):
            event.app.layout.focus(self.label_right)

        filt = has_focus(self.label_right) & text_at_bounds(self.label_right, Extent.left)
        @kb.add('left', filter=filt)
        def _left(event):
            event.app.layout.focus(self.label_left)


    def build_menu_items(self, item: MenuDef):
        """Build a :class:`prompt_toolkit.widgets.MenuItem` from the given
        :class:`MenuDef` and recursively build its children
        """
        items = []
        for c in item.children:
            items.append(self.build_menu_items(c))
        if not len(items):
            items = None
        if item.is_root:
            return items
        handler = item.handler
        if handler is None:
            handler = partial(self.menu_handler, item)
        return widgets.MenuItem(item.title, children=items, handler=handler)

    async def open(self):
        await self.manager.read_config()
        # await self.manager.open()
        self.update_io_tree()
        # umd = self.manager.inputs['umd.UmdInput:000']
        # self.tally_view = TallyView(umd)
        # self.tally_view_window.children.append(self.tally_view.root_container)

    async def close(self):
        await self.manager.close()

    def update_io_tree(self):
        """Update :attr:`label_left` and :attr:`label_right` from the
        :attr:`manager` state
        """
        for key, widget in (('inputs', self.label_left), ('outputs', self.label_right)):
            obj = getattr(self.manager, key)
            d = obj.serialize()
            fd = StringIO()
            yaml.dump(d, fd)
            s = fd.getvalue()
            widget.text = s

    def menu_handler(self, item: MenuDef):
        """Default handler for all menu items

        Triggers creation of :attr:`form_dialog` and attr:`chooser_dialog`
        using the :attr:`MenuDef.fqdn`
        """
        if item.fqdn.startswith('root.add'):
            ns = item.class_namespace
            if ns is not None:
                io_type = getattr(IOType, ns.split('.')[0])
                self.create_add_dialog(item, io_type)
        elif item.fqdn.startswith('root.edit.'):
            item_type = item.fqdn.split('.')[-1]
            item_type = getattr(IOType, item_type)
            self.create_choice_dialog(item_type, ChooserMode.edit)
        elif item.fqdn.startswith('root.remove.'):
            item_type = item.fqdn.split('.')[-1]
            item_type = getattr(IOType, item_type)
            self.create_choice_dialog(item_type, ChooserMode.remove)


    def create_choice_dialog(self, io_type: IOType, mode: ChooserMode):
        """Create a :class:`ChooserDialog`
        """
        assert not len(self.body.floats)
        assert self.form_dialog is None
        assert self.chooser_dialog is None
        if io_type == IOType.input:
            item_dict = self.manager.inputs
        elif io_type == IOType.output:
            item_dict = self.manager.outputs
        self.chooser_dialog = ChooserDialog(
            title=f'Select {io_type.name} to {mode.name}',
            item_dict=item_dict,
            io_type=io_type,
            mode=mode,
        )
        self.chooser_dialog.bind_async(self.loop,
            on_submit=self.on_chooser_dialog_submit,
        )
        self.chooser_dialog.bind(
            on_cancel=self.on_dialog_cancel,
        )
        self.body.floats.append(self.chooser_dialog.container)
        self.chooser_dialog.focus(self.app)

    def create_add_dialog(self, item: MenuDef, io_type: IOType):
        """Create a :class:`FormDialog` with :attr:`~FormDialog.mode` set to
        :attr:`FormMode.add`
        """
        assert not len(self.body.floats)
        assert self.form_dialog is None
        ns = item.class_namespace
        cls = BaseIO.get_class_for_namespace(ns)
        self.create_form_dialog(
            options=cls.get_init_options(),
            mode=FormMode.add, io_type=io_type,
            item_cls=cls,
        )

    def create_form_dialog(self, **kwargs):
        """Create a :class:`FormDialog` with the given keyword arguments
        """
        self.form_dialog = FormDialog(**kwargs)
        self.form_dialog.bind_async(self.loop,
            on_submit=self.on_form_dialog_submit,
        )
        self.form_dialog.bind(on_cancel=self.on_dialog_cancel)
        self.body.floats.append(self.form_dialog.container)
        self.form_dialog.focus(self.app)


    @logger.catch
    async def on_form_dialog_submit(self, dlg: 'FormDialog', values: Dict, **kwargs):
        """Handler for :event:`FormDialog.on_submit`
        """
        if dlg is not self.form_dialog:
            return
        cls = dlg.item_cls
        obj = cls.create_from_options(values)
        if dlg.io_type == IOType.input:
            items = self.manager.inputs
        elif dlg.io_type == IOType.output:
            items = self.manager.outputs
        # self.manager.readonly = False
        if dlg.mode == FormMode.add:
            async with self.manager.readonly_override as config_written:
                await items.add(obj)
                await config_written.wait()
        elif dlg.mode == FormMode.edit:
            if dlg.edited:
                async with self.manager.readonly_override as config_written:
                    await items.replace(dlg.item_key, obj)
                    await config_written.wait()
        self.close_dialog()
        self.update_io_tree()

    async def on_chooser_dialog_submit(self, dlg: 'ChooserDialog', key: str, item: BaseIO):
        """Handler for :event:`ChooserDialog.on_submit`
        """
        if dlg is not self.chooser_dialog:
            return
        self.close_dialog()
        if dlg.mode == ChooserMode.remove:
            if dlg.io_type == IOType.input:
                items = self.manager.inputs
            elif dlg.io_type == IOType.output:
                items = self.manager.outputs
            async with self.manager.readonly_override as config_written:
                await items.remove(key)
                await config_written.wait()
            self.update_io_tree()
        elif dlg.mode == ChooserMode.edit:
            options = item.get_init_options()
            values = item.serialize_options()
            cls = item.__class__
            self.create_form_dialog(
                options=options, init_values=values, mode=FormMode.edit,
                io_type=dlg.io_type, item_key=key, item_cls=cls,
            )

    def on_dialog_cancel(self, dlg, **kwargs):
        # if dlg is not self.form_dialog:
        #     return
        self.close_dialog()

    def close_dialog(self):
        """Remove all dialogs and refocus the :attr:`menu`
        """
        self.form_dialog = None
        self.chooser_dialog = None
        # self.form_dialog.unbind(self)
        self.body.floats.clear()
        self.app.layout.focus(self.menu.window)

    def focus_conf(self):
        self.app.layout.focus(self.label_left)

    def exit(self):
        self.app.exit()



@dataclass
class FormField:
    """A field within :class:`FormDialog`
    """
    id: str
    """The field id"""
    option: Option
    """The :class:`.config.Option` definition for the field"""
    label_text: Optional[str] = ''
    """Text to display as the field label"""
    label_widget: widgets.Label = field(init=False)
    """The label widget"""
    input_widget: Any = field(init=False)
    """Input widget for the field value"""
    input_widgets: Any = field(init=False)
    """List of input widgets if :attr:`option` is a :class:`~.config.ListOption`"""
    container: VSplit = field(init=False)
    """The widget containing all for the field input and label widgets"""
    initial: Optional[Any] = None
    """The initial value to display in the :attr:`input_widget`"""
    value: Any = field(init=False)
    """The current value from the :attr:`input_widget`"""
    children: Optional[Tuple['FormField']] = field(init=False)
    """Child :class:`FormField` instances if the :attr:`option` contains
    :attr:`~.config.Option.sub_options`
    """
    edited: bool = field(init=False)
    """``True`` if the field was edited (if :attr:`value` differs from
    :attr:`initial`)
    """
    def __post_init__(self):
        self.edited = False
        self.children = None
        self.input_widgets = None
        if not len(self.label_text):
            self.label_text = self.option.title
        if self.initial is None:
            self.initial = self.option.default
        self.value = self.initial
        if len(self.option.sub_options):
            self.container = self.create_sub_fields()
            self.label_widget, self.input_widget = None, None
        elif self.option.type is bool:
            w = self.create_input_widget()
            self.input_widget = self.container = w
            self.label_widget = None
        else:
            self.label_widget = widgets.Label(text=self.label_text, dont_extend_height=False)
            self.input_widget = self.create_input_widget()
            self.container = VSplit([self.label_widget, self.input_widget])

    def focus(self, app: Application):
        """Set the focus on the first available :attr:`input_widget`
        """
        if len(self.option.sub_options):
            self.children[0].focus(app)
            return
        if isinstance(self.option, ListOption):
            w = self.input_widgets[0]
        else:
            w = self.input_widget
        app.layout.focus(w)

    def create_sub_fields(self):
        """If the :attr:`option` contains :attr:`~.config.Option.sub_options`,
        create :class:`FormField` instances for them and add to :attr:`children`
        """
        initial = self.initial
        if not isinstance(initial, dict):
            initial = {}
        children = []
        child_widgets = []
        for subopt in self.option.sub_options:
            child = FormField(
                id=subopt.name, initial=initial.get(subopt.name), option=subopt,
            )
            children.append(child)
            child_widgets.append(child.container)
        w = widgets.Frame(body=HSplit(child_widgets), title=self.label_text)
        self.children = tuple(children)
        return w

    def create_input_widget(self):
        """Create the :attr:`input_widget` or :attr:`input_widgets` appropriate
        for the :attr:`option` definition
        """
        option = self.option
        if isinstance(option, ListOption):
            if None in [option.min_length, option.max_length]:
                raise Exception('not sure how to do that yet')

            children = [widgets.TextArea(multiline=False) for _ in range(option.max_length)]
            if self.initial is not None:
                for i, v in enumerate(self.initial):
                    children[i].text = str(v)
            self.input_widgets = children
            w = HSplit(children)
        else:
            if len(option.choices):
                w = widgets.RadioList(values=[(str(v),str(v)) for v in option.choices])
                if self.initial is not None:
                    i = option.choices.index(self.initial)
                    w.current_value = w.values[i][0]
                    w._selected_index = i
            elif option.type is bool:
                w = widgets.Checkbox(self.label_text)
                if self.initial:
                    w.checked = True
            else:
                if self.initial is None:
                    txt = ''
                else:
                    txt = str(self.initial)
                w = widgets.TextArea(text=txt, multiline=False)
        return w

    def _value_from_str(self, str_val: str):
        if self.option.type in (int, float):
            if not len(str_val):
                return None
            return self.option.type(str_val)
        return str_val

    def get_value(self):
        """Get the current value from the :attr:`input_widget`
        """
        option = self.option
        if len(option.sub_options):
            value = {}
            edited = False
            for child in self.children:
                value[child.id] = child.get_value()
                if child.edited:
                    edited = True
            self.edited = edited
            return value

        elif isinstance(option, ListOption):
            value = []
            for w in self.input_widgets:
                value.append(self._value_from_str(w.text))
        elif option.type is bool:
            value = self.input_widget.checked
        elif len(option.choices):
            value = self.input_widget.current_value
        else:
            value = self._value_from_str(self.input_widget.text)
        self.value = value
        self.edited = value != self.initial
        return value



class FormDialog(Dispatcher):
    """A dialog built from :class:`.config.Option` definitions using
    :class:`FormFields <FormField>`

    :Events:
        .. event:: on_submit(instance: FormDialog, values)

            The "submit" event

            :param instance: The :class:`FormDialog` instance that triggered the event
            :param values: The form :attr:`~FormDialog.values`

        .. event:: on_cancel(instance: FormDialog)

            The "cancel" event

            :param instance: The :class:`FormDialog` instance that triggered the event
    """
    mode: FormMode
    """The dialog mode"""
    io_type: IOType
    """Whether the dialog is for input or output objects"""
    dlg_key: Optional[str]
    """The object key currently being edited
    (if :attr:`mode` is :attr:`~FormMode.edit`)
    """
    options: Tuple[Option]
    """The :class:`.config.Option` definitions
    """
    values: Dict[str, Any]
    """Dict containing the values of all :attr:`fields`"""
    fields: Dict[str, FormField]
    """The :class:`FormField` instances
    """
    edited: bool
    """``True`` if any of the :attr:`fields` has been :attr:`~FormField.edited`
    """
    dlg: widgets.Dialog
    """The :class:`prompt_toolkit.widgets.Dialog` for the form"""
    container: Float
    """The :attr:`dlg` wrapped within a :class:`prompt_toolkit.layout.containers.Float`
    """
    _events_ = ['on_submit', 'on_cancel', 'close']
    def __init__(self,
                 options: Tuple[Option],
                 item_cls: type,
                 mode: FormMode,
                 io_type: IOType,
                 init_values: Optional[Dict] = None,
                 item_key: Optional[str] = None):
        self.mode = mode
        self.io_type = io_type
        self.item_cls = item_cls
        self.item_key = item_key
        self.options = options
        if init_values is None:
            init_values = {}
        self.init_values = init_values
        self.fields = {}
        self.edited = False
        self.build()
    def build(self):
        """Build the :attr:`fields`, :attr:`dlg` and :attr:`container`
        """
        field_widgets = []
        for option in self.options:
            field = self.build_form_field(option)
            self.fields[field.id] = field
            field_widgets.append(field.container)
        self.dlg = widgets.Dialog(
            body=HSplit(field_widgets),
            buttons=[
                widgets.Button(text='OK', handler=self.handle_submit),
                widgets.Button(text='Cancel', handler=self.handle_cancel),
            ],
        )
        self.container = Float(
            content=self.dlg,
            top=3, bottom=3, left=3, right=3, z_index=999,
        )
    def focus(self, app):
        """Calls :meth:`FormField.focus` on the first :attr:`field <fields>`
        """
        opt = self.options[0]
        field = self.fields[opt.name]
        field.focus(app)
    def build_form_field(self, option) -> FormField:
        """Build a :class:`FormField` for the given :class:`~.config.Option`
        """
        initial = self.init_values.get(option.name)
        return FormField(id=option.name, initial=initial, option=option)
    def get_values(self):
        """Retrieve the values for all of the :attr:`fields`

        See :meth:`FormField.get_value`
        """
        edited = False
        values = {}
        for field in self.fields.values():
            values[field.id] = field.get_value()
            if field.edited:
                edited = True
        self.values = values
        self.edited = edited
    def handle_submit(self):
        self.get_values()
        self.emit('on_submit', self, self.values)
        self.emit('close', self)
    def handle_cancel(self):
        self.get_values()
        self.emit('on_cancel', self)
        self.emit('close', self)



class ChooserDialog(Dispatcher):
    """A dialog showing a list of :class:`.common.BaseIO` items to choose from

    :Events:
        .. event:: on_submit(instance: ChooserDialog, item_key: str, item: BaseIO)

            The "submit" event

            :param instance: The :class:`ChooserDialog` instance that triggered the event
            :type instance: ChooserDialog
            :param item_key: The selected item key within :attr:`item_dict`
            :type item_key: str
            :param item: The selected item
            :type item: .common.BaseIO

        .. event:: on_cancel(instance: ChooserDialog)

            The "cancel" event

            :param instance: The :class:`ChooserDialog` instance that triggered the event
    """
    title: str
    """The title text for the dialog"""
    item_dict: Dict[str, BaseIO]
    """The items to display"""
    mode: ChooserMode
    """Mode to use after a selection is made
    Either :attr:`~ChooserMode.edit` or :attr:`~ChooserMode.remove`
    """
    dlg: widgets.Dialog
    """The :class:`prompt_toolkit.widgets.Dialog` for the form"""
    container: Float
    """The :attr:`dlg` wrapped within a :class:`prompt_toolkit.layout.containers.Float`
    """
    _events_ = ['on_submit', 'on_cancel', 'close']
    def __init__(self, title: str, item_dict: Dict[str, BaseIO], mode: ChooserMode, io_type: IOType):
        self.title = title
        self.item_dict = item_dict
        self.mode = mode
        self.io_type = io_type
        self.build()
    def build(self):
        """Build the :attr:`dlg`, :attr:`container` and item list widgets
        """
        radios = []
        for key in sorted(self.item_dict.keys()):
            radios.append((key, key))
        self.radio_list = widgets.RadioList(radios)
        self.dlg = widgets.Dialog(
            title=self.title,
            body=self.radio_list,
            buttons=[
                widgets.Button(text='OK', handler=self.handle_submit),
                widgets.Button(text='Cancel', handler=self.handle_cancel),
            ],
        )
        self.container = Float(
            content=self.dlg,
            top=3, bottom=3, left=3, right=3, z_index=999,
        )

    def focus(self, app):
        """Set focus on the item list widget
        """
        app.layout.focus(self.radio_list)

    def handle_submit(self):
        item_key = self.radio_list.current_value
        item = self.item_dict[item_key]
        self.emit('on_submit', self, item_key, item)
        self.emit('close', self)

    def handle_cancel(self):
        self.emit('on_cancel', self)
        self.emit('close', self)


# class TallyView:
#     def __init__(self, input: 'tallypi.common.BaseInput'):
#         self.input = input
#         # self.num_tallies = 0
#         self.tallies = {}
#         self.tally_row_map = {}
#         self.root_container = HSplit([
#             VSplit([
#                 widgets.Label(text='    '),
#                 widgets.Label(text='rh '),
#                 widgets.Label(text='txt'),
#                 widgets.Label(text='lh '),
#             ]),
#         ])
#         self.rebuild_widgets()
#         self.input.bind(
#             on_tally_added=self.update_tally_list,
#             on_tally_updated=self.on_tally_updated,
#         )
#
#     def update_tally_list(self, *args, **kwargs):
#         tally_row_map = {}
#         tallies = self.tallies.copy()
#         for tally in self.input.get_all_tallies():
#             if tally.index in tallies:
#                 continue
#             tallies[tally.index] = tally
#         if tallies == self.tallies:
#             return
#         for i, key in enumerate(sorted(tallies.keys())):
#             tally_row_map[key] = i
#         self.tallies = tallies
#         self.tally_row_map = tally_row_map
#         self.rebuild_widgets()
#
#     def build_row(self, index_: int) -> VSplit:
#         return VSplit([
#             widgets.TextArea(text=str(index_), multiline=False),
#             widgets.TextArea(text='   ', multiline=False),
#             widgets.TextArea(text='   ', multiline=False),
#             widgets.TextArea(text='   ', multiline=False),
#         ])
#
#     @logger.catch
#     def rebuild_widgets(self, *args, **kwargs):
#         self.root_container.children = self.root_container.children[:1]
#         for key in sorted(self.tallies.keys()):
#             logger.info(f'build_row: {key}')
#             row = self.build_row(key)
#             self.root_container.children.append(row)
#             self.update_tally_row(key)
#
#     def update_tally_row(self, index_: int):
#         row_index = self.tally_row_map[index_]
#         row = self.root_container.children[row_index+1]
#         tally = self.tallies[index_]
#         lbls = row.children[1:]
#         tally_types = ['rh_tally', 'txt_tally', 'lh_tally']
#         style_map = {
#             'off':'bg:#000000',
#             'red':'bg:#ff0000',
#             'green':'bg:#00ff00',
#             'amber':'bg:#ffbf00',
#         }
#         for lbl, attr in zip(lbls, tally_types):
#             tally_color = getattr(tally, attr)
#             style = style_map[tally_color.name.lower()]
#             lbl.window.style = style
#             lbl.text = tally_color.name
#             logger.info(f'{index_=}, {attr}={tally_color}')
#
#     def update_tally_rows(self):
#         for key in self.tallies.keys():
#             self.update_tally_row(key)
#
#     @logger.catch
#     def on_tally_updated(self, tally, **kwargs):
#         if tally.index not in self.tallies:
#             return
#         self.update_tally_row(tally.index)

def main():
    async def inner():
        # root_container = VSplit([
        #
        #
        # ])
        app_state = AppState()
        layout = Layout(app_state.root_container)
        app = Application(
            layout=layout, full_screen=True, mouse_support=True,
            key_bindings=kb,
        )
        try:
            await app_state.open()
            result = await app.run_async()
        finally:
            await app_state.close()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(inner())

if __name__ == '__main__':
    main()
