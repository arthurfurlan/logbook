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
import locale
import socket
import difflib
import getpass
import smtplib
from logbook import LogBook, ProjectDoesNotExistError

# mail settings
MAIL_HOST = 'localhost'
MAIL_USER = ''
MAIL_PASS = ''
MAIL_FROM = getpass.getuser() + '@' + socket.getfqdn()
MAIL_DEST = 'root'
ENCODING = locale.getpreferredencoding().lower()

if __name__ == '__main__':

    # load the logbook project
    try:
        lb = LogBook()
        lb.load_config(sys.argv[1])
    except ProjectDoesNotExistError, ex:
        print 'mail-notification:', str(ex)
        sys.exit(1)

    # create the message
    subject = 'logbook: changes on project "%s"' % (sys.argv[1])
    message = []
    message.append('From: %s' % MAIL_FROM)
    message.append('To: %s' % ', '.join(MAIL_DEST))
    message.append('Subject: %s' % subject)
    message.append('Content-Type: text/plain; charset="%s"\n' % ENCODING)
    message.append('Changes on version %s of project "%s":\n' % \
            tuple(sys.argv[2:0:-1]))

    # append the unified diff
    srcname = lb.config['logfile']
    srcfile = open(srcname)
    dstname = sys.argv[3]
    dstfile = open(dstname)
    content = difflib.unified_diff(srcfile.readlines(), \
        dstfile.readlines(), srcname, dstname)
    message.append(''.join(content))

    # send the message
    smtp = smtplib.SMTP(MAIL_HOST)
    if MAIL_USER or MAIL_PASS:
        smtp.login(MAIL_USER, MAIL_PASS)
    smtp.sendmail(MAIL_FROM, MAIL_DEST, '\n'.join(message))
    smtp.quit()
