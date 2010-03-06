#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2008 Arthur Furlan <afurlan@afurlan.org>
# Copyright (C) 2008 Felipe Augusto van de Wiel <faw@funlabs.org>
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or any later version.
#
# On Debian systems, you can find the full text of the license in
# /usr/share/common-licenses/GPL-2

import os
import re
import sys
import glob
import time
import shutil
import socket
import getpass
import optparse
import subprocess

LOGBOOK_BASEDIR = os.path.expanduser('~/.logbook')
LOGBOOK_HOOKS = {'pre':'hooks.d-pre', 'post':'hooks.d-post',}

class ProjectExistsError(Exception):
	pass

class ProjectDoesNotExistError(Exception):
	pass

class UpdateAbortedError(Exception):
	pass

class LogBook(object):

	def run(self):

		# configure and parse the args
		usage = 'Usage: %prog [OPTIONS] PROJECT'
		parser = optparse.OptionParser(usage=usage)
		parser.add_option('-f', metavar='LOGFILE',
			help='points the logfile to an external file')
		parser.add_option('-m', metavar='MESSAGE',
			help='update message')
		parser.add_option('-l', metavar='LABEL',
			help='project label to be used in the LogBook file')
		parser.add_option('-b', metavar='BASEDIR',
			help='set the logbook base directory')
		parser.add_option('-s', metavar='PROJECT',
			help='show the logbook of a project')
		parser.add_option('-c', metavar='PROJECT',
			help='create a new project')
		parser.add_option('-u', metavar='PROJECT',
			help='update a project')
		parser.add_option('-d', metavar='PROJECT',
			help='delete a project')
		(options, args) = parser.parse_args()

		# execute the action based in the parsed args
		if options.s:
			return self.show_project(options.s)
		elif options.c:
			return self.create_project(options.c, options.f,
					options.l, options.b)
		elif options.d:
			return self.delete_project(options.d)
		elif options.u or args:
			return self.update_project(options.u or args[0], options.m)
		else:
			parser.print_help()

	def show_project(self, project):
		
		if not self.project_exists(project):
			raise ProjectDoesNotExistError(
				'project "%s" could not be found.' % project)

		self.config = self.get_project_config(project)
		return subprocess.call([self.config['pager'],
			self.config['logfile']])

	def create_project(self, project, logfile=None, label=None, basedir=None):

		# create project directory
		if self.project_exists(project):
			raise ProjectExistsError(
				'project "%s" already exists.' % project)

		# create the project's base dir
		project_basedir = self.get_project_basedir(project)
		os.makedirs(project_basedir)
		
		# create the project's hooks dirs
		if basedir:
			if not os.path.exists(basedir):
				os.makedirs(basedir)
			project_basedir = basedir
		for hooks_basedir in LOGBOOK_HOOKS.values():
			hooks_basedir = os.path.join(project_basedir, hooks_basedir)
			if not os.path.exists(hooks_basedir):
				os.mkdir(hooks_basedir)

		self.create_config_file(project, logfile, label, basedir)

	def delete_project(self, project):

		if not self.project_exists(project):
			raise ProjectDoesNotExistError(
				'project "%s" could not be found.' % project)

		shutil.rmtree(self.get_project_basedir(project))

	def update_project(self, project, message=None):

		if not self.project_exists(project):
			raise ProjectDoesNotExistError(
				'project "%s" could not be found.' % project)
		elif not self.check_user_root():
			raise UpdateAbortedError()

		self.config = self.get_project_config(project)
		self.call_hooks(LOGBOOK_HOOKS['pre'])

		self.editor = LogBookEditor(self.config)
		self.editor.parse()

		if not message:
			if not self.editor.edit_file():
				raise UpdateAbortedError()
		else:
			self.editor.add_message_file(message)

		self.editor.commit_changes()
		self.call_hooks(LOGBOOK_HOOKS['post'], send_all_args=True)

	def check_user_root(self):
		login = getpass.getuser()
		if login == 'root':
			print "You're not supposed to update logbook as root."
			option = ''
			while option != 'y':
				message = 'Would you like to proceed? [y/N] '
				option = raw_input(message).strip().lower()
				if not option or option == 'n':
					return False
		return True

	def create_config_file(self, project, logfile, label, basedir):

		project_basedir = self.get_project_basedir(project)
		config_filename = os.path.join(project_basedir, 'config')

		# get the (real) location of the logfile
		if not logfile:
			logfile = os.path.join(basedir or project_basedir, 'logbook')
		elif '~' in logfile:
			logfile = os.path.expanduser(logfile)
		logfile = os.path.realpath(logfile)

		# create the logfile if it doesn't exists
		if not os.path.exists(logfile):
			open(logfile, 'w').close()

		# create the configuration content
		config_lines = []
		config_lines.append(u"logfile = '%s'" % logfile)

		if label:
			config_lines.append(u"label = '%s'" % label)
		if basedir:
			config_lines.append(u"basedir = '%s'" % basedir)

		# create the configuration file
		file_handler = file(config_filename, 'w')
		file_handler.write('\n'.join(config_lines))
		file_handler.close()

	def get_project_basedir(self, project):

		return os.path.join(LOGBOOK_BASEDIR, project)

	def get_project_config(self, project):

		config = {}
		project_basedir = self.get_project_basedir(project)

		# load general config
		config_filename = os.path.join(os.path.dirname(project_basedir), 'config')
		if os.path.exists(config_filename):
			execfile(config_filename, locals(), config)

		# load project config
		config_filename = os.path.join(project_basedir, 'config')
		execfile(config_filename, config, config)
		config = self.get_environ_config(config)

		config['project'] = project
		config['user'] = getpass.getuser()

		return config

	def get_environ_config(self, config):

		if not config.has_key('editor'):
			editor = os.environ.get('EDITOR')
			if not editor:
				# /etc/alternatives/editor in debian
				# defaults to "nano" command
				editor = 'editor'
			config['editor'] = editor

		if not config.has_key('name') or not config.has_key('email'):
			debemail =  os.environ.get('DEBEMAIL')
			if not debemail:
				if not config.has_key('name'):
					config['name'] = getpass.getuser()
				if not config.has_key('email'):
					domain = '.'.join(socket.getfqdn().split('.')[1:])
					config['email'] = getpass.getuser() + '@' + domain
			else:
				pieces = debemail.split()
				if not config.has_key('name'):
					config['name'] = ' '.join(pieces[:-1]).strip(' "')
				if not config.has_key('email'):
					config['email'] = pieces[-1].strip(' <>')

		if not config.has_key('pager'):
			# /etc/alternatives/pager in debian
			# defaults to "more" or "less" command
			config['pager'] = 'pager'

		return config

	def project_exists(self, project):
		return os.path.exists(self.get_project_basedir(project))

	def remove_tmpfile(self):
		try:
			if os.path.exists(self.editor.tmp_filename):
				os.unlink(self.editor.tmp_filename)
		except AttributeError:
			return

	def call_hooks(self, hooksd, send_all_args=False):

		basedir = self.config.get('basedir', self.get_project_basedir(self.config['project']))
		hooksd_dir = os.path.join(basedir, hooksd)
		for s in glob.glob(hooksd_dir + '/*'):
			script_file = os.path.join(hooksd_dir, s)
			if os.access(script_file, os.X_OK):
				cmd_args = [script_file, self.config['project']]
				if send_all_args:
					cmd_args.append(self.editor.get_current_version())
					cmd_args.append(self.editor.tmp_filename)
				subprocess.call(cmd_args)

class LogBookEditor(object):

	entry_header_re = re.compile('^([^ ]+) \(([0-9]{8})\) (\w+); (\w+=\w+ ?)+$')
	entry_footer_re = re.compile('^ -- (.*) <([^>]+)>  (.*)$')
	entry_author_re = re.compile('^  \[ (.*) \]$')
	entry_task_re = re.compile('^  \* (.*)$')

	def __init__(self, config):
		self.config = config
		self.content = ''
		self.file_handler = open(self.config['logfile'])
		self.file_content = ''
		self.tmp_filename = '/tmp/logbook-%s-%d' % \
			(self.config['project'], int(time.time()))

	def parse(self):
		self.current_entry = self.get_current_entry()
		self.add_entry_tasks(self.current_entry, self.config['name'], '  * \n',
			move_last_breakline=True)

	def edit_file(self):
		self.create_tmpfile()
		modify_date = os.path.getmtime(self.tmp_filename)

		editor = self.config['editor']
		cmd_args = [editor]
		cmd_args.extend(self.get_editor_args(editor))
		cmd_args.append(self.tmp_filename)
		subprocess.call(cmd_args)

		return modify_date != os.path.getmtime(self.tmp_filename)
	
	def resolve_editor_path(self, editor):
		for p in os.defpath.split(os.pathsep):
			editor_path = os.path.join(p, editor)
			if os.path.exists(editor_path):
				return os.path.realpath(editor_path)
		return editor

	def get_editor_args(self, editor):
		wrapsize = 70
		position = self.get_cursor_position()

		editor = self.resolve_editor_path(editor)
		editor = os.path.basename(editor)

		if editor in ['vim', 'vim.basic', 'vim.tiny', 'vi']:
			return ['+start', '-c', ':set tw=%d' % wrapsize,
				'-c', ':call cursor(%d, %d)' % position]

		elif editor in ['nano', 'rnano']:
			return ['-r', str(wrapsize), '+%d,%d' % position]

		elif editor in ['emacs', 'emacs22-x', 'emacsclient.emacs22']:
			return ['--execute', "(setq-default auto-fill-function 'do-auto-fill)",
				'+%d:%d' % position]

		return []

	def add_message_file(self, message):
		if not message.endswith('\n'):
			message += '\n'

		name = self.config['name']
		self.current_entry['tasks'][name][-1] = \
			self.current_entry['tasks'][name][-1][:-1]
		self.add_entry_tasks(self.current_entry, self.config['name'],
			message,  move_last_breakline=True)
		self.create_tmpfile()

	def get_cursor_position(self):
		row, col = 1, 5
		for n in self.current_entry['names_order']:
			if len(self.current_entry['names_order']) > 1:
				row += 1

			for t in self.current_entry['tasks'][n]:
				row += t.count('\n')

			if n == self.config['name']:
				break

		return row, col

	def create_tmpfile(self):
		file_handler = open(self.tmp_filename, 'w')
		text = self.get_formatted_entry(self.current_entry) + self.content
		file_handler.write(text)
		file_handler.close()

	def get_current_version(self):
		return time.strftime('%Y%m%d')

	def get_current_entry(self):
		entry = self.get_empty_entry()
		line = self.file_handler.readline()
		if not line:
			return entry

		values = self.entry_header_re.search(line)
		if not values:
			return entry

		values = values.groups()
		if values[1] != self.get_current_version():
			self.content = '\n' + line
			self.content += ''.join(self.file_handler.readlines())
			return entry
		else:
			entry['project'] = values[0]
			entry['hostname'] = values[2]
			entry['attrs'] = values[3:]

			tasks = []
			values,name = None,None
			while not values:
				line = self.file_handler.readline()
				values = self.entry_footer_re.search(line)

				if values:
					values = values.groups()
					entry['name'] = values[0]
					entry['email'] = values[1]
					entry['datetime'] = values[2]

					name = name or entry['name']
					if tasks:
						self.add_entry_tasks(entry, name, tasks)
				elif self.entry_author_re.match(line):
					if tasks:
						self.add_entry_tasks(entry, name, tasks)
					name = line.strip(' []\n')
					tasks = []
				elif self.entry_task_re.match(line):
					tasks.append(line)
				elif tasks and line:
					tasks[-1] += line

			self.content += ''.join(self.file_handler.readlines())

		return entry

	def get_empty_entry(self):
		return {
			'project': self.config['project'],
			'label': self.config.get('label', self.config['project']),
			'version': self.get_current_version(),
			'hostname': socket.gethostname(),
			'name': self.config['name'],
			'email': self.config['email'],
			'attrs': ['urgency=low'],
			'tasks': {},
			'datetime':time.strftime('%a, %d %b %Y %H:%M:%S %z'),
			'names_order': [],
		}

	def get_formatted_entry(self, entry):
		text = '%s (%s) %s; %s\n\n' % (entry['label'], entry['version'],
				entry['hostname'], ' '.join(entry['attrs']))
		for a in entry['names_order']:
			if len(entry['names_order']) > 1:
				text += '  [ %s ]\n' % a
			for e in entry['tasks'][a]:
				text += e
		text += ' -- %s <%s>  %s\n' % (entry['name'], entry['email'],
				entry['datetime'])
		return text

	def add_entry_tasks(self, entry, name, tasks, move_last_breakline=False):
		if name not in entry['tasks'].keys():
			entry['tasks'][name] = []
			entry['names_order'].append(name)

		if move_last_breakline and entry['tasks'][name]:
			entry['tasks'][name][-1] = entry['tasks'][name][-1][:-1]

		if type(tasks) is list:
			if move_last_breakline:
				tasks.append('\n')
			entry['tasks'][name].extend(tasks)
		elif type(tasks) is str:
			if move_last_breakline:
				tasks += '\n'
			entry['tasks'][name].append(tasks)

	def commit_changes(self):
		tmp_handler = open(self.tmp_filename)
		file_handler = open(self.config['logfile'], 'w')
		for line in tmp_handler:
			file_handler.write(line)
		tmp_handler.close()
		file_handler.close()

if __name__ == '__main__':
	logbook = LogBook()
	try:
		logbook.run()
		sys.exit(0)
	except (ProjectExistsError, ProjectDoesNotExistError), ex:
		print 'Error:', str(ex)
		sys.exit(1)
	except UpdateAbortedError, ex:
		print 'Aborting.'
		sys.exit(2)
	finally:
		logbook.remove_tmpfile()
