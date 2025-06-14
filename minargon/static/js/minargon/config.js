import * as DataLink from "./DataLink.js";
import * as TimeSeriesControllers from "./timeseries.js";
import * as GroupDataControllers from "./group_data.js";
import * as Data from "./Data.js";
import {throw_custom_error} from "./error.js";
import {titleize} from "./titleize.js";

export class HWGroupConfigController {
  constructor(config, href, metric, stream_index, hw_selects) {
    this.config = config;
    this.href = href;
    this.hw_selects = hw_selects;
    this.metric = metric;
    this.stream_index = stream_index;
    this.metric_config = this.config.metric_config[this.metric];
    this.controllers = [];
  }

  data_link() {
    return new DataLink.HWGroupMetricLink($SCRIPT_ROOT + "/" + this.config.stream_links[this.stream_index], 
                                      this.config.streams[this.stream_index],
                                      this.config.group,
                                      this.metric,
                                      this.hw_selects,
                                      1 /* Set downsample to 10 for now -- TODO: evaluate this */);
  }

  data_titles() {
    var titles = [];
    for (var i = 0; i < this.hw_selects.length; i++) {
      titles.push(this.config.group + " " + this.metric + " " + this.hw_selects[i]);
    }

    return titles;
  }

  metricController(id) {
    var self = this;
    $(id).change(function() { self.updateMetric(this.value); });
    return this;
  }

  updateMetric(metric) {
    this.metric = metric;
    this.metric_config = this.config.metric_config[metric];

    var data_link = new Data.D3DataLink(this.data_link());
    var data_titles = this.data_titles();
     
    for (var i = 0; i < this.controllers.length; i++) {
      this.controllers[i].updateData(data_link, true);
      this.controllers[i].updateTitles(data_titles);
      this.controllers[i].updateMetricConfig(this.metric_config);
    }
  }

  // Connect the time-series stream name to a HTML form field 
  // id: the jQuery specified of the HTML form field
  streamController(id) {
    var self = this;
    $(id).change(function() {self.updateStream(this.value);});
    return this;
  }
  
  // Internal function: change the stream name of the time-series
  // plotted in cubism 
  updateStream(input) {
    this.stream_index = input;
    var self = this;
    this.infer_step(input, function(step) {
      var data_link = new Data.D3DataLink(self.data_link());
      for (var i = 0; i < self.controllers.length; i++) {
        self.controllers[i].updateStep(step);
        self.controllers[i].updateData(data_link, true);
      }
    });
  }

  infer_step(stream_index, callback) {
    if (this.config.stream_links.length == 0) return callback(0);
    var link = this.data_link();
    return d3.json(link.step_link(), function(data) { 
        var step = 1000;
        if (data && data.step) step = data.step;
   
        callback(step); 
    });
  }

  runAll() {
    if (this.config.streams.length == 0 || this.config.metric_list == 0) {
      throw_custom_error("No data available for requested group");
      return;
    }

    var self = this;
    var data_link = new Data.D3DataLink(this.data_link());
    this.infer_step(0, function(step) {
      for (var i = 0; i < self.controllers.length; i++) {
        self.controllers[i].setStep(step);
        self.controllers[i].updateData(data_link);
      }
    });
  }

  // Internal function: hooks up the defined href to cubism for when the
  // user clicks on a strip chart 
  getLink(index) {
    if (!(this.href === undefined)) {
        // Look up the field at the correct index 
        //
        // This is defined only for cubism controllers. Cubism controllers
        // do have instance_skip set, so we get the correct index
        // by including it 
        return this.href(this.hw_selects[index]);
    }
    return undefined;
  }

  // add a cubism controller 
  addCubismController(target, height) {
    var data_link = new Data.D3DataLink(this.data_link());
    var data_titles = this.data_titles();
    var controller = new TimeSeriesControllers.CubismController(target, data_link, data_titles, this.metric_config, height);
    if (this.href !== undefined ) {
      controller.setLinkFunction(this.getLink.bind(this));
    }
    this.controllers.push(controller);
    return controller;
  }
}

// Class for handling configuration of groups of metrics and for
// changing the names of metric/stream/etc.
export class GroupConfigController {
  // config: DataConfig object generated by the redis backend and
  //         encoded as a JSON dictionary. Should contain the following
  //         fields:
  //           group: name of this group
  //           metric_list: list of all the metrics in this group
  //           instances: list of all the instances in this group
  //           streams: list of stream associated with this group
  //           stream_links: list of links to access each stream
  //           metric_config: configuration for display of each metric
  // href: (optional) function which will be passed the data_config group and
  //        instance corresponding to the clicked time-series and should 
  //        return a URL string that the user will navigate to. If
  //        nothing is passed, then nothing will happen when the user
  //        clicks on a strip chart
  constructor(config, href, metrics, instances, stream_index, max_n_instances, hw_select, channel_map, text_meta) {
    this.config = config;
    this.href = href;

    this.metrics = metrics;
    if (metrics !== undefined && metrics.length == 1) {
      this.metric_config = config.metric_config[metrics[0]];
    }
    else {
      this.metric_config = undefined;
    }

    if (instances === undefined) {
      this.instances = this.config.instances;
    }
    else {
      this.instances = instances;
    }
    this.stream_index = stream_index;

    // set the number of instances to skip each time
    if (max_n_instances !== undefined) {
      var number_instances = this.instances.length;
      this.instance_skip = Math.ceil(number_instances / max_n_instances);
    }
    else {
      this.instance_skip = 1;
    }

    this.controllers = [];

    // holder of 
    this.server_delay = 5000; // guess, for now

    this.hw_select = hw_select;

    // if the channel map is not defined, set it to the instances
    if (!channel_map) {
      this.channel_map = this.instances;
      this.channel_is_mapped = false;
    }
    else {
      this.channel_map = channel_map;
      this.channel_is_mapped = true;
    }
    this.text_meta = text_meta;

    var self = this;
    // sort the instances by the channel map
    this.channel_map.map(function (v, i) {
      return {
          value1  : v,
          value2  : self.instances[i]
      };
    }).sort(function (a, b) {
      return ((Number(a.value1) < Number(b.value1)) ? -1 : ((a.value1 == b.value1) ? 0 : 1));
    }).forEach(function (v, i) {
        self.channel_map[i] = v.value1;
        self.instances[i] = v.value2;
    });

  }

  HWSelectName() {
    var name = "";
    if (this.hw_select) {
      var select = this.hw_select.split(":"); 
      var col = select[1];
      var val = select[2];
      name = titleize(col) + " " + val;    
    }
    return name;
  }

  // Get the "DataLink" object to be used to query data for a list of
  // time-series
  // stream_index: The index into the streams/stream_links list for the
  //               stream corresponding to the DataLink we want
  // metric_list: The list of metric names to be queried in the
  //              time-series list
  // instance_list: The list of instances to be queried in the time-series
  //             list
  // NOTE: The final list of time-series will be a product of the
  // metric_list and the instance_list. I.e. if len(metric_list) = 3 and
  // len(instance_list) = 5 then there will be 15 total time-series
  // generated
  data_link(stream_index, metric_list, instance_list, instance_skip) {
    if (metric_list === undefined) {
      metric_list = this.config.metric_list;
    }
    if (instance_list === undefined) {
      instance_list = this.instances;
    }
    var instances = [];
    for (var i = 0; i < instance_list.length; i+= instance_skip) {
      instances.push(instance_list[i]);
    }

    // use the hw select link if we use each instance and have a hw_select provided
    if (this.hw_select && instance_skip == 1) {
      return new Data.D3DataLink(new DataLink.HwMetricStreamLink($SCRIPT_ROOT + "/" + this.config.stream_links[stream_index], this.config.streams[stream_index], 
          this.config.group, instances, metric_list, this.hw_select));

    }
    else {
      return new Data.D3DataLink(new DataLink.MetricStreamLink($SCRIPT_ROOT + "/" + this.config.stream_links[stream_index], this.config.streams[stream_index], 
          this.config.group, instances, metric_list, false));
    }
  }

  data_titles(channel_skip) {
    var use_metric_name_as_backup = this.channel_map.length == 1;
    var ret = [];
    for (var i = 0; i < this.config.metric_list.length; i++) {
      for (var j = 0; j < this.channel_map.length; j += channel_skip) {
        ret.push(this.getTitle(this.config.metric_list[i], this.instances[j], this.channel_map[j], use_metric_name_as_backup));
      }
    }
    return ret;
  }

  // Get the time step value corresponding to a certain stream
  // stream_index: the index into the streams/stream_links list of the
  //               `stream to be inspected.
  // callback: Callback function to be called after the time-step value  
  //           is retreived. This function will be passed one argument: 
  //           the time step in milliseconds.
  infer_step(stream_index, callback) {
    if (this.config.stream_links.length == 0) return callback(0);
 
    var link = new DataLink.MetricStreamLink($SCRIPT_ROOT + '/' + this.config.stream_links[stream_index], this.config.streams[stream_index],
        this.config.group, this.instances, this.config.metric_list, false);

    return d3.json(link.step_link(), function(data) { 
        var step = 1000;
        if (data && data.step) step = data.step;
   
        callback(step); 
    });
  }


  runAll() {
    if (this.config.streams.length == 0 || this.config.metric_list == 0) {
      throw_custom_error("No data available for requested group");
      return;
    }
    var self = this;
    var data_link_restricted = this.data_link(this.stream_index, this.metrics, this.instances, this.instance_skip);
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, 1);
    this.infer_step(0, function(step) {
      for (var i = 0; i < self.controllers.length; i++) {
        self.controllers[i].setStep(step);
        if (self.controllers[i].restrictNumInstances()) {
          self.controllers[i].updateData(data_link_restricted);
        }
        else {
          self.controllers[i].updateData(data_link);
        }
      }
    });

    this.updateReferenceData();
    this.updateMeanData();
  }

  // collect default parameters from metric
  default_param(metric) {
    return this.config.metric_config[metric];
  }

  // Internal function: hooks up the defined href to cubism for when the
  // user clicks on a strip chart 
  getLink(index) {
    if (!(this.href === undefined)) {
        // Look up the field at the correct index 
        //
        // This is defined only for cubism controllers. Cubism controllers
        // do have instance_skip set, so we get the correct index
        // by including it 
        return this.href(this.config.group, this.instances[index * this.instance_skip]);
    }
    return undefined;
  }

  // Connect the time-series metric name to a HTML form field 
  // id: the jQuery specified of the HTML form field
  metricController(id) {
    var self = this;
    $(id).change(function() { self.updateMetric([this.value]); });
    return this;
  }

  // Connect the time-series stream name to a HTML form field 
  // id: the jQuery specified of the HTML form field
  streamController(id) {
    var self = this;
    $(id).change(function() {self.updateStream(this.value);});
    return this;
  }

  getTitle(metric_name, instance, channel, use_metric_as_backup) {
    // build the channel name
    var channel_name;
    if (instance == channel) {
      channel_name = instance;
    }
    else {
      channel_name = "local: " + String(channel) + " global: " + String(instance);
    }

    var config = this.config.metric_config[metric_name];
    var title;
    if (config !== undefined) {
      title = this.config.metric_config[metric_name].title;
      if (title !== undefined) {
        title = title.replace("%(instance)s", channel_name).replace("%(group)s", this.config.group);    
      }
    }
    if (title === undefined) {
     // use metric as backup title
     if (use_metric_as_backup) {
       title = metric_name;
     }
     else {
       title = channel_name;
     }
    }
    return title;
  }


  processMetricConfig() {
    var ret = $.extend({}, this.metric_config);
    // fix the title
    if (this.metric_config !== undefined && this.metric_config.title !== undefined) {
      ret.title = this.metric_config.title.replace("%(instance)s", this.config.group).replace("%(group)s", this.config.group);
    }
    return ret;
  }

  // Internal function: change the metric name being shown in the cubism charts
  updateMetric(metrics) {
    this.metrics = metrics;
    if (metrics !== undefined && metrics.length == 1) {
      this.metric_config = this.config.metric_config[metrics[0]];
    }
    else {
      this.metric_config = undefined;
    }

    var data_link_restricted = this.data_link(this.stream_index, this.metrics, this.instances, this.instance_skip);
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, 1);

    var data_titles_restricted = this.data_titles(this.instance_skip);
    var data_titles = this.data_titles(1);

    var metric_config = this.processMetricConfig();
     
    for (var i = 0; i < this.controllers.length; i++) {
      if (this.controllers[i].restrictNumInstances()) {
        this.controllers[i].updateData(data_link_restricted, true);
        this.controllers[i].updateTitles(data_titles_restricted);
      }
      else {
        this.controllers[i].updateData(data_link, true);
        this.controllers[i].updateTitles(data_titles);
      }
      this.controllers[i].updateMetricConfig(metric_config);
    }
    this.updateReferenceData();
    this.updateMeanData();
  } 

  updateReferenceData() {
    var archived_stream = this.config.streams.indexOf("archived");
    if (archived_stream >= 0) { // if the archived stream exists
      var link = this.data_link(archived_stream, this.metrics, this.instances, 1);
      var accessors = link.accessors();
      var self = this;
      d3.json(link.link_builder.ref_link(), function(error, data) {
        if (!data) {
          return;
        }

        var out = [];
        for (var i = 0; i < accessors.length; i++) {
          var this_data = data.values;
          for (var k = 0; k < accessors[i].length; k++) {
            this_data = this_data[accessors[i][k]];
            if (this_data == undefined) {
              break;
            }
          }
          if (this_data && this_data.length > 0) {
            out.push(this_data[0]);
          }
        }
        for (var i = 0; i < self.controllers.length; i++) {
          self.controllers[i].updateReferenceData(out);
        }
      });
    }
  }

  updateMeanData() {
    var archived_stream = this.config.streams.indexOf("mean");
    if (archived_stream >= 0) { // if the archived stream exists
      var link = this.data_link(archived_stream, this.metrics, this.instances, 1);
      var accessors = link.accessors();
      var self = this;
      d3.json(link.link_builder.ref_link(), function(error, data) {
        if (!data) {
          return;
        }

        var out = [];
        for (var i = 0; i < accessors.length; i++) {
          var this_data = data.values;
          for (var k = 0; k < accessors[i].length; k++) {
            this_data = this_data[accessors[i][k]];
            if (this_data == undefined) {
              break;
            }
          }
          if (this_data && this_data.length > 0) {
            out.push(this_data[0]);
          }
        }
        for (var i = 0; i < self.controllers.length; i++) {
          self.controllers[i].updateMeanData(out);
        }
      });
    }
  }

  // Internal function: change the stream name of the time-series
  // plotted in cubism 
  updateStream(input) {
    this.stream_index = input;
    var self = this;
    this.infer_step(input, function(step) {
      var data_link = self.data_link(self.stream_index, self.metrics, self.instances, 1);
      var data_link_restricted = self.data_link(self.stream_index, self.metrics, self.instances, self.instance_skip);
      for (var i = 0; i < self.controllers.length; i++) {
        self.controllers[i].updateStep(step);
        if (self.controllers[i].restrictNumInstances()) {
          self.controllers[i].updateData(data_link_restricted, true);
        }
        else {
          self.controllers[i].updateData(data_link, true);
        }
      }
    });
  }

  // add a cubism controller 
  addCubismController(target, height) {
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, this.instance_skip);
    var data_titles = this.data_titles(this.instance_skip);
    var controller = new TimeSeriesControllers.CubismController(target, data_link, data_titles, this.processMetricConfig(), height);
    if (this.href !== undefined ) {
      controller.setLinkFunction(this.getLink.bind(this));
    }
    this.controllers.push(controller);
    return controller;
  }

  // add a plotly controller
  addPlotlyController(target) {
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, this.instance_skip);
    var data_titles = this.data_titles(this.instance_skip);
    var controller = new TimeSeriesControllers.PlotlyController(target, data_link, data_titles, this.processMetricConfig());
    this.controllers.push(controller);
    return controller;
  }

  // add a group data controller
  addGroupDataScatterController(target, title) {
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, 1);

    var text = null;
    // build the list of global channel names
    if (this.channel_is_mapped) {
      var text = [];
      for (var i = 0; i < this.channel_map.length; i++) {
        text.push("Global Channel: " + String(this.instances[i]));
      }
      var xLabel = "Local Channel"
    }
    else if (this.text_meta) {
      text = this.text_meta;
    }
    else {
      var text = null;
      var xLabel = this.config.group;
    }

    var controller = new GroupDataControllers.GroupDataScatterController(target, data_link, this.processMetricConfig(), title, xLabel, this.channel_map, text);
    this.controllers.push(controller);
    return controller;
  }

  // add a group data controller
  addGroupDataHistoController(target, title) {
    var data_link = this.data_link(this.stream_index, this.metrics, this.instances, 1);
    var controller = new GroupDataControllers.GroupDataHistoController(target, data_link, this.processMetricConfig(), title, "# " + this.config.group);
    this.controllers.push(controller);
    return controller;
  }
}

