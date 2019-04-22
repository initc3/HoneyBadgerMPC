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
            raise TypeError(
                f"Type constraint for `{k}` of type `{t}` specified, "
                f"but type constraint already found ({type_dict[k]})")

        # If there are strings passed in, evaluate them as if they were
        # evaluated within the method
        if isinstance(t, tuple):
            t = tuple(eval(t_, func.__globals__, passed_dict)
                      if isinstance(t_, str) else t_ for t_ in t)
        elif isinstance(t, str):
            t = eval(t, func.__globals__, passed_dict)

        type_dict[k] = t

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
