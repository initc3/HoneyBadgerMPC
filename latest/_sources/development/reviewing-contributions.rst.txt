Reviewing and merging pull requests
===================================
.. todo:: Document some guidelines when reviewing and merging pull requests.
    See https://cryptography.io/en/latest/development/reviewing-patches/#reviewing-and-merging-patches as an inspiration.


Merge Requirements
------------------
.. todo:: Come up with merge requirements with the team.

    We can use the following from the `cryptography`_ project as an
    inspiration:

    * Patches must *never* be pushed directly to ``master|dev``, all changes
      (even the most trivial typo fixes!) must be submitted as a pull request.
    * A committer may *never* merge their own pull request, a second party
      must merge their changes. If multiple people work on a pull request, it
      must be merged by someone who did not work on it.
    * A patch that breaks tests, or introduces regressions by changing or
      removing existing tests should not be merged. Tests must always be
      passing on ``master|dev``.
    * If somehow the tests get into a failing state on ``master|dev`` (such as
      by a backwards incompatible release of a dependency) no pull requests
      may be merged until this is rectified.
    * All merged patches must have 100% test coverage.


.. rubric:: Merge vs Rebase vs Squash

.. todo:: Explain the difference between the three and which method should be
    used. Basically, propose to use rebase or squash in order to simplify the
    git history. Find a good resource on the topic.


References
----------
* https://github.community/t5/Support-Protips/Best-practices-for-pull-requests/ba-p/4104
* https://help.github.com/articles/about-pull-request-reviews/A


.. _cryptography: https://github.com/pyca/cryptography/
