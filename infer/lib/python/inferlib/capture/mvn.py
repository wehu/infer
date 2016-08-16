# Copyright (c) 2015 - present Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import os
import logging
import re
import util

from inferlib import jwlib
from inferlib import scalalib

MODULE_NAME = __name__
MODULE_DESCRIPTION = '''Run analysis of code built with a command like:
mvn [options] [task]

Analysis examples:
infer -- mvn build'''
LANG = ['java']


def gen_instance(*args):
    return MavenCapture(*args)

# This creates an empty argparser for the module, which provides only
# description/usage information and no arguments.
create_argparser = util.base_argparser(MODULE_DESCRIPTION, MODULE_NAME)


class MavenCapture:
    def __init__(self, args, cmd):
        self.args = args
        logging.info(util.run_cmd_ignore_fail(['mvn', '-version']))
        # TODO: make the extraction of targets smarter
        self.build_cmd = ['mvn', '-X'] + cmd[1:]

    def get_infer_commands(self, verbose_output):
        calls = []
        calls += self._get_scala_infer_commands(verbose_output)
        if len(calls) == 0:
            calls += self._get_java_infer_commands(verbose_output)
        return calls

    def _get_java_infer_commands(self, verbose_output):
        file_pattern = r'\[DEBUG\] Stale source detected: ([^ ]*\.java)'
        options_pattern = '[DEBUG] Command line options:'
        source_roots_pattern = '[DEBUG] Source roots:'

        files_to_compile = []
        calls = []
        options_next = False
        source_roots_next = False
        for line in verbose_output:
            if options_next:
                #  line has format [Debug] <space separated options>
                javac_args = line.split(' ')[1:] + files_to_compile
                capture = jwlib.create_infer_command(self.args, javac_args)
                calls.append(capture)
                options_next = False
                files_to_compile = []

            elif source_roots_next:
                # line has format [Debug] <space separated directories>
                src_roots = line.split(' ')[1:]
                for src_root in src_roots:
                    for root, dirs, files in os.walk(src_root):
                        for name in files:
                            found = re.match(r'\.java$',name)
                            if found:
                                files_to_compile.append(os.path.join(root, name))
                source_roots_next = False

            elif options_pattern in line:
                #  Next line will have javac options to run
                options_next = True

            elif source_roots_pattern in line:
                # Next line will have directory containing files to compile
                source_roots_next = True

            else:
                found = re.match(file_pattern, line)
                if found:
                    files_to_compile.append(found.group(1))

        return calls

    def _get_scala_infer_commands(self, verbose_output):
        compiler_pattern   = r'[DEBUG]    scala compiler = ([^ ]*)'
        library_pattern    = r'[DEBUG]    scala library = ([^ ]*)'
        extra_pattern      = '[DEBUG]    scala extra = {'
        classpath_pattern  = '[DEBUG]    classpath = {'
        sources_pattern    = '[DEBUG]    sources = {'
        output_dir_pattern = r'\[DEBUG\]    output directory = ([^ ]*)'
        options_pattern    = '[DEBUG]    scalac options = {'
        end_pattern        = '[DEBUG]    }'
        calls = []

        section    = "none"
        output_dir = "."
        classpath  = []
        sources    = []
        options    = []
        for line in verbose_output:
            if classpath_pattern in line:
                section = "classpath"
                continue
            elif sources_pattern in line:
                section = "sources"
                continue
            elif options_pattern in line:
                section = "options"
                continue
            elif extra_pattern in line:
                section = "classpath"
            elif end_pattern in line:
                if section == "options":
                    scalac_args = []
                    if len(classpath) > 0:
                        scalac_args.append("-classpath")
                        scalac_args.append(':'.join(classpath))
                    scalac_args += sources
                    scalac_args += options
                    scalac_args.append("-d")
                    scalac_args.append(output_dir)
                    capture = scalalib.create_infer_command(self.args, scalac_args)
                    calls.append(capture)
                    classpath  = []
                    sources    = []
                    output_dir = "."
                    options    = []
                section = "none"
                continue
            else:
                found = re.match(output_dir_pattern, line)
                if found:
                    output_dir = found.group(1)
                    continue
                found = re.match(compiler_pattern, line)
                if found:
                    classpath.append(found.group(1))
                    continue
                found = re.match(library_pattern, line)
                if found:
                    classpath.append(found.group(1))
                    continue

            if section == "classpath":
               classpath.append(re.split('\\s+', line)[1])
            elif section == "sources":
               sources.append(re.split('\\s+', line)[1])
            elif section == "options":
               options.append(re.split('\\s+', line)[1])
        return calls

    def capture(self):
        cmds = self.get_infer_commands(util.get_build_output(self.build_cmd))
        clean_cmd = '%s clean' % self.build_cmd[0]
        return util.run_compilation_commands(cmds, clean_cmd)
