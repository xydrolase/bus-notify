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

from utils    import GMapMetadata
from geotile  import GlobalMercator
from time     import sleep
from datetime import datetime
from math     import floor
# Gtk
import gi                                                                                                                                                  
gi.require_version('Gtk', '3.0')
from gi.repository import GObject, Gtk, Notify

class BusNotify:
    def __init__(self, lat=None, lng=None, radius=500):
        self.lat = lat
        self.lng = lng
        self.radius = radius
        self.zoom = 17
        self.ftid = None
        self.mercator = GlobalMercator(tileSize = 256)
        self.gmm = GMapMetadata(zoom=self.zoom)

        Notify.init('bus-notify')

    def main(self):
        win = Gtk.Window(title="Bus Notify")
        win.set_border_width(10)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        self.title_label = Gtk.Label(label="Select a nearby bus stop.", 
                justify=Gtk.Justification.LEFT)
        vbox.pack_start(self.title_label, False, False, 0)

        self.bus_stops = self.proximity_search(self.lat, self.lng,
                self.radius, self.zoom)

        bus_list = Gtk.ListStore(str, str)
        for ftid, stop in self.bus_stops.iteritems():
            bus_list.append([str(ftid), str(stop['caption'])])

        self.combo_bus_stops = Gtk.ComboBox.new_with_model(bus_list)
        renderer_text = Gtk.CellRendererText()
        self.combo_bus_stops.pack_start(renderer_text, True)
        self.combo_bus_stops.add_attribute(renderer_text, "text", 1)
        self.combo_bus_stops.connect("changed", self.on_select_stop)

        vbox.pack_start(self.combo_bus_stops, False, False, 0)

        self.stop_assoc_lines = Gtk.ListStore(int, str)
        self.combo_lines = Gtk.ComboBox.new_with_model(self.stop_assoc_lines)
        renderer_text = Gtk.CellRendererText()
        self.combo_lines.pack_start(renderer_text, True)
        self.combo_lines.add_attribute(renderer_text, "text", 1)
        self.combo_lines.connect('changed', self.on_select_line)

        vbox.pack_start(self.combo_lines, False, False, 0)

        win.add(vbox)
        win.connect("delete-event", Gtk.main_quit)
        win.show_all()
        Gtk.main()

    def on_select_stop(self, combo):
        combo_iter = combo.get_active_iter()
        if combo_iter != None:
            model = combo.get_model()
            ftid = model[combo_iter][0]

            self.watched_stop = model[combo_iter][1]

            self.bus_lines = self.gmm.get_stop_metadata(ftid)
            if self.bus_lines:
                self.stop_assoc_lines.clear()
                for subscript, line in enumerate(self.bus_lines['lines']):
                    self.stop_assoc_lines.append(
                        [
                            subscript, 
                            ' - '.join([line['line'], line.get('direction', '')])
                        ])
        pass

    def on_select_line(self, combo):
        combo_iter = combo.get_active_iter()
        if combo_iter != None:
            model = combo.get_model()
            line_index = model[combo_iter][0]

            if self.bus_lines and line_index < len(self.bus_lines['lines']):
                self.watch(self.bus_lines['lines'][line_index])

    def watch(self, line):
        self.watched_line = ' - '.join([line['line'], 
            line.get('direction', '')])

        self.watched_schedules = [datetime.combine(datetime.today(),
            datetime.strptime(tp[0], "%I:%M %p").time())
            for tp in line['schedules']]

        self.title_label.set_label("Start watching " + self.watched_line)
        self.combo_lines.set_sensitive(False)
        self.combo_bus_stops.set_sensitive(False)

        self.check_schedule(immediate=True)

    def check_schedule(self, immediate=False):
        for t in self.watched_schedules:
            minutes_to_due = floor((t - datetime.now()).total_seconds() / 60.)
            if immediate and minutes_to_due > 0 \
                    or (minutes_to_due <= 20 and \
                    minutes_to_due in (0, 5, 10, 20)):
                notify = Notify.Notification.new(
                        "%s is due in %d minutes" % (
                            self.watched_line, minutes_to_due),
                        "@ %s on %s" % (
                            self.watched_stop, 
                            t.strftime("%I:%M %p")),
                        None)
                notify.show()

                break

        # set next timeout
        GObject.timeout_add_seconds(60, self.check_schedule)

    def proximity_search(self, lat, lng, radius=500, zoom=17):
        mx, my = self.mercator.LatLonToMeters(lat, lng)
        tx_prime, ty_prime = self.mercator.MetersToTile(mx - radius,
                my + radius, zoom)
        tx_prime, ty_prime = self.mercator.GoogleTile(tx_prime, ty_prime, zoom)

        tx, ty = self.mercator.MetersToTile(mx, my, zoom)
        tx, ty = self.mercator.GoogleTile(tx, ty, zoom)

        landmarks = self.gmm.get_landmarks(tx_prime, ty_prime,
                max(tx - tx_prime, ty - ty_prime) * 2)

        stops = self.gmm.extract_bus_stops(landmarks)
        return stops

lat, lng = 42.02891, -93.647096
bn = BusNotify(lat, lng, 500)
bn.main()
