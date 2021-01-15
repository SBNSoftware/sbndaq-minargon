from __future__ import absolute_import
from minargon import app
from redis import Redis
from flask import jsonify
import struct
import math
from six.moves import range
from six.moves import zip

# import gevent

class MalformedRedisEntry(Exception):
    pass

def convert(data):
    if isinstance(data, bytes):  return data.decode('ascii')
    if isinstance(data, dict):   return dict(map(convert, data.items()))
    if isinstance(data, tuple):  return map(convert, data)
    return data

def type_to_struct_type(name):
    if name == "int8_t": return "b"
    if name == "int16_t": return "h"
    if name == "int32_t": return "i"
    if name == "int64_t": return "q"

    if name == "uint8_t": return "B"
    if name == "uint16_t": return "H"
    if name == "uint32_t": return "I"
    if name == "uint64_t": return "Q"

    if name == "float": return "f"
    if name == "double": return "d"
    return None

def type_to_size(name):
    if name == "int8_t": return 1
    if name == "int16_t": return 2
    if name == "int32_t": return 4
    if name == "int64_t": return 8

    if name == "uint8_t": return 1
    if name == "uint16_t": return 2
    if name == "uint32_t": return 4
    if name == "uint64_t": return 8

    if name == "float": return 4
    if name == "double": return 8

def parse_binary(binary, typename):
    size = type_to_size(typename)
    form = type_to_struct_type(typename)
    ret = []
    for i in range(len(binary) / size):
       dat = binary[i*size : (i+1)*size]
       ret.append(struct.unpack(form, dat)[0])

    return ret

def extract_datum(dat):
    invert = "INVERT" in dat
    dat.pop("INVERT", None)
    d = convert(dat)
    if "dat" in d:
        try:
            val = float(d["dat"])
        except:
            return d["dat"]
    else:
        typename = list(d.keys())[0]
        structname = type_to_struct_type(typename)
        if structname is None:
            raise MalformedRedisEntry("Redis Steam entry missing binary type.")
        val = struct.unpack(structname.encode(), d[typename].encode())[0]
    if invert:
        if abs(val) < 1e-4: return "inf" # JSON compatible infinity
        val = 1. / val
    if math.isnan(val): val = 0
    return val

def get_waveform_binary(rdb, key):
    return rdb.hget(key, "Data")

def get_waveform(rdb, key):
    data_type = rdb.hget(key, "DataType")
    offset_type = rdb.hget(key, "OffsetType")
    size_type = rdb.hget(key, "SizeType")
    period = rdb.hget(key, "TickPeriod")
    data = rdb.hget(key, "Data")
    sizes = rdb.hget(key, "Sizes")
    offsets = rdb.hget(key, "Offsets")
    if data:
        data = parse_binary(data, data_type)
    else:
        data = []
    if sizes:
        sizes = parse_binary(sizes, size_type)
    else:
        sizes = [len(data)]
    if period is not None:
        period = float(period)
    else:
        period = 0.
    split_data = []
    index = 0
    for s in sizes:
        split_data.append(data[index:index+s])
        index += s

    if offsets:
        offsets = parse_binary(offsets, offset_type)
    else:
        offsets = [0]
    return split_data, offsets, period

# get a single redis key value
def get_key(rdb, key):
    # key may be individual value or list
    key_type = rdb.type(key)
    if key_type == "list":
        redis_data = list(rdb.lrange(key, 0, -1))
    elif key_type == "string":
        redis_data = rdb.get(key)
    else:
        redis_data = 0 
    return redis_data

def fetch_alarms(rdb):
    # first load all the alarm keys
    keys = set(rdb.smembers("ALARMS_MIDNIGHT")) | set(rdb.smembers("ALARMS_MIDDAY"))
    # load the members
    pipeline = rdb.pipeline()
    for key in keys:
        pipeline.hgetall(key)
    ret = {}
    for key, alarm in zip(keys, pipeline.execute()):
        ret[key] = alarm
    return ret

def get_expire(rdb, *keys):
    pipeline = rdb.pipeline()
    for k in keys:
        pipeline.ttl(k)
    return list(pipeline.execute())

# get most recent data point from a set of streams
def get_last_streams(rdb, stream_list,count=1):
    ret = {}
    pipeline = rdb.pipeline()
    for stream in stream_list:
        pipeline.xrevrange(stream, count=count)
    for stream, data in zip(stream_list, pipeline.execute()):
        ret[stream] = []
        for datapoint in data:
            time = datapoint[0].split("-")[0]
            val = extract_datum(datapoint[1])
            ret[stream].append((time, val))
    return ret

# get number of data points from list of streams
def avg_streams(rdb, stream_list, n_data=None, start=None, stop=None):
    if start is None:
        start = u'-'
    else:
        start += 1
    if stop is None:
        stop = u'+'
    if n_data is None:
        n_data = -1

    lua_avg = app.config["LUA_ASSETS"]["avg"]
    lua_struct = app.config["LUA_ASSETS"]["struct"]

    avg = rdb.register_script(lua_struct + lua_avg)

    ret = {}
    pipeline = rdb.pipeline()
    for streams in stream_list:
        avg(keys=streams, args=(stop, start, n_data), client=pipeline)

    for streams, data in zip(stream_list, pipeline.execute()):
        stream = streams[0]
        ret[stream] = []
        # data is already processed by the avg function
        for d in reversed(data):
            time =  d[0]
            val = d[1]
            ret[stream].append( (time, val) )

    return ret

# get number of data points from list of streams
def get_streams(rdb, stream_list, n_data=None, start=None, stop=None):
    if start is None:
        start = u'-'
    else:
        start += 1
    if stop is None:
        stop = u'+'
    ret = {}
    pipeline = rdb.pipeline()
    for stream in stream_list:
        pipeline.xrevrange(stream, min=start, max=stop, count=n_data)
    for stream, data in zip(stream_list, pipeline.execute()):
        ret[stream] = []
        for d in reversed(data):
            a = d[0].decode()
            time =  a.split("-")[0].encode()
            val = extract_datum(d[1])
            ret[stream].append( (time, val) )
    return ret

def block_streams(rdb, streams):
    while True:
        ret = {}
        n_received = 0
        #while n_received < len(streams):
        while n_received < 1:
            data = rdb.xread(streams, block=0)
            for stream_data in data:
                stream = stream_data[0]
                ret[stream] = []
                for d in stream_data[1]:
                    n_received += 1
                    time = d[0].split("-")[0]
                    val = extract_datum(d[1])
                    ret[stream].append( (time, val) )
                streams[stream] = ret[stream][-1][0]
        yield ret

def subscribe_streams(rdb, stream_list, n_data=None, start=None, stop=None):
    data = get_streams(rdb, stream_list, n_data, start, stop)
    streams = {}
    for s in stream_list:
        if len(data[s]) > 0:
            streams[s] = data[s][-1][0] # set "last seen" to most recent time value
        else:
            streams[s] = 0
    
    yield data

    for item in block_streams(rdb, streams):
        yield item

def clean_float(x):
    ret = float(x)
    if math.isnan(ret):
        ret = "NaN"
    return ret

