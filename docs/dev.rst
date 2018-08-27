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


FAQ
===

**Q.** Why some test functions import modules-under-test or related ones locally
instead of importing at the top?

**A.** See https://pylonsproject.org/community-unit-testing-guidelines.html
