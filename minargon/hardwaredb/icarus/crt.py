from minargon.hardwaredb import HWSelector, hardwaredb_route
from werkzeug.exceptions import HTTPException
import itertools

db_name = "icarus_crt_hw"

feb_table = "febs"
feb_columns = ["feb_id", "mac_address"]
orm_table = "orms"
orm_columns = ["orms_id", "feb_id", "module_id", ]
module_table = "minos_modules"
module_columns = ["module_id", "module_position"]

def CRTLOCs():
    try:
        return [(hw.value, hw) for hw in available_values(module_table, "module_position")]
    except HTTPException as e:
        return []

def to_column(c):
    return c

def to_display(c):
    return c

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
    return [HWSelector(table, column, d) for d in sorted_data]

@hardwaredb_route(db_name)
def module_board_list(conn, column, condition):
    cur = conn.cursor()

    column = to_column(column)
    if column not in module_columns:
        raise ValueError("Column (%s) is not an available selector in table (%s)" % (column, module_table))

    modules = cur.execute("SELECT module_id FROM %s WHERE %s=?" % (module_table, column), (condition,))
    modules = [str(m[0]) for m in modules if m]
    module_spec = "(" + ",".join(["?" for _ in modules]) + ")"

    # Take the modules to the ORM table
    febs = cur.execute("SELECT feb_id FROM %s WHERE module_id IN %s" % (orm_table, module_spec), modules)
    #febs = cur.execute("SELECT feb_id FROM %s WHERE module_id=%s" % (orm_table, modules[0]))
    febs = [str(f[0]) for f in febs if f]
    feb_spec = "(" + ",".join(["?" for _ in febs]) + ")"

    macs = cur.execute("SELECT mac_address FROM %s WHERE feb_id IN %s" % (feb_table, feb_spec), febs)
    macs = sorted([int(m[0]) for m in macs if m], key=int)
    
    cur.close()
    return macs

@hardwaredb_route(db_name)
def feb_board_list(conn, column, condition):
    cur = conn.cursor()

    column = to_column(column)
    if column not in feb_columns:
        raise ValueError("Column (%s) is not an available selector in table (%s)" % (column, feb_table))

    macs = cur.execute("SELECT mac_address FROM %s WHERE %s=?" % (feb_table, column), (condition,))
    macs = sorted([int(m[0]) for m in macs if m], key=int)

    cur.close()
    return macs

def available_selectors():
    ret = {}
    ret[feb_table] = dict([(to_display(c), available_values(feb_table, c)) for c in feb_columns])
    ret[module_table] = dict([(to_display(c), available_values(module_table, c)) for c in module_columns])
    return ret

SELECTORS = {}
SELECTORS[module_table] = module_board_list
SELECTORS[feb_table] = feb_board_list

MAPPINGS = {}
