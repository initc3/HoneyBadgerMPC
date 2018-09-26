Introduction
============
HoneyBadgerMPC is a research project under active development that aims to be
a novel confidentiality layer for consortium blockchains.

HoneyBadgerMPC is the first system implementation of asynchronous MPC.

HoneyBadgerMPC is the first MPC toolkit to provide all the following desired
properties:

* Scales to large number of nodes (5 to 50). *Viff fails at this!*
* Guarantees output even if some nodes crash or are compromised recent
  developments like SPDZ and EMP-Toolkit fail at this.
* Prevents data breaches even if some nodes are compromised.


Motivation Use Case: Supply Chain Tracking
------------------------------------------

.. rubric:: Security Goals

* **Integrity and consistency:**
    * Records cannot be modified or removed without leaving an audit trail.
    * All parties can see a consistent view of records.
* **Availability:**
    * No one can be prevented from submitting or reading a record.
* **Privacy:**
    * Names of participants, business relationships, are proprietary &
      sensitive.


Blockchain databases today: Hyperledger Fabric
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. todo:: Keep going!
