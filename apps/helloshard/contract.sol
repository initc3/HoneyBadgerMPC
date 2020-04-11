pragma solidity >=0.4.22 <0.6.0;

contract MpcCoordinator {
    /* A blockchain-based MPC coordinator.
     * 1. Keeps track of the MPC "preprocessing buffer"
     * 2. Accepts client input 
     *      (makes use of preprocess randoms)
     * 3. Initiates MPC epochs (MPC computations)
     *      (can make use of preprocessing values if needed)
     */

    // Session parameters
    uint public n;
    uint public t;
    address[] public shard_1;
    address[] public shard_2;
    mapping (address => uint) public servermap;
    // mapping (address => uint) public shard_1_map;
    // mapping (address => uint) public shard_2_map;

    // Who shards?
    // ===========
    // A different approach could be that that a list of servers is
    // passed and then split into shards, as opposed to expect shards.
    // 
    // In other words, the task of assigning servers to shards can be:
    // 
    // 1. the responsibility of the code that instantiates the contract
    // 2. the responsibility of the contract code
    constructor(address[] _shard_1, address[] _shard_2, uint _t) public {
        // for simplicity, both shards have the same number of servers
        require(_shard_1.length == _shard_2.length);
	    n = _shard_1.length;
	    t  = _t;
	    require(3*t < n);
	    shard_1.length = n;
	    shard_2.length = n;
	    for (uint i = 0; i < n; i++) {
	        shard_1[i] = _shard_1[i];
	        shard_2[i] = _shard_2[i];
	        servermap[_shard_1[i]] = i+1;   // servermap is off-by-one
	        servermap[_shard_2[i]] = i+1+n; // servermap is off-by-one
	        // shard_1_map[_shard_1[i]] = i+1; // servermap is off-by-one
	        // shard_2_map[_shard_2[i]] = i+1; // servermap is off-by-one
	    }
    }

    // ###############################################
    // 1. Preprocessing Buffer (the MPC offline phase)
    // ###############################################

    struct PreProcessCount {
        uint intershardmasks;
        uint inputmasks;     // [r]
    }

    // Consensus count (min of the player report counts)
    PreProcessCount public preprocess;

    // How many of each have been reserved already
    PreProcessCount public preprocess_used;

    function inputmasks_available () public view returns(uint) {
        return preprocess.inputmasks - preprocess_used.inputmasks;
    }

    // Report of preprocess buffer size from each server
    mapping ( uint => PreProcessCount ) public preprocess_reports;

    event PreProcessUpdated();

    function min(uint a, uint b) private pure returns (uint) {
        return a < b ? a : b;
    }

    function max(uint a, uint b) private pure returns (uint) {
        return a > b ? a : b;
    }

    function preprocess_report(uint[1] rep) public {
        // Update the Report 
        require(servermap[msg.sender] > 0);   // only valid servers
        uint id = servermap[msg.sender] - 1;
        preprocess_reports[id].inputmasks = rep[0];

        // Update the consensus
        // .triples = min (over each id) of _reports[id].triples; same for bits, etc. 
        PreProcessCount memory mins;
        mins.inputmasks = preprocess_reports[0].inputmasks;
        for (uint i = 1; i < n; i++) {
            mins.inputmasks = min(mins.inputmasks, preprocess_reports[i].inputmasks);
        }
        if (preprocess.inputmasks < mins.inputmasks) {
            emit PreProcessUpdated();
        }
        preprocess.inputmasks = mins.inputmasks;
    }



    // ######################
    // 2. Accept client input 
    // ######################

    // Step 2.a. Clients can reserve an input mask [r] from Preprocessing

    // maps each element of preprocess.inputmasks to the client (if any) that claims it
    mapping (uint => address) public inputmasks_claimed;

    event InputMaskClaimed(address client, uint inputmask_idx);

    // Client reserves a random values
    function reserve_inputmask() public returns(uint) {
        // Extension point: override this function to add custom token rules

        // An unclaimed input mask must already be available
        require(preprocess.inputmasks > preprocess_used.inputmasks);

        // Acquire this input mask for msg.sender
        uint idx = preprocess_used.inputmasks;
        inputmasks_claimed[idx] = msg.sender;
        preprocess_used.inputmasks += 1;
        emit InputMaskClaimed(msg.sender, idx);
        return idx;
    }

    // Step 2.b. Client requests (out of band, e.g. over https) shares of [r]
    //           from each server. Servers use this function to check authorization.
    //           Authentication using client's address is also out of band
    function client_authorized(address client, uint idx) view public returns(bool) {
        return inputmasks_claimed[idx] == client;
    }

    // Step 2.c. Clients publish masked message (m+r) to provide a new input [m]
    //           and bind it to the preprocess input
    mapping (uint => bool) public inputmask_map; // Maps a mask 

    struct Input {
        bytes32 masked_input; // (m+r)
        uint inputmask;       // index in inputmask of mask [r]

        // Extension point: add more metadata about each input
    }

    Input[] public input_queue; // All inputs sent so far
    function input_queue_length() public view returns(uint) {
        return input_queue.length;
    }

    event MessageSubmitted(uint idx, uint inputmask_idx, bytes32 masked_input);

    function submit_message(uint inputmask_idx, bytes32 masked_input) public {
        // Must be authorized to use this input mask
        require(inputmasks_claimed[inputmask_idx] == msg.sender);

        // Extension point: add additional client authorizations,
        //  e.g. prevent the client from submitting more than one message per mix

        uint idx = input_queue.length;
        input_queue.length += 1;

        input_queue[idx].masked_input = masked_input;
        input_queue[idx].inputmask = inputmask_idx;

        // QUESTION: What is the purpose of this event?
        emit MessageSubmitted(idx, inputmask_idx, masked_input);

        // The input masks are deactivated after first use
        inputmasks_claimed[inputmask_idx] = address(0);
    }

    // ######################
    // 3. Initiate MPC Epochs
    // ######################

    uint public constant K = 1; // number of messages per epoch

    // Preprocessing requirements
    uint public constant PER_EPOCH_INTERSHARDMASKS = K * n * 2;

    // Return the maximum number of mixes that can be run with the
    // available preprocessing
    function intershardmasks_available() public view returns(uint) {
        return preprocess.intershardmasks - preprocess_used.intershardmasks;
    }

    // Step 3.a. Trigger MPC to start
    uint public inputs_unmasked;
    uint public epochs_initiated;
    event MpcEpochInitiated(uint epoch);

    function inputs_ready() public view returns(uint) {
        return input_queue.length - inputs_unmasked;
    }

    function initiate_mpc() public {
        // Must mix eactly K values in each epoch
        require(input_queue.length >= inputs_unmasked + K);
        inputs_unmasked += K;
        emit MpcEpochInitiated(epochs_initiated);
        epochs_initiated += 1;
        intershard_msg_votes.length = epochs_initiated;
        intershard_messages.length = epochs_initiated;
        output_votes.length = epochs_initiated;
        output_hashes.length = epochs_initiated;
    }

    // Step 3.b. Output reporting: the output is considered "approved" once
    //           at least t+1 servers report it 
    struct IntershardMessage {
        bytes32 masked_msg; // (m+r)
        uint mask_idx;     // index of intershard mask
    }

    IntershardMessage[] public intershard_msg_queue; // All inputs sent so far
    function intershard_msg_queue_length() public view returns(uint) {
        return intershard_msg_queue.length;
    }

    uint public intershard_msg_ready;
    event IntershardMessageReady(uint epoch, uint msg_idx, bytes32 masked_msg);
    bytes32[] public intershard_messages;
    uint[] public intershard_msg_votes;
    mapping (uint => uint) public server_voted_in_epoch; // highest epoch voted in

    // function propose_intershard_secrets(uint epoch, uint[] secrets) public {
    function transfer_intershard_message(uint epoch, bytes32 masked_msg) public {
        require(epoch < epochs_initiated);    // can't provide output if it hasn't been initiated
        require(servermap[msg.sender] > 0);   // only valid servers
        uint id = servermap[msg.sender] - 1;

        // Each server can only vote once per epoch
        // Hazard note: honest servers must vote in strict ascending order, or votes
        //              will be lost!
        require(epoch <= server_voted_in_epoch[id]);
        server_voted_in_epoch[id] = max(epoch + 1, server_voted_in_epoch[id]);

        if (intershard_messages[epoch] > 0) {
            // All the votes must match
            require(masked_msg == intershard_messages[epoch]);
        } else {
            intershard_messages[epoch] = masked_msg;
        }

        intershard_msg_votes[epoch] += 1;
        if (intershard_msg_votes[epoch] == t + 1) {    // at least one honest node agrees
            uint idx = intershard_msg_queue.length;
            intershard_msg_queue.length += 1;
            intershard_msg_queue[idx].masked_msg = masked_msg;
            intershard_msg_queue[idx].mask_idx = epoch;
            emit IntershardMessageReady(epoch, idx, masked_msg);
            intershard_msg_ready += 1;
        }
    }

    // Output reporting: the output is considered "approved" once
    // at least t+1 servers report it 

    uint public outputs_ready;
    event MpcOutput(uint epoch, string output);
    bytes32[] public output_hashes;
    uint[] public output_votes;
    mapping (uint => uint) public server_voted; // highest epoch voted in

    function propose_output(uint epoch, string output) public {
        require(epoch < epochs_initiated);    // can't provide output if it hasn't been initiated
        require(servermap[msg.sender] > 0);   // only valid servers
        uint id = servermap[msg.sender] - 1;

        // Each server can only vote once per epoch
        // Hazard note: honest servers must vote in strict ascending order, or votes
        //              will be lost!
        require(epoch <= server_voted[id]);
        server_voted[id] = max(epoch + 1, server_voted[id]);

        bytes32 output_hash = sha3(output);

        if (output_votes[epoch] > 0) {
            // All the votes must match
            require(output_hash == output_hashes[epoch]);
        } else {
            output_hashes[epoch] = output_hash;
        }

        output_votes[epoch] += 1;
        if (output_votes[epoch] == t + 1) {    // at least one honest node agrees
            emit MpcOutput(epoch, output);
            outputs_ready += 1;
        }
    }
}
