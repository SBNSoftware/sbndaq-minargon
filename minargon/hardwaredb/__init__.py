from __future__ import absolute_import
from minargon import app
from werkzeug.routing import BaseConverter, ValidationError
from flask import abort, g
from functools import wraps
import sqlite3
import os

class HWSelector:
    def __init__(self, table, columns=[], values=[]):
        if not isinstance(columns, list):
            raise ValidationError("HWSelector columns must be a list")
        if not isinstance(values, list):
            raise ValidationError("HWSelector values must be a list")
        if len(columns) != len(values):
            raise ValidationError("Number of columns must match number of values")

        self.table = table
        self.columns = [str(c) for c in columns]
        self.values = [str(v) for v in values]

    def to_url(self):
        return ("%s:%s:%s" % (self.table, ",".join(self.columns), ",".join(self.values))).replace(";", "|")

    def display_values(self):
        return "-".join([str(v) for v in self.values])

    def where(self, column, value):
        self.columns.append(column)
        self.values.append(value)
        return self

    def trim(self, level=1):
        self.columns = self.columns[:level]
        self.values = self.values[:level]
        return self

    def __repr__(self):
        return self.__str__()
    def __str__(self):
        return self.to_url()

class HWSelectorConverter(BaseConverter):
    def to_python(self, values):
        data = [s.replace("|", ";") for s in values.split(":")]
        table = data[0]
        columns = data[1].split(",")
        values = data[2].split(",")
        return HWSelector(table, columns, values)

    def to_url(self, selector):
        return selector.to_url()

class HWSelectorListConverter(BaseConverter):
    def to_python(self, values):
        return [HWSelector(*[s.replace("|", ";") for s in values.split(":")]) for values in values.split(".")]

    def to_url(self, selectors):
        return ".".join([s.to_url() for s in selectors])

class HardwareDBConnectionError:
    def __init__(self, err):
        self.err = err
        self.msg = "Error accessing hardware DB: %s" % str(err)
        self.name = "Hardware DB"
        self.front_end_abort = True

    def message(self):
        return self.msg

    def database_name(self):
        return self.name

def get_hw_db(db_name, db_file):
    db = getattr(g, '_sqlite_%s' % db_name, None)
    if db is None:
        fd = os.open(db_file, os.O_RDONLY)
        db = sqlite3.connect('/dev/fd/%d' % fd)
        os.close(fd)
        setattr(g, '_sqlite_%s' % db_name, db)
    return db

@app.teardown_appcontext
def close_sqlite_connections(exception):
    for connection_name in app.config["SQLITE_INSTANCES"]: 
        db = getattr(g, '_sqlite_%s' % connection_name, None)
        if db is not None:
            db.close()

# Decorator which handles and HardwareDB related access errors
def hardwaredb_route(db_name):
    def hardwaredb_route_decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
                if db_name not in app.config["SQLITE_INSTANCES"]: 
                    return abort(404, HardwareDBConnectionError("sqlite instance does not exist."))
                try:
                    conn = get_hw_db(db_name, app.config["SQLITE_INSTANCES"][db_name]["file"])
                except OSError:
                    return abort(503, HardwareDBConnectionError("Unable to open SQLite file (%s) for db (%s)" % (app.config["SQLITE_INSTANCES"][db_name]["file"], db_name)))
                if not isinstance(conn, sqlite3.Connection):
                    return abort(503, HardwareDBConnectionError(conn))
                try:
                    return func(conn, *args, **kwargs)
                except (sqlite3.OperationalError, sqlite3.ProgrammingError, sqlite3.InternalError, ValueError) as err:
                    return abort(503, HardwareDBConnectionError(err))
        return wrapper
    return hardwaredb_route_decorator

hw_mappings = {}
hw_selectors = {}
def select(hw_select):
    if hw_select.table in hw_selectors:
        return hw_selectors[hw_select.table](hw_select.columns, hw_select.values)
    return abort(404)

def channel_map(hw_select, channels):
    if hw_select.table in hw_mappings:
        return hw_mappings[hw_select.table](hw_select.columns, hw_select.values)
    return None

if app.config["FRONT_END"] == "icarus":
    #from . import icarus
    #from minargon import hardwaredb
    #from .hardwaredb import icarus
    from .icarus import tpc
    hw_selectors = icarus.tpc.SELECTORS
    hw_mappings = icarus.tpc.MAPPINGS

    from .icarus import crt
    hw_selectors = dict(hw_selectors, **icarus.crt.SELECTORS)
    hw_mappings = dict(hw_mappings, **icarus.crt.MAPPINGS)

    from .icarus import pmt
    hw_selectors = dict(hw_selectors, **icarus.pmt.SELECTORS)
    hw_mappings = dict(hw_mappings, **icarus.pmt.MAPPINGS)

