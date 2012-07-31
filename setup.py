#!/usr/bin/python
# mythnettv install script
# Copyright (C) 2008, Thomas Mashos <thomas@weilandhomes.com>
#
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

from distutils.core import setup

import subprocess, glob, os.path

setup(
    name="mythnettv",
    author="Elkin Fricke",
    author_email="managementboy@gmail.com",
    url="http://github.com/managementboy/mntv",
    license="gpl",
    description="Plugin to download RSS video feeds for MythTV",
    data_files=[("share/mythnettv", glob.glob("*.py")),
		("share/mythnettv/plugins", glob.glob("plugins/*.py")),
		("share/mythnettv", glob.glob("README*")),
		("share/mythnettv", glob.glob("mythnettv*")),
		("share/mythnettv", glob.glob("COPYING"))],
)
