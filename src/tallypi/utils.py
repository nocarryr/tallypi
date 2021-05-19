from pydispatch.properties import Property, Observable

class SetProperty(Property):
    """Property with a :class:`set` type value

    Args:
        default (Optional): If supplied, this will be the default value of the
            Property for all instances of the class. Otherwise :obj:`None`
        copy_on_change (bool, optional): If :obj:`True`, the set will be copied
            when contents are modified. This can be useful for observing the
            original state of the set from within callbacks. The copied
            (original) state will be available from the keyword argument 'old'.
            The default is :obj:`False` (for performance and memory reasons).

    Changes to the contents of the set are able to be observed through
    :class:`ObservableSet`.
    """
    def __init__(self, default=None, copy_on_change=False):
        if default is None:
            default = set()
        self.copy_on_change = copy_on_change
        super().__init__(default)
    def _add_instance(self, obj):
        default = self.default.copy()
        default = ObservableSet(default, obj=obj, property=self)
        super()._add_instance(obj, default)
    def __set__(self, obj, value):
        value = ObservableSet(value, obj=obj, property=self)
        super().__set__(obj, value)
    def __get__(self, obj, objcls=None):
        if obj is None:
            return self
        value = super().__get__(obj, objcls)
        if not isinstance(value, ObservableSet):
            value = ObservableSet(value, obj=obj, property=self)
            self._Property__storage[id(obj)] = value
        return value

class ObservableSet(set, Observable):
    """A :class:`set` subclass that tracks changes to its contents
    """
    def __init__(self, initset=None, **kwargs):
        self._init_complete = False
        super().__init__()
        self.property = kwargs.get('property')
        self.obj = kwargs.get('obj')
        self.parent_observable = kwargs.get('parent')
        if self.property is not None:
            self.copy_on_change = self.property.copy_on_change
        else:
            self.copy_on_change = False
        if initset is not None:
            self |= initset
        self._init_complete = True
    def _deepcopy(self):
        o = self.copy()
        for item in self:
            if isinstance(item, Observable):
                o[key] = item._deepcopy()
        return o
    def _build_observable(self, item):
        if isinstance(item, set):
            item = ObservableSet(item, parent=self)
        else:
            item = super()._build_observable(item)
        return item
    def add(self, item):
        if item in self:
            return
        old = self._get_copy_or_none()
        item = self._build_observable(item)
        super().add(item)
        self._emit_change(keys=[], old=old)
    def discard(self, item):
        if item not in self:
            return
        old = self._get_copy_or_none()
        item = self._build_observable(item)
        super().discard(item)
        self._emit_change(keys=[], old=old)
    def remove(self, item):
        if item not in self:
            raise KeyError(item)
        self.discard(item)
    def pop(self):
        old = self._get_copy_or_none()
        item = super().pop()
        self._emit_change(keys=[], old=old)
        return item
    def clear(self):
        if not len(self):
            return
        old = self._get_copy_or_none()
        super().clear()
        self._emit_change(keys=[], old=old)
    def __ior__(self, it):
        old = self._get_copy_or_none()
        super().__ior__(it)
        self._emit_change(keys=[], old=old)
        return self
    def __iand__(self, it):
        old = self._get_copy_or_none()
        super().__iand__(it)
        self._emit_change(keys=[], old=old)
        return self
    def __ixor__(self, it):
        old = self._get_copy_or_none()
        super().__ixor__(it)
        self._emit_change(keys=[], old=old)
        return self
    def __isub__(self, it):
        old = self._get_copy_or_none()
        super().__isub__(it)
        self._emit_change(keys=[], old=old)
        return self
