"""
A Mixin for Gradle build log analysis.
"""

import re

from ..log_file_analyzer import LogFileAnalyzer


class JavaGradleAnalyzer(LogFileAnalyzer):
    def __init__(self, primary_language, folds, job_id):
        super().__init__(primary_language, folds, job_id)
        self.reactor_lines = []
        self.tests_failed_lines = []
        self.analyzer = 'java-gradle'
        self.build_system = 'Gradle'
        # Assume tests did not fail unless we detect that they did.
        self.did_tests_fail = False

    def custom_analyze(self):
        self.extract_tests()
        self.analyze_tests()

    def extract_tests(self):
        test_section_started = False
        line_marker = 0

        for line in self.folds[self.OUT_OF_FOLD]["content"]:
            # We cannot tell when the test started, so we assume test started when we have the first task.
            if re.search(r'^:.+', line, re.M):
                line_marker = 1
                test_section_started = True
                self.tests_run = True
                self.add_framework('JUnit')
            elif re.search(r'^:', line, re.M) and line_marker == 1:
                line_marker = 0
                test_section_started = False
            elif re.search(r'^> Task', line, re.M):
                # New version of Gradle use > Task :name instead of :name
                line_marker = 1
                test_section_started = True
            elif re.search(r'^BUILD (SUCCESSFUL|FAILED) in ', line, re.M) and line_marker == 1:
                self.test_lines.append(line)  # We still need this line
                line_marker = 0
                test_section_started = False

            if test_section_started:
                self.test_lines.append(line)

    def match_failed_test(self, line):
        # Matches the likes of co.paralleluniverse.fibers.FiberTest > testSerializationWithThreadLocals[0] FAILED
        # and DownloadExtensionTest > downloadSingleFileError() FAILED
        # Appends 'co.paralle.universe.fibers.FiberTest.testSerializationWithThreadLocals[0]' to self.tests_failed
        match = re.search(r'([^\s]+) > ([^\s\.\[\(]+(\[.+\]|\(\))?) FAILED$', line, re.M)
        if match:
            self.tests_run = True
            self.init_tests()
            self.tests_failed.append(match.group(1) + '.' + match.group(2))
            self.did_tests_fail = True
            return

        # Matches the likes of
        # ProtocolCompatibilityTest > serviceTalkToServiceTalkClientTimeout(boolean, boolean, String) > io.servicetalk.g
        # rpc.netty.ProtocolCompatibilityTest.serviceTalkToServiceTalkClientTimeout(boolean, boolean, String)[10] FAILED
        #
        # Appends io.servicetalk.grpc.netty.ProtocolCompatibilityTest.serviceTalkToServiceTalkClientTimeout
        # (boolean, boolean, String)[10] to self.tests_failed
        match = re.search(r'([^\s]+(\(.*\))? > )+([^\s\[\(]+(\(.*\))?(\[.+\]|\(\))?) FAILED', line, re.M)
        if match:
            self.tests_run = True
            self.init_tests()
            self.tests_failed.append(match.group(3))
            self.did_tests_fail = True
            return

        # Matches the likes of TestNG > Regression2 > test.groupinvocation.GroupSuiteTest.Regression2 FAILED
        # Appends 'test.groupinvocation.GroupSuiteTest.Regression2' to self.tests_failed
        match = re.search(r'(.* >)+ ([^\s\[\(]+\.[^\[\(]+(\[.+\])?) FAILED$', line, re.M)
        if match:
            self.tests_run = True
            self.init_tests()
            self.tests_failed.append(match.group(2))
            self.did_tests_fail = True
            return

    def analyze_tests(self):
        for line in self.test_lines:
            self.match_failed_test(line)

            match = re.search(r'(\d*) tests completed(, (\d*) failed)?(, (\d*) skipped)?', line, re.M)
            if match:
                self.tests_run = True
                self.init_tests()
                self.add_framework('JUnit')
                self.num_tests_run += int(match.group(1))
                self.num_tests_failed += 0 if match.group(3) is None else int(match.group(3))
                self.num_tests_skipped += 0 if match.group(5) is None else int(match.group(5))
                continue
            # Added a space after Total tests run:, this differs from
            # TravisTorrent's original implementation. The observed output
            # of testng has a space. Consider updating the regex if we observe
            # a testng version that outputs whitespace differently.
            match = re.search(r'^Total tests run: (\d+), Failures: (\d+), Skips: (\d+)', line, re.M)
            if match:
                self.tests_run = True
                self.init_tests()
                self.add_framework('testng')
                self.num_tests_run += int(match.group(1))
                self.num_tests_failed += int(match.group(2))
                self.num_tests_skipped += int(match.group(3))
                continue

            # Same with Maven and Ant. Only use the last build to calculate pure_build_duration
            match = re.search(r'Total time: (.*)', line, re.M)
            if match:
                self.pure_build_duration = JavaGradleAnalyzer.convert_gradle_time_to_seconds(match.group(1))

            match = re.search(r'BUILD (FAILED|SUCCESSFUL) in (.*)', line, re.M)
            if match:
                self.pure_build_duration = JavaGradleAnalyzer.convert_gradle_time_to_seconds(match.group(2))

        self.uninit_ok_tests()

    @staticmethod
    def convert_gradle_time_to_seconds(string):
        match = re.search(r'((\d+) mins)? (\d+)(\.\d+) secs', string, re.M)
        if match:
            # If we have minute, we add 60 * minutes to the seconds, final unit is seconds
            return int(match.group(3)) if match.group(2) is None else int(match.group(2)) * 60 + int(match.group(3))

        match = re.search(r'((\d+)m )?(\d+)s', string, re.M)
        if match:
            # If we have minute, we add 60 * minutes to the seconds, final unit is seconds
            return int(match.group(3)) if match.group(2) is None else int(match.group(2)) * 60 + int(match.group(3))

        return 0

    def bool_tests_failed(self):
        if hasattr(self, "tests_failed") and self.tests_failed:
            return True
        if hasattr(self, "num_tests_failed") and self.num_tests_failed > 0:
            return True
        return False
