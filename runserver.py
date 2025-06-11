#!/usr/bin/env python
from __future__ import absolute_import
from minargon import app
import random

print("Open http://localhost:9394/")

app.run(debug=True, port=9394)
