

bus = VectorBus(channel=1, bitrate=500000)                                          # Link Layer (CAN protocol)
tp_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x7e1, rxid=0x782) # Network layer addressing scheme
stack = isotp.CanStack(bus=bus, address=tp_addr, params=isotp_params)               # Network/Transport layer (IsoTP protocol)
conn = PythonIsoTpConnection(stack)                                                 # interface between Application and Transport layer
with Client(conn, request_timeout=1, config=client_config) as client:                                     # Application layer (UDS protocol)
   client.change_session(3)
   response = client.request_seed(1)
   #client.send_key(2, b'0001')
   response = client.read_data_by_identifier(0xd472)
   print(response)
   #client.routine_control(0xDF00, 1)
   #client.write_data_by_identifier(0xFE01, '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')