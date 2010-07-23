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
import shlex
import shutil
import socket
import getpass
import optparse
import subprocess


# Directory which stores the user data
LOGBOOK_USERDIR = os.path.realpath(os.path.expanduser('~/.logbook'))

# Directory which stores some template files (configurations and scripts)
LOGBOOK_BASEPATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
LOGBOOK_SHAREDIR = os.path.join(LOGBOOK_BASEPATH, 'doc', 'examples')

# Current configured hooks and its script directories
LOGBOOK_HOOKS = {
    'pre': 'hooks.d-pre',       # before the temporary file is created
    'saved': 'hooks.d-saved',   # after the temporary file is saved
    'post': 'hooks.d-post',     # after the real logbook file is saved
}


# Exception thrown when a project currently exists. This exception is raised
# if the user try to create a new project using a name that is already being
# used by another project
class ProjectExistsError(Exception):
    '''
    Exception thrown when a project currently exists. This exception is raised
    if the user try to create a new project using a name that is already being
    used by another project.
    '''
    pass


# Exception thrown when a project doesn't exists. This exception is raised if
# the user try to work with a project that doesn't exists
class ProjectDoesNotExistError(Exception):
    '''
    Exception thrown when a project doesn't exists. This exception is raised if
    the user try to work with a project that doesn't exists.
    '''
    pass

# Exception thrown if the user execute the editor but doesn't make any changes
# what means the user aborted the logbook update
class UpdateAbortedError(Exception):
    '''
    Exception thrown if the user execute the editor but doesn't make any changes
    what means the user aborted the logbook update.
    '''
    pass


# Main application class
class LogBook(object):
    '''
    Main application class.
    '''


    # Initial application setup
    def __init__(self):
        '''
        Initial application setup.
        '''

        self.config = {}
        self.load_config()


    # Run the application via command line interface. Parse the arguments and
    # execute the action based on them
    def run(self):
        '''
        Run the application via command line interface. Parse the arguments and
        execute the action based on them.
        '''

        usage = 'Usage: %prog [OPTIONS] [PROJECT]'
        parser = optparse.OptionParser(usage=usage)

        # application actions
        parser.add_option('-V', metavar='PROJECT',
            help='view a logbook project file')
        parser.add_option('-C', metavar='PROJECT',
            help='create a new logbook project')
        parser.add_option('-U', metavar='PROJECT',
            help='update a logbook project')
        parser.add_option('-D', metavar='PROJECT',
            help='delete a logbook project')
        parser.add_option('-L', '--list', action='count',
            help='list the configured projects')

        # application options
        parser.add_option('-f', metavar='FILE',
            help='configure the project to use an external file')
        parser.add_option('-m', metavar='MESSAGE',
            help='set the update message')
        parser.add_option('-l', metavar='LABEL',
            help='project label to be used in the logbook file')
        parser.add_option('-b', metavar='BASEDIR',
            help='set the logbook base directory')
        (opts, args) = parser.parse_args()

        if opts.list:   # list the configured projects
            return self.do_list_projects()
        elif opts.V:    # view a logbook project file
            return self.do_view_project(opts.V)
        elif opts.C:    # create a new logbook project
            return self.do_create_project(opts.C, opts.f, opts.l, opts.b)
        elif opts.D:    # delete a logbook project
            return self.do_delete_project(opts.D)
        else:           # update a logbook project
            if not opts.U and not args:
                projects = self.get_configured_projects()
                if 'default' in self.config:
                    args.append(self.config['default'])
                elif len(projects) == 1:
                    args.append(projects[0])
                else:
                    raise ProjectDoesNotExistError(
                        'default project could not be found.')
            return self.do_update_project(opts.U or args[0], opts.m)

    
    # Print the list of configured projects
    def do_list_projects(self):
        '''
        Print the list of configured projects.
        '''

        for project in self.get_configured_projects():
            print project


    # View the file logbook file of a project
    def do_view_project(self, project):
        '''
        View the file logbook file of a project.
        '''

        # check if the project really exists
        if not self.project_exists(project):
            raise ProjectDoesNotExistError(
                'project "%s" could not be found.' % project)

        # display the logbook file using the user "pager"
        self.load_config(project)
        return subprocess.call([self.config['pager'],
            self.config['logfile']])


    # Create a new logbook project
    def do_create_project(self, project, logfile=None, label=None, basedir=None):
        '''
        Create a new logbook project.
        '''

        # check if the project already exist
        if self.project_exists(project):
            raise ProjectExistsError(
                'project "%s" already exists.' % project)

        # create the project directory into the user data directory
        project_basedir = self.get_project_basedir(project)
        os.makedirs(project_basedir)
        
        # create the hook directories for the project
        if basedir:
            project_basedir = os.path.realpath(basedir)
            if not os.path.exists(project_basedir):
                os.makedirs(basedir)

        for hooks_basedir in LOGBOOK_HOOKS.values():
            hooks_basedir = os.path.join(project_basedir, hooks_basedir)
            if not os.path.exists(hooks_basedir):
                os.mkdir(hooks_basedir)

        # create the project configuration file
        self._create_config(project, logfile, label, basedir)


    # Delete a logbook project
    def do_delete_project(self, project):
        '''
        Delete a logbook project.
        '''

        # check if the project really exists
        if not self.project_exists(project):
            raise ProjectDoesNotExistError(
                'project "%s" could not be found.' % project)

        # remove the project base directory but don't touch in other files,
        # like external basedir or logfiles.
        shutil.rmtree(self.get_project_basedir(project))


    # Update a logbook project
    def do_update_project(self, project, message=None):
        '''
        Update a logbook project.
        '''

        # check if the project really exists
        if not self.project_exists(project):
            raise ProjectDoesNotExistError(
                'project "%s" could not be found.' % project)
        # ... and if the user running the application isn't the root
        elif not self._check_user_root():
            raise UpdateAbortedError()

        # load the project congif and execute the "pre" hook scripts
        self.load_config(project)
        self._call_hooks(LOGBOOK_HOOKS['pre'])

        # execute the user editor if there's no message sent via command line
        self.editor = LogBookEditor(self.config)
        self.editor.parse()
        if not message:
            if not self.editor.edit_file():
                raise UpdateAbortedError()
        else:
            self.editor.add_entry_message(message)

        # commit the changes and executhe the respective hook scripts
        self._call_hooks(LOGBOOK_HOOKS['saved'], send_all_args=True)
        self.editor.commit_changes()
        self._call_hooks(LOGBOOK_HOOKS['post'], send_all_args=True)


    # Return a list containing all configured projects
    def get_configured_projects(self):
        '''
        Return a list containing all configured projects
        '''

        projects = []

        # Search for all projects into the user data directory
        try:
            for p in os.listdir(LOGBOOK_USERDIR):
                if os.path.isdir(os.path.join(LOGBOOK_USERDIR, p)):
                    projects.append(p)
        except OSError:
            pass

        return projects


    # Return the absolut base directory of a project
    def get_project_basedir(self, project):
        '''
        Return the absolut base directory of a project.
        '''

        return os.path.join(LOGBOOK_USERDIR, project)


    # Load the configuration of a specific project, if "project" has any value,
    # otherwise load the global logbook configuration
    def load_config(self, project=''):
        '''
        Load the configuration of a specific project, if "project" has any value,
        otherwise load the global logbook configuration.
        '''

        # check if the project really exists
        if project and not self.project_exists(project):
            raise ProjectDoesNotExistError(
                'project "%s" could not be found.' % project)

        config_file_path = os.path.join(LOGBOOK_USERDIR, project, 'config')
        if os.path.exists(config_file_path):
            execfile(config_file_path, {}, self.config)

        # load the configuration from the environment vars (if needed) and force
        # some "non-optional" configuration values
        self._load_environ_config()
        self.config['project'] = project
        self.config['user'] = getpass.getuser()

        return self.config


    # Check if a project really exists
    def project_exists(self, project):
        '''
        Check if a project really exists.
        '''

        return os.path.exists(self.get_project_basedir(project))


    # Remove the temporary file
    def _remove_temp_file(self):
        '''
        Remove the temporary file.
        '''

        try:
            os.unlink(self.editor.temp_file_name)
        except (AttributeError, IOError):
            pass


    # Check if the current running user is the root and if was, display a
    # warning message and asks for confirmation to proceed. Logbook isn't
    # intended to be updated by root
    def _check_user_root(self):
        '''
        Check if the current running user is the root and if was, display a
        warning message and asks for confirmation to proceed. Logbook isn't
        intended to be updated by root.
        '''

        user = getpass.getuser()

        # display the warning and asks for confirmation to proceed
        if user == 'root':
            print "You're not supposed to update logbook as root."
            option = ''
            while option != 'y':
                message = 'Would you like to proceed? [y/N] '
                option = raw_input(message).strip().lower()
                if not option or option == 'n':
                    return False

        return True


    # Load some configuration from environment vars (if needed)
    def _load_environ_config(self):
        '''
        Load some configuration from environment vars (if needed).
        '''

        # if the user doesn't have the editor configured on logbook but has the
        # $EDITOR variable defined, uses the environment configuration
        if not self.config.has_key('editor'):
            editor = os.environ.get('EDITOR')
            if not editor:
                editor = 'editor'
            self.config['editor'] = editor

        # if the user doesn't have the name or email configured on logbook but
        # has the $DEBEMAIL variable defined, uses the environment configuration
        if not self.config.has_key('name') or not self.config.has_key('email'):
            debemail =  os.environ.get('DEBEMAIL')
            if not debemail:
                if not self.config.has_key('name'):
                    self.config['name'] = getpass.getuser()
                if not self.config.has_key('email'):
                    domain = '.'.join(socket.getfqdn().split('.')[1:])
                    self.config['email'] = getpass.getuser() + '@' + domain
            else:
                pieces = debemail.split()
                if not self.config.has_key('name'):
                    self.config['name'] = ' '.join(pieces[:-1]).strip(' "')
                if not self.config.has_key('email'):
                    self.config['email'] = pieces[-1].strip(' <>')

        # set a default "pager" value if the user doesn't have one configured
        if not self.config.has_key('pager'):
            self.config['pager'] = 'pager'


    # Create the logbook project configuration file. The configuration files are
    # based on templates of the "LOGBOOK_SHAREDIR" directory
    def _create_config(self, project, logfile, label, basedir):
        '''
        Create the logbook project configuration file. The configuration files
        are based on templates of the "LOGBOOK_SHAREDIR" directory.
        '''

        # create the global configuration file if it doesn't exist
        global_config_file_path = os.path.join(LOGBOOK_USERDIR, 'config')
        if not os.path.exists(global_config_file_path):
            global_config_file_path_share = os.path.join(LOGBOOK_SHAREDIR,
                    'config', 'config.global')
            shutil.copyfile(global_config_file_path_share,
                    global_config_file_path)

        # get the configuration file paths
        project_basedir = self.get_project_basedir(project)
        project_config_file_path = os.path.join(project_basedir, 'config')
        project_config_file_path_share = os.path.join(LOGBOOK_SHAREDIR,
                'config', 'config.project')

        # get the location of the logfile and create it as an empty file
        if not logfile:
            logfile = os.path.join(basedir or project_basedir, 'logbook')
        elif '~' in logfile:
            logfile = os.path.expanduser(logfile)
        logfile = os.path.realpath(logfile)

        if not os.path.exists(logfile):
            open(logfile, 'w+').close()

        # create the configuration file of the logbook project
        config_data = {'logfile':logfile}
        if label:
            config_data['label'] = label
        if basedir:
            config_data['basedir'] = basedir

        config_share_handler = open(project_config_file_path_share, 'r')
        config_real_handler = open(project_config_file_path, 'w+')
        for line in config_share_handler:
            for k, v in config_data.iteritems():
                if re.match('\s*#?\s*%s\s*=' % k, line):
                    line = "%s = '%s'\n" % (k, v)
            config_real_handler.write(line)
        config_share_handler.close()
        config_real_handler.close()


    # Execute the respective scripts for a specified hook
    def _call_hooks(self, hook, send_all_args=False):
        '''
        Execute the respective scripts for a specified hook.
        '''

        # get the hooks basedir of the project
        basedir = self.get_project_basedir(self.config['project'])
        basedir = self.config.get('basedir', basedir)
        hooks_basedir = os.path.join(basedir, hook)

        # create the hook directory if it doesn't exist
        if not os.path.exists(hooks_basedir):
            os.mkdir(hooks_basedir)
            return

        # execute all the scripts in the hooks directory
        for s in glob.glob(hooks_basedir + '/*'):
            script_file_path = os.path.join(hooks_basedir, s)
            if os.access(script_file_path, os.X_OK):
                cmd_args = [script_file_path, self.config['project']]
                if send_all_args:
                    cmd_args.append(self.editor.get_current_version())
                    cmd_args.append(self.editor.temp_file_name)
                subprocess.call(cmd_args)


# Class responsible for editting the files and for text editor handling
class LogBookEditor(object):
    '''
    Class responsible for editting the files and for text editor handling.
    '''


    # Patterns used to parse the logbook entries
    entry_header_re = re.compile('^([^ ]+) \(([0-9]{8})\) (\w+); (\w+=\w+ ?)+$')
    entry_footer_re = re.compile('^ -- (.*) <([^>]+)>  (.*)$')
    entry_author_re = re.compile('^  \[ (.*) \]$')
    entry_task_re = re.compile('^  \* (.*)$')


    # Initial setup based on the "config"
    def __init__(self, config):
        '''
        Initial setup based on the "config"
        '''
    
        self.content = ''
        self.config = config

        # start the file processing process
        self.real_file_handler = open(self.config['logfile'])
        self.temp_file_name = '/tmp/logbook-%s-%d' % \
            (self.config['project'], int(time.time()))


    # Parse the current logfile in order to extract the current entry, if there
    # is no current entry (an entry where the version date is "today") on file,
    # create a new empty entry for this new update. After that, insert a new
    # task containing only " * HH:MM "
    def parse(self):

        # get the current entry on file
        self.current_entry = self.get_current_entry()
        
        # set some data for the new task
        current_time = time.strftime('%H:%M ')
        task_content = '  * %s\n' % current_time

        # add a new task containig only " * HH:MM "
        self.add_entry_tasks(self.current_entry, self.config['name'],
            task_content, move_last_breakline=True)


    # Create the temporary file and open the text editor to edit it
    def edit_file(self):
        '''
        Create the temporary file and open the text editor to edit it.
        '''

        # create the temporary file and get the modify date
        self._create_temp_file()
        modify_date = os.path.getmtime(self.temp_file_name)

        # get the editor args based on the user text editor and run it
        cmd_args = shlex.split(self.config['editor'])
        cmd_args.extend(self.get_editor_args(cmd_args[0]))
        cmd_args.append(self.temp_file_name)
        subprocess.call(cmd_args)

        # return a value indicating if the file was changed
        return modify_date != os.path.getmtime(self.temp_file_name)

    
    # Get the list of configuration arguments based on the text editor
    def get_editor_args(self, editor):
        '''
        Get the list of configuration arguments based on the text editor.
        '''

        # text size and position
        wrapsize = 80
        position = self.get_cursor_position()

        # get the real path of the editor
        editor = self._resolve_editor_path(editor)
        editor = os.path.basename(editor)

        # text editor: vim/vi
        if editor in ['vim', 'vim.basic', 'vim.tiny', 'vi', 'gvim']:
            return ['+start', '-c', ':set tw=%d' % wrapsize,
                '-c', ':call cursor(%d, %d)' % position]

        # text editor: nano
        elif editor in ['nano', 'rnano']:
            return ['-r', str(wrapsize), '+%d,%d' % position]

        # text editor: emacs
        elif editor in ['emacs', 'emacs22-x', 'emacsclient.emacs22']:
            emacs_func = "(setq-default auto-fill-function 'do-auto-fill)"
            return ['--execute', emacs_func, '+%d:%d' % position]

        # other text editor
        return []


    # Get the initial position of the cursor to get focus on the last task
    def get_cursor_position(self):
        '''
        Get the initial position of the cursor to get focus on the last task.
        '''

        # count the name titles and tasks to set the focused line
        row, col = 1, 11
        for n in self.current_entry['names_order']:
            if len(self.current_entry['names_order']) > 1:
                row += 1
            for t in self.current_entry['tasks'][n]:
                row += t.count('\n')
            if n == self.config['name']:
                break

        return row, col


    # Get the current version, what (in a date-based version system) means the
    # version of current day
    def get_current_version(self):
        '''
        Get the current version, what (in a date-based version system) means the
        version of current day.
        '''

        return time.strftime('%Y%m%d')


    # Get the current entry (the entry of the current day) or, if there is no
    # current entry, return a new empty entry
    def get_current_entry(self):
        '''
        Get the current entry (the entry of the current day) or, if there is no
        current entry, return a new empty entry.
        '''

        entry = self.get_empty_entry()
        line = self.real_file_handler.readline()

        # if the there is no lines (empty file)
        if not line:
            return entry

        # get the first "entry header" in the file
        values = self.entry_header_re.search(line)
        if not values:
            return entry
        values = values.groups()

        # check if the this entry is the current entry (the entry of the current
        # day), if not return an empty entry
        if values[1] != self.get_current_version():
            self.content = '\n' + line
            self.content += ''.join(self.real_file_handler.readlines())
            return entry

        # ... otherwise, parse this entry
        else:
            entry['project'] = values[0]
            entry['hostname'] = values[2]
            entry['attrs'] = values[3:]

            # parse all the entry tasks... the code below is complicated to
            # explain and problably easier to understand by reading :)
            tasks = []
            values,name = None,None
            while not values:
                line = self.real_file_handler.readline()
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
           
            # save the rest of the file content
            self.content += ''.join(self.real_file_handler.readlines())

        # return the just parsed entry
        return entry


    # Get an empty entry using some default values based on the configuration
    def get_empty_entry(self):
        '''
        Get an empty entry using some default values based on the configuration.
        '''

        return {
            'project': self.config['project'],
            'label': self.config.get('label', self.config['project']),
            'version': self.get_current_version(),
            'hostname': socket.gethostname(),
            'name': self.config['name'],
            'email': self.config['email'],
            'attrs': ['urgency=low'],
            'tasks': {},    # no tasks for now
            'datetime':time.strftime('%a, %d %b %Y %H:%M:%S %z'),
            'names_order': [],
        }


    # Get a string version of the entry, formatted in Debian Changelog Syntax
    def get_formatted_entry(self, entry):
        '''
        Get a string version of the entry, formatted in Debian Changelog Syntax.
        '''

        # entry header
        text = '%s (%s) %s; %s\n\n' % (entry['label'], entry['version'],
                entry['hostname'], ' '.join(entry['attrs']))

        # add the entry tasks (and users)
        for a in entry['names_order']:
            if len(entry['names_order']) > 1:
                text += '  [ %s ]\n' % a
            for e in entry['tasks'][a]:
                text += e

        # entry footer
        text += ' -- %s <%s>  %s\n' % (entry['name'], entry['email'],
                entry['datetime'])

        return text

    
    # Add a message to an entry directly and regenerate the temporary file
    def add_entry_message(self, message):
        '''
        Add a message to an entry directly and regenerate the temporary file.
        '''

        # append a '\n' to end of the message
        if not message.endswith('\n'):
            message += '\n'

        # add the message as a new task in the last entry
        name = self.config['name']
        self.current_entry['tasks'][name][-1] = \
            self.current_entry['tasks'][name][-1][:-1]
        self.add_entry_tasks(self.current_entry, self.config['name'],
            message,  move_last_breakline=True)

        # regenerate the temporary file
        self._create_temp_file()


    # Add a new tasks in an entry
    def add_entry_tasks(self, entry, name, tasks, move_last_breakline=False):
        '''
        Add a new tasks in an entry
        '''

        # if there is no entries of this user (aka 'name'), inser the user
        if name not in entry['tasks'].keys():
            entry['tasks'][name] = []
            entry['names_order'].append(name)

        # move the last breakline, if needed
        if move_last_breakline and entry['tasks'][name]:
            entry['tasks'][name][-1] = entry['tasks'][name][-1][:-1]

        # add all the tasks in the list to the entry
        if type(tasks) is list:
            if move_last_breakline:
                tasks.append('\n')
            entry['tasks'][name].extend(tasks)

        # or add  only one task to the entry
        elif type(tasks) is str:
            if move_last_breakline:
                tasks += '\n'
            entry['tasks'][name].append(tasks)


    # Commit the changes made on the temporary file on the real file
    def commit_changes(self):
        '''
        Commit the changes made on the temporary file on the real file.
        '''

        # open the files
        temp_handler = open(self.temp_file_name)
        file_handler = open(self.config['logfile'], 'w')

        # read lines from the temporary file and write on the real
        for line in temp_handler:
            file_handler.write(line)

        # close the files
        temp_handler.close()
        file_handler.close()


    # Create the temporary file to be editted
    def _create_temp_file(self):
        '''
        Create the temporary file to be editted.
        '''

        # write all the entries on the file
        file_handler = open(self.temp_file_name, 'w')
        text = self.get_formatted_entry(self.current_entry) + self.content
        file_handler.write(text)
        file_handler.close()


    # Find the real path of the editor program
    def _resolve_editor_path(self, editor):
        '''
        Find the real path of the editor program.
        '''

        # lookup for the program in the directories of the $PYTHONPATH
        for p in os.defpath.split(os.pathsep):
            editor_path = os.path.join(p, editor)
            if os.path.exists(editor_path):
                return os.path.realpath(editor_path)

        return editor


# the main program code
if __name__ == '__main__':

    lb = LogBook()

    # execute the logbook via command line interface
    try:
        lb.run()

    # if there is any error with the project
    except (ProjectExistsError, ProjectDoesNotExistError), ex:
        print 'Error:', str(ex)
        sys.exit(1)

    # if the user didn't change the file
    except UpdateAbortedError, ex:
        print 'Aborting.'
        sys.exit(2)

    # remove the temporary file
    finally:
        lb._remove_temp_file()
