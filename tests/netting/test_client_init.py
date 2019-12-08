import apps.netting.scripts.generate_data as data_gen

import apps.netting.src.client as clients

"""
Test that everything is initilzed correctly for the application.
"""
def test_init():
	data_gen.main()
	clis = clients.init_clients()

	for cli in clis:
		assert cli.balance >= 0, "Init balance >= 0"
		assert len(cli.out_tx) + len(cli.in_tx) >= 1, "With high probability must have atleast one tx"
