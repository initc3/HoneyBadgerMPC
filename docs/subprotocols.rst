Protocol Descriptions
=====================

HBAVSS
------
An Asynchronous Verifiable Secret Sharing protocol. Allows a dealer to share a
secret with :math:`n` parties such that any :math:`t+1` of the honest parties
can reconstruct it. For our purposes (achieving optimal Byzantine Fault
Tolerance), we will always be using :math:`n = 3t+1`.

**Input**: One secret the size of a field element

**Output**: :math:`n` parties will have a :math:`t`-shared share of the secret


BatchHBAVSS
-----------
An altered version of HBAVSS that allows for the more efficient sharing of a
batch of secrets. Details to be worked out soon (TM).


ReliableBroadcast
-----------------
A protocol which allows a broadcaster to send the same message to :math:`n`
different recipients in a bandwidth-saving way, while being assured that every
recipient eventually receives the full correct message.

**Input**: One message to be broadcasted

**Output**: :math:`n` parties will eventually successfully receive the message


BatchReconstruction
-------------------
A protocol to reconstruct many secrets at once with fewer messages

**Input**:  At least :math:`t+1` parties input their shares of :math:`t+1`
total :math:`t`-shared secrets

**Output**: :math:`t+1` reconstructed secrets are output to every
participating party


Rand
----
A protocal that generates a random secret-shared value, which nobody will know
until it is reconstructed


BatchRand
---------
An effiecient batched version of Rand


BatchBeaverMultiplication
-------------------------
Perform multiple shared-secret multiplications at once

**Input**: :math:`n` :math:`t`-shared pairs of secrets that one wishes to
multiply and :math:`n` sets of beaver triples. :math:`2n \geq t+1`

**Output**: :math:`n` :math:`t`-shared secret pairs that have been
successfully multiplied


TripleTransformation
--------------------
Turns a set of triples into a set of co-related and secret-shared triples.
This plus Polynomial Verification together can tell you if all of your input
triples are multiplication triples.

    Co-related triples are triples that make up points on polynomials
    :math:`A()`, :math:`B()`, and :math:`C()` such that

    .. math::

        A() \cdot B() = C(),

i.e. :math:`A(i) \cdot B(i) = C(i) \forall i`.

**Input**: :math:`m` *independent* :math:`t`-shared triples, where
:math:`m = 2d + 1` and :math:`d \geq t`.

    Note the if we have :math:`d == t`, then this whole process gives 1
    multiplication triple, but can tolerate the most dropouts. On the other
    hand, if :math:`d = 3t/2`, we have :math:`m = 3t + 1` and hence have the
    best efficiency but require all parties to provide correct input to
    proceed.

**Output**: :math:`m` :math:`t`-shared, co-related triples


PolynomialVerification
----------------------
Determine if the triples output from TripleTransformation are multiplication
triples.

**Input**: :math:`n` different :math:`t`-shared outputs of
TripleTransformation

**Output**: Knowledge of which polynomials one can extract multiplication
triples from


TripleExtraction
----------------
Extract unknown random multiplication triples from a set of co-related
multiplication triples.

**Input**: :math:`n` different polynomials formed by :math:`t`-shared
co-related multiplication triples

**Output**: :math:`(d + 1 - t)` :math:`t`-shared random triples, where
:math:`d` is the degree of polynomials :math:`A()` and :math:`B()`
