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
def ignition_querymaker(pv, start_t, stop_t, n_data, month):
    query_builder = {
        "MONTH": config["time_name"],
        "GROUP": config["group_name"],
        "PV": pv,
        "START": str(start_t/1000.),
        "STOP": str(stop_t/1000.),
    }

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{MONTH} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%value%'
    AND s.tagpath LIKE '%{PV}%'
    AND d.t_stamp BETWEEN to_timestamp({START}) AND to_timestamp({STOP})
    ORDER BY d.t_stamp DESC
    LIMIT 2""".format(**query_builder)


    return query


@ignition_route
def ignition_query(pv, start_t, stop_t, n_data, connection, month):
    cursor = connection[0].cursor()
    database = connection[1]["name"]
    query = ignition_querymaker(pv, start_t, stop_t, n_data, month)
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

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()
    formatted = []
    for row in dbrows:
#        try:
#            time = datetime.fromtimestamp(row[2]/1000) # ms since epoch
#            time = time.strftime("%Y-%m-%d %H:%M")
#        except:
#            time = row[2]
        formatted.append((row[0], row[1], row[2]))
    return formatted

@ignition_route
def get_ignition_2hr_value_pv(connection, month, group, pv):
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    now = datetime.now(timezone('UTC')) # Get the time now in UTC
    stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms

    start = int(stop_t)-7200000
    LATEST_RAMP = 1720020000000
    if (start < LATEST_RAMP):
        start = LATEST_RAMP
    start = str(start)
    stop = str(int(stop_t))
    #print("start", start)
    #print("stop", stop)

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%{}%'
    AND d.t_stamp BETWEEN {} AND {}
    ORDER BY d.t_stamp""".format(month, group, pv, start, stop)

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()
    formatted = []
    for row in dbrows:
#        try:
#            time = datetime.fromtimestamp(row[2]/1000) # ms since epoch
#            time = time.strftime("%Y-%m-%d %H:%M")
#        except:
#            time = row[2]
        formatted.append((row[0], row[1], row[2]))
    return formatted



@app.route("/<connection>/cryo_ps_series/<month>/<pv>")
@ignition_route
def cryo_ps_series(connection, month, pv):
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    args = stream_args(request.args)
    start_t = args['start']    # Start time
    if start_t is None:
        return abort(404, "Must specify a start time to a Ignition request") 
        # start_t = datetime.now(timezone('UTC')) - timedelta(days=100)  # Start time
        # start_t = calendar.timegm(start_t.timetuple()) *1e3 + start_t.microsecond/1e3 # convert to unix ms
    stop_t  = args['stop']     # Stop time
    if (stop_t is None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms
    start = str(int(start_t))
    stop = str(int(stop_t))
    current_month = datetime.now().month
    n_data = args['n_data']    # Number of data points
    n_data = 1000

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{:02d} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%value%'
    AND d.t_stamp BETWEEN {} AND {}
    ORDER BY d.t_stamp""".format(current_month, pv, start, stop)
    # LIMIT {}""".format(month, pv, start, stop, n_data)

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()
    formatted = []
    for row in dbrows:
        # formatted.append((row[0], row[1], row[2]))
        formatted.append((float(row[2]), float(row[1])))
    ret = {
        pv: formatted
    }
    return jsonify(values=ret, query=query)

# Gets the sample step size in unix miliseconds
@app.route("/<connection>/cryo_ps_step/<month>/<pv>")
@ignition_route
def cryo_ps_step(connection, month, pv):
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    args = stream_args(request.args)
    start_t = args['start']    # Start time
    if start_t is None:
        # return abort(404, "Must specify a start time to a Ignition request") 
        start_t = datetime.now(timezone('UTC')) - timedelta(days=100)  # Start time
        start_t = calendar.timegm(start_t.timetuple()) *1e3 + start_t.microsecond/1e3 # convert to unix ms
    stop_t  = args['stop']     # Stop time
    if (stop_t is None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms
    start = str(int(start_t))
    stop = str(int(stop_t))
    n_data = args['n_data']    # Number of data points
    n_data = 1000

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%value%'
    AND d.t_stamp BETWEEN {} AND {}
    ORDER BY d.t_stamp 
    LIMIT {}""".format(month, pv, start, stop, n_data)

    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()

    # Predeclare variable otherwise it will complain the variable doesnt exist 
    step_size = None

    # Get the sample size from last two values in query
    try:
        step_size = data[len(data) - 2][2] - data[len(data) - 1][2] 
    except:
        print("Error in step size")

    # Catch for if no step size exists
    if (step_size is None):
        step_size = 1e3

    step_size = 1e3
    return jsonify(step=float(step_size))


@app.route("/<connection>/cryo_pv_meta/<pv>")
def cryo_pv_meta(connection, pv):
    return jsonify(metadata=cryo_pv_meta_internal(connection, pv))

@ignition_route
def cryo_pv_meta_internal(connection, pv):
    ret = {}
    ret["unit"] = "K"
    ret["yTitle"] = "Temperature"
    ret["title"] = str(pv)
    return ret
 
@app.route("/<connection>/drifthv_ps_series/<pv>")
@ignition_route
def drifthv_ps_series(connection, pv):
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    args = stream_args(request.args)
    start_t = args['start']    # Start time
    if start_t is None:
        return abort(404, "Must specify a start time to a Ignition request") 
        # start_t = datetime.now(timezone('UTC')) - timedelta(days=100)  # Start time
        # start_t = calendar.timegm(start_t.timetuple()) *1e3 + start_t.microsecond/1e3 # convert to unix ms
    stop_t  = args['stop']     # Stop time
    if (stop_t is None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms
    start = str(int(start_t))
    stop = str(int(stop_t))
    current_month = datetime.now().month
    n_data = args['n_data']    # Number of data points
    n_data = 1000

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{:02d} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%drifthv%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%value%'
    AND d.t_stamp BETWEEN {} AND {}
    ORDER BY d.t_stamp""".format(current_month, pv, start, stop)
    # LIMIT {}""".format(month, pv, start, stop, n_data)

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()
    formatted = []
    for row in dbrows:
        # formatted.append((row[0], row[1], row[2]))
        formatted.append((float(row[2]), float(row[1])))
    ret = {
        pv: formatted
    }
    return jsonify(values=ret, query=query)

# Gets the sample step size in unix miliseconds
@app.route("/<connection>/drifthv_ps_step/<pv>")
@ignition_route
def drifthv_ps_step(connection, pv):
    current_month = datetime.now().month
    cursor = connection[0].cursor()
    database = connection[1]["name"]

    args = stream_args(request.args)
    start_t = args['start']    # Start time
    if start_t is None:
        # return abort(404, "Must specify a start time to a Ignition request") 
        start_t = datetime.now(timezone('UTC')) - timedelta(days=100)  # Start time
        start_t = calendar.timegm(start_t.timetuple()) *1e3 + start_t.microsecond/1e3 # convert to unix ms
    stop_t  = args['stop']     # Stop time
    if (stop_t is None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms
    start = str(int(start_t))
    stop = str(int(stop_t))
    n_data = args['n_data']    # Number of data points
    n_data = 1000

    query = """SELECT d.tagid, COALESCE((d.intvalue::numeric)::text, (trunc(d.floatvalue::numeric,3))::text), d.t_stamp
    FROM cryo_prd.sqlt_data_1_2024_{:02d} d, cryo_prd.sqlth_te s
    WHERE d.tagid=s.id
    AND s.tagpath LIKE '%sbnd%'
    AND s.tagpath LIKE '%drifthv%'
    AND s.tagpath LIKE '%{}%'
    AND s.tagpath LIKE '%value%'
    AND d.t_stamp BETWEEN {} AND {}
    ORDER BY d.t_stamp 
    LIMIT {}""".format(current_month, pv, start, stop, n_data)

    cursor.execute(query)
    data = cursor.fetchall()
    cursor.close()

    # Predeclare variable otherwise it will complain the variable doesnt exist 
    step_size = None
    # Get the sample size from last two values in query
    try:
        step_size = data[len(data) - 2][2] - data[len(data) - 1][2] 
    except:
        print("Error in step size")

    # Catch for if no step size exists
    if (step_size is None):
        step_size = 1e3

    step_size = 1e3
    return jsonify(step=float(step_size))


@app.route("/<connection>/drifthv_pv_meta/<pv>")
def drifthv_pv_meta(connection, pv):
    return jsonify(metadata=drifthv_pv_meta_internal(connection, pv))

@ignition_route
def drifthv_pv_meta_internal(connection, pv):
    ret = {}
    ret["unit"] = "K"
    ret["yTitle"] = "Temperature"
    ret["title"] = str(pv)
    return ret
 
