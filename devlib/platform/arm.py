#    Copyright 2015 ARM Limited
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
#
from __future__ import division
import os
import tempfile
import csv
import time
import pexpect

from devlib.platform import Platform
from devlib.instrument import Instrument, InstrumentChannel, MeasurementsCsv, Measurement,  CONTINUOUS,  INSTANTANEOUS
from devlib.exception import TargetError, HostError
from devlib.host import PACKAGE_BIN_DIRECTORY
from devlib.utils.serial_port import open_serial_connection


class VersatileExpressPlatform(Platform):

    def __init__(self, name,  # pylint: disable=too-many-locals

                 core_names=None,
                 core_clusters=None,
                 big_core=None,
                 modules=None,

                 # serial settings
                 serial_port='/dev/ttyS0',
                 baudrate=115200,

                 # VExpress MicroSD mount point
                 vemsd_mount=None,

                 # supported: dtr, reboottxt
                 hard_reset_method=None,
                 # supported: uefi, uefi-shell, u-boot, bootmon
                 bootloader=None,
                 # supported: vemsd
                 flash_method='vemsd',

                 image=None,
                 fdt=None,
                 initrd=None,
                 bootargs=None,

                 uefi_entry=None,  # only used if bootloader is "uefi"
                 ready_timeout=60,
                 ):
        super(VersatileExpressPlatform, self).__init__(name,
                                                       core_names,
                                                       core_clusters,
                                                       big_core,
                                                       modules)
        self.serial_port = serial_port
        self.baudrate = baudrate
        self.vemsd_mount = vemsd_mount
        self.image = image
        self.fdt = fdt
        self.initrd = initrd
        self.bootargs = bootargs
        self.uefi_entry = uefi_entry
        self.ready_timeout = ready_timeout
        self.bootloader = None
        self.hard_reset_method = None
        self._set_bootloader(bootloader)
        self._set_hard_reset_method(hard_reset_method)
        self._set_flash_method(flash_method)

    def init_target_connection(self, target):
        if target.os == 'android':
            self._init_android_target(target)
        else:
            self._init_linux_target(target)

    def _init_android_target(self, target):
        if target.connection_settings.get('device') is None:
            addr = self._get_target_ip_address(target)
            target.connection_settings['device'] = addr + ':5555'

    def _init_linux_target(self, target):
        if target.connection_settings.get('host') is None:
            addr = self._get_target_ip_address(target)
            target.connection_settings['host'] = addr

    def _get_target_ip_address(self, target):
        with open_serial_connection(port=self.serial_port,
                                    baudrate=self.baudrate,
                                    timeout=30,
                                    init_dtr=0) as tty:
            tty.sendline('')
            self.logger.debug('Waiting for the Android shell prompt.')
            tty.expect(target.shell_prompt)

            self.logger.debug('Waiting for IP address...')
            wait_start_time = time.time()
            while True:
                tty.sendline('ip addr list eth0')
                time.sleep(1)
                try:
                    tty.expect(r'inet ([1-9]\d*.\d+.\d+.\d+)', timeout=10)
                    return tty.match.group(1)
                except pexpect.TIMEOUT:
                    pass  # We have our own timeout -- see below.
                if (time.time() - wait_start_time) > self.ready_timeout:
                    raise TargetError('Could not acquire IP address.')

    def _set_hard_reset_method(self, hard_reset_method):
        if hard_reset_method == 'dtr':
            self.modules.append({'vexpress-dtr': {'port': self.serial_port,
                                                  'baudrate': self.baudrate,
                                                  }})
        elif hard_reset_method == 'reboottxt':
            self.modules.append({'vexpress-reboottxt': {'port': self.serial_port,
                                                        'baudrate': self.baudrate,
                                                        'path': self.vemsd_mount,
                                                        }})
        else:
            ValueError('Invalid hard_reset_method: {}'.format(hard_reset_method))

    def _set_bootloader(self, bootloader):
        self.bootloader = bootloader
        if self.bootloader == 'uefi':
            self.modules.append({'vexpress-uefi': {'port': self.serial_port,
                                                   'baudrate': self.baudrate,
                                                   'image': self.image,
                                                   'fdt': self.fdt,
                                                   'initrd': self.initrd,
                                                   'bootargs': self.bootargs,
                                                   }})
        elif self.bootloader == 'uefi-shell':
            self.modules.append({'vexpress-uefi-shell': {'port': self.serial_port,
                                                         'baudrate': self.baudrate,
                                                         'image': self.image,
                                                         'bootargs': self.bootargs,
                                                         }})
        elif self.bootloader == 'u-boot':
            uboot_env = None
            if self.bootargs:
                uboot_env = {'bootargs': self.bootargs}
            self.modules.append({'vexpress-u-boot': {'port': self.serial_port,
                                                     'baudrate': self.baudrate,
                                                     'env': uboot_env,
                                                     }})
        elif self.bootloader == 'bootmon':
            self.modules.append({'vexpress-bootmon': {'port': self.serial_port,
                                                      'baudrate': self.baudrate,
                                                      'image': self.image,
                                                      'fdt': self.fdt,
                                                      'initrd': self.initrd,
                                                      'bootargs': self.bootargs,
                                                      }})
        else:
            ValueError('Invalid hard_reset_method: {}'.format(bootloader))

    def _set_flash_method(self, flash_method):
        if flash_method == 'vemsd':
            self.modules.append({'vexpress-vemsd': {'vemsd_mount': self.vemsd_mount}})
        else:
            ValueError('Invalid flash_method: {}'.format(flash_method))


class Juno(VersatileExpressPlatform):

    def __init__(self,
                 vemsd_mount='/media/JUNO',
                 baudrate=115200,
                 bootloader='u-boot',
                 hard_reset_method='dtr',
                 **kwargs
                 ):
        super(Juno, self).__init__('juno',
                                   vemsd_mount=vemsd_mount,
                                   baudrate=baudrate,
                                   bootloader=bootloader,
                                   hard_reset_method=hard_reset_method,
                                   **kwargs)


class TC2(VersatileExpressPlatform):

    def __init__(self,
                 vemsd_mount='/media/VEMSD',
                 baudrate=38400,
                 bootloader='bootmon',
                 hard_reset_method='reboottxt',
                 **kwargs
                 ):
        super(TC2, self).__init__('tc2',
                                  vemsd_mount=vemsd_mount,
                                  baudrate=baudrate,
                                  bootloader=bootloader,
                                  hard_reset_method=hard_reset_method,
                                  **kwargs)


class JunoEnergyInstrument(Instrument):

    binname = 'readenergy'
    mode = CONTINUOUS | INSTANTANEOUS

    _channels = [
        InstrumentChannel('sys_curr', 'sys', 'current'),
        InstrumentChannel('a57_curr', 'a57', 'current'),
        InstrumentChannel('a53_curr', 'a53', 'current'),
        InstrumentChannel('gpu_curr', 'gpu', 'current'),
        InstrumentChannel('sys_volt', 'sys', 'voltage'),
        InstrumentChannel('a57_volt', 'a57', 'voltage'),
        InstrumentChannel('a53_volt', 'a53', 'voltage'),
        InstrumentChannel('gpu_volt', 'gpu', 'voltage'),
        InstrumentChannel('sys_pow', 'sys', 'power'),
        InstrumentChannel('a57_pow', 'a57', 'power'),
        InstrumentChannel('a53_pow', 'a53', 'power'),
        InstrumentChannel('gpu_pow', 'gpu', 'power'),
        InstrumentChannel('sys_cenr', 'sys', 'energy'),
        InstrumentChannel('a57_cenr', 'a57', 'energy'),
        InstrumentChannel('a53_cenr', 'a53', 'energy'),
        InstrumentChannel('gpu_cenr', 'gpu', 'energy'),
    ]

    def __init__(self, target):
        super(JunoEnergyInstrument, self).__init__(target)
        self.on_target_file = None
        self.command = None
        self.binary = self.target.bin(self.binname)
        for chan in self._channels:
            self.channels[chan.name] = chan
        self.on_target_file = self.target.tempfile('energy', '.csv')
        self.command = '{} -o {}'.format(self.binary, self.on_target_file)
        self.command2 = '{}'.format(self.binary)

    def setup(self):
        self.binary = self.target.install(os.path.join(PACKAGE_BIN_DIRECTORY,
                                                       self.target.abi, self.binname))

    def reset(self, sites=None, kinds=None):
        super(JunoEnergyInstrument, self).reset(sites, kinds)
        self.target.killall(self.binname, as_root=True)

    def start(self):
        self.target.kick_off(self.command, as_root=True)

    def stop(self):
        self.target.killall(self.binname, signal='TERM', as_root=True)

    def get_data(self, output_file):
        temp_file = tempfile.mktemp()
        self.target.pull(self.on_target_file, temp_file)
        self.target.remove(self.on_target_file)

        with open(temp_file, 'rb') as fh:
            reader = csv.reader(fh)
            headings = reader.next()

            # Figure out which columns from the collected csv we actually want
            select_columns = []
            for chan in self.active_channels:
                try:
                    select_columns.append(headings.index(chan.name))
                except ValueError:
                    raise HostError('Channel "{}" is not in {}'.format(chan.name, temp_file))

            with open(output_file, 'wb') as wfh:
                write_headings = ['{}_{}'.format(c.site, c.kind)
                                  for c in self.active_channels]
                writer = csv.writer(wfh)
                writer.writerow(write_headings)
                for row in reader:
                    write_row = [row[c] for c in select_columns]
                    writer.writerow(write_row)

        return MeasurementsCsv(output_file, self.active_channels)

    def take_measurement(self):
        result = []
        output = self.target.execute(self.command2).split()
        reader=csv.reader(output)
        headings=reader.next()
        values = reader.next()
        for chan in self.active_channels:
            value = values[headings.index(chan.name)]
            result.append(Measurement(value, chan))
        print result
        return result


