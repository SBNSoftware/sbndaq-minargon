from minargon.hardwaredb import HWSelector, hardwaredb_route
from werkzeug.exceptions import HTTPException
import itertools
from . import validate_columns, wherestr, to_column, to_display

db_name = "icarus_topcrt_hw"

feb_table = "crtfeb"
feb_columns = ["mac_add"]

position_table = "crtposition"
position_columns = ["wall", "row_index", "column_index"]

def CRTLOCs():
    try:
        return [(hw.values[0], hw) for hw in available_values(position_table, "wall")]
    except:
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
def feb_board_list(conn, columns, conditions):
    cur = conn.cursor()

    columns = validate_columns(columns, feb_columns, feb_table)

    macs = cur.execute("SELECT mac_add FROM %s %s" % (feb_table, wherestr(columns)), tuple(conditions))
    macs = sorted([int(m[0]) for m in macs if m], key=int)

    cur.close()
    return macs

@hardwaredb_route(db_name)
def position_list(conn, columns, conditions):
    cur = conn.cursor()

    columns = validate_columns(columns, position_columns, position_table)

    crts = cur.execute("SELECT crt_barcode FROM %s %s" % (position_table, wherestr(columns)), tuple(conditions))
    crts = [str(m[0]) for m in crts if m]
    crt_spec = "(" + ",".join(["?" for _ in crts]) + ")"

    # Take the crts to the module table
    febs = cur.execute("SELECT feb_barcode FROM crtmodule WHERE crt_barcode IN %s" % crt_spec, crts)
    febs = [str(m[0]) for m in febs if m]
    feb_spec = "(" + ",".join(["?" for _ in febs]) + ")"

    # Take the febs to the crtfeb table
    macs = cur.execute("SELECT mac_add FROM %s WHERE feb_barcode IN %s" % (feb_table, feb_spec), febs)
    macs = sorted([int(m[0]) for m in macs if m], key=int)

    cur.close()

    return macs

def available_selectors():
    ret = {}
    ret[feb_table] = dict([(to_display(c), available_values(feb_table, c)) for c in feb_columns])
    ret[position_table] = dict([(to_display(c), available_values(position_table, c)) for c in position_columns])
    return ret

SELECTORS = {}
SELECTORS[feb_table] = feb_board_list
SELECTORS[position_table] = position_list

MAPPINGS = {}
