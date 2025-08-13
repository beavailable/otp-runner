#!/bin/env python3
import sys
import base64
import hmac
import time
import struct
import shutil
import subprocess

from gi.repository import Gio, GLib

# The hotp and totp functions are from https://github.com/susam/mintotp by Susam Pal, licensed under the MIT License.
# Modifications have been made to the original code.

# License text:

# The MIT License (MIT)
# =====================
#
# Copyright (c) 2019 Susam Pal
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


def hotp(key, counter, digits=6):
    key = base64.b32decode(key.upper() + '=' * ((8 - len(key)) % 8))
    counter = struct.pack('>Q', counter)
    mac = hmac.new(key, counter, 'sha1').digest()
    offset = mac[-1] & 0x0F
    binary = struct.unpack('>L', mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary)[-digits:].zfill(digits)


def totp(key):
    return hotp(key, int(time.time() / 30))


def copy_text(text):
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS, None, 'org.kde.klipper', '/klipper', 'org.kde.klipper.klipper', None)
        proxy.setClipboardContents('(s)', text)
    except GLib.Error:
        if shutil.which('wl-copy'):
            subprocess.run(['wl-copy', text])
        elif shutil.which('xclip'):
            process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE, text=True)
            try:
                process.communicate(input=text, timeout=10)
            except subprocess.TimeoutExpired:
                pass
            process.terminate()


class KWallet:

    def __init__(self, app_id):
        self._proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS, None, 'org.kde.kwalletd6', '/modules/kwalletd6', 'org.kde.KWallet', None)
        self._app_id = app_id
        self._handle = 0

    def open(self):
        if self._handle <= 0:
            self._handle = self._proxy.open('(sxs)', 'kdewallet', 0, self._app_id)
            if self._handle <= 0:
                raise RuntimeError('Open failed')

    def read_password(self, folder, key):
        return self._proxy.readPassword('(isss)', self._handle, folder, key, self._app_id)

    def write_password(self, folder, key, value):
        return self._proxy.writePassword('(issss)', self._handle, folder, key, value, self._app_id) == 0

    def create_folder(self, folder):
        return self._proxy.createFolder('(iss)', self._handle, folder, self._app_id)

    def close(self):
        if self._handle > 0:
            self._proxy.close('(ibs)', self._handle, False, self._app_id)
            self._handle = 0


class OTPApplication(Gio.Application):

    def __init__(self, **kwargs):
        super().__init__(**kwargs, flags=Gio.ApplicationFlags.ALLOW_REPLACEMENT | Gio.ApplicationFlags.REPLACE, inactivity_timeout=120 * 1000)
        self._registration_id = None
        self._wallet = KWallet(self.get_application_id())
        self._wallet.open()
        self._value = None

    def _on_method_call(self, connection, sender, object_path, interface_name, method_name, parameters, invocation):
        func = getattr(self, method_name)
        args = parameters.unpack()
        result = func(*args)
        if result is None:
            result = ()
        else:
            result = (result,)
        outargs = ''.join(arg.signature for arg in invocation.get_method_info().out_args)
        invocation.return_value(GLib.Variant(f'({outargs})', result))

    def _read_otp_key(self, name):
        return self._wallet.read_password('OTP Keys', name)

    def _write_otp_key(self, name, key):
        self._wallet.create_folder('OTP Keys')
        self._wallet.write_password('OTP Keys', name, key)

    def do_local_command_line(self, arguments):
        if len(arguments) == 1:
            return Gio.Application.do_local_command_line(self, arguments)
        elif len(arguments) == 2:
            key = self._read_otp_key(arguments[1])
            if key:
                print(totp(key))
                return (True, [], 0)
            else:
                return (True, [], 1)
        elif len(arguments) == 3:
            self._write_otp_key(arguments[1], arguments[2])
            return (True, [], 0)
        else:
            return (True, [], 1)

    def do_dbus_register(self, connection, object_path):
        introspection_xml = '''
            <node>
                <interface name="org.kde.krunner1">
                    <method name="Match">
                        <arg name="query" type="s" direction="in" />
                        <arg name="matches" type="a(sssida{sv})" direction="out" />
                    </method>
                    <method name="Actions">
                        <arg name="matches" type="a(sss)" direction="out" />
                    </method>
                    <method name="Run">
                        <arg name="matchId" type="s" direction="in" />
                        <arg name="actionId" type="s" direction="in" />
                    </method>
                </interface>
            </node>
        '''
        interface_info = Gio.DBusNodeInfo.new_for_xml(introspection_xml).interfaces[0]
        self._registration_id = connection.register_object('/otp', interface_info, self._on_method_call)
        return Gio.Application.do_dbus_register(self, connection, object_path)

    def do_dbus_unregister(self, connection, object_path):
        Gio.Application.do_dbus_unregister(self, connection, object_path)
        if self._registration_id:
            connection.unregister_object(self._registration_id)

    def do_activate(self):
        self.hold()
        self.release()

    def do_shutdown(self):
        Gio.Application.do_shutdown(self)
        self._wallet.close()

    def Match(self, query):
        self.do_activate()
        args = query.split()
        if args[0] != 'otp':
            return []
        unknown_result = [('', '- - - - - -', 'otp', 100, 1.0, {})]
        if len(args) == 2:
            key = self._read_otp_key(args[1])
            if key:
                self._value = totp(key)
                return [('copy', f'{self._value[0]}****{self._value[-1]}', 'otp', 100, 1.0, {})]
            else:
                return unknown_result
        if len(args) == 3:
            self._value = (args[1], args[2])
            return [('write', 'Press enter to store the key', 'otp', 100, 1.0, {})]
        else:
            return unknown_result

    def Actions(self):
        return []

    def Run(self, match_id, action_id):
        if match_id == 'copy':
            copy_text(self._value)
        elif match_id == 'write':
            self._write_otp_key(*self._value)


def main():
    app = OTPApplication(application_id='com.github.otp')
    sys.exit(app.run(sys.argv))


main()
