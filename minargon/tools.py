from __future__ import print_function
from datetime import datetime
import calendar

def total_seconds(td):
    """Returns the total number of seconds contained in the duration."""
    return (td.microseconds + (td.seconds + td.days * 24 * 3600) * 10**6) / 10**6

def parseiso(timestr):
    """Convert an iso time string -> unix timestamp."""
    dt = datetime.strptime(timestr,'%Y-%m-%dT%H:%M:%S.%fZ')
    return calendar.timegm(dt.timetuple()) + dt.microsecond/1e6

# try parsing as int, falling back to parseiso
def parseiso_or_int(inp_str):
    try:
        return int(inp_str)
    except ValueError:
        return parseiso(inp_str)

# parse input file for channel to wire mapping
def parse_channel_map_file(fname, n_channel_per_fem, n_fem, slot_offset):
    channel_to_wire = {}
    wire_to_channel = {}
    wire_per_fem = [0 for i in range(n_fem)]
    with open(fname) as f:
        for i,line in enumerate(f):
            dat = line.split(" ")
            slot = int(dat[-2])
            slot_ch = int(dat[-1])
            channel = slot * n_channel_per_fem + slot_ch
            wire = int(dat[0])
            channel_to_wire[channel] = wire
            wire_to_channel[wire] = channel
            wire_per_fem[slot - slot_offset] += 1


    return (channel_to_wire, wire_to_channel, wire_per_fem)

# 1-1 mapping for debugging purposes
def default_channel_map(n_channels, n_fem):
    channel_to_wire = [i for i in range(n_channels)]
    wire_to_channel = [i for i in range(n_channels)]
    assert(n_channels % n_fem == 0)
    wire_per_fem = [n_channels / n_fem for i in range(n_fem)]
    return (channel_to_wire, wire_to_channel, wire_per_fem)

    


