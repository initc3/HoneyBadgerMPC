HoneyBadgerMPC Tutorial
==
This folder [(`apps/tutorial`)](./) contains a few tutorials as a starting point for developing with HoneyBadgerMPC. The tutorials assume you have a working development environment (instructions). 


I. [`hbmpc-tutorial-1.py`](./hbmpc-tutorial-1.py)
--
The first tutorial gives a tour of the MPC programming environment. To summarize:
- Secret shares are represented by a `Share` object.
- linear operations on `Share` objects are just computed locally
- `share.open()`: causes the servers to communicate with each other to open a share
- `ctx.preproc.get_random()`: (and related functions) can be used to get fetch random `Share`s from preprocessing. This is used when multiplying two `Share` objects
- a `Share` supports dataflow programming with Futures, like in Viff
- `SharreArray(shares).open()`: batch methods (TODO)
- an MPC program run is always run in an MPC context, like `def my_mpc_program(ctx, ...)`. When it's running, `ctx.myid` gives the name of the currently running server
- The simplest way to run the MPC program is with `TaskProgramRunner`, which runs each server as a lightweight process in a simulated network. This is the simplest operating mode, so it's the way to start when writing an MPC program and testing it
- There are some lines you can uncomment to simulate Byzantine faults and see how HoneyBadgerMPC handles them

Simple MPC programs:
- `beaver_multiply` the hello world of MPC program
- `random_permute_pair` as used in the mixing application
- `dot product` 

More examples of this programming model can be found in:
- [`honeybadgermpc/progs/mixins/share_arithmetic.py`](../../honeybadgermpc/progs/mixins/share_arithmetic.py)
- operations on fixed-point numbers (rather than field elements) [honeybadgermpc/progs/fixedpoint.py](../../honeybadgermpc/progs/fixedpoint.py) (TODO)
- [`honeybadgermpc/progs/mimc.py`](../../honeybadgermpc/progs/mimc.py)  symmetric key cryptography
- [`honeybadgermpc/progs/jubjub.py`](../../honeybadgermpc/progs/jubjub.py)  public key cryptography
- [`apps/asynchromix/butterfly_network.py`](../../apps/asynchromix/butterfly_network.py)  switching network based on the random pair permutation

To check the development environment works:
- Follow [these instructions](../../docs/development/getting-started.rst#managing-your-development-environment-with-docker-compose) to set up the `docker-compose` development environment
- The tutorials assume you have a shell session in the development container, so run:
```
$ docker-compose run --rm honeybadgermpc bash
root@{containerid}:/usr/src/HoneyBadgerMPC# python apps/tutorial/hbmpc-tutorial-1.py
```
and look for the output `Tutorial 1 ran successfully`

II. [`hbmpc-tutorial-2.py`](./hbmpc-tutorial-2.py)
---
The second tutorial shows how to run the MPC program in different processes that communicate over sockets. Run it with 
```
scripts/launch-tmuxlocal.sh apps/tutorial/hbmpc-tutorial-2.py conf/mpc/local
```
This scripts launches `4` processes (in the `n=4,t=1` setting) each in its own terminal subwindow.
You can crash one other terminals at any time, the rest will still be available.

This script also creates a simulated latency using the `tc` tool (look for the call to [`scripts/latency-control.sh`](../../scripts/latency-control.sh). The latency and jitter can be changed by modifying the script.

III. Blockchain integration
---
Tutorial coming soon... but for now you can run and look at the examples in [`apps/asynchromix`](../asynchromix) which uses Ethereum (`web3py` library, and a Solidity smart contract) as an MPC coordinator and broadcast channel.
```
python apps/asynchromix/asynchromix.py
```
