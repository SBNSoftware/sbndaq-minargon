#!/usr/bin/env python
"""
########################################
This script contains all the functions
used to access the PostgreSQL database
and useful helper functions related to
this.
########################################
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
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
import numpy as np
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

# status interpreter functions
from .checkStatus import statusString
from .checkStatus import oscillatorString
from .checkStatus import transferString
from .checkStatus import messageString
import six
from six.moves import range
import io
from PIL import Image
import base64


# error class for connecting to postgres
class PostgresConnectionError:
    def __init__(self):
        self.err = None
        self.msg = "Unknown Error"
        self.name = "Unknown"


    def with_front_end(self, front_end_abort):
        self.front_end_abort = front_end_abort
        return self

    def register_postgres_error(self, err, name):
        self.err = err
        self.name = name
        self.msg = str(err)
        if isinstance(err, psycopg2.Error):
            self.msg += "\nError occured while executing query:\n\n%s" % err.cursor.query
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
class PostgresURLException(Exception): 
	pass

#________________________________________________________________________________________________
# database connection configuration
postgres_instances = app.config["POSTGRES_INSTANCES"]

def make_connection(connection_name, config):
    key = config["epics_secret_key"]
    database_name = config["name"]
    host = config["host"]
    port = config["port"]
    try:
        with open(key) as f:
            u = (f.readline()).strip() # strip: removes leading and trailing chars
            p = (f.readline()).strip()
    except IOError as err:
        connection = PostgresConnectionError().register_fileopen_error(err, connection_name)
        success = False
        return (connection, success)
	
    config["web_name"] = connection_name
    # Connect to the database
    try:
        connection = psycopg2.connect(database=database_name, user=u, password=p, host=host, port=port)
        success = True
    except psycopg2.OperationalError as err:
        connection = PostgresConnectionError().register_postgres_error(err, connection_name)
        success = False
	
    # return
    return connection, success

def get_postgres_db(connection_name, config):
    db = getattr(g, '_epics_%s' % connection_name, None)
    if db is None:
        db = make_connection(connection_name, config)
        setattr(g, '_epics_%s' % connection_name, db)
    return db

@app.teardown_appcontext
def close_postgres_connections(exception):
    for connection_name in postgres_instances:
        db = getattr(g, '_epics_%s' % connection_name, None)
        if db is not None:
            connection, success = db
            if success:
                connection.close()

#________________________________________________________________________________________________
# decorator for getting the correct database from the provided link
def postgres_route(func):
    from functools import wraps
    @wraps(func)
    def wrapper(connection, *args, **kwargs):
        connection_name = connection
        front_end_abort = kwargs.pop("front_end_abort", False)
        if connection_name in postgres_instances:
            config = postgres_instances[connection_name]
            connection, success = get_postgres_db(connection_name, config)
            if success:
                try:
                    return func((connection,config), *args, **kwargs)
                except (psycopg2.Error, PostgresURLException) as err:
                    error = PostgresConnectionError().register_postgres_error(err, connection_name).with_front_end(front_end_abort)

                    if isinstance(err, psycopg2.Error):
                        err.cursor.execute("ROLLBACK")
                        err.cursor.connection.commit()

                    return abort(503, error)
            else:
                error = connection.with_front_end(front_end_abort)
                return abort(503, error)
        else:
            return abort(404, PostgresConnectionError().register_notfound_error(connection).with_front_end(front_end_abort))
	
    return wrapper

def is_valid_connection(connection_name):
    if connection_name not in postgres_instances:
        return False
    connection, success = get_postgres_db(connection_name, postgres_instances[connection_name])
    return success

#________________________________________________________________________________________________
# Make the DB query and return the data
def postgres_querymaker(IDs, start_t, stop_t, n_data, config, **table_args):
    # build the value string
    value_string = ""
    for i,v in enumerate(config["value_names"]):
        value_string += ", %s as VAL%i" % (v, i)

    # build the table name
    try:
        table_name = config["table_func"](**table_args)
    # if the function can't be called, wrong table args were provided
    except TypeError:
        raise PostgresURLException("Incorrect args to access table for database %s" % config["name"])
		
    # build the ndata string
    if isinstance(n_data, int):
        ndata_str = "LIMIT %i" % n_data
    else:
        ndata_str = ""
    # information needed by the query
    query_builder = {
        "TIME": config["time_name"],
        "VALUE_STRING": value_string,
        "TABLE": table_name,
        "START": str(start_t / 1000.),
        "STOP": str(stop_t / 1000.),
        "IDs": ",".join(IDs),
        "NDATA_STR": ndata_str,
    }

    # Database query to execute, times converted to unix [ms]
    query = "SELECT extract(epoch FROM {TIME})*1000 AS SAMPLE_TIME, CHANNEL_ID AS ID {VALUE_STRING} FROM {TABLE} WHERE CHANNEL_ID in ({IDs})"\
            " AND {TIME} BETWEEN to_timestamp({START}) AND to_timestamp({STOP}) ORDER BY {TIME} DESC {NDATA_STR}".format(**query_builder)
    return query
	
def postgres_query(IDs, start_t, stop_t, n_data, connection, config, **table_args):
    # Make PostgresDB connection
    cursor = connection.cursor(cursor_factory=RealDictCursor) 

    query = postgres_querymaker(IDs, start_t, stop_t, n_data, config, **table_args)
    # Execute query, rollback connection if it fails
    cursor.execute(query)
    data = cursor.fetchall()

    return data, query

#________________________________________________________________________________________________
# Gets the sample step size in unix miliseconds
@app.route("/<connection>/ps_step/<ID>")
@postgres_route
def ps_step(connection, ID):
    # Define time to request for the postgres database
    start_t = datetime.now(timezone('UTC')) - timedelta(days=100)  # Start time
    stop_t  = datetime.now(timezone('UTC'))    	                 # Stop time

    start_t = calendar.timegm(start_t.timetuple()) *1e3 + start_t.microsecond/1e3 # convert to unix ms
    stop_t  = calendar.timegm(stop_t.timetuple())  *1e3 + stop_t.microsecond/1e3 

    data, query = postgres_query([ID], start_t, stop_t, 2, *connection, **request.args.to_dict())

    # Predeclare variable otherwise it will complain the variable doesnt exist 
    step_size = None

    # Get the sample size from last two values in query
    try:
        step_size = data[len(data) - 2]['sample_time'] - data[len(data) - 1]['sample_time'] 
    except:
        print("Error in step size")

    # Catch for if no step size exists
    if (step_size == None):
        step_size = 1e3

    return jsonify(step=float(step_size))
#________________________________________________________________________________________________
# Function to check None Values and empty unit
def CheckVal(var):
    if var == None or var == " ":
        return True
    else:
        return False
#________________________________________________________________________________________________
# Function to get the metadata for the PV
@app.route("/<connection>/pv_meta/<ID>")
def pv_meta(connection, ID):
    return jsonify(metadata=pv_meta_internal(connection, ID))
#________________________________________________________________________________________________
@postgres_route
def pv_meta_internal(connection, ID):
	
    database = connection[1]["name"]
    connection = connection[0]

    # return nothing if no connection
    if connection is None:
        return {}
	
    # Make PostgresDB connection
    cursor = connection.cursor(cursor_factory=RealDictCursor) 

    # Only implemented for Icarus epics right now
    if (database == "sbnteststand"):
        query="""SELECT low_disp_rng, high_disp_rng, low_warn_lmt, high_warn_lmt, low_alarm_lmt, high_alarm_lmt, unit, SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',1) AS title, SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',2) AS y_title
                 FROM DCS_ARCHIVER.num_metadata, DCS_ARCHIVER.CHANNEL
                 WHERE DCS_ARCHIVER.CHANNEL.CHANNEL_ID=%s AND DCS_ARCHIVER.num_metadata.CHANNEL_ID=%s """ % (ID, ID)
    else:
        query="""SELECT low_disp_rng, high_disp_rng, low_warn_lmt, high_warn_lmt, low_alarm_lmt, high_alarm_lmt, unit, SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',1) AS title, SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',2) AS y_title
                 FROM DCS_PRD.num_metadata, DCS_PRD.CHANNEL
                 WHERE DCS_PRD.CHANNEL.CHANNEL_ID=%s AND DCS_PRD.num_metadata.CHANNEL_ID=%s """ % (ID, ID)

    # Failure handled by decorator
    cursor.execute(query)
    data = cursor.fetchall()
	
    # Format the data from database query
    ret = {}
    warningRange = []
    DispRange = []
    for row in data:
        warningRange.append(row['low_alarm_lmt'])
        warningRange.append(row['high_alarm_lmt'])
        DispRange.append(row['low_disp_rng'])
        DispRange.append(row['high_disp_rng'])

        # Add the data to the list only if it has a value andlow != high otherwise just give empty

        # Unit
        if CheckVal(row['unit']) == False:
            ret["unit"] = row["unit"]

        # y Title	
        ret["yTitle"] = row['y_title']

        # Title
        ret["title"] = row["title"]

        # Display Range
        if (CheckVal(row['low_disp_rng']) == False and CheckVal(row['high_disp_rng']) == False) and row['low_disp_rng'] != row['high_disp_rng']:
            ret["range"] = DispRange

        # Warning Range
        if  (CheckVal(row['low_alarm_lmt']) == False and CheckVal(row['high_alarm_lmt']) == False) and row['low_alarm_lmt'] != row['high_alarm_lmt']:
             ret["warningRange"] = warningRange

        # only take the first row of data -- there should really only be one configuration per id
        break

    # Setup the return dictionary
    return ret

#________________________________________________________________________________________________
@postgres_route
def pv_list(connection, link_name=None, IDs=None):
    config = connection[1]
    database = connection[1]["name"]
    config = connection[1]
    connection = connection[0]

    # Cursor allows python to execute a postgres command in the database session. 
    cursor = connection.cursor() # Fancy way of using cursor

    # Database command to execute
    if (database == "sbnteststand"):
        query="""
                 SELECT DCS_ARCHIVER.CHAN_GRP.NAME, SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',1), SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',2), DCS_ARCHIVER.CHANNEL.CHANNEL_ID
                 FROM DCS_ARCHIVER.CHANNEL, DCS_ARCHIVER.CHAN_GRP
                 WHERE DCS_ARCHIVER.CHANNEL.GRP_ID = DCS_ARCHIVER.CHAN_GRP.GRP_ID 
                 ORDER BY DCS_ARCHIVER.CHAN_GRP.NAME, DCS_ARCHIVER.CHANNEL.NAME;
              """
    else:
        query="""
                 SELECT DCS_PRD.CHAN_GRP.NAME,SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',1),
                 SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',2),DCS_PRD.CHANNEL.CHANNEL_ID
                 FROM DCS_PRD.CHANNEL,DCS_PRD.CHAN_GRP WHERE DCS_PRD.CHANNEL.GRP_ID=DCS_PRD.CHAN_GRP.GRP_ID 
                 ORDER BY DCS_PRD.CHAN_GRP.NAME,DCS_PRD.CHANNEL.NAME;
              """
    # add in select for IDS
    if isinstance(IDs, tuple):
        if (database == "sbnteststand"):
            query = query.replace("WHERE", "WHERE DCS_ARCHIVER.CHANNEL.CHANNEL_ID IN %s AND")
        else:
            query = query.replace("WHERE", "WHERE DCS_PRD.CHANNEL.CHANNEL_ID IN %s AND")

    if isinstance(IDs, tuple):
        cursor.execute(query, (IDs,))
    else:
        cursor.execute(query)

    rows = cursor.fetchall()

    # some variables for bookkeeping
    tags = [0, 0, 0]

    ret = []

    # A list of id numbers for a variable
    list_id=[]
    id_flag=False 

    for row in rows:
        # the timestamp column does not correspond to a metric
        if str(row[2]) == "timestamp": continue

        # Push back every time
        if not link_name is None:
            ret.append({ 
                        "file": config["web_name"] + " " + str(row[0]) + " " + str(row[1]) + " " + str(row[2]),
                        "text" : str(row[2]), 
                        "tags" : [str(tags[1])], 
                        "database": config["web_name"], 
                        "database_type": "postgres",
                        "ID": str(row[3]), 
                        "name": str(row[2]), 
                        "href": app.config["WEB_ROOT"] + "/" + link_name + "/" + config["web_name"] + "/" + str(row[3])  
            }) # Level 3
        else: 
            ret.append({ 
                        "file": config["web_name"] + " " + str(row[0]) + " " + str(row[1]) + " " + str(row[2]),
                        "text" : str(row[2]), 
                        "tags" : [str(tags[1])], 
                        "database": config["web_name"], 
                        "database_type": "postgres",
                        "ID": str(row[3]), 
                        "name": str(row[2])  
            }) # Level 3

        tags[1] = tags[1] + 1

    # return the list
    return ret
#________________________________________________________________________________________________
@app.route("/<connection>/ps_series/<ID>")
@postgres_route
def ps_series(connection, ID):
    config = connection[1]

    # Make a request for time range
    args = stream_args(request.args)
    start_t = args['start']    # Start time
    now = datetime.now(timezone('UTC')) # Get the time now in UTC
    # 24 hours ago
    start_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 - 48*60*60*1e3 # convert to unix ms
    if start_t is None:
        # TODO:
        return abort(404, "Must specify a start time to a PostgreSQL request") 

    stop_t  = args['stop']     # Stop time

    # Catch for if no stop time exists
    if (stop_t == None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms

    # remove the timing keys from the dict
    table_args = request.args.to_dict()
    table_args.pop('start', None)
    table_args.pop('stop', None)
    table_args.pop('n_data', None)
    table_args.pop('now', None)

    data, query = postgres_query([ID], start_t, stop_t, args['n_data'], *connection, **table_args)

    # Format the data from database query
    data_list = []

    for row in reversed(data):
        value = None
        for i in range(len(config["value_names"])):
            accessor = "val%i" % i
            if row[accessor] is not None:
                value = row[accessor]
                break
            else: # no good data here, ignore this time value
                continue

            # Throw out values > 1e30 which seem to be an error
            if value > 1e30:
                continue

            # Add the data to the list
        ts = float(row['sample_time'])
        if ID == "9367":
            ts = ts #+ 5*60*60*1e3
        data_list.append( [ts, value] )

    # Setup the return dictionary
    ret = {
        ID: data_list,
        "warningRange": []
    }

    return jsonify(values=ret, query=query)

BREAK_TIMESTAMPS = [1719343380000, 1719412080000, 1719426720000, 1719500460000, 1719514320000]
VOLTS = [15, 20, 25, 30, 35]
BREAK_TIMESTAMPS = [big/1000. for big in BREAK_TIMESTAMPS]
@app.route("/<connection>/ps_series_mean/<ID>")
@postgres_route
def ps_series_mean(connection, ID):
    config = connection[1]

    # Make a request for time range
    args = stream_args(request.args)
    start_t = args['start']    # Start time
    if start_t is None:
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        #start_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 - 60*60*60*1e3 # convert to unix ms
        start_t = BREAK_TIMESTAMPS[0]*1e3

    stop_t  = args['stop']     # Stop time

    # Catch for if no stop time exists
    if (stop_t == None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms

    # remove the timing keys from the dict
    table_args = request.args.to_dict()
    table_args.pop('start', None)
    table_args.pop('stop', None)
    table_args.pop('n_data', None)
    table_args.pop('now', None)

    data, query = postgres_query([ID], start_t, stop_t, args['n_data'], *connection, **table_args)

    # Format the data from database query
    data_list = []
    val_list = []
    t_list = []

    for row in reversed(data):
        value = None
        for i in range(len(config["value_names"])):
            accessor = "val%i" % i
            if row[accessor] is not None:
                value = row[accessor]
                break
            else: # no good data here, ignore this time value
                continue

        # Add the data to the list
        if value is None:
            continue
        if value < 1:
            continue
        query_ts = float(row['sample_time'])
        query_ts = query_ts + 5*60*60*1e3
        data_list.append( [query_ts, value] )
        val_list.append( value )
        t_list.append( query_ts )

    # make a list of rolling averages
    rolling = []
    break_idx = [0] + [np.argmin(np.abs(np.array(data_list)[:,0]/1e3 - b)) for b in BREAK_TIMESTAMPS]
    period = 0
    for i in range(len(data_list)-1):
        this_vals = val_list[break_idx[period]:i+1]
        this_len = float(len(this_vals))
        if this_len < 20:
            this_vals = val_list[break_idx[period]:break_idx[period]+20]
        this_avg = float(sum(this_vals)) / this_len
        if len(this_vals) == 0:
             continue
        this_avg = np.mean(this_vals)
        this_avg = np.median(this_vals)
        rolling.append([t_list[i], this_avg])
        if (period < len(break_idx)-1):
            if (i == break_idx[period+1]):
                 period += 1

    # firm mean, rms
    firm_mean = []
    firm_median = []
    firm_std = []
    for v_setting in range(len(break_idx)-1):
        this_vals = val_list[break_idx[v_setting]:break_idx[v_setting+1]]
        if (v_setting == 0):
            print("this_vals", this_vals)
        this_mean = np.mean(this_vals)
        this_median = np.median(this_vals)
        this_std = np.std(this_vals)
        firm_mean.append(this_mean)
        firm_median.append(this_median)
        firm_std.append(this_std)
    this_vals = val_list[break_idx[-1]:]
    this_mean = np.mean(this_vals)
    this_median = np.median(this_vals)
    this_std = np.std(this_vals)
    firm_mean.append(this_mean)
    firm_median.append(this_median)
    firm_std.append(this_std)

    # Setup the return dictionary
    ret = {
        "metrics": {
            "volts": [0]+VOLTS,
            "mean": firm_mean,
            "median": firm_median,
            "std": firm_std,
        },
        ID: rolling,
        "configs": {
            "warningRange": [0, 1000]
        }
    }
    
    print("sunset metrics", ret["metrics"])

    return jsonify(values=ret, query=query)

@app.route("/<connection>/ps_series_plot/<ID>")
@postgres_route
def ps_series_plot(connection, ID):
    config = connection[1]

    # Make a request for time range
    args = stream_args(request.args)
    start_t = args['start']    # Start time
    now = datetime.now(timezone('UTC')) # Get the time now in UTC
    if start_t is None:
        #start_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 - 48*60*60*1e3 # convert to unix ms
        start_t = BREAK_TIMESTAMPS[0]*1e3

    stop_t  = args['stop']     # Stop time

    # Catch for if no stop time exists
    if (stop_t == None): 
        now = datetime.now(timezone('UTC')) # Get the time now in UTC
#        now = now.astimezone(timezone('US/Central'))
        stop_t = calendar.timegm(now.timetuple()) *1e3 + now.microsecond/1e3 # convert to unix ms

    # remove the timing keys from the dict
    table_args = request.args.to_dict()
    table_args.pop('start', None)
    table_args.pop('stop', None)
    table_args.pop('n_data', None)
    table_args.pop('now', None)

    data, query = postgres_query([ID], start_t, stop_t, 5000, *connection, **table_args)

    # Format the data from database query
    data_list = []
    val_list = []
    t_list = []

    for row in reversed(data):
        value = None
        for i in range(len(config["value_names"])):
            accessor = "val%i" % i
            if row[accessor] is not None:
                value = row[accessor]
                break
            else: # no good data here, ignore this time value
                continue

        # Add the data to the list
        if value is None:
            continue
        if value < 1:
            continue
        query_ts = float(row['sample_time'])
        query_ts = query_ts + 5*60*60*1e3
        data_list.append( [query_ts, value] )
        val_list.append( value )
        t_list.append( query_ts )

    # make a list of rolling averages
    rolling_avg = []
    rolling_med = []
    break_idx = [0] + [np.argmin(np.abs(np.array(t_list)/1e3 - b)) for b in BREAK_TIMESTAMPS]
    period = 0
    for i in range(len(data_list)-1):
        this_vals = val_list[break_idx[period]:i+1]
        this_len = float(len(this_vals))
        if this_len < 20.:
            this_vals = val_list[break_idx[period]:break_idx[period]+20]
        this_avg = np.mean(this_vals)
        rolling_avg.append([t_list[i], this_avg])
        this_med = np.median(this_vals)
        rolling_med.append([t_list[i], this_med])
        if (period < len(break_idx)-1):
            if (i == break_idx[period+1]):
                 period += 1

    # make a list of window scan averages
    window_avg = []
    window_med = []
    break_idx = [0] + [np.argmin(np.abs(np.array(t_list)/1e3 - b)) for b in BREAK_TIMESTAMPS]
    period = 0
    for i in range(len(data_list)-1):
        this_t = t_list[i]
        setting_start_t = t_list[break_idx[period]]
        if (period == (len(break_idx)-1)):
            setting_end_t = this_t
            this_setting_vals = val_list[break_idx[period]:]
            setting_end_idx = i
        else:
            setting_end_t = t_list[break_idx[period+1]]
            this_setting_vals = val_list[break_idx[period]:break_idx[period+1]]
            setting_end_idx = break_idx[period+1]

        window_len_ts = 20*60*60*1e3
        window_len = 20
        if ((this_t - setting_start_t) < window_len) :
            this_window_vals = val_list[break_idx[period]:(break_idx[period]+window_len)]
        elif ((setting_end_t - this_t) < window_len) :
            this_window_vals = val_list[(setting_end_idx-window_len):setting_end_idx]
        else:
            this_window_vals = val_list[(i-20):(i+20)]
        this_window_avg = np.mean(this_window_vals)
        this_window_med = np.median(this_window_vals)

        window_avg.append([t_list[i], this_window_avg])
        window_med.append([t_list[i], this_window_med])
        if (period < len(break_idx)-1):
            if (i == break_idx[period+1]):
                 period += 1

    # firm mean, rms
    firm_mean = []
    firm_median = []
    firm_std = []
    for v_setting in range(len(break_idx)-1):
        this_vals = val_list[break_idx[v_setting]:break_idx[v_setting+1]]
        if (v_setting == 0):
            print("this_vals", this_vals)
        this_mean = np.mean(this_vals)
        this_median = np.median(this_vals)
        this_std = np.std(this_vals)
        firm_mean.append(this_mean)
        firm_median.append(this_median)
        firm_std.append(this_std)
    this_vals = val_list[break_idx[-1]:]
    this_mean = np.mean(this_vals)
    this_median = np.median(this_vals)
    this_std = np.std(this_vals)
    firm_mean.append(this_mean)
    firm_median.append(this_median)
    firm_std.append(this_std)

    x = np.array(data_list)[:,0]
    y = np.array(data_list)[:,1]
    x_mean = np.array(rolling_avg)[:,0]
    y_mean = np.array(rolling_avg)[:,1]
    x_med = np.array(rolling_med)[:,0]
    y_med = np.array(rolling_med)[:,1]
    x_w_mean = np.array(window_avg)[:,0]
    y_w_mean = np.array(window_avg)[:,1]
    x_w_med = np.array(window_med)[:,0]
    y_w_med = np.array(window_med)[:,1]

    # summary plot
    fig, ax = plt.subplots(figsize=(12,4))

    for i, b in enumerate(BREAK_TIMESTAMPS):
        utc_dt = datetime.utcfromtimestamp(b)
        timestamp = calendar.timegm(utc_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        ct_dt = local_dt.replace(microsecond=utc_dt.microsecond)
        timestamp_string = local_dt.strftime('%m-%d %H:%M')
        plt.axvline(b*1e3, color="k", linestyle="--")
        ax_string = timestamp_string+", V = %i kV" % VOLTS[i]
        plt.text(b*1e3+1e6, 150, ax_string, rotation=90, fontsize=8)
        if i < len(BREAK_TIMESTAMPS)-1:
            xs = np.linspace(BREAK_TIMESTAMPS[i], BREAK_TIMESTAMPS[i+1], 21)
        else:
            xs = np.linspace(BREAK_TIMESTAMPS[i], x[-1]/1e3, 21)
        xs = xs*1e3
        ys = np.array([firm_mean[i+1]]*len(xs))/60
        y_devs = np.array([firm_std[i+1]]*len(xs))/60
        plt.plot(xs, ys, color="skyblue", alpha=0.4)
        plt.fill_between(list(xs), 
                         list(ys-y_devs), list(ys+y_devs), step="post", 
                         color="skyblue", alpha=0.1)

    plt.plot(x, y/60, "o", markersize=1, alpha=0.5, color="navy")
    plt.plot(x_mean, y_mean/60, "o-", markersize=1, label="mean (cumulative)", color="red")
    plt.plot(x_med, y_med/60, "o-", markersize=1, label="median (cumulative)", color="orange")
    plt.plot(x_w_mean, y_w_mean/60, "o-", markersize=1, label="mean (20-point window)", color="green")
    plt.plot(x_w_med, y_w_med/60, "o-", markersize=1, label="median (20-point window)", color="y")

    for i, b in enumerate(BREAK_TIMESTAMPS):
        utc_dt = datetime.utcfromtimestamp(b)
        timestamp = calendar.timegm(utc_dt.timetuple())
        local_dt = datetime.fromtimestamp(timestamp)
        ct_dt = local_dt.replace(microsecond=utc_dt.microsecond)
        timestamp_string = local_dt.strftime('%m-%d %H:%M')
        plt.axvline(b*1e3, color="k", linestyle="--")
        ax_string = timestamp_string+", V = %i kV" % VOLTS[i]
        plt.text(b*1e3+1e6, 150, ax_string, rotation=90, fontsize=8)
        if i < len(BREAK_TIMESTAMPS)-1:
            xs = np.linspace(BREAK_TIMESTAMPS[i], BREAK_TIMESTAMPS[i+1], 21)
        else:
            xs = np.linspace(BREAK_TIMESTAMPS[i], x[-1]/1e3, 21)
        ys = np.array([firm_mean[i+1]]*len(xs))
        plt.plot(xs*1e3, ys/60, color="blue")
   
    utc_dt = datetime.utcfromtimestamp(t_list[-1]/1e3)
    timestamp = calendar.timegm(utc_dt.timetuple())
    local_dt = datetime.fromtimestamp(timestamp)
    ct_dt = local_dt.replace(microsecond=utc_dt.microsecond)
    last_timestamp_string = local_dt.strftime('%m-%d %H:%M')

    ax.set_xticks([])
    ax.set_xticklabels([])
    ax.set_ylabel("Sunsets Frequency [Hz]")
    ax.set_xlabel("Time")
    ax.set_title("Ramp-up Summary, last update: %s" % last_timestamp_string)
    ax.legend(loc="upper left", ncol=2)
    plt.tight_layout()

    temp_data = io.BytesIO()
    plt.savefig(temp_data, format="JPEG", dpi=300)
    encoded_img_data = base64.b64encode(temp_data.getvalue())
    summary_img = encoded_img_data.decode('utf-8')

    # trend fit plot
    fig, ax = plt.subplots(figsize=(6,4))
    xs = [15,20,25,30,35]
    ys = np.array(firm_mean[1:])/60
    yerrs = np.array(firm_std[1:])/60
    plt.errorbar(xs, ys, yerr=yerrs, capsize=3, color="k")
    plt.xlim(0, 100)
    plt.ylim(0, 15)
    plt.xlabel("Cathode Voltage")
    plt.ylabel("Sunset Frequency [Hz]")
    plt.grid()
    plt.tight_layout()

    temp_data = io.BytesIO()
    plt.savefig(temp_data, format="JPEG", dpi=300)
    encoded_img_data = base64.b64encode(temp_data.getvalue())
    trend_img = encoded_img_data.decode('utf-8')

    # deadtime fit plot
    fig, ax = plt.subplots(figsize=(6,4))
    xs = [15,20,25,30,35]
    ys = np.array(firm_mean[1:])*4*1e-3/60*100
    yerrs = np.array(firm_std[1:])*4*1e-3/60*100
    plt.errorbar(xs, ys, yerr=yerrs, capsize=3, color="k")
    plt.xlim(0, 100)
    plt.ylim(0, 15)
    plt.xlabel("Cathode Voltage")
    plt.ylabel("Approx. Dead Time [%]")
    plt.grid()
    plt.tight_layout()

    temp_data = io.BytesIO()
    plt.savefig(temp_data, format="JPEG", dpi=300)
    encoded_img_data = base64.b64encode(temp_data.getvalue())
    deadtime_img = encoded_img_data.decode('utf-8')

    imgs = [summary_img, trend_img, deadtime_img]
    return imgs
    


def get_configs(connection, IDs, **kwargs):
    return pv_list(connection, IDs=tuple(IDs), **kwargs)
#________________________________________________________________________________________________
@postgres_route
def pv_internal(connection, link_name=None, ret_id=None):
    config = connection[1]
    database = connection[1]["name"]
    config = connection[1]
    connection = connection[0]

    # Cursor allows python to execute a postgres command in the database session. 
    cursor = connection.cursor() # Fancy way of using cursor

    # Database command to execute
    if (database == "sbnteststand"):
        query="""
                 SELECT DCS_ARCHIVER.CHAN_GRP.NAME, SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',1), SPLIT_PART(DCS_ARCHIVER.CHANNEL.NAME,'/',2), DCS_ARCHIVER.CHANNEL.CHANNEL_ID
                 FROM DCS_ARCHIVER.CHANNEL, DCS_ARCHIVER.CHAN_GRP
                 WHERE DCS_ARCHIVER.CHANNEL.GRP_ID = DCS_ARCHIVER.CHAN_GRP.GRP_ID 
                 ORDER BY DCS_ARCHIVER.CHAN_GRP.NAME, DCS_ARCHIVER.CHANNEL.NAME;
        """
    else:
        query="""
                 SELECT DCS_PRD.CHAN_GRP.NAME,SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',1),
                 SPLIT_PART(DCS_PRD.CHANNEL.NAME,'/',2),DCS_PRD.CHANNEL.CHANNEL_ID
                 FROM DCS_PRD.CHANNEL,DCS_PRD.CHAN_GRP WHERE DCS_PRD.CHANNEL.GRP_ID=DCS_PRD.CHAN_GRP.GRP_ID 
                 ORDER BY DCS_PRD.CHAN_GRP.NAME,DCS_PRD.CHANNEL.NAME;
        """
    cursor.execute(query)

    rows = cursor.fetchall()

    # some variables for bookkeeping
    old = [" ", " ", " "]
    tags = [0, 0, 0]
    index = [ 0, 0, 0 ]

    pydict = { 
        "text" : [database],
        "expanded": "true",
        "color" : "#000000",
        "selectable" : "false",
        "displayCheckbox": False,
        "nodes" : []
    }

    # A list of id numbers for a variable
    list_id=[]
    id_flag=False 

    # Create a python dictonary out of the database query
    for row in rows:
        # Header 1
        if row[0] != old[0]: # only use chan name part 1 once in loop to avoid overcounting e.g. grab APC then skip block until CRYO
            tags[0] = 0
            tags[1] = 0
            pydict["nodes"].append( { "color" : "#7D3C98","expanded": "false", "text" : str(row[0]), "href": "#parent1","nodes" : [], "displayCheckbox": False, "tags": [str(tags[0])]} ) # Top Level 
            old[0] = row[0]         
            index[0] = index[0] + 1 # Increment the index
            index[1] = 0

        # Header 2
        if row[1] != old[1]: # only use chan name part 2 once in loop to avoid overcounting 
            tags[1] = 0
            pydict["nodes"][index[0] - 1 ]["nodes"].append( {"href":"#child","expanded": "false","tags":[str(tags[1])], "displayCheckbox": False,
                "text" : str(row[1]), "nodes": [], "href": app.config["WEB_ROOT"] + "/" + "pv_multiple_stream" + "/" + config["web_name"] + "/" + str(row[1])  } ) # Level 2
            index[1] = index[1] + 1
            tags[0] = tags[0] + 1
            old[1] = row[1]			

        # the "timestamp column does not correspond to a metric
        if str(row[2]) == "timestamp": continue

        # Append the ID numbers for selected variable name
        if row[1] == ret_id:
            list_id.append(str(row[3]))

        # Push back every time
        if not link_name is None:
            pydict["nodes"][index[0] - 1 ]["nodes"][index[1] - 1]["nodes"].append({ 
                "text" : str(row[2]), 
                "tags" : [str(tags[1])], 
                "database": config["web_name"], 
                "database_type": "postgres",
                "ID": str(row[3]), 
                "name": str(row[2]), 
                "color" : "#229954",
                "href": app.config["WEB_ROOT"] + "/" + link_name + "/" + config["web_name"] + "/" + str(row[3])  
            }) # Level 3
        else: 
            pydict["nodes"][index[0] - 1 ]["nodes"][index[1] - 1]["nodes"].append({ 
                "text" : str(row[2]), 
                "tags" : [str(tags[1])], 
                "database": config["web_name"], 
                "database_type": "postgres",
                "color" : "#229954",
                "ID": str(row[3]), 
                "name": str(row[2])  
            }) # Level 3

        index[2] = index[2] + 1
        tags[1] = tags[1] + 1
    # Decide what type of data to return
    if ret_id is None:
        return pydict # return the full tree
    else:
        return list_id # return the ids of a variable
 

#__________________________________________________________________
@postgres_route
def get_pmt_readout_temp(connection):
    cursor = connection[0].cursor();
    query = """select name,last_smpl_time,to_char(last_float_val,'99999D99') from dcs_prd.channel where grp_id=16"""

    cursor.execute(query);
    dbrows = cursor.fetchall();
    cursor.close();

    formatted = []
    for row in dbrows:
        time = row[1].strftime("%Y-%m-%d %H:%M")
        formatted.append((row[0], time, row[2]))

    return formatted

#__________________________________________________________________
@postgres_route
def get_icarus_cryo(connection):
    cursor = connection[0].cursor();
    query = """select name,last_smpl_time,to_char(last_float_val,'99999D99') from dcs_prd.channel where grp_id=9"""

    cursor.execute(query);
    dbrows = cursor.fetchall();
    cursor.close();

    formatted = []
    for row in dbrows:
        time = row[1].strftime("%Y-%m-%d %H:%M")
        formatted.append((row[0], time, row[2]))

    return formatted

#______________________________________________________________________
@postgres_route
def get_icarus_tpcps(connection, flange):
    cursor = connection[0].cursor()
    query = """select channel_id, name, last_smpl_time, to_char(last_float_val,'99999D99') from dcs_prd.channel where grp_id=14 and name like '%""" + flange + """%'"""

    cursor.execute(query)
    dbrows = cursor.fetchall();
    cursor.close();

    res = []
    for row in dbrows:
        id = row[0]
        name = row[1]
        tmp = name.split('/')[0].split('_')
        n = name.split('/')[1]
        flange = tmp[2][0:2]
        tpc = tmp[2]
        if 'fan' in name:
            type = 'None'
        else:
            type = tmp[3]
        if row[3] is None:
            value = "None"
        else:
            value = row[3]
        res.append([id, flange, tpc, type, n, value])
    rr = sorted(res)

    end = []
    
    volt = []
    temp = []
    curr = []

    for r in rr:
       if 'volt' in r[4]:
           volt.append(r)
       elif 'temp' in r[4]:
           temp.append(r)
       elif 'curr' in r[4]:
           curr.append(r)

    end.append([volt, temp, curr])
    return end;

#______________________________________________________________________
@postgres_route
def get_icarus_pmthv(connection, side):
    cursor = connection[0].cursor()
    if side == 'E':
        s = "2"
    else:
        s = "1"
    query = """select channel_id, name, last_smpl_time, last_num_val, to_char(last_float_val, '0000D00') from dcs_prd.channel where grp_id=11 and name like '%pmt""" + s + """%'"""

    cursor.execute(query)
    dbrows = cursor.fetchall()
    cursor.close()

    pmtmapE = []
    pmtmapW = []
    pmtm = []

    try:
        with open(app.config["PMT_MAP"] + 'Sy1527' + side + 'ch.sub.fnal') as f:
            for line in f:
                tmp = []
                if "icarus" in line:
                    l = line.split(', ');
                    tmp.append(l[3])
                    tmp.append(l[4])
                    tmp.append(l[6])
                pmtm.append(tmp)
    except FileNotFoundError:
        abort(404)

    pmtmap = sorted(pmtm)

    rows = []
    east = []
    west = []
    boards = []
    channels = []
    pmts = []
    v = []
    res = []
    for row in dbrows:
        id = row[0]
        name = row[1]
        if 'bertan' not in name:
            tmp = name.split('/')[0].split('_')
            n = name.split('/')[1]
            t = tmp[3]
            board = t[1:3]
            channel = t[4:6]
                            
            temp = []
            group = 'pmt' + side
            for p in pmtmap:
                if p != []:
                    if board == p[0]:
                        if channel == p[1]:
                            pmtt = p[2]
                            
            time = row[2].strftime("%Y-%m-%d %H:%M")
            if 'onoff' in name:
                if row[3] == 1:
                    tmp = "On"
                else:
                    tmp = "Off"
            elif 'status' in name:
                tmp = row[3]
            else:
                tmp = row[4]
            res.append([group, board, channel, pmtt, row[0], n, tmp])
    rr = sorted(res)
    end = []

    power = []
    status = []
    vset = []
    vmon = []
    for r in rr:
        if 'pwonoff' in r[5]:
            power.append(r)
        elif 'status' in r[5]:
            status.append(r)
        elif 'v0set' in r[5]:
            vset.append(r)
        else:
            vmon.append(r)

    end.append([power, vset, vmon, status])
    return end;

#________________________________________________________________________________________________
@postgres_route
def get_gps(connection):
    cursor = connection[0].cursor();
    database = connection[1]["name"]
    if (database == "sbnteststand"):
        query = """select c1.name, c1.last_smpl_time, coalesce((c1.last_num_val::numeric)::text,(c1.last_float_val::numeric)::text, C1.last_str_val), m1.unit from dcs_archiver.channel c1 left join dcs_archiver.num_metadata m1 on c1.channel_id = m1.channel_id where c1.channel_id in (3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,20,21,42,43) order by c1.channel_id;"""
    else:
        # since strings cannot coalesce with floating point or integer types, we must first convert those into numeric and then strings to be able to coalesce.
        # ex: (float::numeric)::text
        # get the unit from another table (num_metadata) by using a left join
        query = """select c1.name, c1.last_smpl_time, coalesce((c1.last_num_val::numeric)::text,(c1.last_float_val::numeric)::text, C1.last_str_val), m1.unit from dcs_prd.channel c1 left join dcs_prd.num_metadata m1 on c1.channel_id = m1.channel_id where c1.channel_id in (3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,20,21,42,43) order by c1.channel_id;"""
        # where name like '%GPS%' order by c1.channel_id;"""

    #
    cursor.execute(query);
    dbrows = cursor.fetchall();
    cursor.close();

    # converting to a list does not work : yields another tuple and thus immutable
    # why do we need to change an element? Because 4 components need to go through an interpreter
    # to interpret the status ( the integer has a corresponding message/code/string )
    # solution: create new list, copy elements into list, getting the new strings from checkStatus.py
    # note: elements in formatted are still immutable. Most likely due to row[0] being a tuple
    formatted = []
    i = 0
    for row in dbrows:
        time = row[1].strftime("%Y-%m-%d %H:%M")
        if row[0].endswith("/message"):
            formatted.append((row[0], time, messageString(row[2]), row[3]))
        elif row[0].endswith("/transferQuality"):
            formatted.append((row[0], time, transferString(row[2]), row[3]))
        elif row[0].endswith("/oscillatorQuality"):
            formatted.append((row[0], time, oscillatorString(row[2]), row[3]))
        elif row[0].endswith("/status"):
            formatted.append((row[0], time, statusString(row[2]), row[3]))
        elif row[0].endswith("/TimeStampString"):
            formatted.insert(0, (row[0], time, row[2], row[3]))
        elif row[0].endswith("/location"):
            formatted.insert(0, (row[0], time, row[2], row[3]))
        elif row[0].endswith("/sigmaPPS") or row[0].endswith("/systemDifference"):
            flt_val = float(row[2]) #"{:.4f}".format(row[2])
            flt_str = "{:.4f}".format(flt_val)
            formatted.append((row[0], time, flt_str, row[3]))
        else:
            formatted.append((row[0], time, six.text_type(row[2], "utf-8"), row[3]))
        i = i + 1
        #dbrows
    return formatted

@postgres_route
def get_epics_last_value(connection,group):
    cursor = connection[0].cursor();

    database = connection[1]["name"]
    if (database == "sbnteststand"):
        query = """select c.name, c.descr, to_char( c.last_smpl_time,'YYYY.MM.DD HH24:MI:SS'),
    coalesce((c.last_num_val::numeric)::text,(trunc(c.last_float_val::numeric,3))::text, c.last_str_val),channel_id
    from dcs_archiver.channel c,dcs_archiver.chan_grp g
    where c.grp_id=g.grp_id and g.name='%s' order by c.name""" % group
    else:
        query = """select c.name, c.descr, to_char( c.last_smpl_time,'YYYY.MM.DD HH24:MI:SS'),
    coalesce((c.last_num_val::numeric)::text,(trunc(c.last_float_val::numeric,3))::text, c.last_str_val),c.channel_id,m.unit 
    from dcs_prd.channel c,dcs_prd.chan_grp g,dcs_prd.num_metadata m 
    where c.grp_id=g.grp_id and g.name='%s' and c.channel_id=m.channel_id order by c.name""" % group

    cursor.execute(query);
    dbrows = cursor.fetchall();
    cursor.close();
    formatted = []
    for row in dbrows:  
        try:
            time = row[2].strftime("%Y-%m-%d %H:%M")
        except:
            time = row[2]
        formatted.append((row[0],row[1],time,row[3],row[4],row[5]))

    return formatted

@postgres_route
def get_epics_last_value_pv(connection,pv):
    cursor = connection[0].cursor();

    database = connection[1]["name"]
    if (database == "sbnteststand"):
        query = """select c.name, c.descr, c.last_smpl_time, 
   coalesce((c.last_num_val::numeric)::text,(trunc(c.last_float_val::numeric,3))::text, c.last_str_val),c.channel_id,
   c.datatype,c.grp_id,g.name,g.descr,g.eng_id,m.prec,m.unit,m.low_disp_rng,m.high_disp_rng,
   m.low_warn_lmt,m.high_warn_lmt,m.low_alarm_lmt,m.high_alarm_lmt
   from dcs_archiver.chan_grp g,dcs_archiver.channel c left join dcs_archiver.num_metadata m on c.channel_id=m.channel_id 
   where c.channel_id=%s and c.grp_id=g.grp_id""" % pv
    else:
        query = """select c.name, c.descr, c.last_smpl_time, 
   coalesce((c.last_num_val::numeric)::text,(trunc(c.last_float_val::numeric,3))::text, c.last_str_val),c.channel_id,
   c.datatype,c.grp_id,g.name,g.descr,g.eng_id,m.prec,m.unit,m.low_disp_rng,m.high_disp_rng,
   m.low_warn_lmt,m.high_warn_lmt,m.low_alarm_lmt,m.high_alarm_lmt
   from dcs_prd.chan_grp g,dcs_prd.channel c left join dcs_prd.num_metadata m on c.channel_id=m.channel_id 
   where c.channel_id=%s and c.grp_id=g.grp_id""" % pv

    cursor.execute(query);
    dbrows = cursor.fetchall();
    cursor.close();
    formatted = []
    for row in dbrows:  
        try:
            time = row[2].strftime("%Y-%m-%d %H:%M")
        except:
            time = row[2]
        formatted.append((row[0],row[1],time,row[3],row[4],row[5],row[6],row[7],row[8],row[9],row[10],row[11],row[12],row[13],row[14],row[15],row[16],row[17]))

    return formatted

@postgres_route
def get_sbnd_drifthvps(connection):
    cursor = connection[0].cursor()
    query = """select channel_id, name, last_smpl_time, to_char(last_float_val,'99999D99'), last_str_val from dcs_prd.channel where grp_id=6"""

    cursor.execute(query)
    dbrows = cursor.fetchall();
    cursor.close();

    formatted = []
    def sort_id(var):
        return var[0];
    for row in dbrows:
        time = row[2].strftime("%Y-%m-%d %H:%M")
        formatted.append((row[0], row[1], time, row[3]))
        result = sorted(formatted, key = sort_id);

    return result;
