pragma solidity >=0.4.22 <0.6.0;

contract AsynchromixCoordinator {
    /* A blockchain-based MPC coordinator for Asychromix.
     * 1. Keeps track of the MPC "preprocessing buffer"
     * 2. Accepts client input 
     *      (makes use of preprocess randoms)
     * 3. Initiates mixing epochs (MPC computations)
     *      (makes use of preprocess triples, bits, powers)
     */
     
    // Session parameters
    uint public n;
    uint public t;
    address[] public servers;
    mapping (address => uint) public servermap;
    
    constructor(address[] _servers, uint _t) public {
	    n = _servers.length;
	    t  = _t;
	    require(3*t < n);
	    servers.length = n;
	    for (uint i = 0; i < n; i++) {
	        servers[i] = _servers[i];
    	    servermap[_servers[i]] = i+1; // servermap is off-by-one
    	}
    }
   /*
    * It's necessary to paste JSON into the "_servers" constructor to use the Remix IDE
    * Copy and paste the following for n=4:
["0xca35b7d915458ef540ade6068dfe2f44e8fa733c",
 "0xca35b7d915458ef540ade6068dfe2f44e8fa733c",
 "0xca35b7d915458ef540ade6068dfe2f44e8fa733c",
 "0xca35b7d915458ef540ade6068dfe2f44e8fa733c"]
    *
    */
    
    // ###############################################
    // 1. Preprocessing Buffer (the MPC offline phase)
    // ###############################################

    struct PreProcessCount {
        uint triples;        // [a],[b],[ab]
        uint bits;           // [b] with b in {-1,1}
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

    function preprocess_report(uint[3] rep) public {
        // Update the Report 
        require(servermap[msg.sender] > 0);   // only valid servers
        uint id = servermap[msg.sender] - 1;
        preprocess_reports[id].triples    = rep[0];
        preprocess_reports[id].bits       = rep[1];
        preprocess_reports[id].inputmasks = rep[2];

        // Update the consensus
        // .triples = min (over each id) of _reports[id].triples; same for bits, etc. 
        PreProcessCount memory mins;
        mins.triples    = preprocess_reports[0].triples;
        mins.bits       = preprocess_reports[0].bits;
        mins.inputmasks = preprocess_reports[0].inputmasks;
        for (uint i = 1; i < n; i++) {
            mins.triples    = min(mins.triples,    preprocess_reports[i].triples);
            mins.bits       = min(mins.bits,       preprocess_reports[i].bits);
            mins.inputmasks = min(mins.inputmasks, preprocess_reports[i].inputmasks);
        }
        if (preprocess.triples    < mins.triples ||
            preprocess.bits       < mins.bits    ||
            preprocess.inputmasks < mins.inputmasks) {
            emit PreProcessUpdated();
        }
        preprocess.triples    = mins.triples;
        preprocess.bits       = mins.bits;
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
        
        emit MessageSubmitted(idx, inputmask_idx, masked_input);

        // The input masks are deactivated after first use
        inputmasks_claimed[inputmask_idx] = address(0);
    }
    
    // #########################
    // 3. Initiate Mixing Epochs
    // #########################
    
    uint public constant K = 32; // Mix Size 
    
    // Preprocessing requirements
    uint public constant PER_MIX_TRIPLES = (K / 2) * 5 * 5; // k log^2 k
    uint public constant PER_MIX_BITS    = (K / 2) * 5 * 5;

    // Return the maximum number of mixes that can be run with the
    // available preprocessing
    function mixes_available() public view returns(uint) {
        uint triples_available = preprocess.triples - preprocess_used.triples;
        uint bits_available    = preprocess.bits    - preprocess_used.bits;
        return min(triples_available / PER_MIX_TRIPLES,
                   bits_available    / PER_MIX_BITS);
    }
    
    // Step 3.a. Trigger a mix to start
    uint public inputs_mixed;
    uint public epochs_initiated;
    event MixingEpochInitiated(uint epoch);

    function inputs_ready() public view returns(uint) {
        return input_queue.length - inputs_mixed;
    }
    
    function initiate_mix() public {
        // Must mix eactly K values in each epoch
        require(input_queue.length >= inputs_mixed + K);
        
        // Can only initiate mix if enough preprocessings are ready
        require(preprocess.triples >= preprocess_used.triples + PER_MIX_TRIPLES);
        require(preprocess.bits    >= preprocess_used.bits    + PER_MIX_BITS);
        preprocess_used.triples += PER_MIX_TRIPLES;
        preprocess_used.bits    += PER_MIX_BITS;
        
        inputs_mixed += K;
        emit MixingEpochInitiated(epochs_initiated);
        epochs_initiated += 1;
        output_votes.length = epochs_initiated;
        output_hashes.length = epochs_initiated;
    }
    
    // Step 3.b. Output reporting: the output is considered "approved" once
    //           at least t+1 servers report it 
    
    uint public outputs_ready;
    event MixOutput(uint epoch, string output);
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
            emit MixOutput(epoch, output);
            outputs_ready += 1;
        }
    }
}
