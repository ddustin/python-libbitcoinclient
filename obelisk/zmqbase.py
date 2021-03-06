import random
import struct
import logging

# Broken for ZMQ 4
#try:
#    from zmqproto import ZmqSocket
#except ImportError:
#    from zmq_fallback import ZmqSocket
from zmq_fallback import ZmqSocket
from twisted.internet import defer, reactor


SNDMORE = 1

MAX_UINT32 = 4294967295


class ClientBase(object):

    valid_messages = []

    def __init__(self,
                 address,
                 public_key=None,
                 block_address=None,
                 tx_address=None,
                 version=3):
        self._messages = []
        self._tx_messages = []
        self._block_messages = []
        self.zmq_version = version
        self.address = address
        self.public_key = public_key
        self._socket = self.setup(address, public_key)
        if block_address:
            self._socket_block = self.setup_block_sub(
                block_address, self.on_raw_block)
        if tx_address:
            self._socket_tx = self.setup_transaction_sub(
                tx_address, self.on_raw_transaction)
        self._subscriptions = {'address': {}}
        self._timeouts = {}

    # Message arrived
    def on_raw_message(self, id, cmd, data):
        res = None
        short_cmd = cmd.split('.')[-1]
        if short_cmd in self.valid_messages:
            res = getattr(self, '_on_'+short_cmd)(data)
        else:
            logging.warning("Unknown Message " + cmd)
        if res:
            self.trigger_callbacks(id, *res)

    def on_raw_block(self, height, hash, header, tx_num, tx_hashes):
        print "block", height, len(tx_hashes)

    def on_raw_transaction(self, tx_data):
        print "tx", tx_data.encode('hex')

    # Base Api
    def send_command(self, command, data='', cb=None):
        tx_id = random.randint(0, MAX_UINT32)

        # command
        self.send(command, SNDMORE)
        # id (random)
        self.send(struct.pack('I', tx_id), SNDMORE)
        # data
        self.send(data, 0)

        if cb:
            self._subscriptions[tx_id] = cb
        timeout = reactor.callLater(4, self._reconnect)
        self._timeouts[tx_id] = [timeout, command, data, cb]
        return tx_id

    def unsubscribe(self, cb):
        for sub_id in self._subscriptions.keys():
            if self._subscriptions[sub_id] == cb:
                self._subscriptions.pop(sub_id)

    def trigger_callbacks(self, tx_id, *args):
        if tx_id in self._timeouts:
            self._timeouts[tx_id][0].cancel()
            del self._timeouts[tx_id]
        if tx_id in self._subscriptions:
            self._subscriptions[tx_id](*args)
            del self._subscriptions[tx_id]

    def _reconnect(self):
        self.log.error("Libbitcoin server timed out. Refreshing socket and resending requests.")
        self._socket.close()
        self._socket = self.setup(self.address, self.public_key)
        for tx_id in self._timeouts.keys():
            v = self._timeouts[tx_id]
            if v[0].active():
                v[0].cancel()
            self.send_command(v[1], data=v[2], cb=v[3])
            del self._timeouts[tx_id]
            del self._subscriptions[tx_id]
        for address in self._subscriptions["address"].keys():
            callbacks = self._subscriptions["address"][address]["callbacks"]
            for callback in callbacks:
                self.subscribe_address(address, callback)

    # Low level zmq abstraction into obelisk frames
    def send(self, *args, **kwargs):
        self._socket.send(*args, **kwargs)

    def frame_received(self, frame, more):
        self._messages.append(frame)
        if not more:
            if not len(self._messages) == 3:
                print "Sequence with wrong messages", len(self._messages)
                print [m.encode("hex") for m in self._messages]
                self._messages = []
                return
            command, id, data = self._messages
            self._messages = []
            id = struct.unpack('I', id)[0]
            self.on_raw_message(id, command, data)

    def block_received(self, frame, more):
        self._block_messages.append(frame)
        if not more:
            nblocks = struct.unpack('Q', self._block_messages[3])[0]
            if not len(self._block_messages) == 4 + nblocks:
                print "Sequence with wrong messages",\
                      len(self._block_messages),\
                      4 + nblocks
                self._block_messages = []
                return
            height, hash, header, tx_num = self._block_messages[:4]
            tx_hashes = self._block_messages[5:]
            if len(tx_num) >= 4:
                tx_num = struct.unpack_from('I', tx_num, 0)[0]
            else:
                print "wrong tx_num length", len(tx_num), tx_num
                tx_num = struct.unpack('I', tx_num.zfill(4))[0]
            self._block_messages = []
            height = struct.unpack('I', height)[0]
            self._block_cb(height, hash, header, tx_num, tx_hashes)

    def transaction_received(self, frame, more):
        self._tx_messages.append(frame)
        if not more:
            if not len(self._tx_messages) == 1:
                print "Sequence with wrong messages", len(self._tx_messages)
                self._tx_messages = []
                return
            tx_data = self._tx_messages[0]
            self._tx_messages = []
            self._tx_cb(tx_data)

    def setup(self, address, public_key=None):
        s = ZmqSocket(self.frame_received, self.zmq_version)
        s.connect(address, public_key)
        return s

    def setup_block_sub(self, address, cb):
        s = ZmqSocket(self.block_received, self.zmq_version, type='SUB')
        s.connect(address)
        self._block_cb = cb
        return s

    def setup_transaction_sub(self, address, cb):
        s = ZmqSocket(self.transaction_received, self.zmq_version, type='SUB')
        s.connect(address)
        self._tx_cb = cb
        return s

    # Low level packing
    def get_error(data):
        return struct.unpack_from('<I', data, 0)[0]

    def unpack_table(self, row_fmt, data, start=0):
        # get the number of rows
        row_size = struct.calcsize(row_fmt)
        nrows = (len(data)-start)/row_size

        # unpack
        rows = []
        for idx in xrange(nrows):
            offset = start+(idx*row_size)
            row = struct.unpack_from(row_fmt, data, offset)
            rows.append(row)
        return rows
