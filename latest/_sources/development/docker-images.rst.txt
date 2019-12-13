HoneyBadgerMPC Docker Image
===========================
The Docker image for HoneyBadgerMPC is roughly made up of two main
parts:

1. HoneyBadgerMPC code-independent dependencies
   (`honeybadgermpc-deps`_).
2. HoneyBadgerMPC code-dependent and experimental dependencies
   (`honeybadgermpc`__).

In addition to distinguishing between dependencies that depend on
the HoneyBadgerMPC source code from those that do not, it is also
useful to distinguish between dependencies that can be installed via
a package management tool like ``apt`` or ``pip`` from dependencies
that must be built and installed from their source code.

1. Dependencies obtained from a package repository. (Examples:
   `debian packages`_ or `PyPI`_.)
2. Dependencies which must be installed from their source code.

Some dependencies that must be installed from their source code can
take a lot of time to build and in these cases it may be convenient
to provide standalone Docker images that contain the pre-built binaries
and headers. The parent image of HoneyBadgerMPC makes use of such
images:

* `FLINT`_
* `NTL`_
* `PBC`_
* `Charm-crypto`_
* `Rust nightly frozen`_


Code-independent dependencies
-----------------------------
The Docker image for HoneyBadgerMPC is built from the parent image
`honeybadgermpc-deps`_. This parent image contains core
dependencies that do not need any of the HoneyBadgerMPC code or context
from the HoneyBadgerMPC source repository. NTL or Rust are examples of
such dependencies. The ``Dockerfile`` for the parent image is
maintained in `initc3/docker-honeybadgermpc-deps`_.

Code-dependent and experimental dependencies
--------------------------------------------
The HoneyBadgerMPC main image contains dependencies that rely on the
source code. Examples of such dependencies are the Rust/Python based
`pairing`_ library and the C++ based asynchromix `compute-power-sums`_
program. Dependencies required for integration or experimentation
purposes can be added to the main image as well. For example,
``solidity`` is part of the main image as it is necessary for an
integration with the Ethereum testnet (see `asynchromix.sol`_ and
`asynchromix.py`_). The ``Dockerfile`` for the main image is maintained
in `initc3/HoneyBadgerMPC`__.


Guidelines for modifying the images
-----------------------------------
Changes to the parent or main Docker image may be needed for various
reasons. This section presents some suggestions on how to go about to
perform the necessary changes.

Modifications to the main HoneyBadgerMPC image
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The main image can be modified by simply modifying the Dockerfile under
`initc3/HoneyBadgerMPC <https://github.com/initc3/HoneyBadgerMPC>`_ and
making a pull request. See :ref:`contributing-new-code` for help on
making new contributions to HoneyBadgerMPC.

Build time
""""""""""
Changes to the main image should ideally preserve or reduce the build
time since this image is being built on Travis CI for pull requests
and needs to be built or re-built by those who are developing the
HoneyBadgerMPC code base.

Parent image digest
"""""""""""""""""""
The parent image digest specified in the ``FROM`` statements controls
which version of the parent image will be used. This digest should only
be changed when that is indeed the intention! See
:ref:`use-new-parent-image` to modify the parent image version in the
main image, `honeybadgermpc
<https://hub.docker.com/repository/docker/initc3/honeybadgermpc>`_.


Adding, or modifying a core dependency
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
For dependencies that can be added via a package manager like ``apt``
or ``pip`` you can simply add, or update the version of the dependency
using the package manager.

For dependencies that must be built from source, adding or modifying
the dependency can be done in three or four phases:

1. Modify the main image, by modifying the `Dockerfile
   <https://github.com/initc3/HoneyBadgerMPC/blob/dev/Dockerfile>`_
   under ``initc3/HoneyBadgerMPC``.
2. Create a standalone image such as `NTL`_.
3. Using the standalone image as a stage add the dependency to the main
   or parent image. See `Use an external image as a "stage"`_.
4. If adding the dependency to the parent image, then change the
   sha256 digest of the parent image in the ``FROM`` statements in the
   main image.

A core dependency (that does not depend on the source code of
HoneyBadgerMPC) can always be added to the main image first, and moved
to the parent image at a later time. This may be convenient for
testing, experimentation or troubleshooting purposes.

Modifying an existing core dependency can also be done in the main
image. For instance, if the goal was to upgrade an existing dependency,
like the Rust version, this could be done first in the main image by
installing the new version and making it the default one.

Modifications of honeybadgermpc-deps (parent image)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Modifications to the parent image must be done via a pull request on
the repository `initc3/docker-honeybadgermpc-deps`_.

Once a pull request is merged, a new image will be built and pushed to
Docker Hub. When an image is pushed a sha256 digest of the image is
generated. The sha256 digest is used as an identifier in Dockerfiles
in ``FROM`` and ``--from=`` statements.


.. _use-new-parent-image:

Using a new parent image in honeybadgermpc (main image)
"""""""""""""""""""""""""""""""""""""""""""""""""""""""
In order to use a new parent image in the `honeybadgermpc
<https://hub.docker.com/repository/docker/initc3/honeybadgermpc>`_
image, the sha256 digest in the ``FROM`` statements:

.. code-block:: dockerfile

   # Dockerfile for honeybadgermpc image
   ARG HBMPC_DEPS_DIGEST="46902d869ea881d7b00b72ff6accf2558a5e15849da5fa5cc722b4ff82a507f8"

   FROM initc3/honeybadgermpc-deps@sha256:$HBMPC_DEPS_DIGEST


of the `HoneyBadgerMPC Dockerfile`_ must point to the targeted parent
image. Changing the parent image can be done in two ways:

1. Using ``docker build --build-arg HBMPC_DEPS_DIGEST=<new_digest> ...``
2. Changing the default value of ``HBMPC_DEPS_DIGEST`` in the
   ``Dockerfile``.

**Image digest generation.**  The image digest is generated when the
image is pushed to Docker Hub. For `honeybadgermpc-deps`_ this
happens when a pull request is merged in the ``master`` branch of the
`initc3/docker-honeybadgermpc-deps`_ repository.




.. __: https://hub.docker.com/repository/docker/initc3/honeybadgermpc
.. __: https://github.com/initc3/HoneyBadgerMPC
.. _honeybadgermpc-deps: https://hub.docker.com/repository/docker/initc3/honeybadgermpc-deps
.. _initc3/docker-honeybadgermpc-deps: https://github.com/initc3/docker-honeybadgermpc-deps
.. _HoneyBadgerMPC Dockerfile: https://github.com/initc3/HoneyBadgerMPC/blob/dev/Dockerfile
.. _pairing: https://github.com/initc3/HoneyBadgerMPC/tree/dev/pairing<Paste>
.. _compute-power-sums: https://github.com/initc3/HoneyBadgerMPC/blob/dev/apps/asynchromix/cpp/compute-power-sums.cpp
.. _asynchromix.sol: https://github.com/initc3/HoneyBadgerMPC/blob/dev/apps/asynchromix/asynchromix.sol
.. _asynchromix.py: https://github.com/initc3/HoneyBadgerMPC/blob/dev/apps/asynchromix/asynchromix.py
.. _debian packages: https://www.debian.org/distrib/packages
.. _pypi: https://pypi.org/
.. _FLINT: https://hub.docker.com/repository/docker/initc3/flint2
.. _NTL: https://hub.docker.com/repository/docker/initc3/ntl
.. _PBC: https://hub.docker.com/repository/docker/initc3/pbc
.. _Charm-crypto: https://hub.docker.com/repository/docker/initc3/charm-crypto
.. _Rust nightly frozen: https://hub.docker.com/repository/docker/initc3/rust-frozen
.. _Use an external image as a "stage": https://docs.docker.com/develop/develop-images/multistage-build/#use-an-external-image-as-a-stage
