#!/usr/bin/env python
"""API for cryo Ignition schema
functions to access the db
functions for OM website
"""

from __future__ import absolute_import
from __future__ import print_function
import os
import subprocess 
import psycopg2
#import asyncio
#import asyncpg
import simplejson as json
from psycopg2.extras import RealDictCursor
from minargon.tools import parseiso, parseiso_or_int, stream_args
from minargon import app
from flask import jsonify, request, render_template, abort, g
from datetime import datetime, timedelta # needed for testing only
import time
import calendar
import re
from pytz import timezone

# status interpreter functions
from .checkStatus import statusString
from .checkStatus import oscillatorString
from .checkStatus import transferString
from .checkStatus import messageString
import six
from six.moves import range


# error class for connection
class IgnitionConnectionError:
    def __init__(self):
        self.err = None
        self.msg = "Unknown Error"
        self.name = "Unknown"


    def with_front_end(self, front_end_abort):
        self.front_end_abort = front_end_abort
        return self

    def register_ignition_error(self, err, name):
        self.err = err
        self.name = name
        self.msg = str(err)
        return self

    def register_fileopen_error(self, err, name):
        self.err = err
        self.name = name
        self.msg = "Error opening secret key file: %s" % err[1]
        return self

    def register_notfound_error(self, name):
        self.name = name
        self.msg = "Database (%s) not found" % name
        return self

    def message(self):
        return self.msg
    def database_name(self):
        return self.name

# exception for bad arguments to URL
class IgnitionURLException(Exception): 
	pass

#--------------------
# Database connection configuration
ignition_instances = app.config['IGNITION_INSTANCES']
postgres_instances = app.config['POSTGRES_INSTANCES']

def make_connection(connection_name, config):
    key = config["ignition_secret_key"]
    database_name = config["name"]
    host = config["host"]
    port = config["port"]
    try:
        with open(key) as f:
            u = (f.readline()).strip()
            p = (f.readline()).strip()
    except IOError as err:
        connection = IgnitionConnectionError().register_fileopen_error(err, connection_name)
        success = False
        return (connection, success)

    config["web_name"] = connection_name
    # connect to the db
    try:
        connection = psycopg2.connect(database=database_name, user=u, password=p, host=host, port=port)
        success = True
    except psycopg2.OperationalError as err:
        connection = IgnitionConnectionError().register_ignition_error(err, connection_name)
        success = False

    return connection, success

def get_ignition_db(connection_name, config):
    db = getattr(g, '_ignition_%s' % connection_name, None)
    if db is None:
        db = make_connection(connection_name, config)
        setattr(g, '_ignition_%s' % connection_name, db)
    return db

@app.teardown_appcontext
def close_ignition_connections(exception):
    for connection_name in ignition_instances:
        db = getattr(g, '_ignition_%s' % connection_name, None)
        if db is not None:
            connection, success = db
            if success:
                connection.close()


#--------------------
# decorator for getting the correct database from the provided link
def ignition_route(func):
    from functools import wraps
    @wraps(func)
    def wrapper(connection, *args, **kwargs):
        connection_name = connection
        front_end_abort = kwargs.pop("front_end_abort", False)
        if connection_name in ignition_instances:
            config = postgres_instances[connection_name]
            connection, success = get_ignition_db(connection_name, config)
            if success:
                try:
                    return func((connection, config), *args, **kwargs)
                except (psycopg2.Error, IgnitionURLException) as err:
                    error = IgnitionConnectionError().register_ignition_error(err, connection_name).with_front_end(front_end_abort)
                    return abort(503, error)
            else:
                error = connection.with_front_end(front_end_abort)
                return abort(503, error)
        else:
            return abort(404, IgnitionConnectionError().register_notfound_error(connection).with_front_end(front_end_abort))

    return wrapper


def is_valid_connection(connection_name):
    if connection_name not in ignition_instances:
        return False
    connection, success = get_ignition_db(connection_name, ignition_instances[connection_name])
    return success

#--------------------
# make the db query and return the data
def ignition_querymaker(IDs, start_t, stop_t, n_data, config, **table_args):
    # value string
    value_string = ""
    for i, v in enumerate(config["value_names"]):
        value_string += ", %s as VAL%i" % (v, i)

    # table name
    try:
        table_name = config["table_func"](**table_args)
    except TypeError:
        raise IgnitionURLException("Incorrect args to access table for database %s" % config["name"])

    # ndata string
    if isinstance(n_data, int):
        ndata_str = "LIMIT %i" % n_data
    else:
        ndata_str = ""

    # info needed by the query
    query_builder = {
        "TIME": config["time_name"],
        "VALUE_STRING": value_string,
        "TABLE": table_name,
        "START": str(start_t/1000.),
        "STOP": str(stop_t/1000.),
        "IDs": ",".join(IDs),
        "NDATA_STR": ndata_str,
    }

    # db query to execute, times converted to unix [ms]
    query = "SELECT extract(epoch FROM {})*1000 AS SAMPLE_TIME, CHANNEL_ID AS ID {VALUE_STRING} FROM {TABLE} WHERE CHANNEL_ID in ({IDs})"\
            " AND {TIME} BETWEEN to_timestamp({START}) AND to_timestamp({STOP}) ORDER BY {TIME} DESC {NDATA_STR}".format(**query_builder)
    return query


def ignition_query(IDs, start_t, stop_t, n_data, connection, config, **table_args):
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    query = ignition_querymaker(IDs, start_t, stop_t, n_data, config, **table_args)
    # execute the query, rollback connection if it fails
    try:
        cursor.execute(query)
        data = cursor.fetchall()
    except:
        cursor.execute("ROLLBACK")
        connection.commit()
        raise  # let website handle the error
    return data
    
#def get_ignition_last_value(connection, group):
@ignition_route
def get_ignition_last_value_pv(connection, month, group, pv):
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%{}%'
    ORDER BY d.t_stamp DESC 
    LIMIT 1""".format(month, group, pv)
    print(query)

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()
    formatted = []
    for row in dbrows:
        try:
            time = datetime.fromtimestamp(row[2]/1000) # ms since epoch
            time = time.strftime("%Y-%m-%d %H:%M")
        except:
            time = row[2]
        formatted.append((row[0], row[1], time))
    return formatted








