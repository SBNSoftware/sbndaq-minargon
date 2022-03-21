from __future__ import absolute_import
from minargon import app
from flask import render_template, jsonify, request, redirect, url_for, flash, abort
import jinja2
from minargon.metrics import postgres_api

from minargon.tools import parseiso, RedisDataStream, PostgresDataStream
from minargon.metrics import online_metrics
import os.path
from datetime import date, datetime

from minargon import hardwaredb

"""
	Routes intented to be seen by the user	
"""

@app.route('/test_error')
def test_error():
    sys.stderr.write("Flask error logging test")
    raise Exception("Flask exception logging test")

@app.route('/verify_on')
def verify_on():
    return jsonify(success=True)

@app.route('/hellooo')
def hellooo():
    return 'Hellooooooo!'

@app.route('/')
def index():
    return redirect(url_for('introduction'))

@app.route('/view_plot')
def view_plot():
    plotname = request.args.get("url", "")
    return render_template("common/view_plot.html", plotname=plotname)

@app.route('/<connection>/latest_gps_info')
def latest_gps_info(connection):
    dbrows = postgres_api.get_gps(connection, front_end_abort=True)     

    return render_template('common/gps_info.html',rows=dbrows)

@app.route('/<connection>/pmt_readout_temp')
def pmt_readout_temp(connection):
    dbrows = postgres_api.get_pmt_readout_temp(connection, front_end_abort=True)     
    return render_template('icarus/pmt_readout_temp.html', rows=dbrows, connection=connection)

@app.route('/<connection>/icarus_cryo')
def icarus_cryo(connection):
    dbrows = postgres_api.get_icarus_cryo(connection, front_end_abort=True)     
    return render_template('icarus/cryo.html', rows=dbrows, connection=connection)

@app.route('/<connection>/icarus_tpcps?flange=<flange>')
def icarus_tpcps(connection, flange):
    dbrows = postgres_api.get_icarus_tpcps(connection, flange, front_end_abort=True)
    return render_template('icarus/tpcps.html', rows=dbrows, connection=connection, flange=flange)

@app.route('/<connection>/icarus_pmthv?side=<side>')
def icarus_pmthv(connection, side):
    dbrows = postgres_api.get_icarus_pmthv(connection, side, front_end_abort=True)
    return render_template('icarus/pmthv.html', rows=dbrows, connection=connection, side=side)

@app.route('/<connection>/epics_last_value/<group>')
def epics_last_value(connection,group):
    dbrows = postgres_api.get_epics_last_value(connection,group)     

    try:
        return render_template('common/'+group+'.html',rows=dbrows)
    except jinja2.exceptions.TemplateNotFound:
        abort(404)

@app.route('/<connection>/cathodehv')
def cathodehv(connection):
    dbrows = postgres_api.get_epics_last_value(connection,'cathodehv')     

    try:
        return render_template('icarus/cathodehv.html',rows=dbrows, connection=connection)
    except jinja2.exceptions.TemplateNotFound:
        abort(404)

@app.route('/<connection>/drifthvps')
def drifthvps(connection):
    dbrows = postgres_api.get_sbnd_drifthvps(connection, front_end_abort=True)
    return render_template('sbnd/drifthvps.html', rows=dbrows)

@app.route('/<connection>/epics_last_value_pv/<pv>')
def epics_last_value_pv(connection,pv):
    dbrows = postgres_api.get_epics_last_value_pv(connection,pv)

    try:
        return render_template('common/pv.html',rows=dbrows)
    except jinja2.exceptions.TemplateNotFound:
        abort(404)

@app.route('/<connection>/view_alarms')
def view_alarms(connection):
    return render_template('common/view_alarms.html', connection=connection)

@app.route('/sentinel_alarms')
def sentinel_alarms():
    data = online_metrics.build_sentinel_list("online")
    return render_template('common/alarm_tree.html', data=data)

@app.route('/online_group/<group_name>')
def online_group(group_name):
    return timeseries_view(request.args, group_name)

@app.route('/single_stream/<stream_name>/')
def single_stream(stream_name):
    render_args = {
        "stream_name": stream_name,
    }
    return render_template('common/single_stream.html', **render_args) 

# A test func for the PV Lists this translates the page made by bill to the Minargon webpage
# and also updates the script to be more compatible with python
@app.route('/<connection>/pvTree')
def pvTree(connection):
    return render_template('common/pvTree.html', data=postgres_api.pv_internal(connection, "pv_single_stream", front_end_abort=True))

def timeseries_view(args, instance_name, view_ident="", link_function="undefined", eventmeta_key=None, hw_select=None):
    # TODO: what to do with this?
    initial_datum = args.get('data', None)
    
    # get the config for this group from redis
    config = online_metrics.get_group_config("online", instance_name, front_end_abort=True)

    if initial_datum is None:
        if len(config["metric_list"]) > 0:
            initial_datum = config["metric_list"][0]
        else:
            intial_datum = "rms"

    # process the channels
    # if the hw_select is present, get it
    if hw_select is not None:
        channels = hardwaredb.select(hw_select)
        # lookup if there is a channel mapping
        channel_map = hardwaredb.channel_map(hw_select, channels)
        if channel_map is None:
            channel_map = "undefined"
    else:
        channels = "undefined"
        channel_map = "undefined"

    # setup the title
    title = instance_name
    if hw_select is not None:
        title = ("%s %s -- " % ("-".join(hw_select.columns), "-".join(hw_select.values))) + title

    # setup hw_select
    if hw_select is None:
        hw_select = "undefined"
    else:
        hw_select = hw_select.to_url()

    render_args = {
        'title': title,
        'link_function': link_function,
        'view_ident': view_ident,
        'config': config,
        'metric': initial_datum,
        'eventmeta_key': eventmeta_key,
        'channels': channels,
        'hw_select': hw_select,
        'channel_map': channel_map,
    }

    return render_template('common/timeseries.html', **render_args)

@app.route('/pv_single_stream/<database>/<ID>')
def pv_single_stream(database, ID):
    # get the config
    config = postgres_api.pv_meta_internal(database, ID, front_end_abort=True)
    # get the list of other data
    # tree = postgres_api.test_pv_internal(database)

    # check the currently visited item
    checked = postgres_api.get_configs(database, [ID], front_end_abort=True)

    tree = build_data_browser_tree()
   
    #low and high thresholds given by url parameters 
    low = request.args.get('low')
    high = request.args.get('high')
    #TODO: add try and catch cases for getting timestamps
    #Use 24 hour clock for defining time in url
    #date format from URL: Month-Day-Year_Hour:Minute | mm-dd-yr hr-min
    #date format to turn back to string: Month/Day/Year Hour:Minute
    start = request.args.get('start')
    if start is not None:
        start_obj = datetime.strptime(start, '%m-%d-%Y_%H:%M')
        #start time string to be placed in date picker
        start_time = datetime.strftime(start_obj,'%m/%d/%Y %H:%M')
        #%m%d%y%H:%M format to convert string into integer|mmddyyyyHHMM

        # start timestamp to update plot
        start_timestamp_int = parseiso(start_time);

    else:
        start_obj = None
        start_time = start
        start_timestamp_int = None
 
    end = request.args.get('end')
    if end is not None:
        end_obj = datetime.strptime(end, '%m-%d-%Y_%H:%M')
        #end time string to be placed in date picker
        end_time = datetime.strftime(end_obj, '%m/%d/%Y %H:%M')
        #%m%d%y%H:%M format to convert string into integer|mmddyyyyHHMM

        #end timestamp to update plot
        end_timestamp_int = parseiso(end_time);

    else:
        end_obj = None
        end_time = end
        end_timestamp_int = None

    dbrows = postgres_api.get_epics_last_value_pv(database,ID, front_end_abort=True)

    render_args = {
      "ID": ID,
      "config": config,
      "database": database,
      "tree": tree,
      "low": low,
      "high": high,
      "start_time": start_time,
      "end_time": end_time,
      "start_timestamp": start_timestamp_int,
      "end_timestamp": end_timestamp_int,
      "checked": checked,
      "rows" : dbrows
    }


    return render_template('common/pv_single_stream.html', **render_args)

# View a variable with multiple IDs
@app.route('/pv_multiple_stream/<database>/<var>')
def pv_multiple_stream(database, var):
    
    # Get the list of IDs for the var name
    IDs = postgres_api.pv_internal(database, ret_id=var, front_end_abort=True)

    # get the configs for each ID
    configs, starts, ends, toggles, downloads = [], [], [], [], []
    for ID in IDs:
        configs.append(postgres_api.pv_meta_internal(database, ID, front_end_abort=True))
        starts.append("start-"+str(ID))
        ends.append("end-"+str(ID))
        toggles.append("toggle-"+str(ID))
        downloads.append("download-"+str(ID))

    # print config
    render_args = {
      "var": var, 
      "IDs": IDs,
      "configs": configs,
      "starts" : starts,
      "ends" : ends,
      "toggles" : toggles,
      "downloads" : downloads,
      "database": database
    }
    return render_template('common/pv_multiple_stream.html', **render_args)

@app.route("/data_list")
def data_list():
    data = build_data_browser_list()
    return jsonify(data=build_data_browser_list())

def build_data_browser_list():
    # get the redis instance names
    redis_names = [name for name,_ in app.config["REDIS_INSTANCES"].items()]
    # and the postgres isntance names
    postgres_names = [name for name in app.config["EPICS_INSTANCES"]]
    # build all of the lists
    data = [] 
    for name in postgres_names:
        if postgres_api.is_valid_connection(name):
            data += postgres_api.pv_list(name, front_end_abort=False)
    for name in redis_names:
        data += online_metrics.build_link_list(name, front_end_abort=False)
    return data
    
def build_data_browser_tree(checked=None):
    # get the redis instance names
    redis_names = [] #name for name,_ in app.config["REDIS_INSTANCES"].items()]
    # and the postgres isntance names
    postgres_names = [name for name in app.config["EPICS_INSTANCES"]]
    # build all of the trees
    trees = [postgres_api.pv_internal(name, front_end_abort=True) for name in postgres_names if postgres_api.is_valid_connection(name)] \
        + [online_metrics.build_link_tree(name, front_end_abort=True) for name in redis_names]

    # wrap them up at a top level
    tree_dict = {
      "text": "Data Browser",
      "expanded": True,
      "nodes": trees,
      "displayCheckbox": False,
    }
    # pre-check some instances
    if checked is None:
        checked = []
    for c in checked:
        database_type, database, ID = c
        # do a DFS down the nodes
        stack = [tree_dict]
        while len(stack) > 0:
            vertex = stack.pop()
            if "nodes" in vertex:
                stack = stack + vertex["nodes"]
            elif "ID" in vertex and "database" in vertex and "database_type" in vertex:
                if vertex["ID"] == ID and vertex["database"] == database and vertex["database_type"] == database_type:
                    vertex["state"] = {"checked": True}
                    # if we've found the vertex, we can exit the search
                    break
    return tree_dict

@app.route('/view_correlation/<stream:streamX>/<stream:streamY>')
def view_correlation(streamX, streamY):
    if isinstance(streamX, PostgresDataStream):
        streamXarg = "postgres_" + streamX.name + "=" + str(streamX.ID)
    else:
        streamXarg = "redis_" + streamX.name + "=" + str(streamX.key)

    if isinstance(streamY, PostgresDataStream):
        streamYarg = "postgres_" + streamY.name + "=" + str(streamY.ID)
    else:
        streamYarg = "redis_" + streamY.name + "=" + str(streamY.key)
 

    render_args = {
      "streamX": streamX.to_config(),
      "streamY": streamY.to_config(),
      "urlStreamX": streamX,
      "urlStreamY": streamY,
      "streamXarg": streamXarg,
      "streamYarg": streamYarg
    }
    return render_template("common/view_correlation.html", **render_args)

@app.route('/view_functor/<stream:streamA>/<stream:streamB>/<int:find>')
def view_functor(streamA, streamB, find):
    if isinstance(streamA, PostgresDataStream):
        streamAarg = "postgres_" + streamA.name + "=" + str(streamA.ID)
    else:
        streamAarg = "redis_" + streamA.name + "=" + str(streamA.key)

    if isinstance(streamB, PostgresDataStream):
        streamBarg = "postgres_" + streamB.name + "=" + str(streamB.ID)
    else:
        streamBarg = "redis_" + streamB.name + "=" + str(streamB.key)
 

    render_args = {
      "streamA": streamA.to_config(),
      "streamB": streamB.to_config(),
      "urlStreamA": streamA,
      "urlStreamB": streamB,
      "streamAarg": streamAarg,
      "streamBarg": streamBarg,
      "find": find
    }
    return render_template("common/view_functor.html", **render_args)

@app.route('/view_streams')
@app.route('/view_streams/<int:collapse>')
def view_streams(collapse=0):
    postgres_stream_info = {}
    redis_stream_info = {}
    # parse GET parameters
    try:
        for arg, val in request.args.items(multi=True):
            # postgres streams
            if arg.startswith("postgres_"):
                database_name = arg[9:]
                database_ids = [int(x) for x in val.split(",") if x]
                if database_name not in postgres_stream_info:
                    postgres_stream_info[database_name] = database_ids
                else:
                    postgres_stream_info[database_name] += database_ids
            # redis streams
            elif arg.startswith("redis_"):
                database_name = arg[6:]
                database_keys = val.split(",")
                if database_name not in redis_stream_info:
                    redis_stream_info[database_name] = database_keys
                else:
                    redis_stream_info[database_name] += database_keys
            else:
               raise ValueError
    except:
        return abort(404)

    postgres_streams = []
    redis_streams = []
    # collect configuration for postgres streams
    for database, IDs in postgres_stream_info.items():
        for ID in IDs:
            config = postgres_api.pv_meta_internal(database, ID, front_end_abort=True)
            postgres_streams.append( (ID, database, config) )
    # TODO: collect redis stream configuration
    for database, keys in redis_stream_info.items():
        for key in keys:
            try:
                metric_name = key.split(":")[-2]
            except:
                metric_name = key
            config = {
              "title": key,
              "yTitle": metric_name 
            }
            redis_streams.append( (key, database, config) )

    checked = []
    # get the currently checked items
    for database, IDs in postgres_stream_info.items():
        configs = postgres_api.get_configs(database, IDs, front_end_abort=True)
        checked += configs
    for database, keys in redis_stream_info.items():
        checked += online_metrics.get_configs(database, keys, front_end_abort=True)

    # build the data tree
    tree = build_data_browser_tree()

    # functions to build the "Stream" object from the config
    def make_redis_stream(info):
      key, database, _ = info
      return RedisDataStream(database, key)
    def make_postgres_stream(info):
      ID, database, _ = info
      return PostgresDataStream(database, ID)

    render_args = {
      "tree": tree,
      "redis_streams": redis_streams,
      "postgres_streams": postgres_streams,
      "make_redis_stream": make_redis_stream,
      "make_postgres_stream": make_postgres_stream,
      "checked": checked,
      "collapse": collapse
    }
    return render_template("common/view_streams.html", **render_args)

