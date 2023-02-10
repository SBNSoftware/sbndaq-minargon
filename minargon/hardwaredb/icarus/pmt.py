from minargon.hardwaredb import HWSelector, hardwaredb_route
from werkzeug.exceptions import HTTPException
from . import validate_columns, wherestr, to_column, to_display

db_name = "icarus_pmt_hw"
pmt_columns = ["pmt_in_tpc_plane", "pmt_id"]
pmt_table = "pmt_placements"

def PMTLOCs():
    try:
        return [(hw.values[0], hw) for hw in available_values("pmt_placements", "pmt_in_tpc_plane")] 
    except HTTPException as e:
        return []

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
def pmt_channel_list(conn, columns, conditions):
    cur = conn.cursor()

    columns = validate_columns(columns, pmt_columns, pmt_table)

    channels = cur.execute("SELECT pmt_id FROM %s %s" % (pmt_table, wherestr(columns)), tuple(conditions))
    channels = sorted([int(c[0]) for c in channels if c], key=int)

    cur.close()
    return channels

SELECTORS = {}
SELECTORS[pmt_table] = pmt_channel_list

MAPPINGS = {}
