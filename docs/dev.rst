********************
Notes for Developers
********************

Troubleshooting
===============
Some problems may sometimes be resolved by deleting some cached files. You can
use the `Makefile` to remove such files:

.. code-block:: bash

    $ make clean


Using `docker-compose`:

.. code-block:: bash

    $ docker-compose run --rm honeybadgermpc make clean


:py:data:`sys.path`/:py:envvar:`PYTHONPATH` issues
--------------------------------------------------

:py:exc:`ModuleNotFoundError`
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
If you get an error similar to,

.. code-block:: bash

        @fixture
        def GaloisField():
    >       from honeybadgermpc.field import GF
    E       ModuleNotFoundError: No module named 'honeybadgermpc'

    tests/conftest.py:31: ModuleNotFoundError

when running some tests.

Try running ``make clean``, just in case some outdated cached files would be
causing the error.

If you are running the tests locally (not in a docker container), you
may not have installed the ``honeybadgermpc`` package, i.e.:

.. code-block:: bash

    pip install --editable .[dev]

Make sure to include the option ``--editable`` or its short verion ``-e`` so
that the project is installed in `development mode`_.

Relevant links
^^^^^^^^^^^^^^
* `stackoverflow: PATH issue with pytest 'ImportError: No module named YadaYadaYada'
  <https://stackoverflow.com/questions/10253826/path-issue-with-pytest-importerror-no-module-named-yadayadayada>`_
* `pytest import mechanisms and sys.path/PYTHONPATH
  <https://docs.pytest.org/en/latest/pythonpath.html>`_
* `pytest Good Integration Practices
  <https://docs.pytest.org/en/latest/goodpractices.html>`_


FAQ
===

**Q.** Why some test functions import modules-under-test or related ones locally
instead of importing at the top?

**A.** See https://pylonsproject.org/community-unit-testing-guidelines.html


.. _development mode: https://packaging.python.org/tutorials/installing-packages/#installing-from-a-local-src-tree
