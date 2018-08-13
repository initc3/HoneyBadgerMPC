# HoneyBadgerMPC

Dependencies: python3, gmp, web3, ethereumjs-testrpc

To run a test case:
    
```bash
python -m honeybadgermpc.passive
```

or alternatively:

```bash
pytest -v tests/test_passive.py -s
```
     
This generates and opens 1000 zero-sharings, `N=3` `t=2` (so no fault tolerance)

# Protocol Descriptions
#### HBAVSS
An Asynchronous Verifiable Secret Sharing protocol. Allows a dealer to share a secret with n parties such that any t+1 of the honest parties can reconstruct it. For our purposes (achieving optimal Byzantine Fault Tolerance), we will always be using n = 3t+1.

**Input**: One secret the size of a field element

**Output**: n parties will have a t-shared share of the secret

#### BatchHBAVSS
An altered version of HBAVSS that allows for the more efficient sharing of a batch of secrets. Details to be worked out soon (TM).

#### ReliableBroadcast
A protocol which allows a broadcaster to send the same message to n different recipients in a bandwidth-saving way, while being assured that every recipient eventually receives the full correct message.

**Input**: One message to be broadcasted

**Output**: n parties will eventually successfully receive the message

#### BatchReconstruction
A protocol to reconstruct many secrets at once with fewer messages

**Input**:  At least *t+1* parties input their shares of *t+1* total *t*-shared secrets 

**Output**: *t+1* reconstructed secrets are output to every participating party

#### Rand
A protocal that generates a random secret-shared value, which nobody will know until it is reconstructed

#### BatchRand
An effiecient batched version of Rand

#### BatchBeaverMultiplication 
Perform multiple shared-secret multiplications at once

**Input**: *n t*-shared pairs of secrets that one wishes to multiply and n sets of beaver triples. *2n >= t+1*

**Output**: *n t*-shared secret pairs that have been successfully multiplied

#### TripleTransformation: 
Turns a set of triples into a set of co-related and secret-shared triples. This plus Polynomial Verification together can tell you if all of your input triples are multiplication triples.
> Co-related triples are triples that make up points on polynomials *A*(), *B*(), and *C*() such that *A*()**B*() = *C*(), i.e. *A*(*i*)**B*(*i*) = *C*(*i*) for any *i*

**Input**: *m independent t*-shared triples, where *m = 2d + 1* and *d >= t*. 
>Note the if we have *d == t*, then this whole process gives 1 multiplication triple, but can tolerate the most dropouts. On the other hand, if d = 3t/2, we have m = 3t + 1 and hence have the best efficiency but require all parties to provide correct input to proceed.

**Output**:  *m t*-shared, co-related triples

#### PolynomialVerification: 
Determine if the triples output from TripleTransformation are multiplication triples.

**Input**: *n* different *t*-shared outputs of TripleTransformation

**Output**: Knowledge of which polynomials one can extract multiplication triples from

#### TripleExtraction: 
Extract unknown random multiplication triples from a set of co-related multiplication triples.

**Input**: *n* different polynomials formed by t-shared co-related multiplication triples

**Output**: *(d + 1 - t) t*-shared random triples, where *d* is the degree of polynomials *A*() and *B*()
