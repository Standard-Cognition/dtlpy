import logging
import attr

from .. import entities, miscellaneous

logger = logging.getLogger("dataloop.module")


@attr.s
class PackageModule:
    """
    Webhook object
    """
    # platform
    name = attr.ib(default='default_module')
    init_inputs = attr.ib()
    entry_point = attr.ib(default='main.py')
    functions = attr.ib()

    @functions.default
    def set_functions(self):
        functions = list()
        return functions

    @init_inputs.default
    def set_init_inputs(self):
        init_inputs = list()
        return init_inputs

    @classmethod
    def from_json(cls, _json):
        functions = [entities.PackageFunction.from_json(_function) for _function in _json.get('functions', list())]
        init_inputs = _json.get("initInputs", list())
        return cls(
            init_inputs=init_inputs,
            entry_point=_json.get("entryPoint", 'main.py'),
            name=_json.get("name", 'default_module'),
            functions=functions,
        )

    def add_function(self, function):
        if not isinstance(self.functions, list):
            self.functions = [self.functions]
        if isinstance(function, entities.PackageFunction):
            self.functions.append(function)
        elif isinstance(function, dict):
            self.functions.append(entities.PackageFunction.from_json(function))
        else:
            raise ValueError('Unknown function type: {}. Expecting dl.PackageFunction or dict')

    def print(self):
        miscellaneous.List([self]).print()

    def to_json(self):
        _json = attr.asdict(
            self,
            filter=attr.filters.exclude(attr.fields(PackageModule).functions,
                                        attr.fields(PackageModule).entry_point,
                                        attr.fields(PackageModule).init_inputs))

        # check in inputs is a list
        init_inputs = self.init_inputs
        if not isinstance(init_inputs, list):
            init_inputs = [init_inputs]
        # if is dtlpy entity convert to dict
        if init_inputs and isinstance(init_inputs[0], entities.FunctionIO):
            init_inputs = [_io.to_json() for _io in init_inputs]

        functions = self.functions
        # check in inputs is a list
        if not isinstance(functions, list):
            functions = [functions]
        # if is dtlpy entity convert to dict
        if functions and isinstance(functions[0], entities.PackageFunction):
            functions = [function.to_json() for function in functions]

        _json['entryPoint'] = self.entry_point
        _json['initInputs'] = init_inputs
        _json['functions'] = functions
        return _json
