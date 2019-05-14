# Roadmap

*draft*

## Benchmarking

* Measure the number of Beaver triples that can be generated per seconds.
* Become aware of where the bottlenecks are, for each subprotocol.
* One performance goal is to be able to have similar performance metrics as viff
  with better robustness and capability to support a larger number of participants.
* Figure out how well the protocol performs for real-world applications such as the
  sugar beets auction.
* Identify which parts of the implementation need performance optimizations, and
  write C or Rust extensions for these parts.

## Project structure

* Refine the project structure over time to reflect the modularity and composability
  of the protocol.
* Possibly, eventually package and distribute the key sub-protocols as standalone,
  re-usable software libraries/packages which can be used in diverse larger protocols.
