#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2011 Xin Yin <killkeeper at gmail dot com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.                                                                                         
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import re
import json
from urllib     import urlopen, urlencode
from random     import randint
from itertools  import product
from HTMLParser import HTMLParser


class GMapMetadata:
    """Utitility class to retrieve and process metadata information that is
    typically seen on Google Maps."""

    def __init__(self, zoom=16):
        self.zoomlevel = zoom 

    def generate_callback(self):
        """Generate a pseudo callback hash (for simulating "real" request
        purpose)."""
        return ''.join([chr(97+x) if x < 26 else chr(48+x-26) 
            for x in [randint(0, 35) for i in range(9)]])

    def geohash_to_tile(self, hash):
        """Extract the tile number (x, y) from the 4-radix "geospatial hash" (kind
        of) representataion.
        
        Each 4-base digit is encoded with characters 't', 'u', 'v' ,'w',
        corresponding to 0, 1, 2, 3 respetively. 

        Consider each digit within the 4-radix number as two bits in binary. The
        higher bit maps to x, while the lower bit maps to y.
        """
        exponent = len(hash)-1
        bits = map(lambda x: ord(x) - 116, list(hash))
        x = y = 0

        for idx in range(len(bits)):
            shift = exponent-idx
            x += ((bits[idx] & 2) >> 1) << shift
            y += (bits[idx] & 1) << shift

        return x, y

    def tile_to_geohash(self, x, y, zoom=None):
        """Convert given tile coordinates to Google's geohash."""

        bstr = lambda n, l=16: n<0 and bstr((2L<<l)+n) or n and bstr(n>>1).lstrip('0')+str(n&1) or '0'

        if zoom == None:
            zoom = self.zoomlevel

        x_bits = map(lambda b: int(b), list(bstr(x)))
        y_bits = map(lambda b: int(b), list(bstr(y)))

        x_bits = [0] * (zoom - len(x_bits)) + x_bits
        y_bits = [0] * (zoom - len(y_bits)) + y_bits

        return ''.join([chr(((bx << 1) | by) + 116) 
            for bx, by in zip(x_bits, y_bits)])

    def get_landmarks(self, tx, ty, width):
        """Find landmarks in a WxW block of tiles, within which the top-left
        tile is (x,y).""" 

        tile_hash = [self.tile_to_geohash(x, y)
                for x, y in product(range(tx, tx+width), range(ty, ty+width))]

        url_params = urlencode(
                {
                    'lyrs': 'm@145', # default layer
                    'las': ','.join(tile_hash), # tiles to query
                    'gl': 'us',
                    'hl': 'en',
                    'xc': 1,
                    'z': self.zoomlevel,
                    'opts': 'z',
                    'callback': '_xdc_._%s' % self.generate_callback()
                })

        # Randomly balance requests to different servers.
        url = 'http://mt%(server)d.google.com/vt/ft?%(param)s' % \
                ({
                'server': randint(0, 1),
                'param': url_params
            })

        try:
            f = urlopen(url)
            assert f.getcode() == 200
            return f.read()
        except Exception:
            return None

    def extract_bus_stops(self, response):
        """Find all bus stops within response from API service:
            http://mt0.google.com/vt/ft?lyrs=...&las=...

        We could identify bus stop metadata by recognizing its unique (or not?)
        bounding box [-7, -7, 6, 6]."""

        # Seems to be response w/o useful data
        if response.find('features') == -1:
            return None

        # Some cleaning before JSON library could start its job.
        json_raw = re.sub(r'([{,])([a-z_]+):', r'\1"\2":', 
                response[response.find('(') + 1:response.rfind(')')])
        json_raw = re.sub(r'\"c\":\"\{1:\{(.+?)\}\}"', r'"c":{\1}', json_raw)
        # fix for numeric property names (evil!)
        json_raw = re.sub(r',(\d+):', r',"\1":', json_raw)
        json_raw = json_raw.replace(r'\"', '"')
        json_raw = json_raw.replace(r'\\"', r'\"')

        # Find out all nodes with "features" list.
        metadata = filter(lambda d: 'features' in d, json.loads(json_raw))
        busstops = {}
        try:
            for node in metadata:
                for feat in node['features']:
                    # Identify bus stop by its bounding box (might has problems?)
                    if feat['bb'] == [-7, -7, 6, 6] and \
                            feat['id'] not in busstops:
                        busstops.setdefault(feat['id'], {})
                        busstops[feat['id']]['caption'] = feat['c']['title'] 
        except ValueError:
            return False 

        return busstops

    def get_stop_metadata(self, ftid):
        """Use Google's transit service to get detailed metadata associated
        with given ftid, which is a unique identifier for each landmark (bus
        stop)."""

        bus_node = {}

        convert_chars = lambda match: chr(int(match.group(1), 16)) \
                if match.group(1) else match.group(0)

        url_params = {
                'ftid': ftid,
                'lyr' : 'm@140', # default layer
                'iwp' : 'maps_app',
                'callback' : '_xdc_._%s' % self.generate_callback
            }

        url = "http://maps.google.com/maps/iw?%s" % \
                urlencode(url_params)
        
        f = urlopen(url)
        assert f.getcode() == 200

        try:
            response = re.sub(
                    r'\\x(\w{2})',
                    convert_chars,
                    f.read())

            meta = json.loads(response)
            bus_node['latlng'] = (meta['latlng']['lat'], meta['latlng']['lng'])
        
            if 'infoWindow' in meta:
                info = meta['infoWindow']
                schedule = info['transitSchedules']['stationSchedules']
                
                bus_node['agency'] = schedule['agencies'][0]['agency_name']
        except ValueError:
            return 

        # Retrieve schedule for bus lines at this stop, using Google's transit service 
        url = 'http://maps.google.com/maps/place?ftid=%s' % ftid
        f = urlopen(url)
        
        assert f.getcode() == 200
        metadata = f.read()

        start = metadata.find('<table class="tppjt"')
        end = metadata.find("</table>", start)

        line_parser = BusDOMParser()
        line_parser.feed(metadata[start:end+8])
        line_parser.close()

        bus_node['lines'] = line_parser.lines

        return bus_node

class BusDOMParser(HTMLParser):
    """HTML parser used to parse transit information."""

    def __init__(self):
        self.lines = []
        self.flag = None
        self.tagstack = []
        self.color = re.compile('background:(\#[a-z0-9]{6});')
        self.regex_time = re.compile(r'(\d{1,2}\:\d{2})(am|pm)')
        HTMLParser.__init__(self)

    def handle_starttag(self, tag, attrs):
        self.tagstack.append(tag)

        if tag == 'tr':
            self.line = {}
        elif tag == 'td':
            element_classes = filter(lambda x: x[0] == 'class', attrs)
            if element_classes: 
                element_classes = element_classes[0][1].split(' ')

                if 'nextday' in element_classes:
                    # time schedule
                    self.flag = 'timend'
                elif 'time' in element_classes:
                    self.flag = 'time'
                elif 'tppjdh' in element_classes:
                    # direction
                    self.flag = 'direction'
                elif 'tppjln-short' in element_classes:
                    self.flag = 'line'

        elif tag == 'div':
            attr_style = filter(lambda x: x[0] == 'style', attrs)
            if attr_style:
                color_match = self.color.search(attr_style[0][1])
                if color_match:
                    self.line['color'] = color_match.group(1)

    def handle_data(self, data):
        if self.flag in ('time', 'timend') \
            and self.tagstack[len(self.tagstack)-1] == 'td':
            self.line.setdefault('schedules', [])

            _match = self.regex_time.search(data)
            if _match:
                self.line['schedules'].append(
                        (' '.join(_match.groups()), self.flag=='timend'))
        elif self.flag == 'direction':
            if self.tagstack[-2:] == ['tr','td']:
                self.line['direction'] = data
        elif self.flag == 'line':
            if self.tagstack[-3:] == ['td', 'div', 'div']:
                self.line['line'] = data

    def handle_endtag(self, tag):
        self.tagstack.pop()

        if tag == 'tr':
            # Inherit the line number from the bus of different direction.
            if 'line' not in self.line and len(self.lines) > 0:
                self.line['line'] = self.lines[len(self.lines)-1]['line']
                self.line['color'] = self.lines[len(self.lines)-1].get('color', None)
            self.lines.append(self.line)
