#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, absolute_import, division, print_function


import os
import re
import sys

import argparse
import time
import subprocess
from subprocess import PIPE
import smtplib
from smtplib import SMTPException
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import shlex

from os.path import expanduser
from time import strftime

import json

from colored import fg, bg, attr

# Global vars
colortheme = None
#Load custom parameters from ~/mygitcheck.py
configfile = expanduser('~/mygitcheck.py')
if os.path.exists(configfile):
    sys.path.append(expanduser('~'))
    import mygitcheck as userconf

    # Try to load colortheme
    if hasattr(userconf, 'colortheme'):
        colortheme = userconf.colortheme
if colortheme is None:
    # Default theme
    defaultcolor = attr('reset') + fg('white')
    colortheme = {
        'default': defaultcolor,
        'prjchanged': attr('reset') + attr('bold') + fg('deep_pink_1a'),
        'prjremote': attr('reverse') + fg('light_cyan'),
        'prjname': attr('reset') + fg('chartreuse_1'),
        'reponame': attr('reset') + fg('light_goldenrod_2b'),
        'branchname': defaultcolor,
        'fileupdated': attr('reset') + fg('light_goldenrod_2b'),
        'remoteto': attr('reset') + fg('deep_sky_blue_3b'),
        'committo': attr('reset') + fg('violet'),
        'commitinfo': attr('reset') + fg('deep_sky_blue_3b'),
        'commitstate': attr('reset') + fg('deep_pink_1a'),
        'bell': "\a",
        'reset': "\033[2J\033[H"
    }


class html:
    msg = "<ul>\n"
    topull = ""
    topush = ""
    strlocal = ""
    prjname = ""
    path = ""
    timestamp = ""


def showDebug(mess, level='info'):
    if opts.debugmod:
        print(mess)


# Search all local repositories from current directory
def searchRepositories(args):
    showDebug('Beginning scan... building list of git folders')
    repo = set()
    for curdir in args:
        if curdir[-1:] == '/':
            curdir = curdir[:-1]
        showDebug("  Scan git repositories from %s" % curdir)

        html.path = curdir
        startinglevel = curdir.count(os.sep)

        for directory, dirnames, filenames in os.walk(curdir):
            level = directory.count(os.sep) - startinglevel
            if opts.depth is 0 or level <= opts.depth:
                if '.git' in dirnames:
                    showDebug("  Add %s repository" % directory)
                    repo.add(directory)

    showDebug('Done')
    return sorted(repo)


# Check state of a git repository
def checkRepository(rep, branch, opts, args):
    aitem = []
    mitem = []
    ditem = []
    gsearch = re.compile(r'^.?([A-Z]) (.*)')
    if re.match(opts.ignoreBranch, branch):
        return False

    changes = getLocalFilesChange(rep, opts)
    ischange = len(changes) > 0
    actionNeeded = False  # actionNeeded is branch push/pull, not local file change.

    topush = ""
    topull = ""
    html.topush = ""
    html.topull = ""
    if branch != "":
        remotes = getRemoteRepositories(rep)
        hasremotes = bool(remotes)
        for r in remotes:
            count = len(getLocalToPush(rep, r, branch))
            ischange = ischange or (count > 0)
            actionNeeded = actionNeeded or (count > 0)
            if count > 0:
                topush += " %s%s%s[%sTo Push:%s%s]" % (
                    colortheme['reponame'],
                    r,
                    colortheme['default'],
                    colortheme['remoteto'],
                    colortheme['default'],
                    count
                )
                html.topush += '<b style="color:black">%s</b>[<b style="color:blue">To Push:</b><b style="color:black">%s</b>]' % (
                    r,
                    count
                )

        for r in remotes:
            count = len(getRemoteToPull(rep, r, branch))
            ischange = ischange or (count > 0)
            actionNeeded = actionNeeded or (count > 0)
            if count > 0:
                topull += " %s%s%s[%sTo Pull:%s%s]" % (
                    colortheme['reponame'],
                    r,
                    colortheme['default'],
                    colortheme['remoteto'],
                    colortheme['default'],
                    count
                )
                html.topull += '<b style="color:black">%s</b>[<b style="color:blue">To Pull:</b><b style="color:black">%s</b>]' % (
                    r,
                    count
                )
    if ischange or not opts.quiet:
        # Remove trailing slash from repository/directory name
        if rep[-1:] == '/':
            rep = rep[:-1]

        if opts.full_path:
            repname = rep
        # Do some magic to not show the absolute path as repository name
        else:
            for target in  args:
                if rep.startswith(target):
                    #Case 1: script was started in a directory that is a git repo
                    if target == rep:
                        repname = os.path.basename(rep)
                    # Case 2: script was started in a directory with possible subdirs that contain git repos
                    else:
                        repname = rep[len(target)+1:]
                    break

        if ischange:
            prjname = "%s%s%s" % (colortheme['prjchanged'], repname, colortheme['default'])
            html.prjname = '<b style="color:red">%s</b>' % (repname)
        elif not hasremotes:
            prjname = "%s%s%s" % (colortheme['prjremote'], repname, colortheme['default'])
            html.prjname = '<b style="color:magenta">%s</b>' % (repname)
        else:
            prjname = "%s%s%s" % (colortheme['prjname'], repname, colortheme['default'])
            html.prjname = '<b style="color:green">%s</b>' % (repname)

        # Print result
        if len(changes) > 0:
            strlocal = "%sLocal%s[" % (colortheme['reponame'], colortheme['default'])
            lenFilesChnaged = len(getLocalFilesChange(rep, opts))
            strlocal += "%sTo Commit:%s%s" % (
                colortheme['remoteto'],
                colortheme['default'],
                lenFilesChnaged
            )
            html.strlocal = '<b style="color:orange"> Local</b><b style="color:black">['
            html.strlocal += "To Commit:%s" % (
                lenFilesChnaged
            )
            strlocal += "]"
            html.strlocal += "]</b>"
        else:
            strlocal = ""
            html.strlocal = ""

        if opts.email:
            html.msg += "<li>%s/%s %s %s %s</li>\n" % (html.prjname, branch, html.strlocal, html.topush, html.topull)

        else:
            cbranch = "%s%s" % (colortheme['branchname'], branch)
            print("%(prjname)s/%(cbranch)s %(strlocal)s%(topush)s%(topull)s" % locals())

        if opts.verbose:
            if ischange > 0:
                filename = "  |--Local"
                if not opts.email:
                    print(filename)
                html.msg += '<ul><li><b>Local</b></li></ul>\n<ul>\n'
                for c in changes:
                    filename = "     |--%s%s%s %s%s" % (
                        colortheme['commitstate'],
                        c[0],
                        colortheme['fileupdated'],
                        c[1],
                        colortheme['default'])
                    html.msg += '<li> <b style="color:orange">[To Commit] </b>%s</li>\n' % c[1]
                    if not opts.email: print(filename)
                html.msg += '</ul>\n'
            if branch != "":
                remotes = getRemoteRepositories(rep)
                for r in remotes:
                    commits = getLocalToPush(rep, r, branch)
                    if len(commits) > 0:
                        rname = "  |--%(r)s" % locals()
                        html.msg += '<ul><li><b>%(r)s</b></li>\n</ul>\n<ul>\n' % locals()
                        if not opts.email: print(rname)
                        for commit in commits:
                            pcommit = "     |--%s[To Push]%s %s%s%s" % (
                                colortheme['committo'],
                                colortheme['default'],
                                colortheme['commitinfo'],
                                commit,
                                colortheme['default'])
                            html.msg += '<li><b style="color:blue">[To Push] </b>%s</li>\n' % commit
                            if not opts.email: print(pcommit)
                        html.msg += '</ul>\n'

            if branch != "":
                remotes = getRemoteRepositories(rep)
                for r in remotes:
                    commits = getRemoteToPull(rep, r, branch)
                    if len(commits) > 0:
                        rname = "  |--%(r)s" % locals()
                        html.msg += '<ul><li><b>%(r)s</b></li>\n</ul>\n<ul>\n' % locals()
                        if not opts.email: print(rname)
                        for commit in commits:
                            pcommit = "     |--%s[To Pull]%s %s%s%s" % (
                                colortheme['committo'],
                                colortheme['default'],
                                colortheme['commitinfo'],
                                commit,
                                colortheme['default'])
                            html.msg += '<li><b style="color:blue">[To Pull] </b>%s</li>\n' % commit
                            if not opts.email: print(pcommit)
                        html.msg += '</ul>\n'

    return actionNeeded


def getLocalFilesChange(rep,opts):
    files = []
    #curdir = os.path.abspath(os.getcwd())
    snbchange = re.compile(r'^(.{2}) (.*)')
    onlyTrackedArg = "" if opts.checkUntracked else "uno"
    result = gitExec(rep, "status -s" + onlyTrackedArg)

    lines = result.split('\n')
    for l in lines:
        if not re.match(opts.ignoreLocal, l):
            m = snbchange.match(l)
            if m:
                files.append([m.group(1), m.group(2)])

    return files


def hasRemoteBranch(rep, remote, branch):
    result = gitExec(rep, 'branch -r')
    return '%s/%s' % (remote, branch) in result


def getLocalToPush(rep, remote, branch):
    if not hasRemoteBranch(rep, remote, branch):
        return []
    result = gitExec(rep, "log %(remote)s/%(branch)s..%(branch)s --oneline"
                     % locals())

    return [x for x in result.split('\n') if x]


def getRemoteToPull(rep, remote, branch):
    if not hasRemoteBranch(rep, remote, branch):
        return []
    result = gitExec(rep, "log %(branch)s..%(remote)s/%(branch)s --oneline"
                     % locals())

    return [x for x in result.split('\n') if x]


def updateRemote(rep):
    gitExec(rep, "remote update")


# Get Default branch for repository
def getDefaultBranch(rep):
    sbranch = re.compile(r'^\* (.*)', flags=re.MULTILINE)
    gitbranch = gitExec(rep, "branch"
                        % locals())

    branch = ""
    m = sbranch.search(gitbranch)
    if m:
        branch = m.group(1)

    return {branch}


# Get all branches for repository
def getAllBranches(rep):
    gitbranch = gitExec(rep, "branch"
                        % locals())

    branch = gitbranch.splitlines()

    return [b[2:] for b in branch]


def getRemoteRepositories(rep):
    result = gitExec(rep, "remote"
                     % locals())

    remotes = [x for x in result.split('\n') if x]
    return remotes


def gitExec(path, cmd):
    commandToExecute = "git -C \"%s\" %s" % (path, cmd)
    cmdargs = shlex.split(commandToExecute)
    showDebug("EXECUTE GIT COMMAND '%s'" % cmdargs)
    p = subprocess.Popen(cmdargs, stdout=PIPE, stderr=PIPE)
    output, errors = p.communicate()
    if p.returncode:
        print('Failed running %s' % commandToExecute)
        raise Exception(errors)
    return output.decode('utf-8')


# Check all git repositories
def gitcheck(args):
    if opts.debugmod:
        showDebug("Global Vars:")
        for k, v in opts.__dict__.items():
            showDebug("\t%s: %s" %(k, v))

    repo = searchRepositories(args)
    actionNeeded = False

    if opts.checkremote:
        for r in repo:
            print ("Updating %s remotes..." % r)
            updateRemote(r)

    if opts.watchInterval > 0:
        print(colortheme['reset'])
        print(strftime("%Y-%m-%d %H:%M:%S"))

    showDebug("Processing repositories... please wait.")
    for r in repo:
        if opts.checkall:
            branch = getAllBranches(r)
        else:
            branch = getDefaultBranch(r)
        for b in branch:
            if checkRepository(r, b, opts, args):
                actionNeeded = True
    html.timestamp = strftime("%Y-%m-%d %H:%M:%S")
    html.msg += "</ul>\n<p>Report created on %s</p>\n" % html.timestamp

    if actionNeeded and opts.bellOnActionNeeded:
        print(colortheme['bell'])


def sendReport(content):
    userPath = expanduser('~')
    #filepath = r'%s\Documents\.gitcheck' % userPath
    #filename = filepath + "//mail.properties"
    filepath = os.path.join(userPath, 'Documents', '.gitcheck')
    filename = os.path.join(filepath, 'mail.properties')
    try:
        fh = open(filename)
    except OSError as msg:
            print(msg, file=sys.stderr)
            sys.exit(1)
    try:
        config = json.load(fh)
    except json.decoder.JSONDecodeError as msg:
        print("Unable to load", filename, 'invalid format')
        print(msg, file=sys.stderr)
        sys.exit(1)

    # Create message container - the correct MIME type is multipart/alternative.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Gitcheck Report (%s)" % (html.path)
    msg['From'] = config['from']
    msg['To'] = config['to']

    # Create the body of the message (a plain-text and an HTML version).
    text = "Gitcheck report for %s created on %s\n\n This file can be seen in html only." % (html.path, html.timestamp)
    htmlcontent = "<html>\n<head>\n<h1>Gitcheck Report</h1>\n<h2>%s</h2>\n</head>\n<body>\n<p>%s</p>\n</body>\n</html>" % (
        html.path, content
    )
    # Write html file to disk
    f = open(os.path.join(filepath, 'result.html'), 'w')
    f.write(htmlcontent)
    print ("File saved under %s\\result.html" % filepath)
    # Record the MIME types of both parts - text/plain and text/html.
    part1 = MIMEText(text, 'plain')
    part2 = MIMEText(htmlcontent, 'html')

    # Attach parts into message container.
    # According to RFC 2046, the last part of a multipart message, in this case
    # the HTML message, is best and preferred.
    msg.attach(part1)
    msg.attach(part2)
    try:
        print ("Sending email to %s" % config['to'])
        # Send the message via local SMTP server.
        s = smtplib.SMTP(config['smtp'], config['smtp_port'])
        # sendmail function takes 3 arguments: sender's address, recipient's address
        # and message to send - here it is sent as one string.
        s.sendmail(config['from'], config['to'], msg.as_string())
        s.quit()
    except SMTPException as e:
        print("Error sending email : %s" % str(e))

def bkupMailConfig(src, suffix='old'):
    try:
        os.rename(src, "%s.%s" %(src, suffix))
    except OSError as msg:
        print("Error: could not bkup email properti>es file", file=sys.stderr)
        print(msg, file=sys.stderr)
        sys.exit(1)

def initEmailConfig():

    config = {
        'smtp': 'yourserver',
        'smtp_port': 25,
        'from': 'from@server.com',
        'to': 'to@server.com'
    }
    userPath = expanduser('~')
    saveFilePath = r'%s\Documents\.gitcheck' % userPath
    saveFilePath = os.path.join(userPath, 'Documents', '.gitcheck')
    if not os.path.exists(saveFilePath):
        try: 
            os.makedirs(saveFilePath)
        except OSError as msg:
            print("Error: Unable to create", saveFilePath, file=sys.stderr)
            print(msg, file=sys.stderr)
            exit(1)
    filename = os.path.join(saveFilePath, 'mail.properties')
    if os.path.isfile(filename): bkupMailConfig(filename)
    try: 
        fh=open(filename, 'w')
    except OSError as msg:
        print("Error: Unable to create", filename, file=sys.stderr)
        print(msg, file=sys.stderr)
        sys.exit(1)

    json.dump(config, fh, indent=4)
    print('Please, modify config file located here : %s' % filename)


def readDefaultConfig():
    filename = expanduser('~/.gitcheck')
    if os.path.exists(filename):
        pass

def main(args):
    while True:
        try:
            gitcheck(args)

            if opts.email:
                sendReport(html.msg)

        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            print ("Unexpected error:", str(e))

        if opts.watchInterval > 0:
            time.sleep(opts.watchInterval)
        else:
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check multiple git repository in one pass.',
                                     epilog='example: gitcheck -m 1 -q target'
                                     )
    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        default=False,
                        help='Show files & commits')
    parser.add_argument('--debug',
                        dest='debugmod',
                        action='store_true',
                        default=False,
                        help='Show debug message')
    parser.add_argument('-r', '--remote',
                        dest='checkremote',
                        action='store_true',
                        default=False,
                        help='Force remote update (slow)')
    parser.add_argument('-u', '--untracked',
                        dest='checkUntracked',
                        action='store_true',
                        default=False,
                        help='Show untracked files')
    parser.add_argument('-b', '--bell',
                        dest='bellOnActionNeeded',
                        action='store_true',
                        default=False,
                        help='Bell on action needed')
    parser.add_argument('-w', '--watch',
                        dest='watchInterval',
                        metavar='<sec>',
                        action='store',
                        type=float,
                        default=0,
                        help='After displaying, wait <sec> and run again')
    parser.add_argument('-i', '--ignore-branch',
                        dest='ignoreBranch',
                        metavar='<re>',
                        action='store',
                        default=r'^$',
                        help='Ignore branches matching the regex <re>')
    parser.add_argument('-m', '--maxdepth',
                        dest='depth',
                        metavar='<depth>',
                        action='store',
                        type=int,
                        default=0,
                        help='Limit to <depth> the repositories search')
    parser.add_argument('-q', '--quiet',
                        action='store_true',
                        default=False,
                        help='Display info only when repository needs action')
    parser.add_argument('-e', '--email',
                        action='store_true',
                        default=False,
                        help='Send an email with result as html, using mail.properties parameters')
    parser.add_argument('-a', '--all',
                        dest='checkall',
                        action='store_true',
                        default=False,
                        help='Show the status of all branches')
    parser.add_argument('-l', '--localignore',
                        dest='ignoreLocal',
                        metavar='<re>',
                        action='store',
                        default=r'^$',
                        help='ignore changes in local files which match the regex <re>')
    parser.add_argument('--init-email',
                        action='store_true',
                        default=False,
                        help='Initialize mail.properties file (has to be modified by user using JSON Format)')
    parser.add_argument('-f', '--full-path',
                        action='store_true',
                        default=False,
                        help='Show repository full path')
    parser.add_argument('--no-color',
                        action='store_true',
                        default=False,
                        help='Disable colored output')
    parser.add_argument('args',
                        nargs='*',
                        help='tree or directory to check')

    opts = parser.parse_args(sys.argv[1:])
    args = [os.path.abspath(e) for e in opts.args]
    if opts.no_color:
        for k in colortheme:
            colortheme[k]=''
    if opts.init_email:
        initEmailConfig()
    try:
        main(args)
    except KeyboardInterrupt:
        sys.exit(0)
