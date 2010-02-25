#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2010 Arthur Furlan <afurlan@afurlan.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or any later version.
#
# On Debian systems, you can find the full text of the license in
# /usr/share/common-licenses/GPL-2

import sys
import subprocess
from logbook import LogBook, ProjectDoesNotExistError

try:
	config = LogBook().get_project_config(sys.argv[1])
except ProjectDoesNotExistError, ex:
	print 'svn-update: project "%s" not found.' % sys.argv[1]
	sys.exit(1)

# update project
subprocess.call(['svn', 'up', config['logfile'], '--quiet'])
