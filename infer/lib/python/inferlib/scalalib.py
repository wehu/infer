# Copyright (c) 2009 - 2013 Monoidics ltd.
# Copyright (c) 2013 - present Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import codecs
import os
import subprocess
import sys
import tempfile
import time
import re

from . import analyze, config, utils

# scalac options
parser = argparse.ArgumentParser()

current_directory = utils.decode(os.getcwd())

parser.add_argument('-version', action='store_true')
parser.add_argument('-deprecation', action='store_true')
parser.add_argument('-cp', '-classpath', type=utils.decode,
                    dest='classpath', default=os.getcwd())
parser.add_argument('-bootclasspath', type=utils.decode)
parser.add_argument('-d', dest='classes_out', default=current_directory)
#parser.add_argument('-processorpath', type=utils.decode, dest='processorpath')
#parser.add_argument('-processor', type=utils.decode, dest='processor')
parser.add_argument('-o', '--out', metavar='<directory>',
                    default=utils.encode(config.DEFAULT_INFER_OUT),
                    dest='infer_out',
                    type=utils.decode,
                    action=utils.AbsolutePathAction,
                    help='Set the Infer results directory')


def _get_scalac_args(args):
    try:
        scalac_pos = args.index('scalac')
    except ValueError:
        return None
    scalac_args = args[scalac_pos + 1:]
    if len(scalac_args) == 0:
        return None
    else:
        # replace any -g:.* flag with -g to preserve debugging symbols
        args = map(lambda arg: '-g:notailcalls' if '-g' in arg else arg, scalac_args)
        args = map(lambda arg: '-classpath' if '-cp' == arg else arg, args)
        # skip -Werror
        args = filter(lambda arg: arg != '-Werror', args)
        # skip javac
        args = filter(lambda arg: arg != 'javac', args)
        return args


def create_infer_command(args, scalac_arguments):
    infer_args = ['-o', args.infer_out]
    if args.debug:
        infer_args.append('--debug')
    infer_args += ['--analyzer', 'capture']

    return AnalyzerWithFrontendWrapper(
        analyze.infer_parser.parse_args(infer_args),
        'scalac',
        _get_scalac_args(['scalac'] + scalac_arguments)
    )


# return True if string is empty or an escaped variant of empty
def _is_empty_classpath(string):
    stripped = string.strip("'").strip('"')
    if stripped == '':
        return True
    elif stripped == string:
        return False
    else:
        return _is_empty_classpath(stripped)


class AnnotationProcessorNotFound(Exception):

    def __init__(self, path):
        self.path = path

    def __str__(self):
        return repr(self.path + ' not found')


class CompilerCall(object):

    def __init__(self, scalac_cmd, arguments):
        assert scalac_cmd is not None and arguments is not None
        self.scalac_cmd = scalac_cmd
        self.original_arguments = arguments
        self.args, self.remaining_args = parser.parse_known_args(arguments)
        self.verbose_out = None

    def run(self):
        if self.args.version:
            return subprocess.call([self.scalac_cmd] + self.original_arguments)
        else:
            scalac_args = ['-verbose', '-g:notailcalls']

            if self.args.bootclasspath is not None:
                scalac_args += ['-bootclasspath', self.args.bootclasspath]

            if not os.path.isfile(config.ANNOT_PROCESSOR_JAR):
                raise AnnotationProcessorNotFound(config.ANNOT_PROCESSOR_JAR)
            if self.args.classes_out is not None:
                scalac_args += ['-d', self.args.classes_out]

            scalac_args.append('-J-Duser.language=en')

            classpath = self.args.classpath
            # the -processorpath option precludes searching the classpath for
            # annotation processors, so we don't want to use it unless the
            # javac command does
            #if self.args.processorpath is not None:
            #    processorpath = os.pathsep.join([config.ANNOT_PROCESSOR_JAR,
            #                                    self.args.processorpath])
                #scalac_args += ['-processorpath', processorpath]
            #else:
            #    classpath = os.pathsep.join([config.ANNOT_PROCESSOR_JAR,
            #                                 classpath])

            at_args = [
                arg for arg in self.remaining_args if arg.startswith('@')]
            found_classpath = False
            for at_arg in at_args:
                # remove @ character
                args_file_name = at_arg[1:]
                with codecs.open(args_file_name, 'r',
                                 encoding=config.CODESET) as args_file:
                    args_file_contents = args_file.read()
                prefix_suffix = args_file_contents.split('-classpath\n', 1)
                if len(prefix_suffix) == 2:
                    prefix, suffix = prefix_suffix
                    with tempfile.NamedTemporaryFile(
                            dir=self.args.infer_out,
                            suffix='_cp',
                            delete=False) as args_file_cp:
                        cp_line, _, after_cp = suffix.partition('\n')
                        # avoid errors the happen when we get -classpath '"',
                        # -classpath '', or similar from the args file
                        if _is_empty_classpath(cp_line):
                            cp_line = '\n'
                        else:
                            cp_line = ':%s\n' % cp_line
                        args_file_cp.write(
                            prefix + '-classpath\n' + classpath + cp_line + after_cp)
                        at_arg_cp = '@' + args_file_cp.name
                        self.remaining_args = [
                            at_arg_cp if arg == at_arg else arg
                            for arg in self.remaining_args]
                        found_classpath = True
                        break

            scalac_args += self.remaining_args

            if not found_classpath:
                # -classpath option not found in any args file
                scalac_args += ['-classpath', classpath]

            # this overrides the default mechanism for discovering annotation
            # processors (checking the manifest of the annotation processor
            # JAR), so we don't want to use it unless the javac command does
            #if self.args.processor is not None:
                #processor = '%s,%s' % (config.ANNOT_PROCESSOR_NAMES,
                #                       self.args.processor)
                #javac_args += ['-processor', processor]

            with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.out',
                    prefix='annotations_',
                    delete=False) as annot_out:
                # Initialize the contents of the file to a valid empty
                # json object.
                annot_out.write('{}')
                self.suppress_warnings_out = annot_out.name
            #scalac_args += ['-A%s=%s' %
            #              (config.SUPRESS_WARNINGS_OUTPUT_FILENAME_OPTION,
            #               self.suppress_warnings_out)]

            def arg_must_go_on_cli(arg):
                # as mandated by scalac, argument files must not contain
                # arguments
                return arg.startswith('-J') or arg.startswith('@')
            file_args = filter(lambda x: not arg_must_go_on_cli(x), scalac_args)
            cli_args = filter(arg_must_go_on_cli, scalac_args)

            # pass non-special args via a file to avoid blowing up the
            # command line size limit
            with tempfile.NamedTemporaryFile(
                    mode='w',
                    prefix='scalac_args_',
                    delete=False) as command_line:
                escaped_args = map(lambda x: '"%s"' % (x.replace('"', '\\"')),
                                   file_args)
                command_line.write(utils.encode('\n'.join(escaped_args)))
                command_line.write('\n')
                self.command_line_file = command_line.name

            with tempfile.NamedTemporaryFile(
                    mode='w',
                    suffix='.out',
                    prefix='scalac_',
                    delete=False) as file_out:
                self.verbose_out = file_out.name

                command = [self.scalac_cmd] + cli_args + \
                          ['@' + str(self.command_line_file)]
                try:
                    subprocess.check_call(command, stderr=file_out)
                except subprocess.CalledProcessError:
                    error_msg = 'ERROR: failure during compilation command.' \
                                + '\nYou can run the failing compilation ' \
                                + 'command again by copy-pasting the\nlines ' \
                                + 'below in your terminal:\n\n"""\n' \
                                + 'python <<EOF\n' \
                                + 'import subprocess\n' \
                                + 'cmd = {}\n' \
                                + 'subprocess.check_call(cmd)\n' \
                                + 'EOF\n"""\n'
                    failing_cmd = filter(lambda arg: arg != '-verbose',
                                         command)
                    utils.stderr(error_msg.format(failing_cmd))
                    subprocess.check_call(failing_cmd)

        return os.EX_OK


class AnalyzerWithFrontendWrapper(analyze.AnalyzerWrapper):

    def __init__(self, args, scalac_cmd, scalac_args):
        self.scalac = CompilerCall(scalac_cmd, scalac_args)
        self.scala_source_files = []
        for a in scalac_args:
            found = re.match(r'.*\.(java|scala)$', a)
            if found:
                self.scala_source_files.append(a)
        if not self.scalac.args.version:
            if scalac_args is None:
                help_exit('No scalac command detected')

        analyze.AnalyzerWrapper.__init__(self, args)

        if self.args.buck:
            self.args.infer_out = os.path.join(
                self.scalac.args.classes_out,
                config.BUCK_INFER_OUT)
            self.args.infer_out = os.path.abspath(self.args.infer_out)

    def start(self):
        if self.scalac.args.version:
            if self.args.buck:
                key = self.args.analyzer
                utils.stderr(utils.infer_key(key))
            else:
                return self.scalac.run()
        else:
            start_time = time.time()

            self._compile()
            if self.args.analyzer == config.ANALYZER_COMPILE:
                return os.EX_OK

            self._postprocess_verbose_out()

            self._run_infer_frontend()
            self.timing['capture'] = utils.elapsed_time(start_time)
            if self.args.analyzer == config.ANALYZER_CAPTURE:
                return os.EX_OK

            self.analyze_and_report()
            self._close()
            self.timing['total'] = utils.elapsed_time(start_time)
            self.save_stats()

            return self.stats

    def _postprocess_verbose_out(self):
        f = None
        try:
            f = open(self.scalac.verbose_out, 'r')
            tmp = self.scalac.verbose_out + '.2'
            o = None
            try:
                o = open(tmp, 'w')
                classpath_pattern = r'\[search path for class files: ([^ ]+)\]'
                #parsing_pattern   = r'\[parsing ([^ ]+)\]'
                classfile_pattern = r'\[wrote [^ ]+ to ([^ ]+)\]'
                for a in self.scala_source_files:
                    print("[parsing started RegularFileObject[{0}]]".format(a), file=o)
                for line in f:
                    line = line.strip()
                    found = re.match(classpath_pattern, line)
                    if found:
                        #print("[search path for class files: {0}]".format(','.join(found.group(1).split(':'))))
                        print("[search path for class files: {0}]".format(','.join(found.group(1).split(':'))), file=o)
                        continue
                    #found = re.match(parsing_pattern, line)
                    #if found:
                        #print("[parsing started RegularFileObject[{0}]]".format(found.group(1)))
                    #    print("[parsing started RegularFileObject[{0}]]".format(found.group(1)), file=o)
                    #    continue
                    found = re.match(classfile_pattern, line)
                    if found:
                        #print("[wrote RegularFileObject[{0}]]".format(found.group(1)))
                        print("[wrote RegularFileObject[{0}]]".format(found.group(1)), file=o)
                    else:
                        print(line, file=o)
            finally:
                if o: o.close()
            os.rename(tmp, self.scalac.verbose_out)
        finally:
            if f: f.close()
        

    # create a classpath to pass to the frontend
    def _create_frontend_classpath(self):
        classes_out = '.'
        if self.scalac.args.classes_out is not None:
            classes_out = self.scalac.args.classes_out
        classes_out = os.path.abspath(classes_out)
        original_classpath = []
        if self.scalac.args.bootclasspath is not None:
            original_classpath = self.scalac.args.bootclasspath.split(':')
        if self.scalac.args.classpath is not None:
            original_classpath += self.scalac.args.classpath.split(':')
        if len(original_classpath) > 0:
            # add classes_out, unless it's already in the classpath
            classpath = [os.path.abspath(p) for p in original_classpath]
            if classes_out not in classpath:
                classpath = [classes_out] + classpath
                # remove models.jar; it's added by the frontend
                models_jar = os.path.abspath(config.MODELS_JAR)
                if models_jar in classpath:
                    classpath.remove(models_jar)
            return ':'.join(classpath)
        return classes_out

    def _run_infer_frontend(self):
        infer_cmd = [utils.get_cmd_in_bin_dir('InferJava')]
        infer_cmd += ['-classpath', self._create_frontend_classpath()]

        if not self.args.absolute_paths:
            infer_cmd += ['-project_root', self.args.project_root]

        infer_cmd += [
            '-results_dir', self.args.infer_out,
            '-verbose_out', self.scalac.verbose_out,
            '-suppress_warnings_out', self.scalac.suppress_warnings_out,
        ]

        if os.path.isfile(config.MODELS_JAR):
            infer_cmd += ['-models', config.MODELS_JAR]

        infer_cmd.append('-no-static_final')

        if self.args.debug:
            infer_cmd.append('-debug')
        if self.args.analyzer == config.ANALYZER_TRACING:
            infer_cmd.append('-tracing')
        if self.args.android_harness:
            infer_cmd.append('-harness')


        return analyze.run_command(
            infer_cmd,
            self.args.debug,
            self.scalac.original_arguments,
            'frontend',
            self.args.analyzer
        )

    def _compile(self):
        return self.scalac.run()

    def _close(self):
        os.remove(self.scalac.verbose_out)
        os.remove(self.scalac.suppress_warnings_out)
