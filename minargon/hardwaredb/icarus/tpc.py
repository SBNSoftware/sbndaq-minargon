from __future__ import absolute_import
from minargon.hardwaredb import HWSelector, hardwaredb_route
from werkzeug.exceptions import HTTPException
import itertools
from . import validate_columns, wherestr, to_column, to_display

db_name = "icarus_tpc_hw"
daq_columns = ["readout_board_id", "chimney_number", "readout_board_slot", "plane", "cable_label_number", "channel_type"]
daq_table = "daq_channels"

flange_columns = ["flange_pos_at_chimney", "tpc_id"]
flange_table = "flanges"
readout_table = "readout_boards"

def TPCs():
    try:
        return [hw.values[0] for hw in available_values("flanges", "tpc_id")]
    except HTTPException as e:
        return []

def TPCFlanges():
    try:
        return [hw for hw in available_values("flanges", "flange_pos_at_chimney")]
    except HTTPException as e:
        return []

def flatten(l):
    return [item for sublist in l for item in sublist]

@hardwaredb_route(db_name)
def available_values(conn, table, column):
    cur = conn.cursor()
    data = cur.execute("SELECT %s FROM %s" % (to_column(column), table))
    # make unique and ignore duplicates
    data = list(set([x[0] for x in data if x]))
    # if numeric, sort
    try:
        sorted_data = sorted(data, key=int)
    except:
        sorted_data = data
    cur.close()
    return [HWSelector(table, [column], [d]) for d in sorted_data]

@hardwaredb_route(db_name)
def daq_channel_list(conn, columns, conditions):
    cur = conn.cursor()

    columns = validate_columns(columns, daq_columns, daq_table)
    channels = cur.execute("SELECT channel_id FROM %s %s" % (daq_table, wherestr(columns)), tuple(conditions))
    channels = sorted([int(c[0]) for c in channels if c], key=int)

    cur.close()
    return channels

# fake table name for this lookup
tpc_plane_table = "tpc_plane"
tpc_plane_columns = ["tpc", "plane"]
def tpc_plane_channel_list(columns, conditions):
    TPC = conditions[0]
    plane = conditions[1]

    tpc_channels = set(flange_channel_list(["tpc_id"], [TPC]))
    plane_channels = set(daq_channel_list(["plane"] + columns[2:], [plane] + conditions[2:]))

    channels = sorted(list(tpc_channels.intersection(plane_channels)))
    return channels

def tpc_plane_channel_available_values():
    planes = available_values("daq_channels", "plane") 
    TPCs = available_values("flanges", "tpc_id") 
    return [HWSelector(tpc_plane_table, tpc_plane_columns, [tpc.values[0], plane.values[0]]) for tpc,plane in itertools.product(TPCs, planes)]

def tpc_plane_plane_list(columns, conditions):
    planes = available_values("daq_channels", "plane") 
    return [[conditions[0], p.values[0]] for p in planes]

@hardwaredb_route(db_name)
def tpc_plane_flange_map(conn, columns, conditions):
    TPC = conditions[0]
    plane = conditions[1]
    plane_channels = set(daq_channel_list(["plane"], [plane]))

    cur = conn.cursor()

    flange_ids = cur.execute("SELECT flange_id FROM %s WHERE %s=?" % (flange_table, "tpc_id"), (TPC, ))
    # collect the flange ids into a selector
    flange_id_list = [str(f[0]) for f in flange_ids if f]
    flange_id_spec = "(" + ",".join(["?" for _ in flange_id_list]) + ")"

    flange_id_map = cur.execute("SELECT flange_id,flange_pos_at_chimney FROM %s WHERE %s=?" % (flange_table, "tpc_id"), (TPC, ))
    flange_id_map = dict([(str(f[0]), str(f[1])) for f in flange_id_map if f])

    readout_board_ids = cur.execute("SELECT readout_board_id,flange_id FROM %s WHERE flange_id IN %s" % (readout_table, flange_id_spec), flange_id_list) 
    readout_board_list = [str(f[0]) for f in readout_board_ids if f]
    readout_board_spec = "(" + ",".join(["?" for _ in readout_board_list]) + ")"

    readout_board_ids = cur.execute("SELECT readout_board_id,flange_id FROM %s WHERE flange_id IN %s" % (readout_table, flange_id_spec), flange_id_list) 
    readout_board_map = dict([(str(f[0]), str(f[1])) for f in readout_board_ids if f])

    daq_channel_ids = cur.execute("SELECT channel_id,readout_board_id FROM %s WHERE readout_board_id IN %s" % (daq_table, readout_board_spec), readout_board_list)
    # sort the channels
    daq_channels = sorted([(int(c[0]), flange_id_map[readout_board_map[str(c[1])]])for c in daq_channel_ids if c], key=lambda x: int(x[0]))

    cur.close()
    ret =  [d[1] for d in daq_channels if d[0] in plane_channels]
    return ret

@hardwaredb_route(db_name)
def flange_channel_list(conn, columns, conditions):
    cur = conn.cursor()

    this_flange_columns = validate_columns([columns[0]], flange_columns, flange_table)

    flange_ids = cur.execute("SELECT flange_id FROM %s %s" % (flange_table, wherestr(this_flange_columns)), (conditions[0],))
    # collect the flange ids into a selector
    flange_id_list = [str(f[0]) for f in flange_ids if f]
    flange_id_spec = "(" + ",".join(["?" for _ in flange_id_list]) + ")"

    readout_board_ids = cur.execute("SELECT readout_board_id FROM %s WHERE flange_id IN %s" % (readout_table, flange_id_spec), flange_id_list) 
    readout_board_list = [str(f[0]) for f in readout_board_ids if f]
    readout_board_spec = "(" + ",".join(["?" for _ in readout_board_list]) + ")"

    this_daq_columns = validate_columns(columns[1:], daq_columns, daq_table)
    daq_conditions = conditions[1:] 

    andstr = "AND" if len(this_daq_columns) else ""
    daq_channel_ids = cur.execute("SELECT channel_id FROM %s %s %s readout_board_id IN %s" % (daq_table, wherestr(this_daq_columns), andstr, readout_board_spec), daq_conditions + readout_board_list)
    # sort the channels
    daq_channels = sorted([int(c[0]) for c in daq_channel_ids if c], key=int)

    cur.close()
    return daq_channels

@hardwaredb_route(db_name)
def flange_list(conn, columns, conditions):
    cur = conn.cursor()

    columns = validate_columns(columns, flange_columns, flange_table)

    flange_ids = cur.execute("SELECT flange_pos_at_chimney FROM %s %s" % (flange_table, wherestr(columns)), tuple(conditions))
    flanges = [c[0] for c in flange_ids if c]

    cur.close()
    return flanges


@hardwaredb_route(db_name)
def slot_local_channel_map(conn, columns, conditions):
    cur = conn.cursor()

    this_flange_columns = validate_columns([columns[0]], flange_columns, flange_table)

    flange_ids = cur.execute("SELECT flange_id FROM %s %s" % (flange_table, wherestr(this_flange_columns)), (conditions[0],))

    # collect the flange ids into a selector
    flange_id_list = [str(f[0]) for f in flange_ids if f]
    flange_id_spec = "(" + ",".join(["?" for _ in flange_id_list]) + ")"

    readout_board_ids = cur.execute("SELECT readout_board_id FROM %s WHERE flange_id IN %s" % (readout_table, flange_id_spec), flange_id_list) 
    readout_board_list = [str(f[0]) for f in readout_board_ids if f]
    readout_board_spec = "(" + ",".join(["?" for _ in readout_board_list]) + ")"

    this_daq_columns = validate_columns(columns[1:], daq_columns, daq_table)
    daq_conditions = conditions[1:] 
    andstr = "AND" if len(this_daq_columns) else ""

    daq_channel_ids = cur.execute("SELECT channel_id,channel_number,readout_board_slot FROM %s %s %s readout_board_id IN %s" % (daq_table, wherestr(this_daq_columns), andstr, readout_board_spec), daq_conditions + readout_board_list)

    # sort the channels
    daq_channel_ids = sorted(list(daq_channel_ids), key=lambda x: x[0])
    # map
    daq_channels = [int(r[1]) + 64*int(r[2]) for r in daq_channel_ids]

    cur.close()
    return daq_channels

# build the list of available selectors
def available_selectors():
    ret = {}
    ret[daq_table] = dict([(to_display(c), available_values(daq_table, c)) for c in daq_columns])
    ret[flange_table] = dict([(to_display(c), available_values(flange_table, c)) for c in flange_columns])
    ret[tpc_plane_table] = dict([(to_display("-".join(tpc_plane_columns)), tpc_plane_channel_available_values())])
    return ret

# what functions are available
SELECTORS = {}
SELECTORS[daq_table] = daq_channel_list
SELECTORS[flange_table] = flange_channel_list
SELECTORS[flange_table + "_flanges"] = flange_list
SELECTORS[tpc_plane_table] = tpc_plane_channel_list
SELECTORS[tpc_plane_table + "_planes"] = tpc_plane_plane_list

MAPPINGS = {}
MAPPINGS[flange_table] = slot_local_channel_map
MAPPINGS["tpc_plane_flanges"] = tpc_plane_flange_map
