# ERC721 NFT-based MPC-secured CryptoDNA powered RoboHash
RoboHash Factory to generate robots equipped with secret DNA (aka CryptoDNA
aka private/secret genome).

The creation of RoboHashes and their secret CryptoDNA is coordinated and
secured by an EthBadgerMPC network, in which Ethereum acts as a coordinator
meanwhile HoneyBadgerMPC secures the secret CryptoDNA material, used to create
RoboHashes.

## Vyper-based, Ratel contract
Contracts are written in Ratel, a Vyper-based language that allows writing MPC
programs.

## Galois Field -based Secret CryptoDNA
Each secret CryptoDNA of a new RoboHash is randomly selected from the finest
Galois Fields that mathematics has to offer.

## Try it!

```shell
$ git clone --single-branch --branch robohash-ic3-bcc20 git@github.com:initc3/HoneyBadgerMPC.git

$ cd apps/robohash
$ make run
```

## Original Contributors
This project was started at the
[IC3 Blockchain Camp 2020](https://www.initc3.org/events/2020-07-26-IC3-Blockchain-Camp.html)
and was the result of a great team effort by:

* Andrew Miller, @amiller
* Amit Agarwal, @amitgtx
* Alexander Lee, @cs79
* Chang Yang Jiao, @jiaochangyang
* Nicolás Serrano, @NicoSerranoP
* Sylvain Bellemare, @sbellem
* Zhengxun Wu
