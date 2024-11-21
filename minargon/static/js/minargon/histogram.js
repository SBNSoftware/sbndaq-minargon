import * as Data from "./Data.js";
import * as DataLink from "./DataLink.js";
import * as Chart from "./charts.js";
import {titleize} from "./titleize.js";

// re-export DataLink
export {DataLink, Data};

// This file contains a few classes for plotting time-series data using histograms
//
// Available classes
// HistController: manages a histogram from a provided DataLink along
//                 with a provided metric_config object
// Each of these classes manages a D3DataBuffer object to get data and
// displays a number of strip charts to visualize the data. Each class
// also manages interfaces with the webpage UI for specifying the format
// of the plots to be shown.


// To set up each class, call the contructor, then connect a number UI
// components (using the various "xxxController" functions), then call
// run()
//
// Alternatively, you can also set them up through the
// GroupConfigController if you want them to handle a group of metrics
// -----------------------------------------------------------------------------
export class HistController {
  // target: the div-id (including the '#') where the cubism plots will
  //         be drawn
  // links: the DataLink object which will be used to get data to plot
  // metric_config: The metric configuration for the associated plot
  constructor(target, link, titles, metric_config, plot_title, include_history, split_channels) {
    this.link = link;
    this.target = target;
    this.max_data = 1000;
    this.trace_names = titles;

    // optional parameters default to false
    this.include_history = include_history;
    if (this.include_history === undefined) this.include_history = false;

    this.split_channels = split_channels;
    if (this.split_channels === undefined) this.split_channels = false;

    this.plot_title = plot_title;

    // make a new plotly scatter plot
    var layout = this.layoutHistogram();
    this.histogram =  new Chart.Histogram(this.target, layout, this.include_history, this.split_channels);

    if (this.trace_names) this.histogram.trace_names = this.trace_names;

    this.histogram.draw();
    // appply config
    this.updateMetricConfig(metric_config, false);

    this.is_live = true;
    this.is_running = false;
  }
  // ---------------------------------------------------------------------------
  // commuicate to the "config" wrapper -- whether or not the # of instances in this class should be restricted
  restrictNumInstances() {
    return true;
  }
  updateReferenceData() {} // noop

  updateMeanData() {} // noop

  layoutHistogram() {
    var metric_name = this.link.name();

    var title = this.plot_title + " " + metric_name;

    var ret = {
      title: titleize(title),
      xaxis: {
        title: metric_name,
      }
    };

    return ret;
  }

  setPlotTitle(title) {
    this.histogram.title = title;
  }

  // ---------------------------------------------------------------------------
  // Internal function: grap the time step from the server and run a
  // callback
  getTimeStep(callback) {
    var self = this;
    this.link.get_step(function(data) {
        callback(self, data.step);
    });
  }
  // ---------------------------------------------------------------------------
  // start running
  run() {
    this.is_running = true;
    this.getTimeStep(function(self, step) {
      self.updateStep(step);
      self.updateData(self.link);
    });
  }
  // ---------------------------------------------------------------------------
  // Functions called by the GroupConfigController
  // update the titles
  updateTitles(trace_names) {
    this.histogram.trace_names = trace_names;
    this.trace_names = trace_names;
  }
  // ---------------------------------------------------------------------------
  // update the metric config option
  updateMetricConfig(config, do_append) {
    if (do_append === undefined || !do_append) {
      this.metric_config = [config];
    }
    else {
      this.metric_config.push(config);
    }
  }
  // ---------------------------------------------------------------------------
  // update the data step
  updateStep(step) {
    if (step < 10000) step = 10000;
    this.step = step;
    // set the plot to ignore data from big skips in time
    this.histogram.crop_range = this.step * 100;
  }
  // ---------------------------------------------------------------------------
  // set the step for the first time
  setStep(step) {
    this.updateStep(step);
  }
  // ---------------------------------------------------------------------------
  // update the data link and start polling for new data
  updateData(link) {
    this.link = link;

    // reset the poll
    if (!(this.buffer === undefined) && this.buffer.isRunning()) {
      this.buffer.stop();
    }

    // make a new buffer
    // get the poll
    var poll = new Data.D3DataPoll(this.link, this.step, []);

    // get the data source
    //var source = new Data.D3DataSource(this.link, -1);

    // wrap with a buffer
    this.buffer = new Data.D3DataBuffer(poll, this.max_data, [this.histogram.updateData.bind(this.histogram)]);
    // run it
    this.runBuffer();
  }
 
  setDataRange(start, stop) {
    this.is_live = false;
    this.start = start;
    this.end = end;
  }

  // ---------------------------------------------------------------------------
  // Tell the buffer to get data for a specific time range
  getData(start, stop) {
    this.buffer.stop();
    this.buffer.getData(start, stop);
  }
  // ---------------------------------------------------------------------------
  // Connect setting the time range of the data to be shown to an HTML
  // form
  // id_start: The id of the datatimepicker controlled form field which
  //           holds the start time
  // id_end: The id of the datatimepicker controlled form field which
  //         folds the end time
  // id_toggle: The id of the toggle object which could either specify
  //            "live" -- update in real time, or "lookback" -- get data
  //            from the id_start/id_end time range
  timeRangeController(id_start, id_end, id_toggle) {
    var self = this;

    self.listDateChangeEVTTime = 0;
    $(id_toggle).on("date-change", function() {
      // There is a bug in the date-picker library where this
      // event fires multiple times. "Debounce" this event fire
      // with a timer check.
      var fire = true;
      if (event.timeStamp - self.listDateChangeEVTTime < 500){
        fire = false;
      }
      self.listDateChangeEVTTime = event.timeStamp;
      if (!fire) return;

      var toggle_val = $(id_toggle).val();
      if (toggle_val == "live" ) {
        self.is_live = true;
      }
      else if (toggle_val == "lookback") {
        self.start = $(id_start).datetimepicker('getValue');
        self.end = $(id_end).datetimepicker('getValue');
        self.is_live = false;
        // stop the buffer
        if (self.buffer.isRunning()) {
          self.buffer.stop();
        }
      }
      else if (toggle_val == "hour"){
        var d = new Date();
        d.setHours(d.getHours() -1);
        self.start = d;
        self.end = new Date();
        self.is_live = false;
        // stop the buffer
        if (self.buffer.isRunning()) {
          self.buffer.stop();
        }
      }
      else if (toggle_val == "8hour"){
        var d = new Date();
        d.setHours(d.getHours()-8);
        self.start = d;
        self.end = Date.now();
        self.is_live = false;
        // stop the buffer
        if (self.buffer.isRunning()) {
          self.buffer.stop();
        }
      }
      else if (toggle_val == "day"){
        var d = new Date();
        d.setDate(d.getDate() -1);
        self.start = d;
        self.end = new Date();
        self.is_live = false;
        // stop the buffer
        if (self.buffer.isRunning()) {
          self.buffer.stop();
        }
      }
      else if (toggle_val == "week"){
        var d = new Date();
        d.setDate(d.getDate() -7);
        self.start = d;
        self.end = Date.now();
        self.is_live = false;
        // stop the buffer
        if (self.buffer.isRunning()) {
          self.buffer.stop();
        }
      }

      self.runBuffer();
    });

    //loading the page it makes plots with a fixed time of 6 hours
    var toggle_val = $(id_toggle).val();
    if (toggle_val == "startWith6hour"){
      var d = new Date();
      d.setHours(d.getHours()-6);
      self.start = d;
      self.end = Date.now();
      self.is_live = false;
    }
    return this;
  }
  // ---------------------------------------------------------------------------
  downloadDataController(id) {
    var self = this;
    $(id).click(function() {
      self.download("data.json", JSON.stringify(self.downloadFormat()));
    });
    return this;
  }

  // ---------------------------------------------------------------------------
  runBuffer() {
    if (this.is_live) {
      this.histogram.crop_old_data = true;
      // set the start
      // to be on the safe side, get back to ~1000 data points
      this.start = new Date(); 
      this.start.setSeconds(this.start.getSeconds() - this.step * this.max_data / 1000); // ms -> s
      this.buffer.start(this.start);
    }
    else {
      this.histogram.crop_old_data = false;
      this.buffer.getData(this.start, this.end);
    }
  }

  // ---------------------------------------------------------------------------
  downloadFormat() {
    // get the number of input streams controlled by this plot
    var n_data = this.link.accessors().length;
    var ret = {};
    for (var i = 0; i < n_data; i++) {
      ret[this.trace_names[i]] = this.buffer.buffers[i].get(0, this.buffer.buffers[i].size);
    }
    return ret;
  }
  // ---------------------------------------------------------------------------
  download(filename, data) {
    var blob = new Blob([data], {type: 'text/csv'});
    if(window.navigator.msSaveOrOpenBlob) {
      window.navigator.msSaveBlob(blob, filename);
    }
    else{
      var elem = window.document.createElement('a');
      elem.href = window.URL.createObjectURL(blob);
      elem.download = filename;        
      document.body.appendChild(elem);
      elem.click();        
      document.body.removeChild(elem);
    }
  }
}
