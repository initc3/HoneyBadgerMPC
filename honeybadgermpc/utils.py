import functools
import inspect


def check_types(func, types, kwtypes, args, kwargs):
    spec = inspect.getfullargspec(func)

    # Mapping param name => default value for arguments with defaults
    default_dict = {}

    # Mapping param name => received value
    passed_dict = {}

    # Mapping param name => type signature
    type_dict = {}

    # Build mapping of default arguments to their values
    if spec.defaults is not None:
        default_args = list(reversed(spec.args))
        default_values = list(reversed(spec.defaults))
        for (k, v) in zip(default_args, default_values):
            default_dict[k] = v

    # Build mapping of argument names to passed arguments
    for (k, v) in zip(spec.args, args):
        passed_dict[k] = v

    for (k, v) in kwargs.items():
        passed_dict[k] = v

    # Build mapping of argument names to specified types
    for (k, t) in [*kwtypes.items(), *zip(spec.args, types)]:
        if k in type_dict:
            raise ValueError(
                f"Type constraint for `{k}` of type `{t}` specified, "
                f"but type constraint already found ({type_dict[k]})")

        # Turn type into array of types
        if isinstance(t, (str, type)):
            t_arr = [t]
        elif isinstance(t, (tuple, list)):
            t_arr = [*t]
        else:
            raise ValueError(f"Type constraint for `{k}` of type `{t}` specified, "
                             f"which in not supported. Valid types are `str`, `list`, "
                             f"`tuple`, and `type`")

        # Process the types
        for idx, t_ in enumerate(t_arr):
            # If the type is a string evaluate it as if it were in the method body
            if isinstance(t_, str):
                try:
                    t_eval = eval(t_, func.__globals__, passed_dict)
                except Exception as e:
                    raise ValueError(f'Type constraint for `{k}` specified "{t_}", '
                                     f'which raised:\n{e}')

                if isinstance(t_eval, bool):
                    if not t_eval:
                        del t_arr[idx]
                    else:
                        # This will always pass an isinstance check
                        t_arr[idx] = object
                elif isinstance(t_eval, type):
                    t_arr[idx] = t_eval
                else:
                    raise ValueError(f"Type constraint for {k} provided type constraint"
                                     f"{t_}, which evaluates to {t_eval}. String type "
                                     f"constraints must evaluate to a bool or a type")
            elif not isinstance(t_, type):
                raise ValueError(f"Type constraint for {k} provided type constraint "
                                 f"{t_}, which is neither a type nor a string.")

        type_dict[k] = tuple(t_arr)

    # Typically occurs when extra un-named type constraints specified
    if len(type_dict.keys()) < (len(types) + len(kwtypes.keys())):
        raise TypeError(f"Extra type constraints received!")

    # Check all passed and default values for type constraints
    for (k, t) in type_dict.items():
        if (k not in default_dict) and (k not in passed_dict):
            raise TypeError(
                f"Type constraint for `{k}` of type `{t}` specified, "
                f"but no argument found for {k}.")
        elif (k in default_dict) and not isinstance(default_dict[k], t):
            raise TypeError(
                f"Type constraint for `{k}` of type `{t}` specified, "
                f"but incorrect default type provided ({type(default_dict[k])})")
        elif (k in passed_dict) and not isinstance(passed_dict[k], t):
            raise TypeError(
                f"Type constraint for `{k}` of type `{t}` specified, "
                f"but incorrect type passed in ({type(passed_dict[k])})")


def static_type_check(*types, **kwtypes):
    """Use this as a property on methods to get convenient type-checking.
    Example usage:
    @static_type_check(int, (int, str))
    def func(a, b):
        return a + b

    This would roughly be equivalent to:
    def func(a, b):
        if not isinstance(a, int):
            raise TypeError(f"Expected: {int}; Received: {type(a)})
        if not isinstance(b, (int, str)):
            raise TypeError(f"Expected: {int}; Received: {type(b)})

        return a + b

    You can also provide keyword arguments to this decorator--
    This ensures that the method is always invoked with those named
    arguments, and with the types specified

    TODO: better documentation
    """
    def checked_decorator(func):
        @functools.wraps(func)
        def checked_wrapper(*args, **kwargs):
            check_types(func, types, kwtypes, args, kwargs)

            return func(*args, **kwargs)
        return checked_wrapper
    return checked_decorator


def class_type_check(*types, **kwtypes):
    """Utility decorator to check types on classmethods without worrying about cls
    Equivalent of calling
    @static_type_check(type, *types, **kwtypes)
    """

    return static_type_check(type, *types, **kwtypes)


def type_check(*types, **kwtypes):
    """Utility decorator to check types on instance methods without worrying about self
    Equivalent of calling
    @static_type_check(object, *types, **kwtypes)
    """

    return static_type_check(object, *types, **kwtypes)


@static_type_check(str, 'callable(send)')
def wrap_send(tag, send):
    """Given a `send` function which takes a destination and message,
    this returns a modified function which sends the tag with the object.
    """
    def _send(dest, message):
        send(dest, (tag, message))

    return _send


@static_type_check(list, int)
def chunk_data(data, chunk_size, default=0):
    """ Break data into chunks of size `chunk_size`
    Last chunk is padded with the default value to have `chunk_size` length
    If an empty list is provided, this will return a single chunk of default values
    e.g. chunk_data([1,2,3,4,5], 2) => [[1,2], [3,4], [5, 0]]
         chunk_data([], 2) => [[0, 0]]
    """
    if len(data) == 0:
        return [default] * chunk_size

    # Main chunking
    res = [data[start:(start + chunk_size)] for start in range(0, len(data), chunk_size)]

    # Pad final chunk with default value
    res[-1] += [default] * (chunk_size - len(res[-1]))

    return res


@static_type_check(list)
def flatten_lists(lists):
    """ Given a 2d list, return a flattened 1d list
    e.g. [[1,2,3],[4,5,6],[7,8,9]] => [1,2,3,4,5,6,7,8,9]
    """
    res = []
    for inner in lists:
        res += inner

    return res


@static_type_check(list)
def transpose_lists(lists):
    """ Given a 2d list, return the transpose of the list
    e.g. [[1,2,3],[4,5,6],[7,8,9]] => [[1,4,7],[2,5,8],[3,6,9]]
    """
    rows = len(lists)
    cols = len(lists[0])
    return [[lists[j][i] for j in range(rows)] for i in range(cols)]
