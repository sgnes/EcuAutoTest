from can.interfaces.vector import VectorBus
from udsoncan.connections import PythonIsoTpConnection
from udsoncan.client import Client
import isotp
import udsoncan
import struct

# Refer to isotp documentation for full details about parameters
isotp_params = {
   'stmin' : 32,                          # Will request the sender to wait 32ms between consecutive frame. 0-127ms or 100-900ns with values from 0xF1-0xF9
   'blocksize' : 8,                       # Request the sender to send 8 consecutives frames before sending a new flow control message
   'wftmax' : 0,                          # Number of wait frame allowed before triggering an error
   'll_data_length' : 8,                  # Link layer (CAN layer) works with 8 byte payload (CAN 2.0)
   'tx_padding' : 0,                      # Will pad all transmitted CAN messages with byte 0x00. None means no padding
   'rx_flowcontrol_timeout' : 1000,       # Triggers a timeout if a flow control is awaited for more than 1000 milliseconds
   'rx_consecutive_frame_timeout' : 1000, # Triggers a timeout if a consecutive frame is awaited for more than 1000 milliseconds
   'squash_stmin_requirement' : False     # When sending, respect the stmin requirement of the receiver. If set to True, go as fast as possible.
}

class MyCustomCodecThatShiftBy4(udsoncan.DidCodec):
   def encode(self, val):
      val = (val << 4) & 0xFFFFFFFF # Do some stuff
      return struct.pack('<L', val) # Little endian, 32 bit value

   def decode(self, payload):
      val = struct.unpack('<L', payload)[0]  # decode the 32 bits value
      return val >> 4                        # Do some stuff (reversed)

   def __len__(self):
      return 4    # encoded paylaod is 4 byte long.

class MyCustomCodecHex(udsoncan.DidCodec):
   def encode(self, val):
      return bytes.fromhex(val)

   def decode(self, payload):
      return payload                        # Do some stuff (reversed)

   def __len__(self):
      return 1    # encoded paylaod is 4 byte long.


client_config  = {
	'exception_on_negative_response'	: True,
	'exception_on_invalid_response'		: True,
	'exception_on_unexpected_response'	: True,
	'security_algo'				: None,
	'security_algo_params'		: None,
	'tolerate_zero_padding' 	: True,
	'ignore_all_zero_dtc' 		: True,
	'dtc_snapshot_did_size' 	: 2,		# Not specified in standard. 2 bytes matches other services format.
	'server_address_format'		: None,		# 8,16,24,32,40
	'server_memorysize_format'	: None,		# 8,16,24,32,40
	'data_identifiers' 			: {0x0200:MyCustomCodecThatShiftBy4,
                                     0xD500:MyCustomCodecHex,
                                     0xFE01:MyCustomCodecHex,
                                     0xDF00:MyCustomCodecHex,
                                     0xd472:MyCustomCodecHex},
	'input_output' 				: {}
}


bus = VectorBus(channel=1, bitrate=500000)                                          # Link Layer (CAN protocol)
tp_addr = isotp.Address(isotp.AddressingMode.Normal_11bits, txid=0x7e1, rxid=0x782) # Network layer addressing scheme
stack = isotp.CanStack(bus=bus, address=tp_addr, params=isotp_params)               # Network/Transport layer (IsoTP protocol)
conn = PythonIsoTpConnection(stack)                                                 # interface between Application and Transport layer
with Client(conn, request_timeout=1, config=client_config) as client:                                     # Application layer (UDS protocol)
   client.change_session(3)
   response = client.request_seed(1)
   #client.send_key(2, b'0001')
   response = client.read_data_by_identifier(0x0200)
   print(response)
   client.clear_dtc(0xffffff)
   pass
   #client.routine_control(0xDF00, 1)
   #client.write_data_by_identifier(0xFE01, '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f')
   #client.write_data_by_identifier(0xD500, '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f404142434445464748494a4b4c4d4e4f505152535455565758595a5b5c5d5e5f606162636465666768696a6b6c6d6e6f707172737475767778797a7b7c7d7e7f')