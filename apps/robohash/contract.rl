struct PreProcessCount:
    #inputmasks: uint256     # [r]
    cryptodna: uint256     # [r]
    triples: uint256        # [a],[b],[ab]
    bits: uint256           # [b] with b in {-1,1}

struct RobotRequest:
    # robot 1 details
    token_id_1: uint256         # robot unique id (maps to private genome aka cryptodna)
    public_genome_1: bytes32
    # robot 2 details
    token_id_2: uint256         # robot unique id (maps to private genome aka cryptodna)
    public_genome_2: bytes32
    # cryptodna
    token_id_3: uint256         # robot unique id (maps to private genome aka cryptodna)

# NOTE This is a work around the problem of not having dynamic arrays
# in vyper, and not being able to get how many elements have been inserted
# at a given point in time in a queue.
# FIXME Perhaps a mapping would be sufficient, such that the key would point
# to a unique id for an element that is being queued ...
struct RobotRequestQueue:
    queue: RobotRequest[500]
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
# NOTE BEGIN ROBOHASH state vars, structs, events
#####################################################################
# @dev Mapping from NFT ID to the address that owns it.
idToOwner: HashMap[uint256, address]

# @dev Mapping from NFT ID to approved address.
#idToApprovals: HashMap[uint256, address]
#
## @dev Mapping from owner address to count of his tokens.
ownerToNFTokenCount: HashMap[address, uint256]
#
## @dev Mapping from owner address to mapping of operator addresses.
#ownerToOperators: HashMap[address, HashMap[address, bool]]
#
## @dev Address of minter, who can mint a token
#minter: address
#
## @dev Mapping of interface id to bool about whether or not it's supported
#supportedInterfaces: HashMap[bytes32, bool]
#
## @dev ERC165 interface ID of ERC165
#ERC165_INTERFACE_ID: constant(bytes32) = 0x0000000000000000000000000000000000000000000000000000000001ffc9a7
#
## @dev ERC165 interface ID of ERC721
#ERC721_INTERFACE_ID: constant(bytes32) = 0x0000000000000000000000000000000000000000000000000000000080ac58cd

# additional stuff for robohash MPC app:
idToPublicGenome: HashMap[uint256, bytes32]
# idToApprovedPartners: HashMap[uint256, HashMap[uint256, bool]]
# GENDER_MASK: constant(bytes32) = 0x000000000000000000000000000000000000FF00000000000000000000000000
# MAX_TOKENS: constant(uint256) = 100
# ownerToTokenIds: HashMap[address, uint256[MAX_TOKENS]] # not sure if this is a valid structure
CREATED_TOKEN_COUNT: uint256

#####################################################################
# NOTE END - ROBOHASH
#####################################################################

#####################################################################
# events
#####################################################################
# NOTE not sure if needed, commenting for now
# PreProcessUpdated: event({})
event RobotRequestSubmitted:
    client: address
    token_id: uint256

event MpcEpochInitiated:
    epoch: uint256

# NOTE vyper does not allow dynamic arrays, so we have to set the maximum
# expected length of the output. The output String can contain up through
# the maximum number of characters. Meaning: x = String[1000], x can be
# 1 to 1000 character long.
event MpcOutput:
    epoch: uint256
    output: String[1000]

# NOTE: Not sure if there's a way around this ... must
# hardcode number of participants
N: constant(uint256) = 4

# Session parameters
t: public(uint256)
servers: public(address[4])
servermap: public(HashMap[address, int128])

# Consensus count (min of the player report counts)
_preprocess: PreProcessCount

# How many of each have been reserved already
preprocess_used: public(PreProcessCount)

# Report of preprocess buffer size from each server
preprocess_reports: public(HashMap[int128, PreProcessCount])

# maps each element of preprocess.inputmasks to the client (if any) that claims it
inputmasks_claimed: public(HashMap[uint256, address])
inputmask_map: public(HashMap[uint256, bool])   # Maps a mask
_robot_request_queue: RobotRequestQueue

robots_assembled: public(uint256)
epochs_initiated: public(uint256)
outputs_ready: public(uint256)
output_hashes: public(OutputHashes)
output_votes: public(OutputVotes)
server_voted: public(HashMap[int128, uint256])     # highest epoch voted in

# NOTE Our extensive testing confirm that god exists
# see apps/robohash/tests to test it yourself
god: public(address)
_eve_token_id: constant(uint256) = 0
_adam_token_id: constant(uint256) = 1
_eve_public_genome: constant(bytes32) = keccak256("eve")
_adam_public_genome: constant(bytes32) = keccak256("adam")

@external
@view
def eve_token_id() -> uint256:
    return _eve_token_id

@external
@view
def adam_token_id() -> uint256:
    return _adam_token_id


@external
@view
def n() -> uint256:
    return N


@external
def __init__(_servers: address[N], _t: uint256):
    assert 3 * _t < N
    self.t = _t

    self.idToPublicGenome[_eve_token_id] = _eve_public_genome
    self.idToPublicGenome[_adam_token_id] = _adam_public_genome
    self.god = msg.sender
    self.CREATED_TOKEN_COUNT = 2

    for i in range(N):
        self.servers[i] = _servers[i]
        self.servermap[_servers[i]] = i + 1   # servermap is off-by-one


##############################################################################
# 1. Preprocessing Buffer (the MPC offline phase)                            #
##############################################################################
@external
def preprocess() -> uint256:
    #return self._preprocess.inputmasks
    return self._preprocess.cryptodna

# XXX
#@external
#def inputmasks_available() -> uint256:
#    return self._preprocess.inputmasks - self.preprocess_used.inputmasks


@external
def cryptodna_available() -> uint256:
    return self._preprocess.cryptodna - self.preprocess_used.cryptodna


@external
def robot_request_queue(idx: int128) -> RobotRequest:
    _robot_request: RobotRequest = self._robot_request_queue.queue[idx]
    return _robot_request


@external
def preprocess_report(rep: uint256[3]):
    # Update the Report
    assert self.servermap[msg.sender] > 0   # only valid servers
    id: int128 = self.servermap[msg.sender] - 1
    self.preprocess_reports[id].cryptodna = rep[0]
    self.preprocess_reports[id].triples = rep[1]
    self.preprocess_reports[id].bits = rep[2]

    # Update the consensus
    mins: PreProcessCount = PreProcessCount({
        cryptodna: self.preprocess_reports[0].cryptodna,
        triples: self.preprocess_reports[0].triples,
        bits: self.preprocess_reports[0].bits,
    })
    for i in range(1, N):
        mins.cryptodna = min(mins.cryptodna, self.preprocess_reports[i].cryptodna)
        mins.triples = min(mins.triples, self.preprocess_reports[i].triples)
        mins.bits = min(mins.bits, self.preprocess_reports[i].bits)

    # NOTE not sure if needed, commenting for now
    # if (self._preprocess.cryptodna < mins.cryptodna or
    #     self._preprocess.triples < mins.triples or
    #     self._preprocess.bits < mins.bits):
    #     emit PreProcessUpdated()

    self._preprocess.cryptodna = mins.cryptodna
    self._preprocess.triples = mins.triples
    self._preprocess.bits = mins.bits


# ######################
# 2. Accept client input 
# ######################

# Step 2.b. Client requests (out of band, e.g. over https) shares of [r]
#           from each server. 
@external
def is_client_authorized(client: address, idx: uint256) -> bool:
    """Servers use this function to check authorization.
    
    Client requests (out of band, e.g. over https) shares of [r]
    from each server.

    Authentication using client's address is also out of band
    """
    return self.inputmasks_claimed[idx] == client


##############################################################################
# NOTE ROBOHASH
@internal
def _addTokenTo(_to: address, _tokenId: uint256):
    """
    @dev Add a NFT to a given address
         Throws if `_tokenId` is owned by someone.
    """
    # Throws if `_tokenId` is owned by someone
    assert self.idToOwner[_tokenId] == ZERO_ADDRESS
    # Change the owner
    self.idToOwner[_tokenId] = _to
    # Change count tracking
    self.ownerToNFTokenCount[_to] += 1
    # update the owner's token list

@external
def create_robot(_genes: bytes32):
    """
    @dev Use this to create a robot directly for demo.
    """
    _tokenId: uint256 = self.CREATED_TOKEN_COUNT
    self._addTokenTo(msg.sender, _tokenId)
    self.idToPublicGenome[_tokenId] = _genes
    self.CREATED_TOKEN_COUNT += 1

@external
def request_robot(_token_id_1: uint256, _token_id_2: uint256):
    """
    @dev Breed any 2 token Ids.
    """
    self.CREATED_TOKEN_COUNT += 1
    _token_id_3: uint256 = self.CREATED_TOKEN_COUNT
    self._addTokenTo(msg.sender, _token_id_3)
    log RobotRequestSubmitted(msg.sender, _token_id_3)
    # TODO Check that the token ids DO NOT map to EMPTY_BYTES32
    _mom_genome: bytes32 = self.idToPublicGenome[_token_id_1]
    assert _mom_genome != EMPTY_BYTES32
    _dad_genome: bytes32 = self.idToPublicGenome[_token_id_2]
    assert _dad_genome != EMPTY_BYTES32
    idx: uint256 = self._robot_request_queue.size
    self._robot_request_queue.size += 1
    self._robot_request_queue.queue[idx].token_id_1 = _token_id_1
    self._robot_request_queue.queue[idx].token_id_2 = _token_id_2
    self._robot_request_queue.queue[idx].public_genome_1 = _mom_genome
    self._robot_request_queue.queue[idx].public_genome_2 = _dad_genome
    self._robot_request_queue.queue[idx].token_id_3 = _token_id_3

# NOTE END ROBOHASH
##############################################################################

# ######################
# 3. Initiate MPC Epochs
# ######################

# Preprocessing requirements
_K: constant(uint256) = 32  # mix size
_PER_MIX_TRIPLES: constant(uint256) = (_K / 2) * 5 * 5   # k log^2 k
_PER_MIX_BITS: constant(uint256) = (_K / 2) * 5 * 5

@external
@view
def K() -> uint256:
    return _K


@external
@view
def PER_MIX_TRIPLES() -> uint256:
    return _PER_MIX_TRIPLES


@external
@view
def PER_MIX_BITS() -> uint256:
    return _PER_MIX_BITS


# Return the maximum number of mixes that can be run with the
# available preprocessing
@external
def pp_elems_available() -> uint256:
    triples_available: uint256 = self._preprocess.triples - self.preprocess_used.triples
    bits_available: uint256 = self._preprocess.bits - self.preprocess_used.bits
    return min(triples_available / _PER_MIX_TRIPLES, bits_available / _PER_MIX_BITS)

# Step 3.a. Trigger MPC to start
@external
def start_robot_assembly() -> uint256:
    return self._robot_request_queue.size - self.robots_assembled


@external
def initiate_mpc():
    # Must unmask eactly K values in each epoch
    assert self._robot_request_queue.size >= self.robots_assembled + _K
    # Can only initiate mix if enough preprocessings are ready
    assert self._preprocess.triples >= self.preprocess_used.triples + _PER_MIX_TRIPLES
    assert self._preprocess.bits >= self.preprocess_used.bits + _PER_MIX_BITS
    self.preprocess_used.triples += _PER_MIX_TRIPLES
    self.preprocess_used.bits += _PER_MIX_BITS
    self.robots_assembled += _K
    log MpcEpochInitiated(self.epochs_initiated)
    self.epochs_initiated += 1
    # FIXME not sure this is needed as the size does not appear to be used, at
    # least in the contract ... MUST check if needed by contract consumer(s).
    self.output_votes.size = self.epochs_initiated
    self.output_hashes.size = self.epochs_initiated


# Step 3.b. Output reporting: the output is considered "approved" once
#           at least t+1 servers report it

@external
def propose_output(epoch: uint256,  output: String[1000]):
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
        log MpcOutput(epoch, output)
        self.outputs_ready += 1


@mpc
async def prog(ctx, *, robot_details):
    logging.info(f"[{ctx.myid}] Running MPC network")
    p1 = robot_details[0]['parent_1']
    p2 = robot_details[0]['parent_2']
    kd = robot_details[0]['kid']
    p1_genome = p1[1].hex()
    p2_genome = p2[1].hex()
    p1_cryptodna = p1[2]
    p2_cryptodna = p2[2]
    kd_cryptodna = kd[1]
    cryptodna_shares = (
        ctx.Share(p1_cryptodna),
        ctx.Share(p2_cryptodna),
        ctx.Share(kd_cryptodna),
    )
    cryptodna_sharearray = ctx.ShareArray(cryptodna_shares)
    hasharray = []
    blocksize = int(len(p1_genome) / 11)
    p1_color = int(p1_genome[0:blocksize], 16)
    p2_color = int(p2_genome[0:blocksize], 16)
    for i in range(0, 11):
        # Get 1/numblocks of the hash
        currentstart = (1 + i) * blocksize - blocksize
        currentend = (1 + i) * blocksize
        # this is the part where Amit's code goes to flip biased coin
        #secret_biased_coin = await flip_biased_coin(ctx, mom_secret_genome)
        #biased_coin = await secret_biased_coin.open()

        # NOTE Failed attempts -- I don't know what I am doing
        #b = ctx.preproc.get_bit(ctx)
        #b_flipped = ctx.field(1) - b
        #mystery_cryptodna = b * p1_cryptodna + b_flipped * p2_cryptodna
        #b_revealed = await b.open()
        #if b_revealed.value:
        #o = ctx.preproc.get_one_minus_ones(ctx)
        #o_revealed = await o.open()
        #if o_revealed.value * -1 > 0:
        import random
        if random.getrandbits(1):
            hasharray.append((int(p1_genome[currentstart:currentend], 16), p1_color))
        else:
            hasharray.append((int(p2_genome[currentstart:currentend], 16), p2_color))

    # child_genome = b''.join(bytes.fromhex(hex(i).lstrip('0x')) for i in hasharray)
    child_genome = ''.join(hex(g).lstrip('0x') for g, _ in hasharray)

    # NOTE Beautiful ouput of Crypto DNA
    # revealed_DNAs = await cryptodna_sharearray.open()
    # return zip((p1[0], p2[0], kd[0]), revealed_DNAs)

    return child_genome
