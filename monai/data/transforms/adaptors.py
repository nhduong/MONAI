# Copyright 2020 MONAI Consortium
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import monai

"""
How to use the adaptor function

The key to using 'adaptor' lies in understanding the function that want to
adapt. The 'inputs' and 'outputs' parameters take either strings, lists/tuples
of strings or a dictionary mapping strings, depending on call signature of the
function being called.

The adaptor function is written to minimise the cognitive load on the caller.
There should be a minimal number of cases where the caller has to set anything
on the input parameter, and for functions that return a single value, it is
only necessary to name the dictionary keyword to which that value is assigned.

Use of `outputs`

`outputs` can take either a string, a list/tuple of string or a dict of string
to string, depending on what the transform being adapted returns:
. If the transform returns a single argument, then outputs can be supplied a
  string that indicates what key to assign the return value to in the
  dictionary
. If the transform returns a list/tuple of values, then outputs can be supplied
  a list/tuple of the same length. The strings in outputs map the return value
  at the corresponding position to a key in the dictionary
. If the transform returns a dictionary of values, then outputs must be supplied
  a dictionary that maps keys in the function's return dictionary to the
  dictionary being passed between functions

Note, the caller is free to use a more complex way of specifying the outputs
parameter than is required. The following are synonymous and will be treated
identically:
```
   # single argument
   adaptor(MyTransform(), 'image')
   adaptor(MyTransform(), ['image'])
   adaptor(MyTransform(), {'image': 'image'})

   # multiple arguments
   adaptor(MyTransform(), ['image', 'label'])
   adaptor(MyTransform(), {'image': 'image', 'label': 'label'})
```

Use of `inputs`

`inputs` can usually be omitted when using `adaptor`. It is only required when a
the function's parameter names do not match the names in the dictionary that is
used to chain transform calls.

```
class MyTransform1:
    ...
    def __call__(image):
        return '''do stuff to image'''

class MyTransform2:
    ...
    def __call__(img):
        return '''do stuff to image'''

d = {'image': i}

Compose([
    adaptor(MyTransform1(), 'image'),
    adaptor(MyTransform2(), 'image', {'img':'image'})
])
```

Inputs:
dictionary in: None | Name maps
params in (match): None | Name list | Name maps
params in (mismatch): Name maps
params & **kwargs (match) : None | Name maps
params & **kwargs (mismatch) : Name maps

Outputs:
dictionary out: None | Name maps
list/tuple out: list/tuple
variable out: string

"""
@monai.utils.export('monai.data.transforms')
def adaptor(function, outputs, inputs=None):

    def must_be_types_or_none(variable_name, variable, types):
        if variable is not None:
            if not isinstance(variable, types):
                raise ValueError(
                    "'{}' must be None or {} but is {}".format(
                        variable_name, types, type(variable)))

    def must_be_types(variable_name, variable, types):
        if not isinstance(variable, types):
            raise ValueError(
                "'{}' must be one of {} but is {}".format(
                    variable_name, types, type(variable)))

    def map_names(ditems, input_map):
        return {k if k not in input_map else input_map[k]: v for k, v in ditems.items()}

    def map_only_names(ditems, input_map):
        return {v: ditems[k] for k, v in input_map.items()}

    def _inner(ditems):

        sig = FunctionSignature(function)

        if sig.found_kwargs:
            must_be_types_or_none('inputs', inputs, (dict,))
            # we just forward all arguments unless we have been provided an input map
            if inputs is None:
                dinputs = dict(ditems)
            else:
                # dict
                dinputs = map_names(ditems, inputs)

        else:
            # no **kwargs
            # select only items from the method signature
            dinputs = dict((k, v) for k, v in ditems.items() if k in sig.non_var_parameters)
            must_be_types_or_none('inputs', inputs, (str, list, tuple, dict))
            if inputs is None:
                pass
            elif isinstance(inputs, str):
                if len(sig.non_var_parameters) != 1:
                    raise ValueError("if 'inputs' is a string, function may only have a single non-variadic parameter")
                dinputs = {inputs: ditems[inputs]}
            elif isinstance(inputs, (list, tuple)):
                dinputs = dict((k, dinputs[k]) for k in inputs)
            else:
                # dict
                dinputs = map_only_names(ditems, inputs)

        ret = function(**dinputs)

        # now the mapping back to the output dictionary depends on outputs and what was returned from the function
        op = outputs
        if isinstance(ret, dict):
            must_be_types_or_none('outputs', op, (dict,))
            if op is not None:
                ret = {v: ret[k] for k, v in op.items()}
        elif isinstance(ret, (list, tuple)):
            if len(ret) == 1:
                must_be_types('outputs', op, (str, list, tuple))
            else:
                must_be_types('outputs', op, (list, tuple))

            if isinstance(op, str):
                op = [op]

            if len(ret) != len(outputs):
                raise ValueError("'outputs' must have the same length as the number of elements that were returned")

            ret = dict((k, v) for k, v in zip(op, ret))
        else:
            must_be_types('outputs', op, (str, list, tuple))
            if isinstance(op, (list, tuple)):
                if len(op) != 1:
                    raise ValueError("'outputs' must be of length one if it is a list or tuple")
                op = op[0]
            ret = {op: ret}

        ditems = dict(ditems)
        for k, v in ret.items():
            ditems[k] = v

        return ditems

    return _inner


@monai.utils.export('monai.data.transforms')
class FunctionSignature:
    def __init__(self, function):
        import inspect
        sfn = inspect.signature(function)
        self.found_args = False
        self.found_kwargs = False
        self.defaults = {}
        self.non_var_parameters = set()
        for p in sfn.parameters.values():
            if p.kind is inspect.Parameter.VAR_POSITIONAL:
                self.found_args = True
            if p.kind is inspect.Parameter.VAR_KEYWORD:
                self.found_kwargs = True
            else:
                self.non_var_parameters.add(p.name)
                self.defaults[p.name] = p.default is not p.empty


    def __repr__(self):
        s = "<class 'FunctionSignature': found_args={}, found_kwargs={}, defaults={}"
        return s.format(self.found_args, self.found_kwargs, self.defaults)

    def __str__(self):
        return self.__repr__()
