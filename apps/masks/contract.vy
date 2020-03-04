struct PreProcessCount:
    inputmasks: uint256     # [r]

struct Input:
    masked_input: bytes32   # (m+r)
    inputmask: uint256      # index in inputmask of mask [r]
    # Extension point: add more metadata about each input

# NOTE This is a work around the problem of not having dynamic arrays
# in vyper, and not being able to get how many elements have been inserted
# at a given point in time in a queue.
# FIXME Perhaps a mapping would be sufficient, such that the key would point
# to a unique id for an element that is being queued ...
struct InputQueue:
    queue: Input[500]
    size: uint256

# FIXME A map may be enough.
struct OutputHashes:
    hashes: bytes32[100]
    size: uint256


# FIXME A map may be enough.
struct OutputVotes:
    votes: uint256[100]
    size: uint256


#####################################################################
# events
#####################################################################
# NOTE not sure if needed, commenting for now
# PreProcessUpdated: event({})
InputMaskClaimed: event({client: address, inputmask_idx: uint256})
MessageSubmitted: event({idx: uint256, inputmask_idx: uint256, masked_input: bytes32})
MpcEpochInitiated: event({epoch: uint256})

# NOTE vyper does not allow dynamic arrays, so we have to set the maximum
# expected length of the output. The output string can contain up through
# the maximum number of characters. Meaning: x = string[100], x can be
# 1 to 100 character long.
MpcOutput: event({epoch: uint256, output: string[100]})

# NOTE: Not sure if there's a way around this ... must
# hardcode number of participants
N: constant(uint256) = 4

# Session parameters
t: public(uint256)
servers: public(address[4])
servermap: public(map(address, int128))

# Consensus count (min of the player report counts)
_preprocess: PreProcessCount

# How many of each have been reserved already
preprocess_used: public(PreProcessCount)

# Report of preprocess buffer size from each server
# mapping ( uint => PreProcessCount ) public preprocess_reports;
preprocess_reports: public(map(int128, PreProcessCount))

# maps each element of preprocess.inputmasks to the client (if any) that claims it
inputmasks_claimed: public(map(uint256, address))
inputmask_map: public(map(uint256, bool))   # Maps a mask
_input_queue: InputQueue     # All inputs sent so far

inputs_unmasked: public(uint256)
epochs_initiated: public(uint256)
outputs_ready: public(uint256)
output_hashes: public(OutputHashes)
output_votes: public(OutputVotes)
server_voted: public(map(int128, uint256))     # highest epoch voted in


@public
@constant
def n() -> uint256:
    return N


@public
def __init__(_servers: address[N], _t: uint256):
    assert 3 * _t < N
    self.t = _t

    for i in range(N):
        self.servers[i] = _servers[i]
        self.servermap[_servers[i]] = i + 1   # servermap is off-by-one


##############################################################################
# 1. Preprocessing Buffer (the MPC offline phase)                            #
##############################################################################
@public
def preprocess() -> uint256:
    return self._preprocess.inputmasks


@public
def inputmasks_available() -> uint256:
    return self._preprocess.inputmasks - self.preprocess_used.inputmasks


@public
def input_queue(epoch: int128) -> Input:
    # TODO clean up / simplify
    _input: Input = self._input_queue.queue[epoch]
    #return _input.inputmask, _input.inputmask_idx
    return _input


# TODO probably not needed as builtin min() is available
# also, notice that the name is not min() as this will cause a
# compilation error because min() is a built in.
@private
@constant
def _min(a: uint256, b: uint256) -> uint256:
    if a < b:
        return a
    else:
        return b


# TODO probably not needed as builtin max() is available
# see more details at _min() commments
@private
@constant
def _max(a: uint256, b: uint256) -> uint256:
    if a > b:
        return a
    else:
        return b


@public
def preprocess_report(rep: uint256[1]):
    #/ Update the Report 
    #    require(servermap[msg.sender] > 0);   // only valid servers
    assert self.servermap[msg.sender] > 0   # only valid servers
    id: int128 = self.servermap[msg.sender] - 1
    self.preprocess_reports[id].inputmasks = rep[0]

    # Update the consensus
    mins: PreProcessCount = PreProcessCount({inputmasks: 0})
    mins.inputmasks = self.preprocess_reports[0].inputmasks
    for i in range(1, N):
        mins.inputmasks = min(mins.inputmasks, self.preprocess_reports[i].inputmasks)

    # NOTE not sure if needed, commenting for now
    # if preprocess.inputmasks < mins.inputmasks:
    #     emit PreProcessUpdated()

    self._preprocess.inputmasks = mins.inputmasks


# ######################
# 2. Accept client input 
# ######################

# Step 2.a. Clients can reserve an input mask [r] from Preprocessing
@public
def reserve_inputmask() -> uint256:
    """Client reserves a random values.
    
    Extension point: override this function to add custom token rules
    """
    # An unclaimed input mask must already be available
    assert self._preprocess.inputmasks > self.preprocess_used.inputmasks

    # Acquire this input mask for msg.sender
    idx: uint256 = self.preprocess_used.inputmasks
    self.inputmasks_claimed[idx] = msg.sender
    self.preprocess_used.inputmasks += 1
    log.InputMaskClaimed(msg.sender, idx)
    return idx


# Step 2.b. Client requests (out of band, e.g. over https) shares of [r]
#           from each server. 
@public
def is_client_authorized(client: address, idx: uint256) -> bool:
    """Servers use this function to check authorization.
    
    Client requests (out of band, e.g. over https) shares of [r]
    from each server.

    Authentication using client's address is also out of band
    """
    return self.inputmasks_claimed[idx] == client


# Step 2.c. Clients publish masked message (m+r) to provide a new input [m]
#           and bind it to the preprocess input
@public
def submit_message(inputmask_idx: uint256, masked_input: bytes32):
    # TODO See whether using a map to maintain the input queue would work.
    # The caller would be required to pass a unique id along with the submitted
    # masked_input.
    #
    # Three elements:
    #
    # 1. masked_input
    # 2. identifier of the mask that was used
    # 3. identifier of the masked input, used for storing and retrieval

    # Must be authorized to use this input mask
    assert self.inputmasks_claimed[inputmask_idx] == msg.sender

    # Extension point: add additional client authorizations,
    # e.g. prevent the client from submitting more than one message per mix

    idx: uint256 = self._input_queue.size
    self._input_queue.size += 1

    self._input_queue.queue[idx].masked_input = masked_input
    self._input_queue.queue[idx].inputmask = inputmask_idx

    # QUESTION: What is the purpose of this event?
    log.MessageSubmitted(idx, inputmask_idx, masked_input)

    # The input masks are deactivated after first use
    self.inputmasks_claimed[inputmask_idx] = ZERO_ADDRESS


# ######################
# 3. Initiate MPC Epochs
# ######################

_K: constant(uint256) = 1  # number of messages per epoch


@public
@constant
def K() -> uint256:
    return _K

# TODO
# Step 3.a. Trigger MPC to start
@public
def inputs_ready() -> uint256:
    return self._input_queue.size - self.inputs_unmasked


@public
def initiate_mpc():
    # Must unmask eactly K values in each epoch
    assert self._input_queue.size >= self.inputs_unmasked + _K
    self.inputs_unmasked += _K
    log.MpcEpochInitiated(self.epochs_initiated)
    self.epochs_initiated += 1
    # FIXME not sure this is needed as the size does not appear to be used, at
    # least in the contract ... MUST check if needed by contract consumer(s).
    self.output_votes.size = self.epochs_initiated
    self.output_hashes.size = self.epochs_initiated


# Step 3.b. Output reporting: the output is considered "approved" once
#           at least t+1 servers report it

@public
def propose_output(epoch: uint256,  output: string[100]):
    assert epoch < self.epochs_initiated    # can't provide output if it hasn't been initiated
    assert self.servermap[msg.sender] > 0   # only valid servers
    id: int128 = self.servermap[msg.sender] - 1

    # Each server can only vote once per epoch
    # Hazard note: honest servers must vote in strict ascending order, or votes
    #              will be lost!
    assert epoch <= self.server_voted[id]
    self.server_voted[id] = max(epoch + 1, self.server_voted[id])

    output_hash: bytes32 = keccak256(output)

    if self.output_votes.votes[epoch] > 0:
        # All the votes must match
        assert output_hash == self.output_hashes.hashes[epoch]
    else:
        self.output_hashes.hashes[epoch] = output_hash

    self.output_votes.votes[epoch] += 1
    if self.output_votes.votes[epoch] == self.t + 1:   # at least one honest node agrees
        log.MpcOutput(epoch, output)
        self.outputs_ready += 1


@mpc
async def _prog(ctx, *, field_element):
    logging.info(f"[{ctx.myid}] Running MPC network")
    msg_share = ctx.Share(field_element)
    opened_value = await msg_share.open()
    opened_value_bytes = opened_value.value.to_bytes(32, "big")
    logging.info(f"opened_value in bytes: {opened_value_bytes}")
    msg = opened_value_bytes.decode().strip("\x00")
    return msg
