pragma solidity ^0.4.22;

contract CommonSubset {
    uint public N;
    uint public f;
    address[] public players;
    mapping (address => uint) public playermap;
    uint[] public values;
    uint public deadline = uint(-1); // UINT_MAX
    uint public count; // how many values have been provided so far
    uint public constant ROUNDTIME = 10; // safe time interval, in blocks

    constructor(address[] _players, uint _f) public {
	N = _players.length;
	f = _f;
	require(3*f < N);
	players.length = N;
	values.length = N;
	for (uint i = 0; i < N; i++) {
	    players[i] = _players[i];
	    playermap[_players[i]] = i+1; // playermap is off-by-one
	}
    }

    // Output triggers
    event DeadlineSet(uint deadline);

    function isComplete() public view returns(bool) {
	return block.number > deadline;
    }

    // Provide input
    function input(uint v) public {
	require(block.number < deadline);
	require(playermap[msg.sender] > 0); // only valid players
	require(values[playermap[msg.sender]-1] == 0); // only set once
	require(v != 0);    // only set to nonzero
	values[playermap[msg.sender]-1] = v; // set the value
	count++;
	// if this is the N-f'th value, set the deadline
	if (count == N - f) {
	    deadline = block.number + ROUNDTIME;
	    emit DeadlineSet(deadline);
	}
    }
}
