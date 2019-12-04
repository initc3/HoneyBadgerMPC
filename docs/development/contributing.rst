.. _contributing-new-code:

Contributing new code
=====================
Since `git`_  and `github`_ are used to version and host the code, one needs
to learn to work with both tools.


Suggested Git/Github workflow
-----------------------------
A small example of a possible workflow is provided here. This is by no means a
complete guide on how to work with Git and Github. The `Pro Git book`_ can be
a very useful reference, whether one is a beginner or an advanced user.

.. _git-remotes:

Working with Git Remotes
^^^^^^^^^^^^^^^^^^^^^^^^
First make sure your **git remotes** are properly set, and if not consult
`Configuring a remote for a fork`_ or `Git Basics - Working with Remotes`_ for
more detailed explanations about remotes. The remote names are just
conventions but in order to simplify this documentation we'll adopt the
conventions. So by convention, ``upstream`` should point to the "shared"
repository, whereas ``origin`` should point to your fork. Use
``git remote -v`` to perform the check:

.. code-block:: shell-session

    $ git remote -v
    origin  git@github.com:<github_username>/HoneyBadgerMPC.git (fetch)
    origin  git@github.com:<github_username>/HoneyBadgerMPC.git (push)
    upstream        git@github.com:initc3/HoneyBadgerMPC.git (fetch)
    upstream        git@github.com:initc3/HoneyBadgerMPC.git (push)

Identify the shared remote branch
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
What should be the base (remote) branch for your work? In many cases, if not
most, it'll be the default `dev`_ branch, but in other cases you may need to
base your work on some other branch, such as `jubjub`_.

It is convenient to have a local copy of the remote shared branch that you
need to work on. As an example, if you need to contribute work to the
`jubjub`_ branch:

.. code-block:: shell-session

    $ git fetch upstream
    $ git checkout -b jubjub upstream/jubjub

In order to keep your local copy up-to-date you should periodically sync it
with the remote. First switch to the local branch:

.. code-block:: shell-session

    $ git fetch upstream
    $ git rebase upstream/jubjub jubjub

There are multiple ways to work with remote branches. See
https://git-scm.com/book/en/v2/Git-Branching-Remote-Branches for more
information.

For a small discussion regarding the differences between rebasing and merging
see https://git-scm.com/book/en/v2/Git-Branching-Rebasing#_rebase_vs_merge.


Create a new branch
^^^^^^^^^^^^^^^^^^^
Create a new branch from the shared remote branch to which you wish to
contribute. As an example, say you are working on `issue #23 (Implement jubjub
elliptic curve MPC programs)`_, then you could create a new branch like so:

.. code-block:: shell-session

    $ git checkout -b issue-23-jujub-ec-mpc jubjub

You can name the branch whatever you like, but you may find it useful to
choose a meaningful name along with the issue number you are working on.

Do you work, backup, and stay in sync
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
As you are adding new code, making changes etc you may want to push your work
to your remote on Github, as this will serve as a backup:

.. code-block:: shell-session

    $ git push origin issue-23-jujub-ec-mpc


In addtion to backing up your work on Github you should stay in sync with
the shared remote branch. To do so, periodically ``fetch`` and ``rebase``:

.. code-block:: shell-session

    $ git fetch upstream
    $ git rebase upstream/jubjub issue-23-jujub-ec-mpc

Git commit best practices
^^^^^^^^^^^^^^^^^^^^^^^^^
It is a good idea to familiarize yourself with good practices for the commits
you make when preparing a pull request. A few references are provided here for
the time being and as the ``honeybadgermpc`` project evolves we'll document
good practices that are most relevant to the project.

* https://en.wikipedia.org/wiki/Separation_of_concerns
* https://wiki.openstack.org/wiki/GitCommitMessages#Information_in_commit_messages
* https://www.slideshare.net/TarinGamberini/commit-messages-goodpractices
* http://who-t.blogspot.com/2009/12/on-commit-messages.html

Signing commits
^^^^^^^^^^^^^^^
To sign your commits follow the steps outlined at
https://help.github.com/articles/signing-commits/.

.. rubric:: Resources

* https://git-scm.com/book/en/v2/Git-Tools-Signing-Your-Work
* https://softwareengineering.stackexchange.com/questions/212192/what-are-the-advantages-and-disadvantages-of-cryptographically-signing-commits-a

Making a pull request
^^^^^^^^^^^^^^^^^^^^^
Once you are done with your work, you have to push it to your remote:

.. code-block:: shell-session

    $ git push origin issue-23-jujub-ec-mpc

and then you can `make a pull request`_ to merge your work with the shared
remote branch that you have based your work on.

Pull requests go through the following checks:

* unit tests
* code quality
* documentation quality
* code coverage

These checks are performed using `Travis CI`_ and `Codecov`_. These checks are
there to help keeping the code in good shape and pull requests should ideally
pass these 4 checks before being merged.

Ideally, you want your pull request to address one concern, such that you can
`squash`_ your work into a single commit. An example of a project that uses
this approach is `google/leveldb
<https://github.com/google/leveldb#submitting-a-pull-request>`_.

If you need help to work with the git `rebase`_ command, see Github Help
`About Git rebase`_.


Tests
-----
A pull request should ideally be accompanied by some tests. Code coverage is
checked on Travis CI via codecov. The coverage requirements are defined in the
:file:`.codecov.yaml` file. See codecov's documentation on
`coverage configuration`_ for more information about the codecov.yaml file.

`pytest`_ is the framework used to write tests and it is probably a good idea
to consult its documentation once in a while to learn new tricks as it may
help a lot when writing tests. For instance, learning to work with
`pytest fixtures`_ can help greatly to simplify tests, and re-use test
components throughout the test code.

**Interesting resource on writing unit tests:**:
https://pylonsproject.org/community-unit-testing-guidelines.html


Coding Conventions
------------------
`PEP 8`_ is used as a guide for coding conventions. The maximum line length is
set at 89 characters.

The `flake8`_ tool is used in the continuous integration phase to check the
code quality. The configuration file, ``.flake8``, is under the project root.

.. tip:: **Recommended reading:** The `Code Style`_ section in the
    `The Hitchhiker’s Guide to Python!`_.

Documentation Conventions
-------------------------
`PEP 257`_ is used for docstring conventions. The docstrings are extracted out
into the documentation with the `autodoc`_ Sphinx extension and should be
valid reStructuredText. Here's an example of how a function may be documented:

.. todo:: Use a HoneyBadgerMPC code sample instead of sample shown below.

.. code-block:: python

    def send_message(sender, recipient, message_body, [priority=1]):
        """Send a message to a recipient

        :param str sender: The person sending the message
        :param str recipient: The recipient of the message
        :param str message_body: The body of the message
        :param priority: The priority of the message, can be a number 1-5
        :type priority: integer or None
        :return: the message id
        :rtype: int
        :raises ValueError: if the message_body exceeds 160 characters
        :raises TypeError: if the message_body is not a basestring
        """

See Sphinx documentation: `info field lists`_, for more information on how to
document Python objects.

.. tip:: **Recommended reading:** The `Documentation
    <https://docs.python-guide.org/writing/documentation/>`_ section in the
    `The Hitchhiker’s Guide to Python!`_ is a useful resource.

.. _when-to-ignore-conventions:

Ignoring conventions
--------------------
The `PEP 8`_ style guide has a very important section at the beginning:
`A Foolish Consistency is the Hobgoblin of Little Minds`_. It says:

    *One of Guido’s key insights is that code is read much more often than it
    is written. The guidelines provided here are intended to improve the
    readability of code and make it consistent across the wide spectrum of
    Python code. As* `PEP 20`_ *says, "Readability counts".*

    *A style guide is about consistency. Consistency with this style guide is
    important. Consistency within a project is more important. Consistency
    within one module or function is the most important.*

    *However, know when to be inconsistent—sometimes style guide
    recommendations just aren't applicable. When in doubt, use your best
    judgment. Look at other examples and decide what looks best. And don’t
    hesitate to ask!*

So if you need to ignore some convention(s), and doing so make one or more
checks fail you can `ignore the error inline`_ with the
``# noqa: <error code>`` comment. As an example, say you wanted to ignore
``E221`` (multiple spaces before operator) errors:

.. code-block:: python

    coin_recvs = [None] * N
    aba_recvs  = [None] * N  # noqa: E221
    rbc_recvs  = [None] * N  # noqa: E221

See `Selecting and Ignoring Violations`_ for more information about ignoring
violations reported by `flake8`_.

.. rubric:: Error codes

* flake8: http://flake8.pycqa.org/en/latest/user/error-codes.html
* pycodestyle: https://pycodestyle.readthedocs.io/en/latest/intro.html#error-codes
* pydocstyle: http://www.pydocstyle.org/en/2.1.1/error_codes.html


Logging
-------
Make use of the :mod:`logging` module! If you are unsure about whether you
should log or print, or when you should log, see `When to use logging`_.

Important resources on logging
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
* Python documentation: `Logging HOWTO`_
* Python documentation: `Logging Cookbook`_
* The Hitchhiker’s Guide to Python!: `Logging
  <https://docs.python-guide.org/writing/logging/>`_
* `Plumber Jack`_ Stuff about Python's logging package. By `Vinay Sajip`_,
  main author of the :mod:`logging` module.



Rust bindings
-------------
.. todo:: Document important things to know when contributing to this
    component.

References
----------
* `Pro Git Book`_
* `The Hitchhiker’s Guide to Python!`_
* `On the role of scientific thought`_ by Edsger W. Dijkstra


.. _git: https://git-scm.com/
.. _github: https://help.github.com/
.. _git basics - working with remotes: https://git-scm.com/book/en/v2/Git-Basics-Working-with-Remotes
.. _configuring a remote for a fork: https://help.github.com/articles/configuring-a-remote-for-a-fork/
.. _dev: https://github.com/initc3/HoneyBadgerMPC/tree/dev
.. _jubjub: https://github.com/initc3/HoneyBadgerMPC/tree/jubjub
.. _make a pull request: https://help.github.com/articles/creating-a-pull-request-from-a-fork/
.. _Pro Git Book: https://git-scm.com/book/en/v2
.. _rebase: https://git-scm.com/docs/git-rebase
.. _squash: https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History#Squashing-Commits
.. _About Git rebase: https://help.github.com/articles/about-git-rebase/
.. _Travis CI: https://docs.travis-ci.com/
.. _Codecov: https://codecov.io/
.. _pep 8: http://pep 8.org/
.. _pep 257: https://www.python.org/dev/peps/pep-0257/
.. _pep 20: https://www.python.org/dev/peps/pep-0020/
.. _flake8: http://flake8.pycqa.org/en/latest/index.html
.. _issue #23 (Implement jubjub elliptic curve MPC programs): https://github.com/initc3/HoneyBadgerMPC/issues/23
.. _Coverage Configuration: https://docs.codecov.io/docs/coverage-configuration
.. _pytest: https://docs.pytest.org/
.. _pytest fixtures: https://docs.pytest.org/en/latest/fixture.html#fixture
.. _The Hitchhiker’s Guide to Python!: https://docs.python-guide.org/
.. _code style: https://docs.python-guide.org/writing/style/
.. _autodoc: http://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
.. _info field lists: http://www.sphinx-doc.org/en/master/usage/restructuredtext/domains.html#info-field-lists
.. _when to use logging: https://docs.python.org/3/howto/logging.html#when-to-use-logging
.. _logging howto: https://docs.python.org/3/howto/logging.html
.. _logging cookbook: https://docs.python.org/3/howto/logging-cookbook.html
.. _plumber jack: http://plumberjack.blogspot.com/
.. _Vinay Sajip: https://github.com/vsajip
.. _A Foolish Consistency is the Hobgoblin of Little Minds: http://pep 8.org/#a-foolish-consistency-is-the-hobgoblin-of-little-minds
.. _Selecting and Ignoring Violations: http://flake8.pycqa.org/en/latest/user/violations.html
.. _ignore the error inline: http://flake8.pycqa.org/en/latest/user/violations.html#in-line-ignoring-errors
.. _On the role of scientific thought: http://www.cs.utexas.edu/users/EWD/transcriptions/EWD04xx/EWD447.html
