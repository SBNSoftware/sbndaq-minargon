# HELPER FUNCTIONS

def to_column(s):
    return s.replace(" ", "_").lower()

def to_display(s):
    return s.replace("_", " ").title() \
      .replace("Tpc", "TPC") \
      .replace("Id", "ID")

def wherestr(columns):
    if len(columns) == 0:
        return ""
    return "WHERE " + " AND ".join(["%s=?" % c for c in columns])

def validate_columns(cols, mlist, table):
    cols = [to_column(c) for c in cols]
    for c in cols:
        if c not in mlist:
            raise ValueError("Column (%s) is not an available selector in table %s" % (c, table))

    return cols
