Getting started
===============
To start developing and contributing to HoneyBadgerMPC:

1. `Fork`_ the `HoneyBadgerMPC`_ repository.
2. Clone your fork:

   .. code-block:: shell-session

       $ git clone --branch dev git@github.com:<username>/HoneyBadgerMPC.git

3. `Add the remote`_ repository `initc3/HoneyBadgerMPC`_:

   .. code-block:: shell-session

       $ git remote add upstream git@github.com:initc3/HoneyBadgerMPC.git

.. note:: The remote name ``upstream`` is just a convention and you are free
    to name your remotes whatever you like.

    See :ref:`git-remotes` for more information about remotes.

4. Install `pre-commit`_ to use a pre-commit hook to automate
   formatting the code using `black`_:

   .. code-block:: shell-session

       $ pip3 install --user pre-commit
       $ pre-commit install
       pre-commit installed at .git/hooks/pre-commit

   See https://pre-commit.com/#install for other ways to install `pre-commit`_.

**Next step:** :ref:`setup a development environment <devenv>`.

.. _devenv:

Development environment
-----------------------
You are free to manage your development environment the way you prefer. Two
possible approaches are documented:

.. contents::
    :local:
    :depth: 1

Using ``docker-compose`` has the advantage that you do not need to manage
dependencies as everything is taking care of in the ``Dockerfile``.

You are encouraged to consult the `Your Development Environment
<https://docs.python-guide.org/dev/env/>`_ section in the
`The Hitchhiker’s Guide to Python`_  for tips and tricks about text editors,
IDEs, and interpreter tools.


Managing your development environment with docker-compose
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1. Install `Docker`_. (For Linux, see `Manage Docker as a non-root user`_) to
   run ``docker`` without ``sudo``.)

2. Install `docker-compose`_.

3. Run the tests (the first time will take longer as the image will be built):

    .. code-block:: shell-session

        $ docker-compose run --rm honeybadgermpc

   The tests should pass, and you should also see a small code coverage report
   output to the terminal.

If the above went all well, you should be setup for developing
**HoneyBadgerMPC**!

.. tip:: You may find it useful when developing to have the following 3
    "windows" opened at all times:

    * your text editor or IDE
    * an ``ipython`` session for quickly trying things out
    * a shell session for running tests, debugging, and building the docs

    You can run the ``ipython`` and shell session in separate containers:

    IPython session:

    .. code-block:: shell-session

        $ docker-compose run --rm honeybadgermpc ipython

    Shell session:

    .. code-block:: shell-session

        $ docker-compose run --rm honeybadgermpc bash

    Once in the session (container) you can execute commands just as you would
    in a non-container session.

**Running a specific test in a container (shell session)**
As an example, to run the tests for ``passive.py``, which will generate and
open 1000 zero-sharings, :math:`N=3` :math:`t=2` (so no fault tolerance):

Run a shell session in a container:

.. code-block:: shell-session

    $ docker-compose run --rm honeybadgermpc bash

Run the test:

.. code-block:: shell-session

    $ pytest -vs tests/test_mpc.py

or

.. code-block:: shell-session

    $ python -m honeybadgermpc.mpc

.. rubric:: About code changes and building the image

When developing, you should not need to rebuild the image nor exit running
containers, unless new dependencies were added via the ``Dockerfile``. Hence
you can modify the code, add breakpoints, add new Python modules (files), and
the modifications will be readily available withing the running containers.


Managing your development environment with Pipenv
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1. `Install pipenv`_.
2. Install the `GMP`_, `MPC`_ and `MPFR`_ development packages:

   .. tabs::

       .. tab:: Debian

           .. code-block:: shell-session

               $ apt install libgmp-dev libmpc-dev libmpfr-dev

       .. tab:: Fedora

           .. code-block:: shell-session

               $ dnf install gmp-devel libmpc-devel mpfr-devel

       .. tab:: Mac OS X

           .. code-block:: shell-session

               $ brew install gmp libmpc mpfr

       .. tab:: Windows

           Should not be needed as `pre-compiled versions
           <https://pypi.org/project/gmpy2/#files>`_ of ``gmpy2`` are
           available on PyPI. See `gmpy2 docs for Windows`_ for more information.

3. Install ``honeybadgermpc`` in `editable mode`_ for development:

   .. code-block:: shell-session

       $ cd HoneyBadgerMPC/
       $ pipenv install -e .[dev]

4. Activate a virtualenv:

   .. code-block:: shell-session

       $ pipenv shell

5. Run the tests to check that you are well setup:

   .. code-block:: shell-session

       $ pytest -v --cov

The tests should pass, and you should also see a small code coverage report
output to the terminal.

Useful resources on Pipenv
""""""""""""""""""""""""""
* `Pipenv documentation`_
* `Real Python: A Guide to Pipenv`_


Running the tests
-----------------
The tests for ``honeybadgermpc`` are located under the :file:`tests/`
directory and can be run with `pytest`_:

.. code-block:: shell-session

    $ pytest

Running in verbose mode:

.. code-block:: shell-session

    $ pytest -v

Running a specific test:

.. code-block:: shell-session

    $ pytest -v tests/test_mpc.py::test_open_shares

When debugging, i.e. if one has put breakpoints in the code, use the ``-s``
option (or its equivalent ``--capture=no``):

.. code-block:: shell-session

    $ pytest -v -s
    # or
    $ pytest -v --capture=no

To exit instantly on first error or failed test:

.. code-block:: shell-session

    $ pytest -x

To re-run only the tests that failed in the last run:

.. code-block:: shell-session

    $ pytest --lf

See ``pytest --help`` for more options or the `pytest`_ docs.

Code coverage
^^^^^^^^^^^^^
Measuring the code coverage:

.. code-block:: shell-session

    $ pytest --cov

Generating an html coverage report:

.. code-block:: shell-session

    $ pytest --cov --cov-report html

View the report:

.. code-block:: shell-session

    $ firefox htmlcov/index.html


Coverage configuration file
"""""""""""""""""""""""""""
Configuration for code coverage is located under the file :file:`.coveragerc`.


.. rubric:: Code coverage tools

The code coverage is measured using the `pytest-cov`_ plugin which is based on
`coverage.py`_. The documentation of both projects is important when working
on code coverage related issues. As an example, documentation for
configuration can be first found in `pytest-cov configuration
<https://pytest-cov.readthedocs.io/en/latest/config.html>`__ but details about
the coverage config file need to be looked up in `coverage.py configuration
<https://coverage.readthedocs.io/en/latest/config.html>`__ docs.

Code quality
^^^^^^^^^^^^
In order to keep a minimal level of "code quality" `flake8`_ is used. To run
the check:

.. code-block:: shell-session

    $ flake8


Flake8 configuration file
"""""""""""""""""""""""""
`Configuration for flake8`_ is under the :file:`.flake8` file.



Building and viewing the documentation
--------------------------------------
Documentation for ``honeybadgermpc`` is located under the :file:`docs/`
directory. `Sphinx`_ is used to build the documentation, which is written
using the markup language `reStructuredText`_.

The :file:`docker-compose.yml` can be used to quickly build the docs and view
them.

**To build the docs:**

.. # run `O=-W --keep-going make -C docs html` in a container, which will
.. # write the html docs locally under docs/_build/html
.. code-block:: shell-session

    $ docker-compose up builddocs

**To view the docs**:

.. # start nginx which is used to host the docs locally
.. code-block:: shell-session

    $ docker-compose up -d viewdocs

Visit http://localhost:58888/ in a web browser.


.. tip:: To view the port mapping you can use the command:

    .. code-block:: shell-session

        $ docker-compose port viewdocs 80

    or, alternatively

    .. code-block:: shell-session

        $ docker-compose ps viewdocs


.. tip:: One may get a ``403 Forbidden`` error when trying to view the docs
    at http://localhost:58888/. This may because the generated html docs were
    removed. Using the ``make clean`` command under the :file:`docs/`
    directory, e.g.:

    .. code-block:: shell-session

        $ docker-compose run --rm builddocs make -C docs clean

    wipes out the :file:`_build/` directory, and one has to restart the
    ``viewdocs`` (``nginx``) service, i.e.:

    .. code-block:: shell-session

        $ docker-compose restart viewdocs

    and then re-build the docs:

    .. code-block:: shell-session

        $ docker-compose up builddocs

    Or vice-versa: build the docs and restart the server.

Alternative ways to build and view the docs
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To build the documentation, one can use the :file:`Makefile` under the
:file:`docs/` directory:

.. code-block:: shell-session

    $ make -C docs html

or

.. code-block:: shell-session

    $ cd docs
    $ make html

The :file:`Makefile` makes use of the `sphinx-build`_ command, which one can
also use directly:

.. code-block:: shell-session

    $ sphinx-build -M html docs docs/_build -c docs -W --keep-going

It is possible to set some Sphinx `environment variables`_ when using the
:file:`Makefile`, and more particularly ``SPHINXOPTS`` via the shortcut ``O``.
For instance, to `treat warnings as errors`_ and to `keep going`_ with
building the docs when a warning occurs:

.. code-block:: shell-session

    $ O='-W --keep-going' make html


By default the generated docs are under :file:`docs/_build/html/` and one
can view them using a browser, e.g.:

.. code-block:: shell-session

    $ firefox docs/_build/html/index.html



.. hyperlinks

.. _initc3/HoneyBadgerMPC:
.. _honeybadgermpc: https://github.com/initc3/HoneyBadgerMPC
.. _fork: https://help.github.com/articles/fork-a-repo/
.. _add the remote: https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes#_adding_remote_repositories
.. _Docker: https://docs.docker.com/install/
.. _Manage Docker as a non-root user: https://docs.docker.com/install/linux/linux-postinstall/#manage-docker-as-a-non-root-user
.. _docker-compose: https://docs.docker.com/compose/install/
.. _pipenv documentation: https://pipenv.readthedocs.io/en/latest/
.. _install pipenv: https://pipenv.readthedocs.io/en/latest/#install-pipenv-today
.. _Real Python\: A Guide to Pipenv: https://realpython.com/pipenv-guide/#package-distribution
.. _gmp: https://gmplib.org/
.. _mpc: http://www.multiprecision.org/
.. _mpfr: https://www.mpfr.org/
.. _editable mode: https://pipenv.readthedocs.io/en/latest/basics/#editable-dependencies-e-g-e
.. _pytest: https://docs.pytest.org/
.. _coverage.py: https://coverage.readthedocs.io/
.. _pytest-cov: https://pytest-cov.readthedocs.io/
.. _flake8: http://flake8.pycqa.org/en/latest/index.html
.. _Configuration for flake8: http://flake8.pycqa.org/en/latest/user/configuration.html
.. _reStructuredText: http://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html
.. _Sphinx: http://www.sphinx-doc.org
.. _sphinx-build: http://www.sphinx-doc.org/en/master/man/sphinx-build.html
.. _environment variables: http://www.sphinx-doc.org/en/master/man/sphinx-build.html#environment-variables
.. _treat warnings as errors: http://www.sphinx-doc.org/en/master/man/sphinx-build.html#id6
.. _keep going: http://www.sphinx-doc.org/en/master/man/sphinx-build.html#cmdoption-sphinx-build-keep-going
.. _gmpy2 docs for Windows: https://gmpy2.readthedocs.io/en/latest/intro.html#installing-gmpy2-on-windows
.. _The Hitchhiker’s Guide to Python: https://docs.python-guide.org/
.. _black: https://github.com/ambv/black
.. _pre-commit: https://pre-commit.com
