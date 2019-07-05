import functools
import inspect
from inspect import Parameter, Signature
import os
from typing import _Final


class TypeCheck(object):
    """Class-based decorator to optionally check types of functions
    based on their annotations. When this decorates a function, it adds
    assertions that run before invoking the function to check the types.
    First, this checks the default arguments.
    Then, this will check the passed arguments to the function.
    Finally, this will check the return value of the function.

    There are some nuances to this--
    When python is invoked with -O, none these checks will not run by default.
    This can be overridden by passing in force=True to the constructor of the
    decorator to force that function to be type checked.

    This also supports arithmetic functions by passing in arithmetic=True.
    This will cause the function to return NotImplemented if the type signature
    of the passed arguments is incorrect instead of raising an exception. This
    should be used on functions such as __add__. This will also force type checking.

    Finally, this supports several types of annotations--
    - types
    - strings
        - When evaluating a string constraint, it will evaluate the string
          as if it were code at the beginning of the function (i.e. it has
          access to the locals and globals of the function). This means it
          essentially has access to global values from where the function is
          defined, as well as the arguments of the function. It must evaluate
          to either a boolean, or a type. When it evaluates to a boolean, the
          success of the check is eqaul to the boolean value. If it evaluates
          to a type, the value of that argument will be checked to see if it's
          an instance of that type.
    - tuples of types and strings

    Please note:
    - Adding annotations to *args and **kwargs arguments will result
      in undefined behavior as of now, as well as keyword only arguments.
    - If a class is defined inside of a function, currently, we do not
      support using that class (even in string form) as a type constraint.
    - Normally, typechecking is performed on all decorated functions if
      __debug__ is True. This can be turned off by defining the environment
      variable DISABLE_TYPECHECKING

    For sample usage, please see tests/utils/test_typecheck.py

    TODO: support typechecking args, kwargs, and keyword only arguments
    """

    def __init__(self, force=False, arithmetic=False):
        """ Constructor of the typecheck decorator.
        args:
            force (boolean): Force this function to be typechecked even if
                python was not run in debug mode.
            arithmetic (boolean): Instead of raising an assertion, if the
                type-checking fails, return NotImplemented. This overrides
                the value of force if True.
        """
        self._arithmetic = arithmetic

        # If the environment variable DISABLE_TYPECHECKING exists, then
        # only perform typechecking if required.
        self._check_types = force or arithmetic
        if "DISABLE_TYPECHECKING" not in os.environ:
            self._check_types = self._check_types or __debug__

    def _check_complex_annotation(self, name, value, annotation, local_dict):
        """ Given a string type constraint, evaluate the constraint as
        if it were in the function body being type checked. If the string
        evaluates to a boolean value, the result of the check is that value.
        If it evaluates to a type, the result of the check is if the value is
        an instance of that type. Anything else and the check is failed.

        args:
            value (object): Value being typechecked
            annotation (object): Annotation in the type signature for the given
                value
            local_dict (dict): Mapping of parameter names to values to use when
                evaluating the constraint.

        outputs:
            Returns a boolean value representing the result of this check.
        """
        assert isinstance(annotation, str)
        try:
            t_eval = eval(annotation, self._func.__globals__, local_dict)
        except Exception as e:
            raise AssertionError(
                f"Evaluating string annotation {{{annotation}}} "
                f"raised the exception: {e}"
            )

        if isinstance(t_eval, bool):
            return t_eval
        elif isinstance(t_eval, type):
            return isinstance(value, t_eval)
        else:
            return self._validate_argument(name, value, t_eval, local_dict)

    def _validate_argument(self, name, value, annotation, local_dict={}):
        """ Validate the type constraint for a single name, value, annotation pair.
        Raise an assertion if the argument fails validation.

        args:
            name (str): Name of the parameter being validated
            value (object): Value of the parameter being validated
            annotation (object): Annotation of the parameter being validated
            local_dict (dict): Mapping of argument names to values to use when
                evaluating string annotations.
        """
        if annotation in (Parameter.empty, Signature.empty):
            return True

        if isinstance(annotation, tuple):
            simple_annotations = tuple(
                a for a in annotation if isinstance(a, (type, _Final))
            )
            complex_annotations = [
                a for a in annotation if not isinstance(a, (type, _Final))
            ]
        elif isinstance(annotation, (type, _Final)):
            simple_annotations = annotation
            complex_annotations = []
        else:
            simple_annotations = tuple()
            complex_annotations = [annotation]

        simple_valid = isinstance(value, simple_annotations)
        complex_valid = any(
            [
                self._check_complex_annotation(name, value, c, local_dict)
                for c in complex_annotations
            ]
        )

        assert simple_valid or complex_valid, (
            f"Expected {name} to be of type {annotation}, "
            f"but found ({value}) of type ({type(value)})"
        )

        return True

    def _validate_defaults(self):
        """ Ensures default values match their type signatures
        An assertion will be raised if not.
        """
        for parameter_name in self._signature.parameters:
            parameter = self._signature.parameters[parameter_name]
            if Parameter.empty in (parameter.default, parameter.annotation):
                continue

            self._validate_argument(
                parameter_name,
                parameter.default,
                parameter.annotation,
                self._default_signature.arguments,
            )

    def _validate_annotation(self, annotation):
        """ Validates a single type annotation. This ensures that the annotation is
        either a type, a string, nonexistent, or a tuple of types and strings.

        args:
            annotation (object): Annotation from function signature

        outputs:
            Returns True if the annotation is either:
                - nonexistant
                - type
                - string
                - tuple of strings or types
        """
        if annotation in (Parameter.empty, Signature.empty):
            return True
        elif isinstance(annotation, (type, str, _Final)):
            return True
        elif isinstance(annotation, tuple):
            return all([self._validate_annotation(a) for a in annotation])
        else:
            return False

    def _validate_annotations(self):
        """ Ensure that type annotations for arguments and return values are
        valid annotations.
        An assertion will be raised if not.
        """
        for parameter_name in self._signature.parameters:
            parameter = self._signature.parameters[parameter_name]
            assert self._validate_annotation(parameter.annotation), (
                f"Type annotation for {parameter_name} must be a string, type, "
                f"or a tuple of strings and types ({parameter})"
            )

        assert self._validate_annotation(self._signature.return_annotation), (
            f"Return type annotations must be strings, types, or tuples "
            f"of strings or types ({self._signature.return_annotation})"
        )

        self._validate_defaults()

    def _check_function_args(self, args, kwargs):
        """Checks that the passed arguments match the correct type signature
        An assertion will be raised if not.

        args:
            args (tuple): Arguments passed into the function
            kwargs (dict): Keyword-only arguments passed into the function

        TODO: support args, kwargs
        """
        for arg_name in self._bound_signature.arguments:
            arg_value = self._bound_signature.arguments[arg_name]
            arg_annotation = self._signature.parameters[arg_name].annotation

            self._validate_argument(
                arg_name, arg_value, arg_annotation, self._called_signature.arguments
            )

    def _check_return_value(self, return_value):
        """ Checks the correctness of the return value of the function being typechecked.
        An assertion is raised if it is incorrect.

        args:
            return_value (object): Value returned by the function invocation.
        """
        return_annotation = self._signature.return_annotation
        self._validate_argument("return value", return_value, return_annotation)

    def _wrap_func(self, func):
        """ Given a function, add typechecking to the function as specified in the class
        documentation. This will also set various instance variables for later use in
        the typechecking of the function.

        args:
            func (callable): Function to type check

        outputs:
            checked_wrapper, which is essentially just the function with typechecking
            enabled.
        """
        self._func = func
        self._signature = inspect.signature(func)

        self._default_signature = self._signature.bind_partial()
        self._default_signature.apply_defaults()

        @functools.wraps(func)
        def checked_wrapper(*args, **kwargs):
            self._bound_signature = self._signature.bind(*args, **kwargs)
            self._called_signature = self._signature.bind(*args, **kwargs)
            self._called_signature.apply_defaults()

            self._validate_annotations()

            try:
                self._check_function_args(args, kwargs)
            except AssertionError as e:
                if self._arithmetic:
                    return NotImplemented
                raise e

            return_value = self._func(*args, **kwargs)
            self._check_return_value(return_value)

            return return_value

        return checked_wrapper

    def __call__(self, func):
        """ Add type checking to the function if enabled.

        args:
            func (callable): Function to typecheck

        outputs:
            Returns a version of the passed function with type checking if enabled.
        """
        if self._check_types:
            return self._wrap_func(func)

        return func
