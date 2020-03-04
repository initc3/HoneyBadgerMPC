# Public Data Directory
This directory, `public-data`, serves the purpose of storing data that
does not require any privacy protection, and is meant to be accessible
by all participants involved in an MPC computation, including the
MPC servers, clients, coordinator, and any other entity that may play a
role in the MPC computation from the point of view of making its
execution a reality.

An example of such data is the address of the MPC coordinator contract,
which is needed by clients and MPC servers.

**NOTE**: This data is not meant to be tracked by a version control
system (git) as it may differ from one MPC protocol execution to
another.
