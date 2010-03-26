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
import socket
import difflib
import getpass
import smtplib
from logbook import LogBook, ProjectDoesNotExistError

MAIL_HOST = 'localhost'
MAIL_USER = ''
MAIL_PASS = ''
MAIL_FROM = getpass.getuser() + '@' + socket.getfqdn()
MAIL_DEST = 'root'

try:
	config = LogBook().get_project_config(sys.argv[1])
except ProjectDoesNotExistError, ex:
	print 'mail-notification: project "%s" not found.' % sys.argv[1]
	sys.exit(1)

# create the email message
subject = 'logbook: changes on project "%s"' % (sys.argv[1])
message = []
message.append('From: %s' % MAIL_FROM)
message.append('To: %s' % MAIL_DEST)
message.append('Subject: %s\n' % subject)
message.append('Changes on version %s of project "%s":\n' % tuple(sys.argv[2:0:-1]))

# append the files diff to the message
srcname = config['logfile']
srcfile = open(srcname)
dstname = sys.argv[3]
dstfile = open(dstname)
content = difflib.unified_diff(srcfile.readlines(), dstfile.readlines(), srcname, dstname)
message.append(''.join(content))

# send the notification
smtp = smtplib.SMTP(MAIL_HOST)
if MAIL_USER or MAIL_PASS:
	smtp.login(MAIL_USER, MAIL_PASS)
smtp.sendmail(MAIL_FROM, MAIL_DEST, '\n'.join(message))
smtp.quit()
