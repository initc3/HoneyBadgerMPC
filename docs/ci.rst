Continuous integration
======================

.. epigraph::

    *Continuous Integration (CI) is a development practice that requires
    developers to integrate code into a shared repository several times a day.
    Each check-in is then verified by an automated build, allowing teams to
    detect problems early.*

    *By integrating regularly, you can detect errors quickly, and locate them
    more easily.*

    -- `ThoughtWorks <ThoughtWorks\: Continuous Integration>`_


``honeybadgermpc`` currently uses `Travis CI`_ to perform various checks when
one wishes to merge new code into a shared branch under the shared repository
`initc3/HoneyBadgerMPC`_. The file ``.travis.yml`` under the root of the
project is used to instruct Travis CI on what to do whenever a build is
triggered.

.travis.yml
-----------
Whenever a build is triggered, three checks are currently performed:

1. tests
2. code quality via `flake8`_. and
3. documentation generation.

Each of these checks corresponds to a row in the `build matrix`_:

.. code-block:: yaml

    matrix:
      include:
        - env: BUILD=tests
        - env: BUILD=flake8
        - env: BUILD=docs

Depending on the value of the ``BUILD`` variable the various steps (e.g.:
`install`_, `script`_) of the `build lifecycle`_ may differ.

.. rubric:: Using Python 3.7 on Travis CI

In order to use Python 3.7 the following workaround is used in
``.travis.yml``:

.. code-block:: yaml

    os: linux
    dist: xenial
    language: python
    python: 3.7
    sudo: true

See currently opened issue on this matter:
https://github.com/travis-ci/travis-ci/issues/9815


.. rubric:: Using Docker on Travis CI

In order to use Docker the following settings are needed in
``travis.yml``:

.. code-block:: yaml

    sudo: true

    services:
      - docker

See :ref:`docker-in-travis` below for more information on how we use
``docker`` and ``docker-compose`` on Travis CI to run the tests for
``honeybadgermpc``.


Shell scripts under .ci/
------------------------
In order to simplify the ``.travis.yml`` file, `shell scripts are invoked
<implementing complex build steps>`_ for the ``install``, ``script`` and
``after_success`` steps. These scripts are located under the ``.ci``
directory and should be edited as needed but with care since it is important
that the results of the checks be reliable.


.. _docker-in-travis:

.travis.compose.yml
-------------------
For the ``docs`` and ``tests`` build jobs (i.e.: ``BUILD=docs`` and
``BUILD=tests`` matrix rows), `docker-compose is used
<using docker in builds>`_. The ``Dockerfile`` used is located under the
``.ci/`` directory whereas the ``docker-compose`` file is under the root of
the project and is named ``.travis.compose.yml``. This Dockerfile simply pulls
the last-pushed version of our testing docker-image from Dockerhub, copies over
cloned code, and then runs the tests. This prevents having to install
dependencies in travis, which vastly cuts down our CI time.

.. note:: In order to achieve this, we utilize dockerhub's `automated builds`_.
    Whenever we push to the ``dev`` branch, dockerhub will build a new docker image,
    which then gets pulled down in future travis runs. If you need to rebuild
    the image used by travis for some reason (say, adding a dependency), use the
    ``build_dockerhub_image.sh`` script in ``scripts/``


Code coverage
-------------
`Code coverage`_ is used to check whether code is executed when the tests are
run. Making sure that the code is executed when tests are run helps detecting
errors.

In the ``tests`` build job on Travis CI a code coverage report is generated at
the end of the ``script`` step, with the ``--cov-report=xml`` option:

.. code-block:: bash

    # .ci/travis-install.sh
    $BASE_CMD pytest -v --cov --cov-report=term-missing --cov-report=xml

If the test run was successful the report is uploaded to `codecov`_ in the
``after_success`` step:

.. code-block:: yaml

    # .travis.yml
    after_success: .ci/travis-after-success.sh

.. important:: It is important to note that the coverage measurement happens
    in a docker container meanwhile the report upload happens outside the
    container. There are different ways to handle this situation and the
    current approach used is a variation of what is outlined in
    `Codecov Outside Docker`_.

Configuration
^^^^^^^^^^^^^
Configuring codecov is done via the ``.codecov.yml`` file which is in the
project root. Consult the `codecov`_ documentation for information on how to
work with the ``.codecov.yml`` configuration file. The most relevant sections
are `About the Codecov yaml`_ and `Coverage Configuration`_.

Github integration
^^^^^^^^^^^^^^^^^^
A pull request may fail the code coverage check and if so the pull request
will be marked as failing on Github. The Github integration may require having
a  `team bot`_ set up to be fully operational. See issue
https://github.com/initc3/HoneyBadgerMPC/issues/66 for more details.


.. There are various ways to customize how Travis CI builds the code and
.. executes tests. To learn more consult `Customizing the Build`_.


Recommended readings
--------------------
* `Travis CI: Core Concepts for Beginners`_
* `ThoughtWorks: Continuous Integration`_
* https://docs.python-guide.org/scenarios/ci/


.. _travis ci: https://docs.travis-ci.com/
.. _initc3/HoneyBadgerMPC: https://github.com/initc3/HoneyBadgerMPC
.. _travis ci\: core concepts for beginners: https://docs.travis-ci.com/user/for-beginners
.. _thoughtworks\: continuous integration: https://www.thoughtworks.com/continuous-integration
.. _customizing the build: https://docs.travis-ci.com/user/customizing-the-build/
.. _build matrix: https://docs.travis-ci.com/user/customizing-the-build/#build-matrix
.. _install: https://docs.travis-ci.com/user/customizing-the-build/#customizing-the-installation-step
.. _script: https://docs.travis-ci.com/user/customizing-the-build/#customizing-the-build-step
.. _build lifecycle: https://docs.travis-ci.com/user/customizing-the-build/#the-build-lifecycle
.. _implementing complex build steps: https://docs.travis-ci.com/user/customizing-the-build/#implementing-complex-build-steps
.. _using docker in builds: :https://docs.travis-ci.com/user/docker/
.. _flake8: http://flake8.pycqa.org/en/latest/index.html
.. _codecov: https://codecov.io/gh/initc3/HoneyBadgerMPC
.. _coverage.py: https://coverage.readthedocs.io/
.. _code coverage: https://en.wikipedia.org/wiki/Code_coverage
.. _About the Codecov yaml: https://docs.codecov.io/docs/codecov-yaml
.. _coverage configuration: https://docs.codecov.io/docs/coverage-configuration
.. _Codecov Outside Docker: https://docs.codecov.io/docs/testing-with-docker#section-codecov-outside-docker
.. _team bot: https://docs.codecov.io/docs/team-bot
.. _automated builds: https://docs.docker.com/docker-hub/builds/
