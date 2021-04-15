from pathlib import Path
from typing import Tuple, List, Dict, Sequence, Optional, Any, Callable, Union, ClassVar
import dataclasses
from dataclasses import dataclass, field

from ruamel.yaml import YAML

yaml = YAML(typ='safe')

_GET_INIT_OPTS = 'get_init_options'

class OptionError(ValueError):
    def __init__(self, opt: 'Option', opt_value: Optional[Any] = None):
        self.opt = opt
        self.opt_value = opt_value
    def __str__(self):
        return str(self.opt)

class RequiredError(OptionError):
    def __str__(self):
        return f'Option "{self.opt.name}" is required'

class ChoiceError(OptionError):
    def __str__(self):
        return f'Value for "{self.opt.name}" must be one of {self.opt.choices}, got {self.opt_value}'

class InvalidTypeError(OptionError):
    def __str__(self):
        return f'Invalid type for "{self.opt.name}", got {self.opt_value!r}'

class InvalidLengthError(OptionError):
    def __str__(self):
        return f'Length must be between {self.opt.min_length} and {self.opt.max_length}, got {self.opt_value}'

@dataclass
class Option:
    """A configuration option definition
    """
    name: str #: The parameter name
    type: Any #: The python value type
    required: bool = True #: If ``True`` (default), the parameter is required
    default: Optional[Any] = None #: The default value for the parameter
    choices: Optional[Tuple[Any]] = field(default_factory=tuple)
    """If present, a tuple of allowed values"""

    sub_options: Optional[Tuple['Option']] = field(default_factory=tuple)
    """If present, a tuple of :class:`Option` instances providing nested fields
    """

    doc: Optional[str] = ''
    validate_cb: Optional[Callable] = None
    """A callback to provide custom validation

    The callback must accept a single argument, the value to be validated
    """

    serialize_cb: Optional[Callable] = None
    """A callback to provide custom serialization

    The callback must accept a single argument, the value to be serialized
    """

    def validate(self, value: Any) -> Any:
        """Validate and transform the given value to the defined :attr:`type`

        If :attr:`sub_options` are defined, the value given must be a
        :class:`dict` formatted as is returned from the :meth:`serialize` method.
        The values within it are then validated by this method called in each
        sub option.

        Note:
            If :attr:`validate_cb` is defined, no :attr:`sub_options` will be
            processed.
        """
        if self.validate_cb is not None:
            return self.validate_cb(value)

        if value is None:
            if self.required:
                raise RequiredError(self)
            return None

        if len(self.sub_options):
            assert isinstance(value, dict)
            sub_values = {}
            for opt in self.sub_options:
                if opt.name not in value:
                    if opt.required:
                        raise RequiredError(opt)
                    continue
                sub_values[opt.name] = opt.validate(value[opt.name])
            return self.type(**sub_values)
        if len(self.choices) and value not in self.choices:
            raise ChoiceError(self, value)
        if not isinstance(value, self.type):
            raise InvalidTypeError(self, value)
        return value

    def serialize(self, value: Any) -> Any:
        """Serialize the given value of type :attr:`type`

        If :attr:`sub_options` are defined, this method will be called on each
        with their values looked up by their :attr:`name` and a :class:`dict`
        will be returned.

        Note:
            If :attr:`serialize_cb` is defined, no :attr:`sub_options` will be
            processed.
        """
        if self.serialize_cb is not None:
            return self.serialize_cb(value)
        if len(self.sub_options):
            result = {}
            for opt in self.sub_options:
                sub_value = getattr(value, opt.name)
                result[opt.name] = opt.serialize(sub_value)
            return result
        return value

@dataclass
class ListOption(Option):
    """Option definition for lists

    The :attr:`~Option.type` is used for the list elements themselves
    """
    min_length: Optional[int] = None #: If present, the minimum length of the list
    max_length: Optional[int] = None #: If present, the maximum length of the list

    def validate(self, value: Any) -> Any:
        """Validate the given value to a list of properly-typed items

        The length is checked using :attr:`min_length` and :attr:`max_length`
        (if defined).

        The base class :meth:`Option.validate` method is then called for each
        element of the input.
        """
        if value is None or not len(value):
            if self.required:
                raise RequiredError(self)
            return []
        if not isinstance(value, Sequence):
            raise InvalidTypeError(self, value)

        if self.min_length is not None and len(value) < self.min_length:
            raise InvalidLengthError(self, value)
        if self.max_length is not None and len(value) > self.max_length:
            raise InvalidLengthError(self, value)

        result = []
        for item in value:
            result.append(super().validate(item))
        return result

    def serialize(self, value: Sequence) -> List:
        """Serialize the given list of items

        The base class :meth:`Option.serialize` is called for each element of
        the input.
        """
        result = []
        for item in value:
            result.append(super().serialize(item))
        return result

class Config:
    """Config data storage using YAML
    """
    DEFAULT_FILENAME: ClassVar[Path] = Path.home() / '.config' / 'tallypi.yaml'
    """The default config filename
    """

    filename: Path
    """Path to configuration file
    """

    def __init__(self, filename: Optional[Union[str, Path]] = DEFAULT_FILENAME):
        if not isinstance(filename, Path):
            filename = Path(filename)
        self.filename = filename

    def read(self) -> Dict:
        """Read data from :attr:`filename` and return the result

        If the file does not exist, an empty dictionary is returned
        """
        if not self.filename.exists():
            return {}
        data = yaml.load(self.filename)
        return data

    def write(self, data: Dict):
        """Write the given :class:`dict` data to the config :attr:`filename`
        """
        if not self.filename.parent.exists():
            self.filename.parent.mkdir(parents=True)
        yaml.dump(data, self.filename)
