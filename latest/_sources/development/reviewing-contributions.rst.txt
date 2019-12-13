Reviewing and merging pull requests
===================================
From the `cryptography`_ project:

    Everyone is encouraged to review open pull requests. We only ask that you
    try and think carefully, ask questions and
    `are excellent to one another`_. **Code review is our opportunity to share
    knowledge, design ideas and make friends.**

    -- https://cryptography.io/en/latest/development/reviewing-patches/#reviewing-and-merging-patches

Merge Requirements
------------------
The following has been taken directly as is from the `merge requirements of
the cryptography project
<https://cryptography.io/en/latest/development/reviewing-patches/#merge-requirements>`__
and is suggested as an inspiration, meaning that it can be followed **with a
good dose of tolerance and understanding**.

    Because cryptography is so complex, and the implications of getting it
    wrong so devastating, `cryptography`_ has a strict merge policy for
    committers:

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

    The purpose of these policies is to minimize the chances we merge a change
    that jeopardizes our users' security.

    -- https://cryptography.io/en/latest/development/reviewing-patches/#merge-requirements


About pull request merges
-------------------------
Github's interface for merging pull requests offers three options:

* `Create a merge commit`_
* `Squash and merge`_
* `Rebase and merge`_

In order to simplify the Git history, the squash or rebase options can be
used. Ideally the committer can squash their work into a single commit before
making the pull request, and then rebase can be used to merge the pull
request.

If the pull request contains multiple commits, squash can be used.

As an example, the `LevelDB`_ project has the following requirement:

    In order to keep the commit timeline linear `squash`_ your changes down to
    a single commit and `rebase`_ on google/leveldb/master. This keeps the
    commit timeline linear and more easily sync'ed with the internal
    repository at Google. More information at GitHub's `About Git rebase`_
    page.

    -- https://github.com/google/leveldb#submitting-a-pull-request


References
----------
* https://github.community/t5/Support-Protips/Best-practices-for-pull-requests/ba-p/4104
* https://help.github.com/articles/about-pull-request-reviews/
* https://help.github.com/articles/merging-a-pull-request/
* https://help.github.com/categories/collaborating-with-issues-and-pull-requests/


.. _cryptography: https://github.com/pyca/cryptography/
.. _are excellent to one another: https://speakerdeck.com/ohrite/better-code-review
.. _Create a merge commit: https://help.github.com/articles/about-pull-request-merges/
.. _Squash and merge: https://help.github.com/articles/about-pull-request-merges/#squash-and-merge-your-pull-request-commits
.. _Rebase and merge: https://help.github.com/articles/about-pull-request-merges/#rebase-and-merge-your-pull-request-commits
.. _rebase: https://git-scm.com/docs/git-rebase
.. _squash: https://git-scm.com/book/en/v2/Git-Tools-Rewriting-History#Squashing-Commits
.. _About Git rebase: https://help.github.com/articles/about-git-rebase/
.. _leveldb: https://github.com/google/leveldb
