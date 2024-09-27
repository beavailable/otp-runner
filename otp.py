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
    offset = mac[-1] & 0x0f
    binary = struct.unpack('>L', mac[offset:offset + 4])[0] & 0x7fffffff
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


def bus_name_available(name):
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS, None, 'org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', None)
        proxy.GetNameOwner('(s)', name)
    except GLib.Error:
        return True
    else:
        return False


class KWallet:

    def __init__(self, app_id):
        self._proxy = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION, Gio.DBusProxyFlags.DO_NOT_CONNECT_SIGNALS, None, 'org.kde.kwalletd5', '/modules/kwalletd5', 'org.kde.KWallet', None)
        self._app_id = app_id
        self._handle = 0

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

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


class DBusService:

    def __init__(self, introspection_xml, name, object_path):
        self._interface = Gio.DBusNodeInfo.new_for_xml(introspection_xml).interfaces[0]
        self._name = name
        self._objct_path = object_path
        self._registration_id = None
        self._owner_id = None
        self._loop = GLib.MainLoop()

    def _on_bus_acquired(self, bus, name):
        self._registration_id = bus.register_object(self._objct_path, self._interface, self._on_method_call)

    def _on_name_acquired(self, bus, name):
        pass

    def _on_name_lost(self, bus, name):
        if self._registration_id:
            bus.unregister_object(self._registration_id)
            self._registration_id = None

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

    def run(self):
        if not bus_name_available(self._name):
            sys.exit(1)

        self._owner_id = Gio.bus_own_name(Gio.BusType.SESSION, self._name, Gio.BusNameOwnerFlags.DO_NOT_QUEUE, self._on_bus_acquired, self._on_name_acquired, self._on_name_lost)
        self._loop.run()

    def quit(self):
        if self._owner_id:
            Gio.bus_unown_name(self._owner_id)
            self._owner_id = None
            self._loop.quit()


class OTPService(DBusService):

    def __init__(self, name):
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
        super().__init__(introspection_xml, name, '/otp')
        self._wallet = None
        self._value = None
        self._source_id = 0

    def open_wallet(self):
        if not self._wallet:
            self._wallet = KWallet(self._name)
            self._wallet.open()

    def on_timeout(self, data):
        self.quit()
        self._source_id = 0
        return False

    def quit(self):
        super().quit()
        if self._wallet:
            self._wallet.close()
            self._wallet = None

    def Match(self, query):
        if self._source_id > 0:
            GLib.source_remove(self._source_id)
        self._source_id = GLib.timeout_add_seconds(120, self.on_timeout, None)

        args = query.split()
        if args[0] != 'otp':
            return []
        unknowk_result = [('', '- - - - - -', 'otp', 100, 1.0, {})]
        if len(args) == 2:
            try:
                self.open_wallet()
            except RuntimeError:
                return unknowk_result
            key = self._wallet.read_password('OTP Keys', args[1])
            if key:
                self._value = totp(key)
                return [('copy', self._value, 'otp', 100, 1.0, {})]
            else:
                return unknowk_result
        if len(args) == 3:
            self._value = (args[1], args[2])
            return [('write', 'Press enter to store the key', 'otp', 100, 1.0, {})]
        else:
            return unknowk_result

    def Actions(self):
        return []

    def Run(self, match_id, action_id):
        if match_id == 'copy':
            copy_text(self._value)
        elif match_id == 'write':
            try:
                self.open_wallet()
            except RuntimeError:
                pass
            else:
                self._wallet.create_folder('OTP Keys')
                self._wallet.write_password('OTP Keys', self._value[0], self._value[1])


def main():
    if len(sys.argv) == 1:
        service = OTPService('com.github.otp')
        service.run()
    elif len(sys.argv) == 2:
        with KWallet('com.github.otp') as wallet:
            key = wallet.read_password('OTP Keys', sys.argv[1])
            if key:
                print(totp(key))
            else:
                sys.exit(1)
    elif len(sys.argv) == 3:
        with KWallet('com.github.otp') as wallet:
            wallet.create_folder('OTP Keys')
            wallet.write_password('OTP Keys', sys.argv[1], sys.argv[2])
    else:
        sys.exit(1)


main()
