if __name__ == "__main__":
    import asyncio

    import toml

    from apps.toolkit.httpserver import HTTPServer
    from apps.toolkit.mpcserver import runner
    from apps.toolkit.parsers import ServerArgumentParser
    from apps.auctions.mpcprogrunner import MPCProgRunner
    from apps.auctions.preprocessor import PreProcessor

    from honeybadgermpc.progs.mixins.constants import MixinConstants
    from honeybadgermpc.progs.mixins.share_arithmetic import BeaverMultiplyArrays

    # arg parsing
    parser = ServerArgumentParser()
    args = parser.parse_args()

    # read config and merge with cmdline args -- cmdline args have priority
    config = toml.load(args.config_path)
    _args = parser.post_process_args(args, config)

    asyncio.run(
        runner(
            "sid",
            _args["myid"],
            host=_args["host"],
            mpc_port=_args["mpc_port"],
            peers=_args["peers"],
            w3=_args["w3"],
            contract_context=_args["contract_context"],
            db=_args["db"],
            http_context={"host": _args["host"], "port": _args["http_port"]},
            preprocessor_class=PreProcessor,
            httpserver_class=HTTPServer,
            mpcprogrunner_class=MPCProgRunner,
            mpc_config={MixinConstants.MultiplyShareArray: BeaverMultiplyArrays()},
        )
    )
